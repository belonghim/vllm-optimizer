"""
LLM-powered tuning assistant that reuses the vLLM endpoint being tuned.

The tuning target model doubles as the analyst. All calls are strictly best-effort:
- Timeouts are short.
- Malformed responses degrade to None / empty output.
- Assistant failures never block tuning.
"""

import json
import logging
import re
from typing import Any

import httpx
from services.model_resolver import resolve_model_name

logger = logging.getLogger(__name__)

_TIMEOUT_S = 30.0
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


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


class LLMAssistant:
    """Chat-completions client scoped to the tuning target vLLM endpoint."""

    def __init__(self) -> None:
        self._resolved_models: dict[str, str] = {}

    async def _model_for(self, endpoint: str) -> str | None:
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
        endpoint: str,
        system: str,
        user: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> str | None:
        model = await self._model_for(endpoint)
        if not model:
            logger.debug("[LLMAssistant] Skipping call: unresolved model name")
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
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                resp = await client.post(f"{endpoint.rstrip('/')}/v1/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            logger.debug("[LLMAssistant] Chat call failed: %s", e)
            return None

    async def suggest_warmup_params(
        self,
        endpoint: str,
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
        raw = await self._chat(endpoint, system, user, max_tokens=1024, temperature=0.3)
        if not raw:
            return []
        parsed = _extract_json_array(raw)
        if not parsed:
            logger.debug("[LLMAssistant] Warmup response could not be parsed as JSON: %s", raw[:200])
            return []
        clean: list[dict[str, Any]] = []
        for item in parsed[:count]:
            if isinstance(item, dict):
                clean.append(item)
        return clean

    async def summarize_failure(
        self,
        endpoint: str,
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
        return await self._chat(endpoint, system, user, max_tokens=256, temperature=0.2)

    async def generate_tuning_report(
        self,
        endpoint: str,
        summary: dict[str, Any],
    ) -> str | None:
        system = (
            "You are a vLLM tuning report writer. Produce a markdown report with three "
            "sections: '## Summary', '## Why This Config Works', '## Recommendations'. "
            "Ground your reasoning in the provided model architecture and trial data. "
            "Keep the total under ~250 words."
        )
        user = (
            f"Tuning session summary:\n{json.dumps(summary, indent=2, default=str)}\n\n"
            f"Write the markdown report now."
        )
        return await self._chat(endpoint, system, user, max_tokens=768, temperature=0.4)


_assistant = LLMAssistant()


def get_llm_assistant() -> LLMAssistant:
    return _assistant
