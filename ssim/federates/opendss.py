"""Federate for OpenDSS grid simulation."""
import argparse
import collections

from helics import (
    HelicsCombinationFederate, helics_time_maxtime,
    helicsFederateLogDebugMessage, HelicsLogLevel,
    helicsCreateCombinationFederateFromConfig
)

from ssim import reliability
from ssim.opendss import Storage, DSSModel


class ReliabilityInterface:
    """Wrapper around reliability endpoint.

    Handles event parsing and iteration.

    Parameters
    ----------
    federate : HelicsCombinationFederate
        Federate handle. Must have an endpoint named "reliability".
    """
    def __init__(self, federate):
        self.endpoint = federate.get_endpoint_by_name(
            "reliability"
        )

    @property
    def events(self):
        """An iterator over all pending reliability events."""
        while self.endpoint.has_message():
            message = self.endpoint.get_message()
            yield reliability.Event.from_json(message.data)


class StorageInterface:
    """Handle all publications related to a storage device.

    Parameters
    ----------
    federate :
        HELICS federate handle.
    device : Storage
        The storage device.
    """
    def __init__(self, federate, device):
        self.device = device
        self._federate = federate
        self._power_sub = federate.subscriptions[
            f"{device.name}/power"
        ]
        self._voltage_pub = federate.publications[
            f"grid/storage.{device.name}.voltage"
        ]
        self._soc_pub = federate.publications[
            f"grid/storage.{device.name}.soc"
        ]
        self._power_pub = federate.publications[
            f"grid/storage.{device.name}.power"
        ]

    def update(self):
        if self._power_sub.is_updated():
            self._federate.log_message(
                f"Updating {self.device.name} power @ "
                f"{self._power_sub.get_last_update_time()}: "
                f"{self._power_sub.complex}",
                HelicsLogLevel.TRACE
            )
            self.device.set_power(self._power_sub.complex.real,
                                  self._power_sub.complex.imag)

    def publish(self, voltage):
        self._voltage_pub.publish(voltage)
        self._soc_pub.publish(self.device.soc)
        self._power_pub.publish(
            complex(self.device.kw, self.device.kvar)
        )


class GridFederate:
    def __init__(self, federate: HelicsCombinationFederate, grid_file: str):
        helicsFederateLogDebugMessage(
            federate, f"initializing DSSModel with {grid_file}"
        )
        helicsFederateLogDebugMessage(
            federate, f"pulications: {federate.publications.keys()}"
        )
        self._grid_model = DSSModel.from_json(grid_file)
        self._federate = federate
        self._storage_interface = [
            StorageInterface(federate, device)
            for device in self._grid_model.storage_devices.values()
        ]
        self.voltage = collections.defaultdict(list)
        self._reliability = ReliabilityInterface(federate)

    def _update_storage(self):
        for storage in self._storage_interface:
            storage.update()

    def _publish(self):
        for storage in self._storage_interface:
            voltage = self._grid_model.positive_sequence_voltage(
                storage.device.bus
            )
            self.voltage[storage.device.bus].append(voltage)
            storage.publish(voltage)
        self._federate.publications['grid/total_power'].publish(
            complex(*self._grid_model.total_power())
        )

    def _apply_reliability_event(self, event: reliability.Event):
        """Apply a reliability event to the grid model."""
        if event.type is reliability.EventType.FAIL:
            self._grid_model.fail_line(
                event.element,
                terminal=event.data.get("terminal", 1),
                how=event.mode
            )
        else:
            self._grid_model.restore_line(
                event.element,
                terminal=event.data.get("terminal", 1),
                how=event.mode
            )

    def _update_reliability(self):
        for event in self._reliability.events:
            self._apply_reliability_event(event)

    def step(self, time: float):
        """Step the opendss model to `time`.

        Parameters
        ----------
        time : float
            Time in seconds.
        """
        self._federate.log_message(
            f"granted time: {time}", HelicsLogLevel.INTERFACES)
        self._update_reliability()
        self._update_storage()
        self._grid_model.solve(time)
        self._publish()

    def run(self, hours: float):
        """Run the simulation for `hours`."""
        current_time = self._grid_model.last_update() or 0
        while current_time < hours * 3600:
            current_time = self._federate.request_time(
                self._grid_model.next_update()
            )
            self.step(current_time)


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "grid_config",
        type=str,
        help="path to JSON file specifying the grid configuration"
    )
    parser.add_argument(
        "federate_config",
        type=str,
        help="path to federate config file"
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=helics_time_maxtime,
        help="how many hours the simulation will run"
    )
    args = parser.parse_args()
    federate = helicsCreateCombinationFederateFromConfig(args.federate_config)
    helicsFederateLogDebugMessage(
        federate, f"Federate created: publications: {federate.publications}")
    helicsFederateLogDebugMessage(
        federate, f"Federate created: subscriptions: {federate.subscriptions}")
    helicsFederateLogDebugMessage(
        federate, f"Federate created: endpoints: {federate.endpoints}")
    grid_federate = GridFederate(federate, args.grid_config)
    helicsFederateLogDebugMessage(federate, "Model initialized")
    federate.enter_executing_mode()
    grid_federate.run(args.hours)
    federate.finalize()
