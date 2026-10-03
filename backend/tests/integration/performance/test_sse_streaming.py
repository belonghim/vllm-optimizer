import json

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.performance]


class TestSSEStreaming:
    @pytest.mark.asyncio
    async def test_load_test_sse_events(self, async_http_client, skip_if_overloaded, vllm_endpoint, vllm_model):
        """부하 테스트 중 SSE 이벤트가 정상적으로 수신되는지 확인.

        스트림을 먼저 구독한 뒤 테스트를 시작한다 — 완료 후 늦게 구독하면 이벤트가 이미 broadcast된
        뒤라 keepalive만 수신하고 종료되지 않는다.
        """
        base_url = async_http_client

        async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:
            config = {
                "endpoint": vllm_endpoint,
                "model": vllm_model,
                "prompt_template": "Test prompt",
                "total_requests": 3,
                "concurrency": 1,
                "rps": 1,
                "max_tokens": 10,
                "temperature": 0.7,
                "stream": False,
            }

            events = []
            buffer = ""
            try:
                async with client.stream("GET", "/api/load_test/stream", timeout=60) as stream:
                    resp = await client.post("/api/load_test/start", json=config)
                    assert resp.status_code == 200

                    async for chunk in stream.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            event_str, buffer = buffer.split("\n\n", 1)
                            for line in event_str.split("\n"):
                                if line.startswith("data: "):
                                    try:
                                        data = json.loads(line[6:])
                                        events.append(data)
                                    except json.JSONDecodeError:
                                        pass
                        if len(events) >= 3:
                            break
            except (httpx.ReadTimeout, httpx.RemoteProtocolError):
                pass

            assert len(events) >= 1, f"Expected at least 1 SSE event, got {len(events)}"
            for event in events:
                assert isinstance(event, dict)
