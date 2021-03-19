from unittest import mock
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
