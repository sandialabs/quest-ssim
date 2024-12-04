from unittest import mock
import hashlib
import pytest
import opendssdirect as dssdirect
import pandas as pd
from pandas.testing import assert_frame_equal
import ssim.dssutil as dssutil


@pytest.fixture
def simple_circuit():
    dssutil.run_command("clear")
    dssutil.run_command("new circuit.simple_circuit")
    dssutil.run_command("new line.line1 phases=3 bus1=sourcebus bus2=lb1")
    dssutil.run_command("new line.line2 phases=3 bus1=lb1 bus2=lb2")
    dssutil.run_command("new load.load1 bus1=lb1 kw=2.3 kvar=0 kv=0.240")
    dssutil.run_command("solve")
    yield
    dssutil.run_command("clear")


def test_missing_file():
    with pytest.raises(dssutil.OpenDSSError):
        dssutil.load_model("missing_file.dss")


@mock.patch('opendssdirect.run_command', return_value='oh no!')
def test_run_command_exception(mock_dssdirect_run_command):
    with pytest.raises(dssutil.OpenDSSError, match='oh no!'):
        dssutil.run_command('everything is fine.')
    with pytest.warns(UserWarning,
                      match="OpenDSS command returned error: 'oh no!'"):
        dssutil.run_command('nothing is okay.', warn=True)


def test_to_dataframe(simple_circuit):
    df = dssutil.to_dataframe(dssdirect.Loads, ("kW", "kvar", "kV"))
    assert_frame_equal(
        pd.DataFrame([(2.3, 0.0, 0.240)], index=["load1"],
                     columns=("kW", "kvar", "kV")),
        df
    )
    df = dssutil.to_dataframe(dssdirect.Lines)
    assert len(df) == 2
    assert "Bus1" in df.columns
    assert "Bus2" in df.columns
    assert "Phases" in df.columns
    assert (df["Phases"] == 3).all()
    assert "line1" in df.index
    assert "line2" in df.index


def test_open(simple_circuit):
    assert not dssdirect.CktElement.IsOpen(1, 1)
    dssutil.open_terminal("line.line1", 2)
    dssdirect.Circuit.SetActiveElement("line.line1")
    assert dssdirect.CktElement.IsOpen(2, 1)
    assert dssdirect.CktElement.IsOpen(2, 2)
    assert dssdirect.CktElement.IsOpen(2, 3)


def test_close(simple_circuit):
    dssutil.open_terminal("line.line2", 1, 1)
    dssdirect.Circuit.SetActiveElement("line.line2")
    assert dssdirect.CktElement.IsOpen(1, 1)
    dssutil.close_terminal("line.line2", 1, 1)
    dssdirect.Circuit.SetActiveElement("line.line2")
    assert not dssdirect.CktElement.IsOpen(1, 1)


def test_lock_unlock_switch(simple_circuit):
    dssutil.run_command("new swtcontrol.swc1"
                        " delay=0.0"
                        " normal=closed"
                        " SwitchedObj=line.line2"
                        " SwitchedTerm=1"
                        " enabled=y")
    dssutil.run_command("set mode=time stepsize=10s controlmode=time")
    dssdirect.Solution.SolvePlusControl()
    dssdirect.SwtControls.Name("swc1")
    dssdirect.SwtControls.Action(1)  # open the switch
    dssdirect.Solution.SolvePlusControl()
    dssdirect.Circuit.SetActiveElement("line.line2")
    assert dssdirect.CktElement.IsOpen(2, 1)
    dssutil.lock_switch_control("line.line2")
    dssdirect.SwtControls.Name("swc1")
    assert dssdirect.SwtControls.IsLocked()
    dssdirect.SwtControls.Action(2)
    dssdirect.Solution.SolvePlusControl()
    dssdirect.Circuit.SetActiveElement("line.line2")
    assert dssdirect.CktElement.IsOpen(2, 1)
    dssutil.unlock_switch_control("line.line2")
    dssdirect.Solution.SolvePlusControl()
    dssdirect.SwtControls.Name("swc1")
    state = dssdirect.SwtControls.State()
    assert not dssdirect.SwtControls.IsLocked()


@pytest.mark.parametrize("repeat", range(10))
def test_fingerprint(model_dir, grid_model_path, irradiance_path,
                     wind_path, tmp_path_factory, repeat):
    # compute hash directly from list of files
    DSS_FILES = sorted([
        "BusCoords.dss",
        "BusVoltageBases.DSS",
        "Capacitor.DSS",
        "CapControl.DSS",
        "Generator.DSS",
        "GrowthShape.DSS",
        "Line.DSS",
        "LineCode.DSS",
        "Load.DSS",
        "LoadShape.DSS",
        "Master.DSS",
        "RegControl.DSS",
        "Spectrum.DSS",
        "TCC_Curve.DSS",
        "Transformer.DSS",
        "Vsource.dss",
    ])
    DATA_FILES = [
        "irradiance.csv",
        "zavwind.csv",
    ]
    FILES = DSS_FILES + DATA_FILES
    export_dir = tmp_path_factory.mktemp("grid_export")
    h = hashlib.sha256()
    dssutil.run_command("clear")
    dssutil.load_model(grid_model_path)
    dssutil.export(model_dir, export_dir)
    for fname in FILES:
        p = export_dir / fname
        h.update(p.read_bytes())
    expected_hash = h.hexdigest()
    assert expected_hash == dssutil.fingerprint(export_dir)
    dssutil.run_command("clear")
