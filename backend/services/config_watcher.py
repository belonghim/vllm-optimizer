"""
ConfigMap Watcher Service

Periodically polls the Kubernetes ConfigMap for default target changes and broadcasts
updates via EventBroadcaster when values change.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.event_broadcaster import EventBroadcaster

logger = logging.getLogger(__name__)

# ConfigMap fields to watch
_WATCHED_FIELDS = (
    "DEFAULT_ISVC_NAME",
    "DEFAULT_ISVC_NAMESPACE",
    "DEFAULT_LLMISVC_NAME",
    "DEFAULT_LLMISVC_NAMESPACE",
)

# Default polling interval (5 minutes)
_DEFAULT_POLL_INTERVAL_SEC = 300
# Minimum polling interval (1 minute)
_MIN_POLL_INTERVAL_SEC = 60
# ConfigMap name
_CONFIGMAP_NAME = "vllm-optimizer-config"


def _get_poll_interval() -> int:
    """Get polling interval from environment variable with bounds checking."""
    interval = int(os.getenv("CONFIGMAP_POLL_INTERVAL_SEC", _DEFAULT_POLL_INTERVAL_SEC))
    return max(interval, _MIN_POLL_INTERVAL_SEC)


def _get_namespace() -> str:
    """Get namespace from environment variable."""
    return os.getenv("POD_NAMESPACE", "vllm-optimizer-dev")


class ConfigMapWatcher:
    """Watches ConfigMap for default target changes and broadcasts updates."""

    def __init__(self, broadcaster: EventBroadcaster) -> None:
        """Initialize the ConfigMapWatcher.

        Args:
            broadcaster: EventBroadcaster instance for broadcasting updates.
        """
        self._broadcaster = broadcaster
        self._interval_sec: int = _get_poll_interval()
        self._namespace: str = _get_namespace()
        self._stop_event: asyncio.Event = asyncio.Event()
        self._stop_event.set()  # Initially stopped
        self._task: asyncio.Task[None] | None = None
        self._cached_values: dict[str, str] = {field: "" for field in _WATCHED_FIELDS}

    def _read_configmap(self) -> dict[str, str]:
        """Read the ConfigMap and return watched field values.

        Returns:
            Dictionary of watched field names to their values.

        Raises:
            ApiException: If K8s API call fails.
            ConfigException: If K8s config loading fails.
        """
        from kubernetes import client as k8s_client
        from kubernetes import config as k8s_config

        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()

        v1 = k8s_client.CoreV1Api()
        cm = v1.read_namespaced_config_map(name=_CONFIGMAP_NAME, namespace=self._namespace)
        data = cm.data if cm.data else {}

        return {field: data.get(field, "") for field in _WATCHED_FIELDS}

    def _has_changes(self, new_values: dict[str, str]) -> bool:
        """Check if any watched field has changed.

        Args:
            new_values: New values read from ConfigMap.

        Returns:
            True if any field has changed, False otherwise.
        """
        return any(self._cached_values.get(field) != new_values.get(field) for field in _WATCHED_FIELDS)

    def _update_cache(self, new_values: dict[str, str]) -> None:
        """Update the cached values.

        Args:
            new_values: New values to cache.
        """
        self._cached_values = new_values.copy()

    async def _poll_and_broadcast(self) -> None:
        """Poll ConfigMap and broadcast if values changed."""
        try:
            new_values = await asyncio.to_thread(self._read_configmap)

            if self._has_changes(new_values):
                old_values = self._cached_values.copy()
                self._update_cache(new_values)

                logger.info(
                    "[ConfigMapWatcher] Detected config change: %s -> %s",
                    old_values,
                    new_values,
                )

                await self._broadcaster.broadcast(
                    {
                        "type": "configmap_update",
                        "data": {
                            "isvc": {
                                "name": new_values.get("DEFAULT_ISVC_NAME", ""),
                                "namespace": new_values.get("DEFAULT_ISVC_NAMESPACE", ""),
                            },
                            "llmisvc": {
                                "name": new_values.get("DEFAULT_LLMISVC_NAME", ""),
                                "namespace": new_values.get("DEFAULT_LLMISVC_NAMESPACE", ""),
                            },
                        },
                    }
                )
            else:
                logger.debug("[ConfigMapWatcher] No config changes detected")

        except Exception as e:
            # Handle K8s API exceptions gracefully
            logger.warning("[ConfigMapWatcher] ConfigMap read failed: %s", e)

    async def _watch_loop(self) -> None:
        """Main polling loop."""
        logger.info(
            "[ConfigMapWatcher] Starting watch loop (interval=%ds, namespace=%s)",
            self._interval_sec,
            self._namespace,
        )

        # Initial read to populate cache
        try:
            initial_values = await asyncio.to_thread(self._read_configmap)
            self._update_cache(initial_values)
            logger.info("[ConfigMapWatcher] Initial cache populated: %s", initial_values)
        except Exception as e:
            logger.warning("[ConfigMapWatcher] Initial ConfigMap read failed: %s", e)

        while not self._stop_event.is_set():
            await asyncio.sleep(self._interval_sec)
            if self._stop_event.is_set():
                break
            await self._poll_and_broadcast()

        logger.info("[ConfigMapWatcher] Watch loop stopped")

    async def start(self) -> None:
        """Start the ConfigMap watcher.

        Creates and starts a background task for the polling loop.
        Multiple calls to start() without stop() are ignored.
        """
        if self._task is not None and not self._task.done():
            logger.debug("[ConfigMapWatcher] Already running, ignoring start()")
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("[ConfigMapWatcher] Started")

    async def stop(self) -> None:
        """Stop the ConfigMap watcher.

        Signals the polling loop to stop and waits for the task to complete.
        Multiple calls to stop() are safe.
        """
        if self._task is None or self._task.done():
            logger.debug("[ConfigMapWatcher] Not running, ignoring stop()")
            return

        logger.info("[ConfigMapWatcher] Stopping...")
        self._stop_event.set()
        await self._task
        self._task = None
        logger.info("[ConfigMapWatcher] Stopped")

    @property
    def cached_values(self) -> dict[str, str]:
        """Return a copy of the current cached values."""
        return self._cached_values.copy()
