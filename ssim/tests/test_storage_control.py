"""Tests for storage controllers."""
import pytest
from ssim.federates import storage
from ssim.grid import StorageSpecification


@pytest.fixture
def droop_spec():
    return StorageSpecification(
        name='foo',
        bus='bar',
        kwh_rated=100,
        kw_rated=10,
        controller='droop',
        controller_params={'p_droop': 5000, 'q_droop': -500}
    )


@pytest.fixture
def cycle_spec():
    return StorageSpecification(
        name='foo',
        bus='bar',
        kwh_rated=100,
        kw_rated=10,
        controller='cycle',
        soc=1.0
    )


def test_DroopConrtoller_step(droop_spec):
    controller = storage.DroopController(
        droop_spec.controller_params['p_droop'],
        droop_spec.controller_params['q_droop'],
        droop_spec
        )
    assert controller.step(1, 1.0, 0.5) == complex(0, 0)
    assert controller.step(1, 0.0, 0.5) == complex(5000, -500)


def test_storage__init_controller(droop_spec, cycle_spec):
    controller = storage._get_controller(droop_spec)
    assert isinstance(controller, storage.DroopController)
    controller = storage._get_controller(cycle_spec)
    assert isinstance(controller, storage.CycleController)


def test_CycleController_step(cycle_spec):
    controller = storage.CycleController(cycle_spec)
    assert controller.step(0.0, 1.0, 1.0) == complex(10, 0)
    assert controller.step(1.0, 1.0, 0.5) == complex(10, 0)
    assert controller.step(8.0 * 3600, 1.0, 0.2) == complex(-10, 0)
    assert controller.step(9.0 * 3600, 1.0, 0.9) == complex(-10, 0)
