import pytest

import tomli

from ssim.ui import StorageControl


_TOML = r"""
[storage-options."S814"]
required = true
min_soc = 0.2
max_soc = 0.8
initial_soc = 0.5
busses = ['814']
power = [200.0, 500.0, 400.0, 300.0]
duration = [2.0, 3.0, 4.0]

[storage-options."S814".control-params]
mode = 'voltwatt'

[storage-options."S814".control-params.droop]
"p_droop" = 10000.0
"q_droop" = -5000.0

[storage-options."S814".control-params.voltvar]
"volts" = [0.5, 0.95, 1.0, 1.05, 1.5]
"vars" = [1.0, 1.0, 0.0, -1.0, -1.0]

[storage-options."S814".control-params.voltwatt]
"volts" = [0.5, 0.925, 0.95, 1.0, 1.05, 1.5]
"watts" = [1.0, 0.625, 1.0, 0.0, -1.0, -1.0]

[storage-options."S814".control-params.varwatt]
"vars" = [0.5, 0.95, 1.0, 1.05, 1.5]
"watts" = [1.0, 1.0, 0.0, -1.0, -1.0]

[storage-options."S814".control-params.vv_vw]
"vv_volts" = [0.5, 0.95, 1.0, 1.05, 1.5]
"vv_vars" = [1.0, 1.0, 0.0, -1.0, -1.0]
"vw_volts" = [0.5, 0.95, 1.0, 1.05, 1.5]
"vw_watts" = [1.0, 1.0, 0.0, -1.0, -1.0]

[storage-options."S814".control-params.constantpf]
"pf_val" = 0.99
"""


@pytest.fixture
def s814_dict():
    d = tomli.loads(_TOML)
    return d["storage-options"]["S814"]


@pytest.fixture
def s814_control(s814_dict):
    sc = StorageControl("droop")
    sc.read_toml(s814_dict["control-params"])
    return sc


def test_StorageContro_read_toml(s814_control, s814_dict):
    assert s814_dict["control-params"]["mode"] == "voltwatt"
    assert s814_control.mode == "voltwatt"
    assert s814_control.params["voltwatt"] == s814_dict["control-params"]["voltwatt"]


def test_StorageControl_get_invcontrol(s814_control):
    ic = s814_control.get_invcontrol("S814")
    assert list(der.lower() for der in ic.der_list) == ["storage.s814"]
    assert ic.inv_control_mode == "voltwatt"
    # TODO check params


def test_StorageControl_is_external():
    sc = StorageControl("droop")
    assert sc.is_external
    sc = StorageControl("voltvar")
    assert not sc.is_external


def test_StorageControl_ensure_param_droop():
    sc = StorageControl("droop")
    assert "droop" not in sc.params
    # ensure_param() adds specific parameters
    sc.ensure_param("droop", "q_droop")
    assert sc.params["droop"]["q_droop"] == -300.0
    assert "p_droop" not in sc.params["droop"]
    # ensure_param() adds missing parameters
    sc.ensure_param("droop")
    assert sc.params["droop"]["p_droop"] == 500.0
    assert sc.params["droop"]["q_droop"] == -300.0
    # ensuer_param() does not overwrite existing parameters
    sc.params["droop"]["p_droop"] = 600.0
    sc.params["droop"]["q_droop"] = -700.0
    sc.ensure_param("droop")
    assert sc.params["droop"]["p_droop"] == 600.0
    assert sc.params["droop"]["q_droop"] == -700.0
    # ensure_param() adds all parameters
    sc = StorageControl("droop")
    sc.ensure_param("droop")
    assert sc.params["droop"]["p_droop"] == 500.0
    assert sc.params["droop"]["q_droop"] == -300.0


def test_StorageControl_ensure_param_inverter():
    sc = StorageControl("voltvar")
    sc.ensure_param("voltvar")
    params = sc.params["voltvar"].keys()
    assert set(params) == {"volts", "vars"}
    sc.mode = "voltwatt"
    sc.ensure_param("voltwatt")
    params = sc.params["voltwatt"].keys()
    assert set(params) == {"volts", "watts"}
    assert set(sc.params.keys()) == {"voltvar", "voltwatt"}


def test_StorageControl_mixed_params():
    # controller containing params for both droop and inverter controls
    sc = StorageControl("voltvar")
    sc.ensure_param("voltvar")
    params = sc.params["voltvar"].keys()
    assert set(params) == {"volts", "vars"}
    sc.mode = "voltwatt"
    sc.ensure_param("voltwatt")
    params = sc.params["voltwatt"].keys()
    sc.mode = "droop"
    sc.ensure_param("droop")
    assert set(sc.params.keys()) == {"droop", "voltvar", "voltwatt"}


def test_StorageControl_ensure_param_different_mode():
    sc = StorageControl("droop")
    sc.ensure_param("voltvar")
    params = sc.params["voltvar"].keys()
    assert set(params) == {"volts", "vars"}
    assert sc.mode == "droop"


def test_StorageControl_validate():
    sc = StorageControl("droop")
    assert (sc.validate() == "Missing parameters: p_droop, q_droop"
            or sc.validate() == "Missing parameters: q_droop, p_droop")
    sc.ensure_param("droop", "p_droop")
    assert sc.validate() == "Missing parameters: q_droop"
    sc.params["droop"]["q_droop"] = 12345.0
    assert sc.validate() is None
    sc.mode = "voltvar"
    assert sc.validate() is not None
    sc.ensure_param("voltvar")
    assert sc.validate() is None
