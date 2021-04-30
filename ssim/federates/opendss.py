"""Federate for OpenDSS grid simulation."""
import logging

from helics import (
    HelicsDataType,
    HelicsFederateInfo,
    helicsCreateCombinationFederate,
    HelicsCombinationFederate
)

from ssim import reliability
from ssim.grid import GridSpecification
from ssim.opendss import Storage, DSSModel


class GridFederate:
    """Federate state.

    Has a HELICS federate, a grid model (:py:class:`~ssim.opendss.DSSModel`),
    and a storage device (:py:class:`~ssim.opendss.Storge`).

    Parameters
    ----------
    federate : HelicsFederate
        The HELICS federate handle.
    model : DSSModel
        The grid model.
    """
    def __init__(self, federate: HelicsCombinationFederate, model: DSSModel):
        self._federate = federate
        self._storage_subs = {}
        self._voltage_pubs = {}
        self._power_pubs = {}
        self._soc_pubs = {}
        self._storage_devices = {}
        self._grid_model = model
        self._total_power_pub = self._federate.register_publication(
            "total_power",
            HelicsDataType.COMPLEX,
            units="kW"
        )
        self._configure_storage()
        self._reliability_endpoint = self._federate.register_endpoint(
            "reliability"
        )

    def _configure_storage(self):
        """Configure publications and subscriptions for a storage deveice."""
        for storage_device in self._grid_model.storage_devices.values():
            self._configure_storage_inputs(storage_device)
            self._configure_storage_outputs(storage_device)
            self._storage_devices[storage_device.name] = storage_device

    def _configure_storage_inputs(self, device: Storage):
        """Configure the HELICS inputs for the storage device."""
        self._storage_subs[device.name] = {
            'power': self._federate.register_subscription(
                f"storage.{device.name}.power",
                "kW"
            )
        }

    def _configure_storage_outputs(self, device: Storage):
        """Configure HELICS publications for the storage device."""
        self._voltage_pubs[device.bus] = self._federate.register_publication(
            f"voltage.{device.bus}",
            HelicsDataType.DOUBLE,
            units="pu"
        )
        self._power_pubs[device.name] = self._federate.register_publication(
            f"power.{device.name}",
            HelicsDataType.COMPLEX,
            units="kW"
        )
        self._soc_pubs[device.name] = self._federate.register_publication(
            f"soc.{device.name}",
            HelicsDataType.DOUBLE,
            units=""
        )

    def _update_storage(self):
        for device, subs in self._storage_subs.items():
            if subs['power'].is_updated():
                logging.debug(f"power updated: {subs['power'].complex}")
                self._storage_devices[device].set_power(
                    subs['power'].complex.real,
                    subs['power'].complex.imag
                )

    def _publish_power(self):
        active_power, reactive_power = self._grid_model.total_power()
        self._total_power_pub.publish(complex(active_power, reactive_power))

    def _publish_node_voltages(self):
        for device in self._storage_devices.values():
            self._voltage_pubs[device.bus].publish(
                self._grid_model.positive_sequence_voltage(device.bus)
            )

    def _publish_storage_state(self):
        """Publish power and state of charge for each storage device."""
        for name, device in self._grid_model.storage_devices.items():
            self._power_pubs[name].publish(
                complex(device.kw, device.kvar)
            )
            self._soc_pubs[name].publish(
                device.soc
            )

    def _apply_reliability_event(self, event: reliability.Event):
        """Apply a reliability event to the grid model."""
        if event.type is reliability.EventType.FAIL:
            self._grid_model.fail_line(
                event.element,
                terminal=event.data.get("terminal", 1),
                how=str(event.mode)
            )
        else:
            self._grid_model.restore_line(
                event.element,
                terminal=event.data.get("terminal", 1),
                how=str(event.mode)
            )

    def _update_reliability(self):
        """Update failed/restored components.

        Processes messages received at the "reliability" endpoint.
        Each message contains the name of a circuit element and whether
        it is to be failed or restored along with the state to put the
        element in (open/closed/current).
        """
        while self._reliability_endpoint.n_pending_messages > 0:
            message = self._reliability_endpoint.get_message()
            self._apply_reliability_event(
                 reliability.Event.from_json(message.data)
            )

    def step(self, time: float):
        """Step the opendss model to `time`.

        Parameters
        ----------
        time : float
            Time in seconds.
        """
        self._update_storage()
        self._update_reliability()
        self._grid_model.solve(time)
        self._publish_power()
        self._publish_node_voltages()
        self._publish_storage_state()

    def run(self, hours: float):
        """Run the simulation for `hours`."""
        current_time = self._grid_model.last_update() or 0
        while current_time < hours * 3600:
            current_time = self._federate.request_time(
                self._grid_model.next_update()
            )
            self.step(current_time)


def run_federate(name: str,
                 fedinfo: HelicsFederateInfo,
                 grid: GridSpecification,
                 hours: float):
    """Run the grid federate.

    Parameters
    ----------
    name : str
        Federate name
    fedinfo : HelicsFederateInfo
        Federate info structure to use when initializing the federate.
    grid : GridSpecification
        Grid specification to use when building the grid model.
    hours : float
        How many hours to run.
    """
    federate = helicsCreateCombinationFederate(name, fedinfo)
    model = DSSModel.from_grid_spec(grid)
    grid_federate = GridFederate(federate, model)
    federate.enter_executing_mode()
    grid_federate.run(hours)
    federate.finalize()
