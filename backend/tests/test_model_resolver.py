from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_resolve_model_name_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": [{"id": "my-model"}]}

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("services.shared.internal_client", mock_client):
        from services.model_resolver import resolve_model_name

        result = await resolve_model_name("http://test-endpoint")

    assert result == "my-model"


@pytest.mark.asyncio
async def test_resolve_model_name_fallback():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with patch("services.shared.internal_client", mock_client):
        from services.model_resolver import resolve_model_name

        result = await resolve_model_name("http://bad-endpoint")

    assert result == "auto"


@pytest.mark.asyncio
async def test_resolve_model_name_empty_data():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": []}

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("services.shared.internal_client", mock_client):
        from services.model_resolver import resolve_model_name

        result = await resolve_model_name("http://test-endpoint", fallback="auto")

    assert result == "auto"
