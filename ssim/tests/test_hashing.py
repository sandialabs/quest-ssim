import pytest

from ssim.ui.core import Project, StorageControl, StorageOptions

from ssim.metrics import (
    MetricManager,
    MetricTimeAccumulator,
    Metric,
    ImprovementType
)

def test_Project_hash():
    p = Project("test")

    metrics = [("a", Metric(0.1, 1.9, 1.0, ImprovementType.SeekValue)),
               ("b", Metric(0.2, 2.8, 2.0, ImprovementType.SeekValue)),
               ("c", Metric(0.3, 4.7, 3.0, ImprovementType.SeekValue))]

    for name, metric in metrics:
        p.add_metric("bus voltage", name, metric)

    storage_controls = [
        StorageControl("droop", StorageControl._DEFAULT_PARAMS["droop"]),
        StorageControl("voltvar", StorageControl._DEFAULT_PARAMS["voltvar"]),
        StorageControl("varwatt", StorageControl._DEFAULT_PARAMS["varwatt"])
        ]

    storage_options = [
        StorageOptions("so1", 3, [], [], []),
        StorageOptions("so2", 2, [], [], []),
        StorageOptions("so3", 1, [], [], [])
        ]

    for i in range(len(storage_options)):
        storage_options[i].control = storage_controls[i]

    for so in storage_options:
        p.add_storage_option(so)
    
    assert hash(p.get_metric_manager("bus voltage")) == 1422217286034778408
    assert hash(storage_options[0]) == 1703104687242851934
    assert hash(p) == 1827343610290675985
