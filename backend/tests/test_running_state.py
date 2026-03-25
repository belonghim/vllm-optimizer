import pytest
from services.storage import Storage


@pytest.fixture
async def storage():
    s = Storage(":memory:")
    await s.initialize()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_set_and_clear_running(storage):
    row_id = await storage.set_running("tuner")
    assert row_id > 0

    interrupted = await storage.get_interrupted_runs()
    assert len(interrupted) == 1
    assert interrupted[0]["task_type"] == "tuner"
    assert interrupted[0]["id"] == row_id

    await storage.clear_running(row_id)

    interrupted = await storage.get_interrupted_runs()
    assert len(interrupted) == 0


@pytest.mark.asyncio
async def test_interrupted_after_exception(storage):
    row_id = await storage.set_running("tuner")
    try:
        raise RuntimeError("simulated crash")
    except RuntimeError:
        pass
    finally:
        await storage.clear_running(row_id)

    interrupted = await storage.get_interrupted_runs()
    assert len(interrupted) == 0


@pytest.mark.asyncio
async def test_interrupted_without_clear(storage):
    await storage.set_running("loadtest")
    await storage.set_running("tuner")

    interrupted = await storage.get_interrupted_runs()
    assert len(interrupted) == 2
    task_types = {r["task_type"] for r in interrupted}
    assert task_types == {"loadtest", "tuner"}


def test_status_interrupted_endpoint(isolated_client):
    import asyncio

    from routers.status import set_interrupted_runs

    asyncio.run(
        set_interrupted_runs(
            [
                {"id": 1, "task_type": "tuner", "started_at": 1711100000.0},
                {"id": 2, "task_type": "loadtest", "started_at": 1711100001.0},
            ]
        )
    )

    resp = isolated_client.get("/api/status/interrupted")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["interrupted_runs"]) == 2
    assert data["interrupted_runs"][0]["task_type"] == "tuner"

    resp2 = isolated_client.get("/api/status/interrupted")
    assert resp2.status_code == 200
    assert len(resp2.json()["interrupted_runs"]) == 0


def test_status_interrupted_endpoint_empty(isolated_client):
    resp = isolated_client.get("/api/status/interrupted")
    assert resp.status_code == 200
    assert resp.json()["interrupted_runs"] == []
