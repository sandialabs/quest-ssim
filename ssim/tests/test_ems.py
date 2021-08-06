"""Tests for EMS components."""
from pathlib import Path

import pytest
from ssim import ems, grid


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
                assert {'gen1'} == set(grid_model.connected_generators(component))
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
