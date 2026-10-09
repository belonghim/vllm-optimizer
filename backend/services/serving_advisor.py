"""
Serving-argument advisor: which vLLM feature flags a model needs, derived from its config and chat template.

Pure functions — no I/O. Input is a ``ModelAnalysis`` (config.json + auxiliary files) and the target's
current argument list; output is a list of recommendations with the evidence behind each one, so an operator
does not have to boot-test every model to discover a missing tool-call or reasoning parser.

Each recommendation has a ``kind``:
  required — without it the feature is off or responses are wrong (tool calls come back as text, reasoning
             leaks into ``content``, chat completions fail, ...)
  workload — the model supports it; whether to enable it depends on the workload (SLA, modality, concurrency)
  avoid    — present in the current args and known to conflict with auto-detected config
"""

import json
from dataclasses import dataclass
from typing import Any

from services.cr_adapter import extract_arg_value
from services.model_analysis import ModelAnalysis

DEFAULT_MTP_SPECULATIVE_TOKENS = 3
_QWEN_TOOL_PARSER = "qwen3_coder"


@dataclass
class Recommendation:
    flag: str
    kind: str
    status: str  # present | missing | mismatch
    reason: str
    value: str | None = None
    current: str | None = None
    # Full token(s) to append to the argument list, shell-quoted; None when no value can be derived.
    arg: str | None = None
    evidence: str = ""


def _has_flag(args: list[str], flag: str) -> bool:
    return any(a == flag or a.startswith(flag + "=") for a in args)


def _status(args: list[str], flag: str, value: str | None) -> tuple[str, str | None]:
    if not _has_flag(args, flag):
        return "missing", None
    current = extract_arg_value(args, flag)
    if value is not None and current is not None and current != value:
        return "mismatch", current
    return "present", current


def _rec(
    args: list[str],
    flag: str,
    kind: str,
    reason: str,
    *,
    value: str | None = None,
    evidence: str = "",
    json_value: bool = False,
    needs_choice: bool = False,
) -> Recommendation:
    """``needs_choice``: the flag takes a value the advisor cannot derive, so no ready-made ``arg`` is offered."""
    status, current = _status(args, flag, value)
    if needs_choice:
        arg = None
    elif value is None:
        arg = flag
    elif json_value:
        arg = f"{flag} '{value}'"
    else:
        arg = f"{flag}={value}"
    return Recommendation(
        flag=flag,
        kind=kind,
        status=status,
        reason=reason,
        value=value,
        current=current,
        arg=arg if status == "missing" else None,
        evidence=evidence,
    )


def _tool_and_reasoning(a: ModelAnalysis, args: list[str]) -> list[Recommendation]:
    sigs = set(a.template_signatures)
    recs: list[Recommendation] = []
    tool_parser: str | None = None
    reasoning_parser: str | None = None
    model_type = (a.model_type or "").lower()
    if "harmony" in sigs:
        tool_parser, reasoning_parser = "openai", "openai_gptoss"
    elif "gemma4_tool" in sigs:
        tool_parser = "gemma4"
        reasoning_parser = "gemma4" if "enable_thinking" in sigs else None
    elif "tool_xml" in sigs:
        tool_parser = _QWEN_TOOL_PARSER
        reasoning_parser = "qwen3" if "think" in sigs else None
    elif "tool_json" in sigs:
        tool_parser = "hermes"
        reasoning_parser = "qwen3" if "think" in sigs and "qwen" in model_type else None

    if tool_parser:
        evidence = f"chat template: {', '.join(sorted(sigs & {'tool_xml', 'tool_json', 'harmony', 'gemma4_tool'}))}"
        recs.append(
            _rec(
                args,
                "--enable-auto-tool-choice",
                "required",
                "템플릿이 tools를 렌더링 — 이 플래그와 --tool-call-parser가 없으면 tool call이 일반 텍스트로 반환됨",
                evidence=evidence,
            )
        )
        recs.append(
            _rec(
                args,
                "--tool-call-parser",
                "required",
                f"템플릿 형식에 맞는 파서: {tool_parser} (대상 이미지의 `vllm serve --help=tool-call-parser` 목록으로 확인)",
                value=tool_parser,
                evidence=evidence,
            )
        )
    if reasoning_parser:
        recs.append(
            _rec(
                args,
                "--reasoning-parser",
                "required",
                "템플릿에 thinking 블록이 있음 — 파서가 없으면 추론 텍스트가 content에 섞임"
                + (" (생략 시 reasoning을 반환하지 않음)" if reasoning_parser == "openai_gptoss" else ""),
                value=reasoning_parser,
                evidence="chat template: " + ", ".join(sorted(sigs & {"think", "enable_thinking", "harmony"})),
            )
        )
        if reasoning_parser == "qwen3" and a.thinking_default == "disabled":
            recs.append(
                _rec(
                    args,
                    "--default-chat-template-kwargs",
                    "required",
                    "템플릿 thinking 기본값이 비활성인데 qwen3 파서는 reasoning 상태로 시작 — content가 비어 보임",
                    value='{"enable_thinking":false}',
                    evidence="chat template: enable_thinking 기본 비활성",
                    json_value=True,
                )
            )
    elif "think" in sigs and not tool_parser:
        recs.append(
            _rec(
                args,
                "--reasoning-parser",
                "required",
                "템플릿에 thinking 블록이 있으나 파서 이름을 자동 판단할 수 없음 — 이미지의 "
                "`vllm serve --help=reasoning-parser` 목록과 제작사 카드로 선택",
                evidence="chat template: think",
                needs_choice=True,
            )
        )
    return recs


def _template_presence(a: ModelAnalysis, args: list[str]) -> list[Recommendation]:
    if not a.artifacts_read or a.chat_template_source or (a.architecture or "").startswith("DeepseekV4"):
        return []
    return [
        _rec(
            args,
            "--chat-template",
            "required",
            "chat_template.jinja와 tokenizer_config의 chat_template 모두 없음 — /v1/chat/completions가 동작하지 않음."
            " 템플릿 파일 경로를 지정",
            evidence="chat template 없음",
            needs_choice=True,
        )
    ]


def _kv_and_prefix(a: ModelAnalysis, args: list[str], gpu_count: int) -> list[Recommendation]:
    recs: list[Recommendation] = []
    harmony = "harmony" in a.template_signatures
    if gpu_count > 0 and not a.openvino and not harmony:
        recs.append(
            _rec(
                args,
                "--kv-cache-dtype",
                "workload",
                "Hopper(H100/H200)에서는 FP8 KV가 표준 — KV 용량이 약 2배, 정확도 영향은 워크로드로 검증",
                value="fp8",
                evidence=f"현재 KV dtype {a.kv_cache_dtype} ({a.kv_dtype_bytes} B)",
            )
        )
    if a.linear_attention_layers:
        recs.append(
            _rec(
                args,
                "--enable-prefix-caching",
                "workload",
                "hybrid(GDN/Mamba) 모델은 prefix caching이 기본 OFF — EPP 프리픽스 라우팅을 쓰려면 명시."
                " 켜면 GDN 상태 슬롯이 요청당 2개가 되어 동시 요청 수가 줄고, MTP와 병용하지 않음",
                evidence=f"linear attention {a.linear_attention_layers}층",
            )
        )
    return recs


def _speculative(a: ModelAnalysis, args: list[str]) -> list[Recommendation]:
    if a.mtp_layers < 1 or a.openvino:
        return []
    value = json.dumps(
        {"method": "mtp", "num_speculative_tokens": DEFAULT_MTP_SPECULATIVE_TOKENS}, separators=(",", ":")
    )
    return [
        _rec(
            args,
            "--speculative-config",
            "workload",
            "체크포인트에 MTP 헤드가 있음 — 저동시성 지연 단축용. MTP 레이어가 KV를 추가로 쓰고 draft 슬롯만큼 스케줄 토큰이 줄어듦",
            value=value,
            evidence=f"MTP 레이어 {a.mtp_layers}",
            json_value=True,
        )
    ]


def _multimodal(a: ModelAnalysis, args: list[str], tp: int | None) -> list[Recommendation]:
    if not a.multimodal:
        return []
    recs = [
        _rec(
            args,
            "--language-model-only",
            "workload",
            "텍스트 전용 서비스라면 비전/오디오 인코더 로드와 멀티모달 프로파일링을 생략해 KV 풀이 늘어남",
            evidence="vision/audio config 있음",
        ),
        _rec(
            args,
            "--limit-mm-per-prompt",
            "workload",
            "멀티모달 서비스라면 요청당 입력 수를 제한해 메모리 피크를 줄임 (기본값은 모달리티별 999)",
            value='{"image":4}',
            evidence="vision/audio config 있음",
            json_value=True,
        ),
    ]
    if tp and tp > 1:
        recs.append(
            _rec(
                args,
                "--mm-encoder-tp-mode",
                "workload",
                "TP > 1에서 비전 인코더를 배치 단위로 나눠 통신을 줄임 (--language-model-only와 함께 쓰지 않음)",
                value="data",
                evidence=f"TP {tp}",
            )
        )
    if (a.model_type or "").lower().startswith("gemma4") or "Gemma4" in (a.architecture or ""):
        recs.append(
            _rec(
                args,
                "--attention-backend",
                "workload",
                "RHAI 3.5.0(vLLM 0.24.0)의 Gemma 4 + H100/H200 이미지 입력은 FlashAttention-4 sliding-window 결함으로"
                " 1,024 토큰 초과 컨텍스트에서 출력이 깨짐 — 이미지 버전이 다르면 해당 없음",
                value="TRITON_ATTN",
                evidence="Gemma 4 멀티모달",
            )
        )
    return recs


def _custom_code(a: ModelAnalysis, args: list[str]) -> list[Recommendation]:
    if not a.auto_map:
        return []
    return [
        _rec(
            args,
            "--trust-remote-code",
            "required",
            "auto_map 커스텀 모델 코드 — 아키텍처가 vLLM 레지스트리/transformers에 없을 때 필요."
            " 레지스트리에 있으면 불필요하니 `ModelRegistry.get_supported_archs()`로 먼저 확인",
            evidence="config.json auto_map",
        )
    ]


def _avoid(a: ModelAnalysis, args: list[str]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    if a.quantization and not a.openvino:
        for flag in ("--quantization", "--dtype"):
            if _has_flag(args, flag):
                recs.append(
                    Recommendation(
                        flag=flag,
                        kind="avoid",
                        status="present",
                        current=extract_arg_value(args, flag),
                        reason="config가 양자화("
                        + a.quantization
                        + ")·dtype을 자동 감지 — config와 다르게 지정하면 기동 오류. 제거 권장",
                        evidence="quantization_config",
                    )
                )
    return recs


def _notes(a: ModelAnalysis, args: list[str], mamba_cap: int | None = None) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []

    def add(level: str, text: str) -> None:
        notes.append({"level": level, "text": text})

    max_len = extract_arg_value(args, "--max-model-len")
    if max_len and max_len.isdigit() and a.context_limit and int(max_len) > a.context_limit:
        add(
            "warning",
            f"--max-model-len={max_len}이 config 유도 상한 {a.context_limit:,}을 넘음 — 기동 오류"
            " (YaRN 확장은 제작사 카드가 --hf-overrides를 제시한 경우만)",
        )
    if a.auto_map_remote:
        add(
            "warning",
            "auto_map이 다른 Hub 리포('org/repo--module.Class')를 가리킴 — 폐쇄망에서는 코드를 받지 못해 로드 실패",
        )
    elif a.auto_map and a.artifacts_read and not a.custom_code_files:
        add("warning", "auto_map이 있으나 모델 디렉터리에 .py 파일이 없음 — 커스텀 코드를 로드할 수 없음")
    if (
        a.linear_attention_layers
        and _has_flag(args, "--enable-prefix-caching")
        and _has_flag(args, "--speculative-config")
    ):
        add(
            "warning",
            "hybrid 모델에서 prefix caching과 MTP를 함께 켜면 정확도가 떨어지고 장기 대화 출력이 깨질 수 있음 — 하나만 선택",
        )
    if a.linear_attention_layers:
        seqs = extract_arg_value(args, "--max-num-seqs")
        if mamba_cap and seqs and seqs.isdigit() and int(seqs) > mamba_cap:
            add(
                "warning",
                f"--max-num-seqs={seqs}가 vLLM이 할당한 Mamba 캐시 블록 수 {mamba_cap}를 넘음 — full CUDA graph에서"
                f" 'exceeds available Mamba cache blocks'로 기동 실패. {mamba_cap} 이하로 낮추거나"
                " gpu-memory-utilization을 올림",
            )
        else:
            cap_text = f" (현재 할당 블록 {mamba_cap}개)" if mamba_cap else ""
            add(
                "info",
                "hybrid 모델은 디코드 시퀀스마다 Mamba 블록 1개가 필요 — --max-num-seqs가 할당된 블록 수보다 크면"
                f" full CUDA graph 기동 시 'exceeds available Mamba cache blocks'로 실패{cap_text}",
            )
    if a.sliding_attention_layers and a.sliding_window:
        add(
            "info",
            f"sliding window({a.sliding_window}) 레이어는 window-1+max_num_batched_tokens 토큰을 요청마다 예약 —"
            " --max-num-batched-tokens가 동시성에 영향",
        )
    if a.generation_defaults:
        add(
            "info",
            "서버 기본 샘플링은 generation_config.json을 따름: "
            + json.dumps(a.generation_defaults, ensure_ascii=False),
        )
    if not a.artifacts_read:
        add("info", "generation_config/tokenizer_config/chat template을 읽지 못해 기능 인자 추천이 제한됨")
    return notes


def recommend_serving_args(
    analysis: ModelAnalysis,
    args: list[str],
    gpu_count: int = 0,
    tensor_parallel_size: int | None = None,
    mamba_cap: int | None = None,
) -> dict[str, Any]:
    """Recommendations + notes for a target. ``args`` is the full current argument list (static + tuning keys)."""
    recs: list[Recommendation] = [
        *_custom_code(analysis, args),
        *_template_presence(analysis, args),
        *(_tool_and_reasoning(analysis, args) if analysis.artifacts_read else []),
        *_kv_and_prefix(analysis, args, gpu_count),
        *_speculative(analysis, args),
        *_multimodal(analysis, args, tensor_parallel_size),
        *_avoid(analysis, args),
    ]
    missing_required = [r.arg for r in recs if r.kind == "required" and r.status == "missing" and r.arg]
    return {
        "recommendations": [r.__dict__ for r in recs],
        "notes": _notes(analysis, args, mamba_cap),
        "add_args": " ".join(missing_required),
    }
