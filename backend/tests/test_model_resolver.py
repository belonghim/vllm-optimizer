from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_resolve_model_name_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": [{"id": "my-model"}]}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.model_resolver.httpx.AsyncClient", return_value=mock_client):
        from services.model_resolver import resolve_model_name

        result = await resolve_model_name("http://test-endpoint")

    assert result == "my-model"


@pytest.mark.asyncio
async def test_resolve_model_name_fallback():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.model_resolver.httpx.AsyncClient", return_value=mock_client):
        from services.model_resolver import resolve_model_name

        result = await resolve_model_name("http://bad-endpoint")

    assert result == "auto"


@pytest.mark.asyncio
async def test_resolve_model_name_empty_data():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": []}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.model_resolver.httpx.AsyncClient", return_value=mock_client):
        from services.model_resolver import resolve_model_name

        result = await resolve_model_name("http://test-endpoint", fallback="auto")

    assert result == "auto"
