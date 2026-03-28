"""
Model name resolver — vLLM /v1/models API를 통해 실제 모델명 해석
"""

import logging

import httpx

from services.retry_helper import with_retry

logger = logging.getLogger(__name__)


async def resolve_model_name(endpoint: str, fallback: str = "auto") -> str:
    from services.shared import get_internal_client

    try:
        internal_client = get_internal_client()

        async def _do_get():
            r = await internal_client.get(f"{endpoint}/v1/models", timeout=10)
            r.raise_for_status()
            return r

        resp = await with_retry(_do_get, label="model-resolver")
        models_data = resp.json().get("data", [])
        if models_data:
            model_name = models_data[0]["id"]
            logger.info("[ModelResolver] Resolved model name: %s", model_name)
            return model_name
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("[ModelResolver] Failed to resolve model name, using '%s': %s", fallback, e)
    return fallback
