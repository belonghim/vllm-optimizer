import pytest


def test_load_empty(isolated_client) -> None:
    resp = isolated_client.get("/api/targets/load")
    assert resp.status_code == 200
    data = resp.json()
    assert data["loaded"] is False
    assert data["targets"] == []


def test_save_and_load_roundtrip(isolated_client) -> None:
    payload = {
        "targets": [
            {"namespace": "ns1", "name": "svc1", "cr_type": "inferenceservice", "metrics_source": "prometheus"}
        ]
    }
    save_resp = isolated_client.post("/api/targets/save", json=payload)
    assert save_resp.status_code == 200
    save_data = save_resp.json()
    assert save_data["loaded"] is True
    assert len(save_data["targets"]) == 1

    load_resp = isolated_client.get("/api/targets/load")
    assert load_resp.status_code == 200
    load_data = load_resp.json()
    assert load_data["loaded"] is True
    assert load_data["targets"][0]["namespace"] == "ns1"
    assert load_data["targets"][0]["name"] == "svc1"
    assert load_data["targets"][0]["cr_type"] == "inferenceservice"


def test_save_overwrites_previous(isolated_client) -> None:
    first = {"targets": [{"namespace": "ns1", "name": "a", "cr_type": "inferenceservice", "metrics_source": "prometheus"}]}
    second = {"targets": [{"namespace": "ns2", "name": "b", "cr_type": "llminferenceservice", "metrics_source": "prometheus"}]}

    isolated_client.post("/api/targets/save", json=first)
    isolated_client.post("/api/targets/save", json=second)

    resp = isolated_client.get("/api/targets/load")
    data = resp.json()
    assert len(data["targets"]) == 1
    assert data["targets"][0]["namespace"] == "ns2"
    assert data["targets"][0]["name"] == "b"


def test_save_empty_list(isolated_client) -> None:
    resp = isolated_client.post("/api/targets/save", json={"targets": []})
    assert resp.status_code == 200
    data = resp.json()
    assert data["targets"] == []
    assert data["loaded"] is True

    load_resp = isolated_client.get("/api/targets/load")
    assert load_resp.json()["loaded"] is False


def test_save_multiple_targets(isolated_client) -> None:
    payload = {
        "targets": [
            {"namespace": "ns1", "name": "svc1", "cr_type": "inferenceservice", "metrics_source": "prometheus"},
            {"namespace": "ns2", "name": "svc2", "cr_type": "llminferenceservice", "metrics_source": "prometheus"},
        ]
    }
    save_resp = isolated_client.post("/api/targets/save", json=payload)
    assert save_resp.status_code == 200
    assert len(save_resp.json()["targets"]) == 2

    load_resp = isolated_client.get("/api/targets/load")
    data = load_resp.json()
    assert data["loaded"] is True
    assert len(data["targets"]) == 2


def test_default_cr_type_and_metrics_source(isolated_client) -> None:
    isolated_client.post("/api/targets/save", json={"targets": [{"namespace": "ns", "name": "svc"}]})
    resp = isolated_client.get("/api/targets/load")
    target = resp.json()["targets"][0]
    assert target["cr_type"] == "inferenceservice"
    assert target["metrics_source"] == "prometheus"


def test_save_invalid_payload_returns_422(isolated_client) -> None:
    resp = isolated_client.post("/api/targets/save", json={"wrong_field": []})
    assert resp.status_code == 422


def test_llminferenceservice_cr_type_preserved(isolated_client) -> None:
    payload = {
        "targets": [
            {"namespace": "llm-d-demo", "name": "small-llm-d", "cr_type": "llminferenceservice", "metrics_source": "prometheus"}
        ]
    }
    isolated_client.post("/api/targets/save", json=payload)
    resp = isolated_client.get("/api/targets/load")
    target = resp.json()["targets"][0]
    assert target["cr_type"] == "llminferenceservice"
    assert target["namespace"] == "llm-d-demo"
