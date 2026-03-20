from prometheus_client import Gauge, Counter

from metrics.prometheus_metrics import _registry

storage_db_size_bytes = Gauge(
    'vllm_optimizer_storage_db_size_bytes',
    'SQLite database file size in bytes',
    registry=_registry
)

storage_wal_size_bytes = Gauge(
    'vllm_optimizer_storage_wal_size_bytes',
    'SQLite WAL (Write-Ahead Log) file size in bytes',
    registry=_registry
)

storage_load_test_count = Gauge(
    'vllm_optimizer_storage_load_test_count',
    'Number of records in load_test_history table',
    registry=_registry
)

storage_benchmark_count = Gauge(
    'vllm_optimizer_storage_benchmark_count',
    'Number of records in benchmarks table',
    registry=_registry
)

storage_last_checkpoint_timestamp = Gauge(
    'vllm_optimizer_storage_last_checkpoint_timestamp',
    'Unix timestamp of the last successful checkpoint operation',
    registry=_registry
)

storage_prune_total = Counter(
    'vllm_optimizer_storage_prune_total',
    'Total number of records pruned from storage',
    registry=_registry
)
