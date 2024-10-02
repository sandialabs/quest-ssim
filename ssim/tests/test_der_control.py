from ssim.ui import StorageControl


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
