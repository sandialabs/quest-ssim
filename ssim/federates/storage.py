"""Storage device federate"""
from abc import ABC, abstractmethod
import logging
from typing import Dict, List

from helics import (
    HelicsValueFederate,
    HelicsDataType,
    helics_time_maxtime,
    helicsInputSetOption,
    helics_handle_option_only_update_on_change,
    helicsInputSetMinimumChange,
    HelicsFederateInfo,
    helicsFederateInfoSetTimeProperty,
    helics_property_time_delta,
    helicsCreateValueFederate
)

from ssim.grid import StorageSpecification
from ssim.storage import StorageState


class StorageController(ABC):
    """Base class for storage controllers."""
    @abstractmethod
    def step(self, time: float, voltage: float) -> complex:
        """Step the model to `time`.

        Parameters
        ----------
        time : float
            Current time in seconds.
        voltage : float
            Voltage at the bus where the device is connected. [pu]

        Returns
        -------
        complex
            Active and reactive power as a complex number. [kW]
        """

    @abstractmethod
    def next_update(self) -> float:
        """Return the time of the next controller action in seconds."""


class DroopController(StorageController):
    """Storage droop control.

    Parameters
    ----------
    device : StorageSpecification
        Specification of the storge device being controlled.
    """
    def __init__(self, device: StorageSpecification):
        self._reference_voltage = device.controller_params.get(
            'reference_voltage', 1.0
        )
        if 'p_droop' not in device.controller_params:
            raise ValueError(self._missing_param_message('p_droop', device))
        if 'q_droop' not in device.controller_params:
            raise ValueError(self._missing_param_message('q_droop', device))
        self._p_droop = device.controller_params['p_droop']
        self._q_droop = device.controller_params['q_droop']

    @staticmethod
    def _missing_param_message(param, device):
        return f"Missing required parameter '{param}' in " \
               f"controller_params for device '{device.name}'. " \
               "Both 'p_droop' and 'q_droop' are required for " \
               "the 'droop' controller. " \
               f"Got params: {set(device.controller_params.keys())}."

    def step(self, time, voltage):
        p = (self._reference_voltage - voltage) * self._p_droop
        q = (self._reference_voltage - voltage) * self._q_droop
        return complex(p, q)

    def next_update(self) -> float:
        # only changes state when the voltage changes.
        return helics_time_maxtime - 1


class IdealStorageModel(StorageController):
    """A device that cycles between charging and discharging.

    The device is 100% efficient and has linear charging
    and discharging profiles.

    Parameters
    ----------
    kwh_rated : float
        Capacity of the device. [kWh]
    kw_rated : float
        Maximum power rating of the device. Used for both charging and
        discharging. [kW]
    initial_soc : float, optional
        Initial state of charge as a float between 0 and 1.
    soc_min : float, default 0.2
        Minimum state of charge for normal operation. Float between 0 and 1.
    """
    def __init__(self, kwh_rated: float, kw_rated: float,
                 initial_soc: float = None, soc_min: float = 0.2):
        if initial_soc is not None and 1 < initial_soc < 0:
            raise ValueError(f"`initial_soc` must be between 0 and 1"
                             f" (got {initial_soc})")
        if 1 < soc_min < 0:
            raise ValueError(f"`soc_min` must be between 0 and 1"
                             f" (got {soc_min})")
        self._kwh_rated = kwh_rated
        if initial_soc is None:
            self._soc = soc_min
        else:
            self._soc = initial_soc
        self._soc_min = soc_min
        self.state = StorageState.IDLE
        self.power = 0.0
        self._last_step = 0.0
        self._charging_power = -kw_rated
        self._discharging_power = kw_rated

    @property
    def complex_power(self):
        return complex(self.power, 0.0)

    def next_update(self) -> float:
        logging.debug(f"getting time to charge: state={self.state}")
        if self.state is StorageState.CHARGING:
            charge_remaining = self._kwh_rated * (1.0 - self._soc)
            time_remaining = charge_remaining / abs(self.power)
            logging.info(f"CHARGING: charge_remaining={charge_remaining} kWh, "
                         f"time_remaining={time_remaining} h")
            return self._last_step + time_remaining * 3600
        if self.state is StorageState.DISCHARGING:
            capacity_remaining = self._kwh_rated * (self._soc - self._soc_min)
            time_remaining = capacity_remaining / abs(self.power)
            logging.info(f"DISCHARGING: "
                         f"capacity_remaining={capacity_remaining} kWh, "
                         f"time_remaining={time_remaining} h")
            return self._last_step + time_remaining * 3600
        return 1.0

    def _step_charging(self, delta_t_hours):
        previous_charge = self._soc * self._kwh_rated
        charged_power = abs(self.power) * delta_t_hours
        new_charge = previous_charge + charged_power
        self._soc = new_charge / self._kwh_rated
        if self._soc >= 1.0:
            logging.info(f"battery fully charged (soc={self._soc})")
            self.state = StorageState.DISCHARGING
            self.power = self._discharging_power

    def _step_discharging(self, delta_t_hours):
        previous_charge = self._soc * self._kwh_rated
        discharged_power = abs(self.power) * delta_t_hours
        new_charge = previous_charge - discharged_power
        self._soc = new_charge / self._kwh_rated
        if self._soc <= self._soc_min:
            logging.info(f"battery exhausted (soc={self._soc})")
            self.state = StorageState.CHARGING
            self.power = self._charging_power

    def step(self, time, voltage):
        if self.state is StorageState.IDLE:
            if self._soc <= self._soc_min:
                self.state = StorageState.CHARGING
                self.power = self._charging_power
            else:
                self.state = StorageState.CHARGING
                self.power = self._discharging_power
        elif self.state is StorageState.CHARGING:
            self._step_charging((time - self._last_step) / 3600)
        elif self.state is StorageState.DISCHARGING:
            self._step_discharging((time - self._last_step) / 3600)
        self._last_step = time
        return self.complex_power


class StorageControllerFederate:
    """A federate that controls storage devices.

    This federate manages the state of one or more storage devices.
    Each device is identified by name and has a :py:class:`StorageController`
    associated with it. When HELICS grants the federate a time, it will
    call :py:meth:`StorageController.step` on each controller. The next time
    requested by the federate is the minimum time returned by
    :py:meth:`StorageController.next_update` from all controllers.
    """
    def __init__(self, federate: HelicsValueFederate,
                 devices: Dict[str, StorageController],
                 busses: Dict[str, str]):
        self._storage_devices = devices
        self._power_pubs = {
            device: federate.register_global_publication(
                f"storage.{device}.power",
                HelicsDataType.COMPLEX,
                units="kW"
            )
            for device in devices
        }
        self._voltage_subs = {
            device: federate.register_subscription(
                f"grid/voltage.{bus}"
            )
            for device, bus in busses.items()
        }
        # Only update the voltage values if they have changed significantly.
        # This prevents us from getting stuck iterating at very small time
        # steps because of meaningless variation in the output of the power
        # flow calculation.
        for sub in self._voltage_subs.values():
            helicsInputSetOption(
                sub,
                helics_handle_option_only_update_on_change,
                True
            )
            helicsInputSetMinimumChange(sub, 1e-8)
        self._federate = federate
        logging.debug("federate initialized")

    def _next_update(self):
        """Return the time of the next update."""
        return min(
            controller.next_update()
            for controller in self._storage_devices.values()
        )

    def _step(self, time: float):
        """Advance the controllers to `time`.

        Parameters
        ----------
        time : float
            Current time in seconds.
        """
        for device, controller in self._storage_devices.items():
            # Only update the controllers if the voltage has changed
            # or the time of the next update has arrived.
            if not (self._voltage_subs[device].is_updated()
                    or time >= controller.next_update()):
                continue
            voltage = self._voltage_subs[device].double
            power = controller.step(time, voltage)
            logging.info("updating device %s: voltage=%s power=%s",
                         device, voltage, power)
            self._power_pubs[device].publish(power)

    def run(self, hours: float):
        """Step the federate.

        Parameters
        ----------
        hours : float
            Number of hours to run.
        """
        time = 0
        while time < hours * 3600:
            time = self._federate.request_time(self._next_update())
            logging.debug("granted time %s", time)
            self._step(time)


def _init_controller(device: StorageSpecification):
    """Initialize a controller for `device`."""
    if device.controller == 'droop':
        return DroopController(device)
    if device.controller == 'cycle':
        return IdealStorageModel(device.kwh_rated, device.kw_rated)


def run_federate(name: str,
                 fedinfo: HelicsFederateInfo,
                 devices: List[StorageSpecification],
                 hours: float):
    """Run `federate` as a storage control federate.

    Parameters
    ----------
    name : str
        Federate name
    fedinfo : HelicsFederateInfo
        Federate info structure to use for initializing the federate.
    devices : List[StorageSpecification]
        Storage devices that are controlled by this federate.
    hours : float
        Number of hours to run before exiting.
    """
    helicsFederateInfoSetTimeProperty(
        fedinfo, helics_property_time_delta, 0.01
    )
    federate = helicsCreateValueFederate(name, fedinfo)
    controllers = {device.name: _init_controller(device)
                   for device in devices}
    busses = {device.name: device.bus for device in devices}
    logging.debug("devices: %s", busses.items())
    storage_controller = StorageControllerFederate(
        federate,
        controllers,
        busses
    )
    logging.debug("entering executing mode")
    federate.enter_executing_mode()
    logging.debug("running...")
    storage_controller.run(hours)
    logging.debug("finalizing")
    federate.finalize()
    logging.debug("exiting")
