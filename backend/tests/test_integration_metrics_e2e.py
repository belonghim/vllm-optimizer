from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_integration_metrics_endpoint_no_mock():
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text

    # End-to-end check: ensure Prometheus text format is served and at least
    # one vLLM metric is present. Do not require an exact count to keep test robust
    # across environment variations.
    names = set()
    for line in text.splitlines():
        if line.startswith("# HELP "):
            parts = line.split()
            if len(parts) >= 3:
                names.add(parts[2])
    assert any(n.startswith("vllm_") for n in names), \
        f"Expected at least one vllm_ metric in output, found: {sorted(list(names))}"
