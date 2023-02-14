"""Tests for metrics."""

from ssim.metrics import (
    MetricManager,
    MetricTimeAccumulator,
    Metric,
    ImprovementType
)


def test_manager_to_dicts():
    mgr = MetricManager()
    metrics = [("a", Metric(0.1, 1.0, ImprovementType.SeekValue)),
               ("b", Metric(0.2, 2.0, ImprovementType.SeekValue)),
               ("c", Metric(0.3, 3.0, ImprovementType.SeekValue))]
    expected = [{"name": "a", "limit": 0.1, "objective": 1.0},
                {"name": "b", "limit": 0.2, "objective": 2.0},
                {"name": "c", "limit": 0.3, "objective": 3.0}]
    for name, metric in metrics:
        mgr.add_accumulator(name, MetricTimeAccumulator(metric))
    dicts = mgr.to_dicts()
    assert sorted(dicts, key=lambda d: d["name"]) == expected
