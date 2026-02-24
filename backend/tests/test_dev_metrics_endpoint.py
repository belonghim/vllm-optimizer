import pytest
from fastapi.testclient import TestClient

def test_metrics_endpoint_plaintext(monkeypatch):
    import backend.metrics.prometheus_metrics as prom
    def fake_generate_metrics():
        return "# HELP vllm_dummy\n# TYPE vllm_dummy gauge\nvllm_dummy 1\n"
    monkeypatch.setattr(prom, 'generate_metrics', fake_generate_metrics)

    from backend.main import app
    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/plain")
    text = resp.text
    assert "vllm_dummy" in text
