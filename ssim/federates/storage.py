import json
from abc import ABC, abstractmethod
import argparse
from typing import Optional, Iterable
import math

from helics import (
    helics_time_maxtime,
    HelicsLogLevel,
    helicsCreateCombinationFederateFromConfig
)

from ssim import ems
from ssim import grid
from ssim.grid import GridSpecification
from ssim.federates import timing


class StorageController(ABC):
    """Base class for storage controllers."""
    @abstractmethod
    def step(self,
             time: float,
             voltage: float,
             soc: float) -> Optional[complex]:
        """Return the target power output of the storage device.

        Parameters
        ----------
        time : float
            Current time in seconds.
        voltage : float
            Voltage at the bus where the device is connected. [pu]
        soc : float
            State of charge of the storage device as a fraction of its total
            capacity.
        """

    @abstractmethod
    def apply_control(self, control_messages: Iterable[bytes]):
        """Apply external control actions (i.e. from the EMS).

        Parameters
        ----------
        control_messages : Iterable[bytes]
            Iterator over all pending control messages.
        """
        for message in control_messages:
            json.loads(message)

    @abstractmethod
    def next_update(self):
        """Returns the next time the storage controller needs to be updated."""


class DroopController(StorageController):
    """Simple droop controller"""
    def __init__(self, p_droop, q_droop, device: grid.StorageSpecification, voltage_tolerance=1.0e-3):
        self._voltage_tolerance = voltage_tolerance
        self.p_droop = p_droop
        self.q_droop = q_droop
        self._last_voltage = 0.0
        self.device = device

    def step(self,
             time: float,
             voltage: float,
             soc: float) -> Optional[complex]:
        if abs(self._last_voltage - voltage) > self._voltage_tolerance:
            voltage_error = 1.0 - voltage
            power = complex(voltage_error * self.p_droop,
                            voltage_error * self.q_droop)
            self._last_voltage = voltage
            return self._limit(power)

    def _limit(self, power):
        # XXX should probably be limited to the kva rating of the device.
        ## TO DO: incorporated p-priority and q-priority modes
        if power.real < 0.0 and power.imag < 0.0:
            # both p and q are negative
            limit_p = min(abs(power.real), self.device.kw_rated)
            limit_q = min(abs(power.imag), self.device.kw_rated)
            return complex(-limit_p, -limit_q)
        elif power.real < 0.0 and power.imag >= 0.0:
            limit_p = min(abs(power.real), self.device.kw_rated)
            limit_q = min(abs(power.imag), self.device.kw_rated)
            return complex(-limit_p, limit_q)
        elif power.real >= 0.0 and power.imag < 0.0:
            limit_p = min(abs(power.real), self.device.kw_rated)
            limit_q = min(abs(power.imag), self.device.kw_rated)
            return complex(limit_p, -limit_q)
    
        return complex(min(power.real, self.device.kw_rated), 
                       min(power.imag, self.device.kw_rated))
    
    def apply_control(self, control_messages: Iterable[dict]):
        # DroopController does not respond to control messages.
        pass

    def next_update(self):
        return math.inf


def pending_messages(endpoint):
    """Iterator over all pending messages received at `endpoint`.

    The iterator yields the raw data from the message, it is not parsed
    or processed.

    Parameters
    ----------
    endpoint : HelicsEndpoint
        The endpoint to receive from.
    """
    while endpoint.has_message():
        message = endpoint.get_message()
        yield message.data


def _send_soc_to_ems(soc, time, federate):
    """Send a message to the ems/control endpoint with the current SOC.

    Parameters
    ----------
    soc : float
        Current state of charge.
    time : float
        Time the message is being sent. [seconds]
    federate : HelicsFederate
        Federate handle to send the message from. Must have a registered
        endpoint named "control".
    """
    endpoint_name = f"storage.{federate.name.lower()}.control"
    endpoint = federate.get_endpoint_by_name(endpoint_name)
    message = endpoint.create_message()
    message.destination = "ems/control"
    message.original_source = endpoint_name
    message.source = endpoint_name
    message.data = grid.StorageStatus(federate.name, soc).to_json()
    message.time = time
    endpoint.send_data(message)


def _controller(federate, controller, hours):
    """Main loop for the storage controller federate.

    Parameters
    ----------
    federate : HelicsFederate
        HELICS federate handle for the controller.
    controller : StorageController
        Controller instance.
    hours : float
        How long to run the controller.
    """
    federate.log_message(f"storage starting ({hours})", HelicsLogLevel.TRACE)
    control_endpoint = federate.endpoints.get(
        f"storage.{federate.name.lower()}.control"
    )
    schedule = timing.schedule(federate, controller.next_update, hours * 3600)
    for time in schedule:
        voltage = federate.subscriptions[
            f"grid/storage.{federate.name}.voltage"
        ].double
        soc = federate.subscriptions[
            f"grid/storage.{federate.name}.soc"
        ].double
        federate.log_message(f"voltage: {voltage}", HelicsLogLevel.TRACE)
        federate.log_message(f"soc: {soc}", HelicsLogLevel.TRACE)
        pending = []
        if control_endpoint is not None:
            pending = pending_messages(control_endpoint)
        controller.apply_control(pending)
        power = controller.step(time, voltage, soc)
        if power is not None:
            federate.log_message(
                f"publishing new power @ {time}: {power}",
                HelicsLogLevel.TRACE
            )
            federate.publications[f"{federate.name}/power"].publish(power)
        if control_endpoint is not None:
            _send_soc_to_ems(soc, time, federate)


class CycleController(StorageController):
    """Operate a device by cycling between charging and discharging.

    Parameters
    ----------
    device : StorageSpecification
        Device that is being controlled.
    """
    def __init__(self, device):
        self.power = device.kw_rated
        self.capacity = device.kwh_rated
        self.soc = device.soc
        self.state = 'charging' if self.soc < 0.95 else 'discharging'
        self.time = 0

    def step(self,
             time: float,
             voltage: float,
             soc: float) -> Optional[complex]:
        self.time = 0
        self.soc = soc
        if self.soc > 0.95:
            self.state = 'discharging'
        if self.soc <= 0.21:
            self.state = 'charging'
        if self.state == 'discharging':
            return complex(self.power, 0)
        return complex(-self.power, 0)

    def apply_control(self, control_messages: Iterable[dict]):
        # Cycle controller does not respond to control messages.
        pass

    def next_update(self):
        return helics_time_maxtime


class ExternalController(StorageController):
    """Controller for a storage device that is dispatched by an external EMS.

    Parameters
    ----------
    device : grid.StorageSpecification
        Specification of the device being controlled.
    """
    def __init__(self, device):
        self.time = 0
        self.power = complex(0.0, 0.0)
        self.soc = device.soc
        self.updated = True

    def _apply_control(self, control):
        if control.action == "charge":
            self.power = complex(-control.real_power, control.reactive_power)
        elif control.action == "discharge":
            self.power = complex(control.real_power, control.reactive_power)
        elif control.action == "idle":
            self.power = complex(0.0, 0.0)
        else:
            raise ValueError(f"Unknown control action: '{control.action}'")

    def apply_control(self, control_messages: Iterable[bytes]):
        self.updated = False
        for message in control_messages:
            self._apply_control(ems.StorageControlMessage.from_json(message))
            self.updated = True

    def step(self,
             time: float,
             voltage: float,
             soc: float) -> Optional[complex]:
        self.time = time
        self.soc = soc
        if self.updated:
            return self.power
        return None

    def next_update(self):
        # What is the right interval to report the SOC to the EMS?
        return self.time + 300


class NoController(StorageController):
    """Controller that does nothing."""

    def step(self, time, voltage, soc):
        pass

    def apply_control(self, control_messages):
        pass

    def next_update(self):
        return helics_time_maxtime


def _get_controller(device):
    """Return a StorageController for `device`.

    Parameters
    ----------
    device : StorageSpecification
        Specification of the storage device. A controller is constructed
        based on ``device.controller`` and ``device.controller_params``.

    Returns
    -------
    StorageController
        A controller for the device.
    """
    if device.controller == 'cycle':
        return CycleController(device)
    if device.controller == 'droop':
        return DroopController(device=device, **device.controller_params)
    if device.controller == 'external':
        return ExternalController(device)
    if device.controller is None:
        return NoController()
    else:
        raise ValueError(f"Unknown controller: '{device.controller}'")


def _add_subscriptions(name, config):
    config["subscriptions"].extend(
        [{"key": f"grid/storage.{name}.soc",
          "unit": "",
          "type": "double",
          "default": 0.5},
         {"key": f"grid/storage.{name}.voltage",
          "unit": "pu",
          "type": "double",
          "default": 1.0}]
    )


def _complete_config(name, skeleton):
    with open(skeleton) as f:
        config = json.load(f)
        config['name'] = name
        config['core'] = f"{name}_core"
        _add_subscriptions(name, config)
        return json.dumps(config)


def _start_controller(name, federate_config_skeleton, grid_config, hours):
    federate_config = _complete_config(name, federate_config_skeleton)
    print(f"federate config: {federate_config}")
    federate = helicsCreateCombinationFederateFromConfig(federate_config)
    spec = GridSpecification.from_json(grid_config)
    device = spec.get_storage_by_name(federate.name)
    federate.log_message(f"loaded device: {device}", HelicsLogLevel.TRACE)
    controller = _get_controller(device)
    if isinstance(controller, ExternalController):
        federate.register_global_endpoint(
            f"storage.{federate.name.lower()}.control"
        )
    federate.enter_executing_mode()
    _controller(federate, controller, hours)
    federate.disconnect()


def run():
    parser = argparse.ArgumentParser(
        description="HELICS federate for a storage controller."
    )
    parser.add_argument(
        "name",
        type=str,
        help="Name of the storage device controlled by this federate."
    )
    parser.add_argument(
        "grid_config",
        type=str,
        help="path to the grid configuration JSON "
             "(used to look up storage controller parameters)"
    )
    parser.add_argument(
        "federate_config",
        type=str,
        help="path to federate config file"
    )
    parser.add_argument(
        "--hours",
        dest='hours',
        type=float,
        default=helics_time_maxtime
    )
    args = parser.parse_args()
    _start_controller(
        args.name, args.federate_config, args.grid_config, args.hours
    )
