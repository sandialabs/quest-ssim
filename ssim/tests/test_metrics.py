"""Tests for metrics."""

from ssim.metrics import (
    MetricManager,
    MetricTimeAccumulator,
    Metric,
    ImprovementType
)


def test_manager_to_dicts():
    mgr = MetricManager()
    metrics = [("a", Metric(0.1, 1.9, 1.0, ImprovementType.SeekValue)),
               ("b", Metric(0.2, 2.8, 2.0, ImprovementType.SeekValue)),
               ("c", Metric(0.3, 4.7, 3.0, ImprovementType.SeekValue))]
    expected = [{"name": "a", "lower_limit": 0.1, "upper_limit": 1.9, "objective": 1.0},
                {"name": "b", "lower_limit": 0.2, "upper_limit": 2.8, "objective": 2.0},
                {"name": "c", "lower_limit": 0.3, "upper_limit": 4.7, "objective": 3.0}]
    for name, metric in metrics:
        mgr.add_accumulator(name, MetricTimeAccumulator(metric))
    dicts = mgr.to_dicts()
    assert sorted(dicts, key=lambda d: d["name"]) == expected
