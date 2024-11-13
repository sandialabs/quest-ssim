"""Federate for OpenDSS grid simulation."""
import argparse
import csv
from pathlib import Path

from helics import (
    HelicsCombinationFederate, helics_time_maxtime,
    helicsFederateLogDebugMessage, HelicsLogLevel,
    helicsCreateCombinationFederateFromConfig, HelicsDataType
)

from ssim import reliability
from ssim.grid import GridSpecification, PVStatus, BusVoltageStatus
from ssim.opendss import DSSModel
from ssim.ems import GeneratorControlMessage
from ssim.federates import timing


class EMSInterface:
    """Wrapper around HELICS endpoints for communication with an EMS.

    This wrapper masks whether or not an EMS exists and silently drops outgoing
    messages when there is no EMS present in the federation.

    """

    def __init__(self, federate: HelicsCombinationFederate, config: GridSpecification):
        self._federate = federate
        self._endpoints = {}
        self._control_endpoint = None
        if config.ems is not None:
            self._control_endpoint = "ems/control"

    def register_endpoint(self, endpoint: str, isglobal: bool = True):
        """Attempt to register `endpoint` if the EMS is running."""
        if self._control_endpoint is None:
            return
        if isglobal:
            self._endpoints[endpoint] = self._federate.register_global_endpoint(
                endpoint
            )
        else:
            self._endpoints[endpoint] = self._federate.register_endpoint(endpoint)

    def send(self, message: str, source: str, dest: str = "ems/control"):
        """Send a message to 'ems/control'.

        Parameters
        ----------
        message : str
            The message to be sent.
        source : str
            The name of the source endpoint used to send the message.
        dest : str, default "ems/control"
            The name of the destination endpoint for the message.
        """
        if source in self._endpoints:
            self._endpoints[source].send_data(message, destination=dest)

    def receive(self, endpoint: str):
        """Get all messages available on `endpoint`."""
        if endpoint not in self._endpoins:
            return
        ep = self._endpoints[endpoint]
        while ep.has_message():
            yield ep.get_message()


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

    @property
    def events(self):
        """An iterator over all pending reliability events."""
        while self.endpoint.has_message():
            message = self.endpoint.get_message()
            yield reliability.Event.from_json(message.data)


class GeneratorInterface:
    """HELICS interface for generators connected to the grid.

    Parameters
    ----------
    federate : HelicsCombinationFederate
    generator : opendss.Generator
    ems : EMSInterface
    """

    def __init__(self, federate, generator, ems: EMSInterface):
        self._federate = federate
        self._ems = ems
        self.generator = generator
        self._ems.register_endpoint(
            f"generator.{generator.name.lower()}.control"
        )
        self.reliability_endpoint = federate.get_endpoint_by_name(
            "reliability")

    def update(self):
        """Update inputs for the generator."""
        for message in self._ems.receive(
                f"generator.{self.generator.name.lower()}.control"
        ):
            gen_control = GeneratorControlMessage.from_json(message.data)
            if gen_control.action == "on":
                self.generator.turn_on()
            elif gen_control.action == "off":
                self.generator.turn_off()
            else:
                self.generator.change_setpoint(
                    gen_control.kw, gen_control.kvar)

    def publish(self):
        status_json = self.generator.status.to_json()
        self._ems.send(status_json, f"generator.{self.generator.name.lower()}.control")
        self.reliability_endpoint.send_data(
            status_json, destination="reliability/reliability"
        )


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
        self._power_sub = federate.register_subscription(
            f"{device.name}/power", units="kW"
        )
        self._power_sub.set_default(complex(0.0, 0.0))
        self._voltage_pub = federate.register_publication(
            f"storage.{device.name}.voltage",
            kind=HelicsDataType.DOUBLE,
            units="pu"
        )
        self._soc_pub = federate.register_publication(
            f"storage.{device.name}.soc",
            kind=HelicsDataType.DOUBLE,
            units=""
        )
        self._power_pub = federate.register_publication(
            f"storage.{device.name}.power",
            kind=HelicsDataType.COMPLEX,
            units="kW"
        )

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


class PVInterface:
    """Manager for the output to other federates related to PV Systems

    Parameters
    ----------
    federate : HelicsFederate
        HELICS federate handle.
    pvsystem : PVSystem
        PVSystem instance providing access to the opendss model.
    ems : EMSInterface
        Interface for the HELICS connection to the ems federate.
    """
    def __init__(self, federate, pvsystem, ems):
        self._federate = federate
        self._system = pvsystem
        self._ems = ems
        self._ems.register_endpoint(f"pvsystem.{pvsystem.name}.control")

    def update(self):
        """Update PVSystem model in response to federate input.

        Since PVSystems are not dispatchable this does nothing; however,
        in the future it could be used to support curtailment or other
        operations managed by the EMS.
        """
        pass

    def publish(self):
        """Send message to the EMS with the current status of the PV system.

        Current real and reactive power are reported to the EMS.
        """
        status = PVStatus(
            self._system.name,
            self._system.kw,
            self._system.kvar
        )
        self._ems.send(
            status.to_json(), f"pvsystem.{self._system.name.lower()}.control"
        )


class EventLog:
    """A record of all events that have occured."""
    def __init__(self):
        self._events = []

    def add_event(self, time, event):
        """Add an event to the event log.

        Parameters
        ----------
        time : float
            Time at which the event occured.
        event : reliability.Event
            The reliability event.
        """
        self._events.append(
            (time, event.type.value, event.element, event.mode.value)
        )

    def to_csv(self, output_dir=None):
        """Save the event log to a file in `output_dir`.

        Parameters
        ---------
        output_dir : PathLike, optional
            The directory to save the output file in. If not
            specified, the current directory is used.
        """
        if output_dir is None:
            output_dir = Path(".")
        with open(output_dir / "event_log.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(("time", "type", "element", "connection"))
            writer.writerows(self._events)


class LoadInterface:
    """Manager for output to other federates related to loads.

    Parameters
    ----------
    federate : HelicsFederate
        HELICS federate handle.
    """
    def __init__(self, federate, model, ems):
        self._federate = federate
        self._ems = ems
        self._ems.register_endpoint("load.control")
        self._model = model

    def update(self):
        """Update the loads in response to input.

        Loads do not currently respond to input, so this method does
        nothing.
        """
        pass

    def _send_to_ems(self, status):
        self._ems.send(status.to_json(), "load.control")

    def publish(self):
        """Send status updates to the EMS federate control endpoint"""
        pass
        # TODO the performance of both _send_to_ems() and Load.status is
        #      too poor to use. Since we aren't using the EMS right now
        #      we don't actually need to send these messages
        # for load in self._model.loads():
        #     self._send_to_ems(load.status)


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
        g_spec = GridSpecification.from_json(grid_file)
        self._grid_model = DSSModel.from_grid_spec(g_spec)
        self.busses_to_measure = set(bus["name"] for bus in g_spec.busses_to_measure)
        ems = EMSInterface(federate, g_spec)
        self._federate = federate
        self._storage_interface = [
            StorageInterface(federate, device)
            for device in self._grid_model.storage_devices.values()
        ]
        self._event_log = EventLog()
        self._pv_interface = [
            PVInterface(federate, device, ems)
            for device in self._grid_model.pvsystems.values()
        ]
        self._reliability = ReliabilityInterface(federate)
        self._load_interface = LoadInterface(federate, self._grid_model, ems)
        self._generator_interface = [
            GeneratorInterface(federate, generator, ems)
            for generator in self._grid_model.generators.values()
        ]
        self.metrics_endpoint = federate.get_endpoint_by_name(
            "metrics"
        )

    def _update_storage(self):
        for storage in self._storage_interface:
            storage.update()

    def _update_bus_voltages(self, time: float):
        for bus_name in self.busses_to_measure:
            voltage = self._grid_model.mean_node_voltage(bus_name)
            message = BusVoltageStatus(bus_name, voltage, time)
            self.metrics_endpoint.send_data(
                message.to_json(), destination="metrics"
            )

    def _publish(self):
        for storage in self._storage_interface:
            voltage = self._grid_model.mean_node_voltage(
                storage.device.bus
            )
            storage.publish(voltage)
        for generator in self._generator_interface:
            generator.publish()
        for pvsystem in self._pv_interface:
            pvsystem.publish()
        self._load_interface.publish()
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

    def _update_reliability(self, time):
        for event in self._reliability.events:
            self._event_log.add_event(time, event)
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
        self._update_reliability(time)
        self._update_storage()
        self._grid_model.solve(time)
        self._grid_model.record_state()
        self._update_bus_voltages(time)
        self._publish()

    def run(self, hours: float):
        """Run the simulation for `hours`."""
        schedule = timing.schedule(
            self._federate,
            self._grid_model.next_update,
            hours * 3600
        )
        for current_time in schedule:
            self.step(current_time)

    def finalize(self):
        """Clean up the grid state and save output files."""
        self._grid_model.save_record()
        self._event_log.to_csv()


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
    grid_federate.finalize()
    federate.disconnect()
