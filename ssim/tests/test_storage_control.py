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
        soc=0.45
    )


def test_DroopController_missing_params():
    spec = StorageSpecification(
        'foo',
        'bus.bar',
        10,
        2.5,
        'droop',
        controller_params={'foo': 1}
    )
    message = "Missing required parameter '(q_droop|p_droop)' in " \
              r"controller_params for device 'foo'\. Both 'p_droop' and " \
              r"'q_droop' are required for the 'droop' controller\. " \
              r"Got params: \{('.*',?)*\}\."
    with pytest.raises(ValueError, match=message):
        storage.DroopController(spec)
    spec.controller_params['p_droop'] = 100
    with pytest.raises(ValueError, match=message):
        storage.DroopController(spec)
    del spec.controller_params['p_droop']
    spec.controller_params['q_droop'] = 10
    with pytest.raises(ValueError, match=message):
        storage.DroopController(spec)
    spec.controller_params['p_droop'] = 100
    spec.controller_params['q_droop'] = 10
    storage.DroopController(spec)


def test_DroopConrtoller_step(droop_spec):
    controller = storage.DroopController(droop_spec)
    assert controller.step(1, 1.0) == complex(0, 0)
    assert controller.step(1, 0.0) == complex(5000, -500)


def test_storage__init_controller(droop_spec, cycle_spec):
    controller = storage._init_controller(droop_spec)
    assert isinstance(controller, storage.DroopController)
    controller = storage._init_controller(cycle_spec)
    assert isinstance(controller, storage.CycleController)
