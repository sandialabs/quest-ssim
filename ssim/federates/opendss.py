"""Federate for OpenDSS grid simulation."""
import logging

from helics import (
    HelicsValueFederate,
    HelicsDataType,
    helicsCreateFederateInfo,
    helicsCreateValueFederate
)

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
    def __init__(self, federate: HelicsValueFederate, model: DSSModel):
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
                self._grid_model.positive_sequence_voltage(
                    device.bus.split('.')[0]
                )
            )

    def _publish_storage_state(self):
        """Publish power and state of charge for each storage device."""
        for device in self._grid_model.storage_devices:
            self._power_pubs[device.name].publish(
                complex(device.kw, device.kvar)
            )
            self._soc_pubs[device.name].publish(
                device.soc
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
        self._publish_storage_state()

    def run(self, hours: float):
        """Run the simulation for `hours`."""
        current_time = self._grid_model.last_update() or 0
        while current_time < hours * 3600:
            current_time = self._federate.request_time(
                self._grid_model.next_update()
            )
            self.step(current_time)


def run_opendss_federate(dss_file, storage_devices, hours,
                         loglevel=logging.INFO):
    """Start the OpenDSS federate.

    Parameters
    ----------
    dss_file : PathLike
        Name of the OpenDSS file containing the circuit definition.
    storage_devices : dict
        Dictionary keys are device names. Values are dictionaries with
        two keys: 'bus' (the bus where the device is connected), and
        'params' storage device parameters.
    hours : float
        Amount of time to simulate. [hours]
    loglevel : logging.Level
        Log level.
    """
    logging.basicConfig(format="[OpenDSS] %(levelname)s - %(message)s",
                        level=loglevel)
    logging.info("starting federate")
    logging.info(f"  {dss_file}")
    fedinfo = helicsCreateFederateInfo()
    fedinfo.core_name = "grid"
    fedinfo.core_type = "zmq"
    fedinfo.core_init = "-f1"
    logging.debug(f"federate info: {fedinfo}")

    federate = helicsCreateValueFederate("grid", fedinfo)
    logging.debug("federate created")

    model = DSSModel(dss_file)
    for name in storage_devices:
        model.add_storage(
            name, storage_devices[name]['bus'], 3,
            storage_devices[name]['params']
        )

    grid_federate = GridFederate(federate, model)
    federate.enter_executing_mode()
    grid_federate.run(hours)
    federate.finalize()
