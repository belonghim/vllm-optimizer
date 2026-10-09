"""
Analyst LLM client — a separate small model (e.g. llm-ov, OpenVINO Qwen3.5-2B) that explains results.

The analyst never sees the tuning target's traffic: it is configured via ANALYST_ENDPOINT and is
disabled when unset. It only narrates facts computed deterministically elsewhere (model analysis,
trial data); numbers it proposes are clamped by the caller. All calls are best-effort:
- Malformed responses degrade to None / empty output.
- Assistant failures never block tuning.
"""

import json
import logging
import os
import re
from typing import Any

import httpx
from services.model_resolver import resolve_model_name

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")
_THINK_RE = re.compile(r"<think>[\s\S]*?</think>\s*")


def _extract_json_array(text: str) -> list[Any] | None:
    for pattern in (_JSON_BLOCK_RE, _JSON_ARRAY_RE):
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group(1) if pattern is _JSON_BLOCK_RE else match.group(0)
        try:
            parsed = json.loads(raw.strip())
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            continue
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return None


def _fmt_bytes(n: Any) -> str:
    if not isinstance(n, (int, float)) or n <= 0:
        return "-"
    for unit, size in (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024)):
        if n >= size:
            return f"{n / size:.1f} {unit}"
    return f"{int(n)} B"


def format_analysis_facts(analysis: dict[str, Any]) -> str:
    """Render a model-analysis response as short human-readable lines with explicit units.

    Small analyst models misread raw byte counts, so every quantity is pre-formatted here.
    """
    m = analysis.get("model") or {}
    budget = analysis.get("memory_budget") or {}
    layers = (
        f"총 {m.get('num_hidden_layers')}개 — full attention {m.get('full_attention_layers', 0)}, "
        f"sliding {m.get('sliding_attention_layers', 0)}, linear(GDN/Mamba) {m.get('linear_attention_layers', 0)}, "
        f"KV 공유 {m.get('kv_shared_layers', 0)}"
    )
    lines = [
        f"- 모델: {m.get('architecture')} (서빙 이름 {m.get('served_model_name') or '-'})"
        + (", 멀티모달" if m.get("multimodal") else ""),
        f"- 레이어: {layers}",
        f"- 어텐션: heads {m.get('num_attention_heads')}, KV heads {m.get('num_key_value_heads')}, "
        f"head_dim {m.get('head_dim')}" + (", MLA" if m.get("mla") else ""),
        f"- KV 캐시(full attention): 토큰당 {_fmt_bytes(m.get('kv_bytes_per_token'))}, dtype {m.get('kv_cache_dtype')}",
    ]
    if m.get("sliding_kv_bytes_per_token"):
        lines.append(
            f"- KV 캐시(sliding): 토큰당 {_fmt_bytes(m.get('sliding_kv_bytes_per_token'))}, "
            f"최대 {m.get('sliding_window')} 토큰까지만 증가"
        )
    if m.get("linear_state_bytes_per_seq"):
        lines.append(
            f"- linear attention 고정 상태: 시퀀스 슬롯(max_num_seqs)당 {_fmt_bytes(m.get('linear_state_bytes_per_seq'))}"
        )
    if m.get("num_experts"):
        lines.append(f"- MoE: 전문가 {m.get('num_experts')}개 중 토큰당 {m.get('num_experts_per_tok')}개 활성")
    weight = m.get("model_weight_gib")
    lines += [
        f"- 가중치: {weight:.2f} GiB" if isinstance(weight, (int, float)) else "- 가중치: -",
        f"- 양자화: {m.get('quantization') or m.get('weight_dtype') or '-'}",
        f"- 컨텍스트: 모델 최대 {m.get('max_position_embeddings')} 토큰, 현재 서빙 {m.get('served_max_model_len')} 토큰",
        f"- 메모리 예산: {budget.get('gib')} GiB ({budget.get('source')})",
    ]
    capacity = analysis.get("capacity") or []
    estimated = [r for r in capacity if r.get("max_concurrent_seqs") is not None]
    if estimated:
        lines.append(
            "- 컨텍스트 길이별 최대 동시 시퀀스(이론 상한): "
            + ", ".join(f"{r['context_len']} 토큰 → {r['max_concurrent_seqs']}" for r in estimated)
        )
    observed = analysis.get("observed")
    if observed:
        lines.append(
            f"- vLLM 실측 KV 풀: {observed.get('kv_cache_size_tokens')} 토큰, "
            f"현재 max_model_len에서 동시 {observed.get('max_concurrency')}배 (현재 설정 기준 실측값)"
        )
    space = analysis.get("suggested_search_space")
    if space:
        lines.append(
            f"- 제안 탐색 범위: max_num_seqs {space['max_num_seqs_min']}~{space['max_num_seqs_max']}, "
            f"max_model_len {space['max_model_len_min']}~{space['max_model_len_max']}"
        )
    recs = (analysis.get("advice") or {}).get("recommendations") or []
    gaps = [r for r in recs if r.get("kind") == "required" and r.get("status") in ("missing", "mismatch")]
    if gaps:
        lines.append(
            "- 필수 기능 인자 누락/불일치(현재 설정 기준): "
            + ", ".join(f"{r['flag']}={r['value']}" if r.get("value") else str(r["flag"]) for r in gaps)
        )
    warnings = [w for w in analysis.get("warnings") or [] if "ANALYST_ENDPOINT" not in w]
    lines += [f"- 주의: {w}" for w in warnings]
    return "\n".join(lines)


class LLMAssistant:
    """Chat-completions client bound to ANALYST_ENDPOINT (never the tuning target)."""

    def __init__(self) -> None:
        self._resolved_models: dict[str, str] = {}

    @property
    def endpoint(self) -> str:
        return os.getenv("ANALYST_ENDPOINT", "").strip().rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self.endpoint)

    @property
    def _timeout(self) -> float:
        try:
            return float(os.getenv("ANALYST_TIMEOUT", "120"))
        except ValueError:
            return 120.0

    async def _model_for(self, endpoint: str) -> str | None:
        configured = os.getenv("ANALYST_MODEL", "").strip()
        if configured:
            return configured
        cached = self._resolved_models.get(endpoint)
        if cached:
            return cached
        name = await resolve_model_name(endpoint, fallback="")
        if not name or name == "auto":
            return None
        self._resolved_models[endpoint] = name
        return name

    async def _chat(
        self,
        system: str,
        user: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        extra: dict[str, Any] | None = None,
    ) -> str | None:
        endpoint = self.endpoint
        if not endpoint:
            return None
        model = await self._model_for(endpoint)
        if not model:
            logger.debug("[LLMAssistant] Skipping call: unresolved analyst model name")
            return None
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            **(extra or {}),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout, verify=False) as client:
                resp = await client.post(f"{endpoint}/v1/chat/completions", json=payload)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as e:
            logger.debug("[LLMAssistant] Chat call failed: %s", e)
            return None
        if not isinstance(content, str):
            return None
        return _THINK_RE.sub("", content).strip() or None

    async def suggest_warmup_params(
        self,
        model_info: dict[str, Any],
        search_space: dict[str, Any],
        hw_context: dict[str, Any],
        count: int = 3,
    ) -> list[dict[str, Any]]:
        system = (
            "You are a vLLM performance-tuning expert. Given model architecture, hardware, "
            "and a hyperparameter search space, propose initial configurations likely to "
            "achieve high throughput without OOM. Output ONLY a JSON array — no prose, "
            "no markdown fences, no commentary."
        )
        user = (
            f"Model architecture:\n{json.dumps(model_info, indent=2)}\n\n"
            f"Runtime environment:\n{json.dumps(hw_context, indent=2)}\n\n"
            f"Search space (min/max or choices):\n{json.dumps(search_space, indent=2)}\n\n"
            f"Propose {count} distinct configurations as a JSON array. Each element must be "
            f"an object with keys: max_num_seqs (int), gpu_memory_utilization (float), "
            f"max_model_len (int), max_num_batched_tokens (int), block_size (int from the choices), "
            f"enable_chunked_prefill (bool), enable_enforce_eager (bool). "
            f"All values must fall within the search space. Output the JSON array now."
        )
        raw = await self._chat(system, user, max_tokens=1024, temperature=0.0)
        if not raw:
            return []
        parsed = _extract_json_array(raw)
        if not parsed:
            logger.debug("[LLMAssistant] Warmup response could not be parsed as JSON: %s", raw[:200])
            return []
        return [item for item in parsed[:count] if isinstance(item, dict)]

    async def summarize_failure(
        self,
        params: dict[str, Any],
        failure_reason: str,
        logs: str | None,
    ) -> str | None:
        system = (
            "You are a vLLM debugging expert. Given tried parameters, a failure "
            "classification, and log tail, explain in at most 3 sentences what went wrong "
            "and how to avoid it. Be concrete. No markdown, plain text only."
        )
        log_tail = (logs or "")[-3000:] if logs else "(logs unavailable)"
        user = (
            f"Tried parameters:\n{json.dumps(params, indent=2)}\n\n"
            f"Failure classification: {failure_reason}\n\n"
            f"Pod log tail:\n{log_tail}\n\n"
            f"What went wrong and how should the next trial avoid it?"
        )
        return await self._chat(system, user, max_tokens=256, temperature=0.0)

    async def generate_tuning_report(self, summary: dict[str, Any]) -> str | None:
        system = (
            "You are a vLLM tuning report writer. Produce a markdown report with three "
            "sections: '## Summary', '## Why This Config Works', '## Recommendations'. "
            "Ground your reasoning in the provided model architecture and trial data. "
            "Keep the total under ~250 words."
        )
        user = (
            f"Tuning session summary:\n{json.dumps(summary, indent=2, default=str)}\n\nWrite the markdown report now."
        )
        return await self._chat(system, user, max_tokens=768, temperature=0.0)

    async def explain_model_analysis(self, analysis: dict[str, Any]) -> str | None:
        system = (
            "You are a vLLM serving engineer. The facts below are computed exactly. "
            "Quote numbers exactly as written (keep their units); never convert, recompute or invent numbers. "
            "Never invent parameter or environment-variable names; mention only names that appear in the facts. "
            "Write concise Korean markdown with sections '## 구조 요약', '## 메모리·동시성 시사점', "
            "'## 튜닝 시 주의점', at most 3 bullets each. Do not repeat yourself."
        )
        user = "모델 분석 결과:\n" + format_analysis_facts(analysis)
        return await self._chat(
            system, user, max_tokens=450, temperature=0.0, extra={"frequency_penalty": 0.5, "repetition_penalty": 1.1}
        )


_assistant = LLMAssistant()


def get_llm_assistant() -> LLMAssistant:
    return _assistant
