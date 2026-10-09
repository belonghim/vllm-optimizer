"""Deterministic diagnosis of vLLM boot failures from container logs and pod status.

Pure functions (no I/O). Every rule keys on a verbatim vLLM/transformers error phrase and turns it into a
cause, a concrete fix and, where the log carries a number, the suggested value. ``fix_args`` lists the
serving arguments to change so the UI/analyst can show them without guessing.
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Diagnosis:
    code: str
    title: str
    cause: str
    fix: str
    evidence: str
    fix_args: list[str] = field(default_factory=list)
    suggested_value: int | None = None


def _line_with(logs: str, needle: str) -> str:
    for line in logs.splitlines():
        if needle in line:
            return line.strip()[:300]
    return needle


def _int(match: re.Match[str] | None, group: int = 1) -> int | None:
    return int(match.group(group).replace(",", "")) if match else None


def _mamba(logs: str) -> Diagnosis | None:
    m = re.search(r"max_num_seqs \((\d+)\) exceeds available Mamba cache blocks \((\d+)\)", logs)
    if not m and "exceeds available Mamba cache blocks" not in logs:
        return None
    blocks = _int(m, 2) or _int(re.search(r"at most (\d+)", logs))
    return Diagnosis(
        code="mamba_blocks_exceeded",
        title="--max-num-seqs가 Mamba 캐시 블록 수보다 큼",
        cause="hybrid(GDN/Mamba) 모델은 디코드 시퀀스마다 Mamba 캐시 블록 1개가 필요한데, full CUDA graph 캡처 시점에"
        " 할당된 블록이 max_num_seqs보다 적음",
        fix=(f"--max-num-seqs를 {blocks} 이하로 낮추거나 " if blocks else "--max-num-seqs를 낮추거나 ")
        + "--gpu-memory-utilization을 올림 (prefix caching을 켰다면 시퀀스당 슬롯이 2개라 더 빨리 부족)",
        evidence=_line_with(logs, "Mamba cache blocks"),
        fix_args=["--max-num-seqs", "--gpu-memory-utilization"],
        suggested_value=blocks,
    )


def _kv_too_small(logs: str) -> Diagnosis | None:
    if not re.search(
        r"larger than the maximum number of tokens that can be stored in KV cache|"
        r"larger than the available KV cache memory",
        logs,
    ):
        return None
    est = _int(re.search(r"estimated maximum model length is ([\d,]+)", logs))
    return Diagnosis(
        code="kv_cache_too_small",
        title="KV 캐시가 max_model_len 한 시퀀스도 담지 못함",
        cause="가중치와 오버헤드를 뺀 KV 풀이 --max-model-len 길이의 요청 1건보다 작음",
        fix=(f"--max-model-len을 {est:,} 이하로 낮추거나 " if est else "--max-model-len을 낮추거나 ")
        + "--gpu-memory-utilization 상향, --kv-cache-dtype fp8, TP 증가로 KV 풀을 키움",
        evidence=_line_with(logs, "larger than the available KV cache memory"),
        fix_args=["--max-model-len", "--gpu-memory-utilization", "--kv-cache-dtype"],
        suggested_value=est,
    )


def _no_cache_memory(logs: str) -> Diagnosis | None:
    if "No available memory for the cache blocks" not in logs:
        return None
    return Diagnosis(
        code="no_kv_memory",
        title="KV 캐시에 쓸 메모리가 없음",
        cause="gpu-memory-utilization 예산에서 가중치·활성화·오버헤드를 빼면 남는 메모리가 0 이하",
        fix="--gpu-memory-utilization을 올리거나 --max-num-batched-tokens/--max-num-seqs를 낮춰 프로파일링 피크를 줄임",
        evidence=_line_with(logs, "No available memory"),
        fix_args=["--gpu-memory-utilization", "--max-num-batched-tokens", "--max-num-seqs"],
    )


def _startup_free_memory(logs: str) -> Diagnosis | None:
    if not re.search(r"Free memory on device .* is less than desired GPU memory utilization", logs):
        return None
    return Diagnosis(
        code="gpu_memory_busy",
        title="기동 시점 GPU 여유 메모리가 요청 utilization보다 적음",
        cause="이전 프로세스(재시작 중인 파드, 다른 워크로드)가 GPU 메모리를 아직 점유 중이거나 utilization이 과도함",
        fix="이전 파드 종료를 기다린 뒤 재시도하거나 --gpu-memory-utilization을 낮춤. 같은 GPU를 쓰는 다른 파드가 없는지 확인",
        evidence=_line_with(logs, "Free memory on device"),
        fix_args=["--gpu-memory-utilization"],
    )


def _cuda_oom(logs: str) -> Diagnosis | None:
    if not re.search(r"CUDA out of memory|torch\.OutOfMemoryError|torch\.cuda\.OutOfMemoryError", logs):
        return None
    return Diagnosis(
        code="cuda_oom",
        title="CUDA 메모리 부족 (OOM)",
        cause="가중치 + 활성화 + CUDA graph 캡처 + 프레임워크 오버헤드가 GPU 메모리를 초과",
        fix="--gpu-memory-utilization·--max-num-batched-tokens·--max-num-seqs를 낮추거나 TP를 늘림. 멀티모달이면"
        " --language-model-only / --limit-mm-per-prompt로 인코더 피크를 줄임",
        evidence=_line_with(logs, "out of memory") if "out of memory" in logs else _line_with(logs, "OutOfMemoryError"),
        fix_args=["--gpu-memory-utilization", "--max-num-batched-tokens", "--max-num-seqs"],
    )


def _max_len_over_derived(logs: str) -> Diagnosis | None:
    m = re.search(r"max_model_len \(([\d,]+)\) is greater than the derived max_model_len", logs)
    if not m:
        return None
    derived = _int(re.search(r"derived max_model_len \([^)]*=\s*([\d,]+)", logs))
    return Diagnosis(
        code="max_model_len_exceeds_model",
        title="--max-model-len이 모델이 지원하는 길이보다 큼",
        cause="config.json 유도 최대 길이를 넘는 값을 지정함",
        fix=(f"--max-model-len을 {derived:,} 이하로 설정. " if derived else "--max-model-len을 모델 상한 이하로 설정. ")
        + "YaRN 확장은 제작사 카드가 --hf-overrides를 제시한 경우만",
        evidence=_line_with(logs, "derived max_model_len"),
        fix_args=["--max-model-len"],
        suggested_value=derived,
    )


def _batched_tokens_small(logs: str) -> Diagnosis | None:
    m = re.search(r"max_num_batched_tokens \((\d+)\) is smaller than max_model_len \((\d+)\)", logs)
    if not m:
        return None
    return Diagnosis(
        code="batched_tokens_below_model_len",
        title="--max-num-batched-tokens가 --max-model-len보다 작음",
        cause="chunked prefill이 꺼진 상태에서는 한 프롬프트가 한 배치에 들어가야 함",
        fix=f"--max-num-batched-tokens를 {m.group(2)} 이상으로 올리거나 chunked prefill을 켬",
        evidence=_line_with(logs, "max_num_batched_tokens"),
        fix_args=["--max-num-batched-tokens"],
        suggested_value=int(m.group(2)),
    )


def _quantization_mismatch(logs: str) -> Diagnosis | None:
    if "Quantization method specified in the model config" not in logs:
        return None
    return Diagnosis(
        code="quantization_mismatch",
        title="--quantization이 모델 config와 다름",
        cause="config.json의 quantization_config와 CLI 인자가 충돌",
        fix="--quantization(과 --dtype) 인자를 제거하고 config 자동 감지에 맡김",
        evidence=_line_with(logs, "Quantization method"),
        fix_args=["--quantization", "--dtype"],
    )


def _quantization_unsupported(logs: str) -> Diagnosis | None:
    m = re.search(r"Cannot find the config file for (\S+)", logs)
    if not m:
        return None
    return Diagnosis(
        code="quantization_not_applicable",
        title=f"--quantization={m.group(1)}를 적용할 수 없음",
        cause="모델이 해당 방식으로 양자화되어 있지 않거나(config.json에 quantization_config 없음) 이 이미지가 지원하지 않음",
        fix="--quantization 인자를 제거(양자화 모델이면 config 자동 감지). 원본 가중치를 양자화하려면 해당 방식으로 변환된 모델을 사용",
        evidence=_line_with(logs, "Cannot find the config file"),
        fix_args=["--quantization"],
    )


def _trust_remote_code(logs: str) -> Diagnosis | None:
    if "trust_remote_code=True" not in logs and "trust-remote-code" not in logs:
        return None
    if not re.search(
        r"custom code which must be executed|requires you to execute|Failed to load the model config", logs
    ):
        return None
    return Diagnosis(
        code="trust_remote_code_required",
        title="커스텀 모델 코드 실행 허용 필요",
        cause="config.json의 auto_map이 모델 디렉터리의 파이썬 코드를 요구하는데 --trust-remote-code가 없음",
        fix="--trust-remote-code 추가 (레지스트리에 이미 있는 아키텍처면 불필요)",
        evidence=_line_with(logs, "trust_remote_code"),
        fix_args=["--trust-remote-code"],
    )


def _unsupported_arch(logs: str) -> Diagnosis | None:
    m = re.search(r"Model architectures \[(.*?)\] (?:are|is) not supported", logs)
    if not m:
        return None
    return Diagnosis(
        code="unsupported_architecture",
        title="이 vLLM 버전이 지원하지 않는 아키텍처",
        cause=f"아키텍처 {m.group(1)}가 현재 이미지의 모델 레지스트리에 없음",
        fix="아키텍처를 지원하는 vLLM 이미지로 올리거나, auto_map 코드가 있으면 --trust-remote-code 사용",
        evidence=_line_with(logs, "not supported"),
        fix_args=["--trust-remote-code"],
    )


def _chat_template(logs: str) -> Diagnosis | None:
    if "default chat template is no longer allowed" not in logs:
        return None
    return Diagnosis(
        code="chat_template_missing",
        title="chat template 없음",
        cause="tokenizer_config.json/chat_template.jinja에 템플릿이 없어 /v1/chat/completions를 처리할 수 없음",
        fix="--chat-template에 템플릿 파일 경로를 지정",
        evidence=_line_with(logs, "chat template"),
        fix_args=["--chat-template"],
    )


def _tool_parser(logs: str) -> Diagnosis | None:
    if (
        "tool choice requires --enable-auto-tool-choice" in logs
        or "--enable-auto-tool-choice and --tool-call-parser" in logs
        or "--enable-auto-tool-choice requires --tool-call-parser" in logs
    ):
        return Diagnosis(
            code="tool_choice_flags_missing",
            title="auto tool choice 플래그 불완전",
            cause="--enable-auto-tool-choice와 --tool-call-parser는 한 쌍으로 지정해야 함",
            fix="둘을 함께 지정 (파서 이름은 모델 템플릿 형식에 맞춤)",
            evidence=_line_with(logs, "tool"),
            fix_args=["--enable-auto-tool-choice", "--tool-call-parser"],
        )
    m = re.search(r"invalid tool call parser: (\S+)", logs)
    if m:
        return Diagnosis(
            code="tool_parser_unknown",
            title=f"알 수 없는 tool call parser '{m.group(1)}'",
            cause="이 vLLM 버전에 해당 이름의 파서가 없음",
            fix="`vllm serve --help=tool-call-parser`로 사용 가능한 이름을 확인해 교체",
            evidence=_line_with(logs, "invalid tool call parser"),
            fix_args=["--tool-call-parser"],
        )
    return None


def _tp_divisibility(logs: str) -> Diagnosis | None:
    m = re.search(
        r"Total number of attention heads \((\d+)\) must be divisible by tensor parallel size \((\d+)\)", logs
    )
    if not m:
        return None
    return Diagnosis(
        code="tp_not_divisible",
        title="attention head 수가 TP로 나누어지지 않음",
        cause=f"attention heads {m.group(1)}개를 TP {m.group(2)}로 균등 분할할 수 없음",
        fix="--tensor-parallel-size를 head 수의 약수(예: 1, 2, 4, 8)로 변경",
        evidence=_line_with(logs, "divisible by tensor parallel size"),
        fix_args=["--tensor-parallel-size"],
    )


def _world_size(logs: str) -> Diagnosis | None:
    m = re.search(r"World size \((\d+)\) is larger than the number of available GPUs \((\d+)\)", logs)
    if not m:
        return None
    return Diagnosis(
        code="world_size_exceeds_gpus",
        title="요청한 병렬도가 파드에 할당된 GPU 수보다 큼",
        cause=f"TP×PP 월드 크기 {m.group(1)}인데 컨테이너에는 GPU {m.group(2)}개만 보임",
        fix=f"--tensor-parallel-size(×pipeline)를 {m.group(2)} 이하로 낮추거나 nvidia.com/gpu limit을 늘림",
        evidence=_line_with(logs, "World size"),
        fix_args=["--tensor-parallel-size", "--pipeline-parallel-size"],
        suggested_value=int(m.group(2)),
    )


def _chat_template_path(logs: str) -> Diagnosis | None:
    m = re.search(r"chat template string \((.*?)\) appears path-like, but doesn't exist", logs)
    if not m:
        return None
    return Diagnosis(
        code="chat_template_path_missing",
        title="--chat-template 경로의 파일이 없음",
        cause=f"지정한 템플릿 파일 {m.group(1)}이 컨테이너에 존재하지 않음",
        fix="템플릿 파일을 볼륨/모델 디렉터리로 마운트해 실제 경로를 지정하거나 인자를 제거(모델 기본 템플릿 사용)",
        evidence=_line_with(logs, "appears path-like"),
        fix_args=["--chat-template"],
    )


def _bf16_unsupported(logs: str) -> Diagnosis | None:
    if "Bfloat16 is only supported on GPUs with compute capability" not in logs:
        return None
    return Diagnosis(
        code="bf16_unsupported",
        title="GPU가 bfloat16을 지원하지 않음",
        cause="compute capability 8.0 미만 GPU",
        fix="--dtype=half(float16)로 지정",
        evidence=_line_with(logs, "Bfloat16"),
        fix_args=["--dtype"],
    )


_RULES = (
    _mamba,
    _kv_too_small,
    _no_cache_memory,
    _startup_free_memory,
    _max_len_over_derived,
    _batched_tokens_small,
    _quantization_mismatch,
    _quantization_unsupported,
    _trust_remote_code,
    _unsupported_arch,
    _chat_template_path,
    _chat_template,
    _tool_parser,
    _tp_divisibility,
    _world_size,
    _bf16_unsupported,
    _cuda_oom,
)


def _from_pod_status(pod: dict[str, Any]) -> list[Diagnosis]:
    out: list[Diagnosis] = []
    restarts = pod.get("restarts") or 0
    last = pod.get("last_terminated_reason")
    state = pod.get("state")
    if last == "OOMKilled" or state == "OOMKilled":
        out.append(
            Diagnosis(
                code="container_oom_killed",
                title="컨테이너가 OOMKilled로 종료됨",
                cause="GPU가 아닌 호스트(CPU) 메모리가 컨테이너 memory limit을 초과 — 가중치 로딩·CPU swap·멀티프로세스 워커가 원인",
                fix="resources.limits.memory를 올리거나 --swap-space를 낮춤",
                evidence=f"lastState.terminated.reason={last or state}, exitCode={pod.get('exit_code')}",
                fix_args=["--swap-space"],
            )
        )
    if state == "CrashLoopBackOff":
        out.append(
            Diagnosis(
                code="crash_loop",
                title="CrashLoopBackOff — 기동 반복 실패",
                cause=f"컨테이너가 {restarts}회 재시작됨. 직전 종료 로그(previous)에 원인이 남아 있음",
                fix="아래 로그 기반 진단을 우선 확인",
                evidence=f"restarts={restarts}, lastReason={last}",
            )
        )
    elif state in ("ImagePullBackOff", "ErrImagePull"):
        out.append(
            Diagnosis(
                code="image_pull",
                title="이미지를 받지 못함",
                cause="이미지 이름·태그·pull secret 또는 레지스트리 접근 문제",
                fix="InferenceService의 이미지와 imagePullSecrets를 확인",
                evidence=f"waiting.reason={state}",
            )
        )
    return out


def diagnose_boot(logs: str | None, pod: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Diagnoses (most specific first) for a failed boot; ``pod`` is the container status summary."""
    found: list[Diagnosis] = []
    if logs:
        for rule in _RULES:
            d = rule(logs)
            if d is not None:
                found.append(d)
    if pod:
        found.extend(_from_pod_status(pod))
    return [asdict(d) for d in found]


def summarize_diagnoses(diagnoses: list[dict[str, Any]], limit: int = 2) -> str | None:
    """One short Korean sentence per top diagnosis (used when the analyst LLM is unavailable)."""
    if not diagnoses:
        return None
    return " / ".join(f"{d['title']} → {d['fix']}" for d in diagnoses[:limit])


LEARNED_LIMIT_TTL_S = 7 * 86400

_LEARNABLE = {
    "mamba_blocks_exceeded": "max_num_seqs",
    "kv_cache_too_small": "max_model_len",
    "max_model_len_exceeds_model": "max_model_len",
}


def learn_limits(diagnoses: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    """Upper bounds implied by a failed boot, each valid for trials at the same or a lower GPU memory utilization.

    The Mamba block count and the KV pool only shrink as ``gpu_memory_utilization`` drops, so a bound measured at
    utilization U also holds for every trial with utilization <= U (``util``). The derived max_model_len bound is
    utilization-independent (``util`` None).
    """
    limits: list[dict[str, Any]] = []
    for d in diagnoses:
        param = _LEARNABLE.get(d["code"])
        value = d.get("suggested_value")
        if not param or not value or value < 1:
            continue
        util = None if d["code"] == "max_model_len_exceeds_model" else params.get("gpu_memory_utilization")
        limits.append({"param": param, "max": int(value), "util": util, "code": d["code"]})
    return limits


def first_violated_limit(params: dict[str, Any], limits: list[dict[str, Any]]) -> dict[str, Any] | None:
    for limit in limits:
        value = params.get(limit["param"])
        if value is None or value <= limit["max"]:
            continue
        util = limit.get("util")
        if util is None or params.get("gpu_memory_utilization", 1.0) <= util:
            return limit
    return None


def compact_failure(reason: str, diagnoses: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "reason": reason,
        "diagnoses": [{"code": d["code"], "title": d["title"], "fix": d["fix"]} for d in diagnoses[:3]],
    }
