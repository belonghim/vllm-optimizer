import asyncio
import logging
from collections.abc import Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def with_retry(
    coro_fn: Callable[[], Any],
    retries: int = 3,
    base_delay: float = 1.0,
    label: str = "request",
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await coro_fn()
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_exc = e
            if attempt < retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "[retry] %s attempt %d/%d failed: %s — retrying in %.1fs",
                    label,
                    attempt + 1,
                    retries + 1,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                last_exc = e
                if attempt < retries:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "[retry] %s attempt %d/%d got %d — retrying in %.1fs",
                        label,
                        attempt + 1,
                        retries + 1,
                        e.response.status_code,
                        delay,
                    )
                    await asyncio.sleep(delay)
            else:
                raise
    assert last_exc is not None
    raise last_exc
