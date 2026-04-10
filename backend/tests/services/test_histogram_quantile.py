import pytest
from services.multi_target_collector import MultiTargetMetricsCollector


def _make_collector() -> MultiTargetMetricsCollector:
    return MultiTargetMetricsCollector()


class TestComputeHistogramQuantile:
    def test_empty_buckets_returns_zero(self) -> None:
        collector = _make_collector()
        assert collector._compute_histogram_quantile([], 0.5) == 0.0

    def test_invalid_quantile_returns_zero(self) -> None:
        collector = _make_collector()
        buckets = [(0.1, 10.0)]
        assert collector._compute_histogram_quantile(buckets, -0.1) == 0.0
        assert collector._compute_histogram_quantile(buckets, 1.5) == 0.0

    def test_single_bucket_median(self) -> None:
        collector = _make_collector()
        buckets = [(0.05, 10.0), (float("inf"), 10.0)]
        result = collector._compute_histogram_quantile(buckets, 0.5, 1.0)
        assert result > 0.0

    def test_simple_median_with_scale(self) -> None:
        collector = _make_collector()
        buckets = [(1.0, 5.0), (2.0, 10.0), (float("inf"), 10.0)]
        result = collector._compute_histogram_quantile(buckets, 0.5, 1000.0)
        assert 999.0 <= result <= 1001.0

    def test_p99_quantile(self) -> None:
        collector = _make_collector()
        buckets = [(0.01, 1.0), (0.05, 6.0), (0.1, 9.0), (float("inf"), 10.0)]
        result = collector._compute_histogram_quantile(buckets, 0.99, 1000.0)
        assert result > 0.0

    def test_nan_count_skipped(self) -> None:
        collector = _make_collector()
        buckets = [(0.01, float("nan")), (0.05, 10.0), (float("inf"), 10.0)]
        result = collector._compute_histogram_quantile(buckets, 0.5, 1000.0)
        assert result > 0.0

    def test_negative_count_skipped(self) -> None:
        collector = _make_collector()
        buckets = [(0.01, -1.0), (0.05, 10.0), (float("inf"), 10.0)]
        result = collector._compute_histogram_quantile(buckets, 0.5, 1000.0)
        assert result > 0.0
