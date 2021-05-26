from abc import ABC, abstractmethod
import argparse
from typing import Optional

from helics import (
    helicsCreateValueFederateFromConfig,
    helics_time_maxtime,
    HelicsLogLevel
)

from ssim.grid import GridSpecification


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
    def next_update(self):
        """Returns the next time the storage controller needs to be updated."""


class DroopController(StorageController):
    """Simple droop controller"""
    def __init__(self, p_droop, q_droop, voltage_tolerance=1.0e-3):
        self._voltage_tolerance = voltage_tolerance
        self.p_droop = p_droop
        self.q_droop = q_droop
        self._last_voltage = 0.0

    def step(self,
             time: float,
             voltage: float,
             soc: float) -> Optional[complex]:
        if abs(self._last_voltage - voltage) > self._voltage_tolerance:
            voltage_error = 1.0 - voltage
            power = complex(voltage_error * self.p_droop,
                            voltage_error * self.q_droop)
            self._last_voltage = voltage
            return power

    def next_update(self):
        return helics_time_maxtime


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
    time = federate.request_time(0)
    while time < (hours * 3600):
        federate.log_message(f"granted time: {time}", HelicsLogLevel.TRACE)
        voltage = federate.subscriptions[
            f"grid/storage.{federate.name}.voltage"
        ].double
        soc = federate.subscriptions[
            f"grid/storage.{federate.name}.soc"
        ].double
        federate.log_message(f"voltage: {voltage}", HelicsLogLevel.TRACE)
        federate.log_message(f"soc: {soc}", HelicsLogLevel.TRACE)
        power = controller.step(time, voltage, soc)
        if power is not None:
            federate.log_message(
                f"publishing new power @ {time}: {power}",
                HelicsLogLevel.TRACE
            )
            federate.publications[f"{federate.name}/power"].publish(power)
        time = federate.request_time(controller.next_update())


def _start_controller(federate_config, grid_config, hours):
    federate = helicsCreateValueFederateFromConfig(federate_config)
    spec = GridSpecification.from_json(grid_config)
    device = spec.get_storage_by_name(federate.name)
    federate.log_message(f"loaded device: {device}", HelicsLogLevel.TRACE)
    # XXX assuming everything is using a droop controller.
    controller = DroopController(
        device.controller_params['p_droop'],
        device.controller_params['q_droop']
    )
    federate.enter_executing_mode()
    _controller(federate, controller, hours)
    federate.finalize()


def run():
    parser = argparse.ArgumentParser(
        description="HELICS federate for a storage controller."
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
        args.federate_config, args.grid_config, args.hours
    )
