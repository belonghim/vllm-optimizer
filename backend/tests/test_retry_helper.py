from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from services.retry_helper import with_retry


async def test_success_no_retry():
    coro_fn = AsyncMock(return_value="ok")
    result = await with_retry(coro_fn, retries=2, base_delay=0.0)
    assert result == "ok"
    coro_fn.assert_called_once()


async def test_retry_on_timeout_then_success():
    call_count = 0

    async def coro_fn():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.TimeoutException("timeout")
        return "recovered"

    with patch("services.retry_helper.asyncio.sleep", new=AsyncMock()):
        result = await with_retry(coro_fn, retries=2, base_delay=0.01)

    assert result == "recovered"
    assert call_count == 2


async def test_retry_on_connect_error_then_success():
    call_count = 0

    async def coro_fn():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.ConnectError("connection refused")
        return "connected"

    with patch("services.retry_helper.asyncio.sleep", new=AsyncMock()):
        result = await with_retry(coro_fn, retries=3, base_delay=0.01)

    assert result == "connected"
    assert call_count == 2


async def test_max_retries_exceeded_raises_last_exception():
    coro_fn = AsyncMock(side_effect=httpx.ConnectError("always fails"))

    with patch("services.retry_helper.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(httpx.ConnectError, match="always fails"):
            await with_retry(coro_fn, retries=2, base_delay=0.01)

    assert coro_fn.call_count == 3


async def test_5xx_status_error_retries_then_success():
    response_mock = MagicMock()
    response_mock.status_code = 503
    exc = httpx.HTTPStatusError("service unavailable", request=MagicMock(), response=response_mock)

    call_count = 0

    async def coro_fn():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise exc
        return "ok"

    with patch("services.retry_helper.asyncio.sleep", new=AsyncMock()):
        result = await with_retry(coro_fn, retries=2, base_delay=0.01)

    assert result == "ok"
    assert call_count == 2


async def test_4xx_status_error_raises_immediately_without_retry():
    response_mock = MagicMock()
    response_mock.status_code = 404
    exc = httpx.HTTPStatusError("not found", request=MagicMock(), response=response_mock)
    coro_fn = AsyncMock(side_effect=exc)

    with pytest.raises(httpx.HTTPStatusError):
        await with_retry(coro_fn, retries=3, base_delay=0.0)

    coro_fn.assert_called_once()
