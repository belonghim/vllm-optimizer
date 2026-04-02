import pytest
from services.config_watcher import ConfigMapWatcher


@pytest.fixture
def broadcaster():
    from services.event_broadcaster import EventBroadcaster

    return EventBroadcaster()


@pytest.fixture
def watcher(broadcaster):
    return ConfigMapWatcher(broadcaster)


@pytest.mark.asyncio
async def test_watcher_initializes_with_empty_cache(watcher):
    assert watcher.cached_values == {
        "DEFAULT_ISVC_NAME": "",
        "DEFAULT_ISVC_NAMESPACE": "",
        "DEFAULT_LLMISVC_NAME": "",
        "DEFAULT_LLMISVC_NAMESPACE": "",
    }


@pytest.mark.asyncio
async def test_start_creates_task(watcher):
    await watcher.start()
    assert watcher._task is not None
    assert not watcher._task.done()
    await watcher.stop()


@pytest.mark.asyncio
async def test_stop_waits_for_task(watcher):
    await watcher.start()
    await watcher.stop()
    assert watcher._task is None


@pytest.mark.asyncio
async def test_double_start_ignored(watcher):
    await watcher.start()
    first_task = watcher._task
    await watcher.start()
    assert watcher._task is first_task
    await watcher.stop()


@pytest.mark.asyncio
async def test_double_stop_ignored(watcher):
    await watcher.start()
    await watcher.stop()
    await watcher.stop()
    assert watcher._task is None


@pytest.mark.asyncio
async def test_broadcasts_on_config_change(watcher, broadcaster):
    q = await broadcaster.subscribe()

    initial_data = {
        "DEFAULT_ISVC_NAME": "isvc-1",
        "DEFAULT_ISVC_NAMESPACE": "ns-1",
        "DEFAULT_LLMISVC_NAME": "llmisvc-1",
        "DEFAULT_LLMISVC_NAMESPACE": "ns-2",
    }
    changed_data = {
        "DEFAULT_ISVC_NAME": "isvc-2",
        "DEFAULT_ISVC_NAMESPACE": "ns-1",
        "DEFAULT_LLMISVC_NAME": "llmisvc-1",
        "DEFAULT_LLMISVC_NAMESPACE": "ns-2",
    }

    call_count = 0

    def mock_read_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                field: initial_data.get(field, "")
                for field in (
                    "DEFAULT_ISVC_NAME",
                    "DEFAULT_ISVC_NAMESPACE",
                    "DEFAULT_LLMISVC_NAME",
                    "DEFAULT_LLMISVC_NAMESPACE",
                )
            }
        return {
            field: changed_data.get(field, "")
            for field in (
                "DEFAULT_ISVC_NAME",
                "DEFAULT_ISVC_NAMESPACE",
                "DEFAULT_LLMISVC_NAME",
                "DEFAULT_LLMISVC_NAMESPACE",
            )
        }

    original_read = watcher._read_configmap
    watcher._read_configmap = mock_read_side_effect

    watcher._update_cache(initial_data)
    await watcher._poll_and_broadcast()
    assert q.empty()

    await watcher._poll_and_broadcast()
    assert not q.empty()
    msg = q.get_nowait()
    assert msg["type"] == "configmap_update"
    assert msg["data"]["isvc"]["name"] == "isvc-2"

    watcher._read_configmap = original_read


@pytest.mark.asyncio
async def test_no_broadcast_when_values_unchanged(watcher, broadcaster):
    q = await broadcaster.subscribe()

    test_data = {
        "DEFAULT_ISVC_NAME": "isvc-1",
        "DEFAULT_ISVC_NAMESPACE": "ns-1",
        "DEFAULT_LLMISVC_NAME": "llmisvc-1",
        "DEFAULT_LLMISVC_NAMESPACE": "ns-2",
    }

    original_read = watcher._read_configmap
    watcher._read_configmap = lambda: {
        field: test_data.get(field, "")
        for field in (
            "DEFAULT_ISVC_NAME",
            "DEFAULT_ISVC_NAMESPACE",
            "DEFAULT_LLMISVC_NAME",
            "DEFAULT_LLMISVC_NAMESPACE",
        )
    }

    watcher._update_cache(test_data)
    await watcher._poll_and_broadcast()
    assert q.empty()

    watcher._read_configmap = original_read


@pytest.mark.asyncio
async def test_handles_api_exception_gracefully(watcher, broadcaster):
    q = await broadcaster.subscribe()

    from kubernetes.client.exceptions import ApiException

    def mock_raise():
        raise ApiException("Test error")

    original_read = watcher._read_configmap
    watcher._read_configmap = mock_raise

    watcher._update_cache({"DEFAULT_ISVC_NAME": ""})
    await watcher._poll_and_broadcast()
    assert q.empty()

    watcher._read_configmap = original_read


@pytest.mark.asyncio
async def test_has_changes_detects_difference(watcher):
    # Set up cache with all four fields
    full_old = {
        "DEFAULT_ISVC_NAME": "old",
        "DEFAULT_ISVC_NAMESPACE": "ns",
        "DEFAULT_LLMISVC_NAME": "llmisvc-old",
        "DEFAULT_LLMISVC_NAMESPACE": "llmisvc-ns",
    }
    full_new_changed = {
        "DEFAULT_ISVC_NAME": "new",  # Changed
        "DEFAULT_ISVC_NAMESPACE": "ns",
        "DEFAULT_LLMISVC_NAME": "llmisvc-old",
        "DEFAULT_LLMISVC_NAMESPACE": "llmisvc-ns",
    }
    full_new_same = {
        "DEFAULT_ISVC_NAME": "old",
        "DEFAULT_ISVC_NAMESPACE": "ns",
        "DEFAULT_LLMISVC_NAME": "llmisvc-old",
        "DEFAULT_LLMISVC_NAMESPACE": "llmisvc-ns",
    }

    watcher._update_cache(full_old)
    assert watcher._has_changes(full_new_changed)
    assert not watcher._has_changes(full_new_same)


@pytest.mark.asyncio
async def test_update_cache(watcher):
    new_values = {
        "DEFAULT_ISVC_NAME": "test-isvc",
        "DEFAULT_ISVC_NAMESPACE": "test-ns",
        "DEFAULT_LLMISVC_NAME": "test-llmisvc",
        "DEFAULT_LLMISVC_NAMESPACE": "test-ns2",
    }
    watcher._update_cache(new_values)
    assert watcher.cached_values == new_values
