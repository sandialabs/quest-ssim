"""Federate for OpenDSS grid simulation."""
import argparse
import logging

from helics import (
    HelicsCombinationFederate, helics_time_maxtime,
    helicsFederateLogDebugMessage, HelicsLogLevel,
    helicsCreateCombinationFederateFromConfig
)

from ssim import reliability
from ssim.grid import GridSpecification
from ssim.opendss import DSSModel


class ReliabilityInterface:
    """Wrapper around the HELICS endpoint for reliability.

    Handles the interaction with the "reliability" endpoint, including
    iteration over all pending receives and parsing messages into reliability
    events.

    Parameters
    ----------
    federate : HelicsCombinationFederate
        Federate handle. Must have an endpoint named "reliability".
    """
    def __init__(self, federate):
        self.endpoint = federate.get_endpoint_by_name(
            "reliability"
        )
        self._federate = federate

    def update_generators(self, generators):
        """Send updated GeneratorStatus messages to the reliability federate.

        These messages include the cumulative number of hours the generator
        has been running which can be used to update the reliability model for
        each individual generator.

        Messages are sent from the "grid/reliability" endpoint to the
        "reliability/reliability" endpoint.
        """
        for generator in generators:
            self._federate.log_message(f"updating generator {generator.name}:"
                                       f" {generator.status}",
                                       logging.DEBUG)
            self.endpoint.send_data(
                generator.status.to_json(), "reliability/reliability"
            )

    @property
    def events(self):
        """An iterator over all pending reliability events."""
        while self.endpoint.has_message():
            message = self.endpoint.get_message()
            yield reliability.Event.from_json(message.data)


class StorageInterface:
    """HELICS publications and subscriptions related to a storage device.

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
        """Update inputs for the storage device.

        If the power subscription has been updated then the device model
        is updated with the new power setting.
        """
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
        """Publish all values associated with the device."""
        self._voltage_pub.publish(voltage)
        self._soc_pub.publish(self.device.soc)
        self._power_pub.publish(
            complex(self.device.kw, self.device.kvar)
        )


class GridFederate:
    """Manage HELICS interfaces for reliability and storage devices.

    Parameters
    ----------
    federate : HelicsCombinationFederate
        HELICS federate handle. Assumed to already have the publications
        and subscriptions needed for the grid configuration specified in
        `grid_file`.
    grid_file : str
        Path to the JSON grid configuration file.
    """
    def __init__(self, federate: HelicsCombinationFederate, grid_file: str):
        helicsFederateLogDebugMessage(
            federate, f"initializing DSSModel with {grid_file}"
        )
        helicsFederateLogDebugMessage(
            federate, f"publications: {federate.publications.keys()}"
        )
        self._grid_model = DSSModel.from_grid_spec(
            GridSpecification.from_json(grid_file)
        )
        self._federate = federate
        self._storage_interface = [
            StorageInterface(federate, device)
            for device in self._grid_model.storage_devices.values()
        ]
        self._reliability = ReliabilityInterface(federate)

    def _update_storage(self):
        for storage in self._storage_interface:
            storage.update()

    def _publish(self):
        for storage in self._storage_interface:
            voltage = self._grid_model.positive_sequence_voltage(
                storage.device.bus
            )
            storage.publish(voltage)
        self._reliability.update_generators(
            self._grid_model.generators.values()
        )
        real, reactive = self._grid_model.total_power()
        self._federate.publications['grid/total_power'].publish(
            complex(real, reactive)
        )

    def _apply_failure(self, event):
        component_type, component_name = event.element.split(".")
        if component_type == "line":
            self._grid_model.fail_line(
                component_name,
                terminal=event.data.get("terminal", 1),
                how=event.mode
            )
        elif component_type == "generator":
            self._grid_model.fail_generator(component_name)

    def _apply_repair(self, event):
        component_type, component_name = event.element.split(".")
        if component_type == "line":
            self._grid_model.restore_line(
                component_name,
                terminal=event.data.get("terminal", 1),
                how=event.mode
            )
        elif component_type == "generator":
            self._grid_model.restore_generator(
                component_name,
                enable=event.data.get("enable", True)
            )

    def _apply_reliability_event(self, event: reliability.Event):
        """Apply a reliability event to the grid model."""
        if event.type is reliability.EventType.FAIL:
            self._apply_failure(event)
        else:
            self._apply_repair(event)

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
    """Federate entry point."""
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
