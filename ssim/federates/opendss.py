"""Federate for OpenDSS grid simulation."""
import logging
import math
from os import PathLike

import opendssdirect as dssdirect
from helics import (
    HelicsValueFederate,
    HelicsDataType,
    helicsCreateFederateInfo,
    helicsCreateValueFederate
)

from ssim import dssutil
from ssim.opendss import Storage
from ssim.storage import StorageState


class OpenDSS:
    """Federate state.

    Parameters
    ----------
    federate : HelicsFederate
    dss_file : PathLike
        Path the the opendss file specifying the circuit.
    """
    def __init__(self, federate: HelicsValueFederate, dss_file: PathLike):
        self._federate = federate
        self._dss_file = dss_file
        self._storage_devices = {}
        self._storage_subs = {}
        self._voltage_pubs = {}
        dssutil.load_model(dss_file)
        dssutil.run_command("set mode=time loadshapeclass=daily")
        self._total_power_pub = self._federate.register_publication(
            "total_power",
            HelicsDataType.COMPLEX,
            units="W"
        )
        self._load_multiplier_sub = self._federate.register_subscription(
            "load_multiplier",
        )

    def add_storage(self, storage_device):
        name = storage_device.name
        bus = storage_device.bus
        logging.debug(f"adding storage device {name} at {bus}.")
        self._storage_devices[name] = storage_device
        self._voltage_pubs[bus] = self._federate.register_publication(
            f"voltage.{bus}",
            HelicsDataType.DOUBLE,
            units="pu"
        )
        logging.debug(f"storage device {name} - voltage publication created: "
                      f"{self._voltage_pubs[bus]}")
        self._storage_subs[name] = {
            'power': self._federate.register_subscription(
                f"{name}/power", "kW"
            ),
            'state': self._federate.register_subscription(f"{name}/state")
        }

    def _update_loads(self):
        """Update the load multiplier if it has changed."""
        if self._load_multiplier_sub.is_updated():
            dssdirect.Solution.LoadMult(self._load_multiplier_sub.double)

    def _update_storage(self):
        for device, subs in self._storage_subs.items():
            if subs['power'].is_updated():
                logging.debug(f"power updated: {subs['power'].complex}")
                self._storage_devices[device].set_power(
                    subs['power'].complex.real,
                    subs['power'].complex.imag
                )
            if subs['state'].is_updated():
                logging.debug(f"state updated: {subs['state'].string} "
                              f"@ {subs['state'].get_last_update_time()}")
                self._storage_devices[device].set_state(
                    StorageState(subs['state'].string)
                )

    def _publish_power(self):
        active_power, reactive_power = dssdirect.Circuit.TotalPower()
        self._total_power_pub.publish(complex(active_power, reactive_power))

    def _publish_node_voltages(self):
        node_voltages = dict(zip(dssdirect.Circuit.AllNodeNames(),
                                 dssdirect.Circuit.AllBusMagPu()))
        for device in self._storage_devices.values():
            dssdirect.Circuit.SetActiveBus(device.bus)
            self._voltage_pubs[device.bus].publish(node_voltages[device.bus])

    def _set_time(self, time):
        """Update the time in OpenDSS.

        Parameters
        ----------
        time : float
            New time in seconds.
        """
        hours = math.floor(time) // 3600
        seconds = time - (hours * 3600)
        dssdirect.Solution.Hour(hours)
        dssdirect.Solution.Seconds(seconds)

    def step(self, time):
        """Step the opendss model to `time`.

        Parameters
        ----------
        time : float
            Time in seconds.
        """
        self._set_time(time)
        self._update_loads()
        self._update_storage()
        dssdirect.Solution.Solve()
        # ensure that monitors and controls are sampled
        dssdirect.Circuit.SaveSample()
        self._publish_power()
        self._publish_node_voltages()

    def wait(self):
        # requesting `helics_time_maxtime` causes the sim to hang, so we
        # request one less than the max. The idea is to be interrupted
        # when the loads or the storage device(s) change state.
        hour = dssdirect.Solution.Hour()
        next_time = hour * 3600 + dssdirect.Solution.Seconds()
        return self._federate.request_time(next_time)


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
    dss_federate = OpenDSS(federate, dss_file)
    storage_device = Storage(storage_name, storage_bus, storage_params,
                             state=StorageState.DISCHARGING)
    storage_device.set_power(kw=10, kvar=0.0)
    dss_federate.add_storage(storage_device)
    federate.enter_executing_mode()
    time = 0
    while time < 1000 * 3600:
        logging.debug("stepping grid model")
        dss_federate.step(time)
        time = dss_federate.wait()
        logging.debug(f"granted time {time}")
    federate.finalize()
