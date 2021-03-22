"""Tests for ssim.opendss"""
import os.path
from pathlib import Path
import pytest
import opendssdirect as dssdirect
from ssim import opendss, dssutil


@pytest.fixture(scope='function')
def data_dir(request):
    return Path(
        os.path.abspath(os.path.dirname(request.module.__file__))) / "data"


@pytest.fixture(scope='function')
def test_circuit(data_dir):
    yield opendss.DSSModel(data_dir / "test_circuit.dss")
    dssutil.run_command("clear")


@pytest.fixture(scope='function')
def wind_data(data_dir):
    """Loadshape data used for the wind generator."""
    with open(data_dir / "ZavWind.csv") as f:
        return list(float(x) for x in f)


def test_set_loadshape_class(test_circuit):
    test_circuit.loadshapeclass = opendss.LoadShapeClass.DAILY
    assert test_circuit.loadshapeclass == opendss.LoadShapeClass.DAILY
    test_circuit.loadshapeclass = opendss.LoadShapeClass.YEARLY
    assert test_circuit.loadshapeclass == opendss.LoadShapeClass.YEARLY


def test_loadshape_changes(test_circuit, wind_data):
    normalized_wind = list(map(lambda x: x / max(wind_data), wind_data))
    test_circuit.solve(3600.0)
    dssdirect.Generators.Name('gen1')
    assert (8000 * normalized_wind[3600 % 2400]
            == pytest.approx(dssdirect.Generators.kW(), abs=5.0))
    active_power, reactive_power = test_circuit.total_power()
    test_circuit.solve(10*3600.0)  # hour 10
    assert (8000 * normalized_wind[(10 * 3600) % 2400]
            == pytest.approx(dssdirect.Generators.kW(), abs=5.0))
    active_power_ten, reactive_power_ten = test_circuit.total_power()
    assert active_power_ten != active_power
    assert reactive_power_ten != reactive_power


def test_DSSModel_node_voltage(test_circuit):
    test_circuit.solve(0)
    voltage = test_circuit.node_voltage('loadbus1.1')
    test_circuit.solve(10*3600)
    assert voltage != pytest.approx(test_circuit.node_voltage('loadbus1.1'))


def test_DSSModel_storage(test_circuit):
    test_circuit.add_storage(
        "TestStorage",
        "loadbus1",
        3,
        {"kwhrated": 5000, "kwrated": 1000, "kv": 12.47},
        initial_soc=0.5,
        state=opendss.StorageState.DISCHARGING
    )
    test_circuit.update_storage("TestStorage", 0.0, 0)
    test_circuit.solve(0)
    kw, kvar = test_circuit.total_power()
    test_circuit.update_storage("TestStorage", 1000, 0)
    test_circuit.solve(0)
    new_kw, _ = test_circuit.total_power()
    assert 900 < (new_kw - kw) < 1100
    test_circuit.update_storage("TestStorage", -1000, 0)
    test_circuit.solve(0)
    new_kw, _ = test_circuit.total_power()
    assert 900 < (kw - new_kw) < 1100


def test_DSSModel_add_pvsystem(test_circuit, data_dir):
    test_circuit.add_loadshape(
        "TestProfile", data_dir / "triangle.csv", 1.0, 24)
    test_circuit.add_pvsystem(
        "TestPV", "loadbus1", 3, 12.47, 12.0, "",
        1000.0, 12.0, 27, 1.0, "TestProfile"
    )
    test_circuit.solve(0)
    dssdirect.PVsystems.Name("TestPV")
    assert dssdirect.PVsystems.kW() == pytest.approx(0.0)
    test_circuit.solve(3600 * 12)
    assert dssdirect.PVsystems.kW() == pytest.approx(12)


def test_DSSModel_add_xycurve(test_circuit):
    with pytest.raises(
            ValueError,
            match="`x_values` and `y_values` must be the same length"):
        test_circuit.add_xycurve("TestXY", [0, 0.5, 1.0], [1.0, 1.5])
    test_circuit.add_xycurve("TestXY", [0, 0.5, 1.0], [1.0, 1.5, 2.0])
    dssdirect.XYCurves.Name("TestXY")
    assert dssdirect.XYCurves.Npts() == 3
    assert dssdirect.XYCurves.XArray() == [0, 0.5, 1.0]
    assert dssdirect.XYCurves.YArray() == [1.0, 1.5, 2.0]
