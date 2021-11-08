"""Tests for EMS components."""
from pathlib import Path

import pytest
from ssim import ems, grid, reliability


@pytest.fixture
def gridspec(request):
    return grid.GridSpecification(
        Path(request.fspath.dirname) / "data" / "test_circuit.dss"
    )


@pytest.fixture
def grid_model(gridspec):
    """Network model of a grid with 4 busses."""
    return ems.GridModel(gridspec)


@pytest.fixture
def all_busses():
    return {
        'subbus', 'regbus', 'sourcebus',
        'loadbus1', 'loadbus2', 'loadbus3'
    }


def test_node_to_bus_mapping(grid_model):
    expected_nodes = {
        'subbus', 'regbus', 'sourcebus',
        'loadbus1', 'loadbus2', 'loadbus3'
    }
    assert grid_model.num_components == 1
    component, = grid_model.components()
    assert component == expected_nodes


def test_component_sets(grid_model):
    component, = grid_model.components()
    assert {'gen1'} == set(grid_model.connected_generators(component))
    for cut in {'line.line3', 'transformer.reg1'}:
        grid_model.disable_edge(cut)
        for component in grid_model.components():
            if 'regbus' in component:
                generators = grid_model.connected_generators(component)
                assert {'gen1'} == set(generators)
            else:
                assert set() == set(grid_model.connected_generators(component))
        grid_model.enable_edge(cut)
    component, = grid_model.components()
    assert {'gen1'} == set(grid_model.connected_generators(component))


def test_disable_generator(grid_model, all_busses):
    grid_model.disable_element('Generator.gen1')
    assert 'gen1' not in grid_model.connected_generators(all_busses)
    grid_model.enable_element('generator.gen1')
    assert 'gen1' in grid_model.connected_generators(all_busses)


def test_enable_non_existing_generator(grid_model, all_busses):
    with pytest.raises(KeyError):
        grid_model.disable_element("generator.fake")
    assert {'gen1'} == set(grid_model.connected_generators(all_busses))
    with pytest.raises(KeyError):
        grid_model.enable_element("generator.fake")
    assert {'gen1'} == set(grid_model.connected_generators(all_busses))


def test_apply_reliability_events(grid_model):
    line2_failure = reliability.Event(
        reliability.EventType.FAIL,
        reliability.Mode.OPEN,
        "line.line2"
    )
    line3_failure = reliability.Event(
        reliability.EventType.FAIL,
        reliability.Mode.OPEN,
        "line.line3"
    )
    gen1_failure = reliability.Event(
        reliability.EventType.FAIL,
        reliability.Mode.CLOSED,
        "generator.gen1"
    )
    repair_line2 = reliability.Event(
        reliability.EventType.RESTORE,
        reliability.Mode.CLOSED,
        "line.line2"
    )
    repair_line3 = reliability.Event(
        reliability.EventType.RESTORE,
        reliability.Mode.CLOSED,
        "line.line3"
    )
    repair_gen1 = reliability.Event(
        reliability.EventType.RESTORE,
        reliability.Mode.CLOSED,
        "generator.gen1"
    )
    grid_model.apply_reliability_events(
        [line2_failure, line3_failure, gen1_failure]
    )
    assert grid_model.num_components == 3
    grid_model.apply_reliability_events(
        [repair_gen1]
    )
    assert grid_model.num_components == 3
    for component in grid_model.components():
        if "regbus" in component:
            generators = set(grid_model.connected_generators(component))
            assert "gen1" in generators
    grid_model.apply_reliability_events(
        [repair_line2, repair_line3]
    )
    assert grid_model.num_components == 1


def test_connected_loads(grid_model):
    """Loads are added to the grid model."""
    component = next(grid_model.components())
    assert {'load1', 'load2'} == set(grid_model.connected_loads(component))


@pytest.mark.parametrize("element", ["load.load1", "generator.gen1",
                                     "pvsystem.pv1", "storage.ess1"])
def test_component_from_element(gridspec, element):
    gridspec.add_pvsystem(
        grid.PVSpecification(
            "pv1",
            "loadbus2",
            160.0,
            150.0
        )
    )
    gridspec.add_storage(
        grid.StorageSpecification(
            "ESS1",
            "loadbus2",
            250.0,
            150.0,
            "external"
        )
    )
    grid_model = ems.GridModel(gridspec)
    component = next(grid_model.components())
    assert grid_model.component_from_element(element) == component


def test_generator_control_message():
    message = ems.GeneratorControlMessage("on")
    message = ems.GeneratorControlMessage("off")
    message = ems.GeneratorControlMessage("setpoint", kw=100.0)
    assert message.kw == 100.0
    assert message.kvar == 0.0
    message = ems.GeneratorControlMessage("setpoint", kvar=100.0)
    assert message.kw == 0.0
    assert message.kvar == 100.0
    message = ems.GeneratorControlMessage("setpoint", kw=10.0, kvar=-1.5)
    assert message.kw == 10.0
    assert message.kvar == -1.5


@pytest.mark.parametrize("action", ["on", "off"])
@pytest.mark.parametrize("kw,kvar", [(x, y)
                                     for x in [100.0, None]
                                     for y in [100.0, None]
                                     if x is not None or y is not None])
def test_generator_control_message_invalid(action, kw, kvar):
    with pytest.raises(ValueError):
        ems.GeneratorControlMessage(action, kw, kvar)


@pytest.mark.parametrize("action", ["on", "off", "setpoint"])
def test_generator_control_to_from_json(action):
    message = ems.GeneratorControlMessage(action)
    message2 = ems.GeneratorControlMessage.from_json(message.to_json())
    assert message.action == message2.action
    if action == "setpoint":
        assert message2.kw == 0.0
        assert message2.kvar == 0.0
        message = ems.GeneratorControlMessage(action, kw=100.0, kvar=-120.0)
        message2 = ems.GeneratorControlMessage.from_json(message.to_json())
        assert message2.action == action
        assert message2.kw == 100.0
        assert message2.kvar == -120.0
    else:
        assert message2.kw == None
        assert message2.kvar == None
