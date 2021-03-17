"""Federate for OpenDSS grid simulation."""
import logging
from os import PathLike

from helics import (
    HelicsValueFederate,
    HelicsDataType,
    helicsCreateFederateInfo,
    helicsCreateValueFederate
)

from ssim.opendss import Storage, DSSModel
from ssim.storage import StorageState


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
    def __init__(self, federate: HelicsValueFederate, model: DSSModel):
        self._federate = federate
        self._storage_subs = {}
        self._voltage_pubs = {}
        self._storage_devices = {}
        self._grid_model = model
        self._total_power_pub = self._federate.register_publication(
            "total_power",
            HelicsDataType.COMPLEX,
            units="W"
        )
        self._load_multiplier_sub = self._federate.register_subscription(
            "load_multiplier",
        )
        self._configure_storage()

    def _configure_storage(self):
        """Configure publications and subscriptions for a storage deveice."""
        for storage_device in self._grid_model.storage_devices:
            self._configure_storage_inputs(storage_device)
            self._configure_storage_outputs(storage_device)
            self._storage_devices[storage_device.name] = storage_device

    def _configure_storage_inputs(self, device: Storage):
        """Configure the HELICS inputs for the storage device."""
        self._storage_subs[device.name] = {
            'power': self._federate.register_subscription(
                f"{device.name}/power", "kW"
            )
        }

    def _configure_storage_outputs(self, device: Storage):
        """Configure HELICS publications for the storage device."""
        self._voltage_pubs[device.bus] = self._federate.register_publication(
            f"voltage.{device.bus}",
            HelicsDataType.DOUBLE,
            units="pu"
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
                self._grid_model.node_voltage(device.bus)
            )

    def step(self, time: float):
        """Step the opendss model to `time`.

        Parameters
        ----------
        time : float
            Time in seconds.
        """
        self._update_storage()
        self._grid_model.solve(time)
        self._publish_power()
        self._publish_node_voltages()

    def run(self, hours: float):
        """Run the simulation for `hours`."""
        current_time = self._grid_model.last_update() or 0
        while current_time < hours * 3600:
            current_time = self._federate.request_time(
                self._grid_model.next_update()
            )
            self.step(current_time)


def run_opendss_federate(dss_file, storage_name, storage_bus, storage_params,
                         loglevel=logging.INFO):
    """Start the OpenDSS federate.

    Parameters
    ----------
    dss_file : PathLike
        Name of the OpenDSS file containing the circuit definition.
    storage_name : str
        Name of a storage device connected to the simulation.
    storage_bus : str
        Name of the bus where the storage device is connected.
    storage_params : dict
        Storage device parameters.
    """
    logging.basicConfig(format="[OpenDSS] %(levelname)s - %(message)s",
                        level=loglevel)
    logging.info("starting federate")
    logging.info(f"  {dss_file}")
    logging.info(f"  {storage_name}")
    logging.info(f"  {storage_bus}")
    logging.info(f"  {storage_params}")
    fedinfo = helicsCreateFederateInfo()
    fedinfo.core_name = "grid"
    fedinfo.core_type = "zmq"
    fedinfo.core_init = "-f1"
    logging.debug(f"federate info: {fedinfo}")

    federate = helicsCreateValueFederate("grid", fedinfo)
    logging.debug("federate created")

    model = DSSModel(dss_file)
    storage_device = model.add_storage(
        storage_name, storage_bus, 3, storage_params,
        StorageState.DISCHARGING, initial_soc=0.5
    )
    storage_device.set_power(kw=10, kvar=0.0)
    grid_federate = GridFederate(federate, model)
    federate.enter_executing_mode()
    grid_federate.run(1000)
    federate.finalize()
