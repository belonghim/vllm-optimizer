"""
Model name resolver — vLLM /v1/models API를 통해 실제 모델명 해석
"""
import logging
import httpx

logger = logging.getLogger(__name__)


async def resolve_model_name(endpoint: str, fallback: str = "auto") -> str:
    """vLLM /v1/models API에서 첫 번째 모델명을 반환한다.

    Args:
        endpoint: vLLM 엔드포인트 URL
        fallback: 해석 실패 시 반환할 기본값 (default: "auto")

    Returns:
        해석된 모델명 또는 fallback
    """
    try:
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            resp = await client.get(f"{endpoint}/v1/models")
            if resp.status_code == 200:
                models_data = resp.json().get("data", [])
                if models_data:
                    model_name = models_data[0]["id"]
                    logger.info("[ModelResolver] Resolved model name: %s", model_name)
                    return model_name
    except Exception as e:
        logger.warning("[ModelResolver] Failed to resolve model name, using '%s': %s", fallback, e)
    return fallback
