"""Storage device federate"""
from abc import ABC, abstractmethod
import logging

from helics import (
    HelicsValueFederate,
    HelicsDataType,
    helicsCreateFederateInfo,
    helicsCreateValueFederate
)

from ssim.storage import StorageState


class StorageController(ABC):
    """Base class for storage controllers."""
    @abstractmethod
    def step(self, time: float) -> complex:
        """Step the model to `time`.

        Parameters
        ----------
        time : float
            Current time in seconds.

        Returns
        -------
        complex
            Active and reactive power as a complex number. [kW]
        """

    @abstractmethod
    def next_update(self) -> float:
        """Return the time of the next controller action in seconds."""

    @property
    @abstractmethod
    def device_name(self) -> str:
        """The name of the device being controlled"""


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
    def __init__(self, name: str, kwh_rated: float, kw_rated: float,
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
        self._name = name
        self._charging_power = -kw_rated
        self._discharging_power = kw_rated

    @property
    def device_name(self):
        return self._name

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

    def step(self, time):
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
    """Simple storage device federate.

    Has a kWh rating and a maximum kW rating. Currently there
    are no losses modeled (100% efficiency).
    """
    def __init__(self, federate: HelicsValueFederate,
                 storage_model: StorageController):
        self._model = storage_model
        self._power_pub = federate.register_global_publication(
            f"storage.{storage_model.device_name}.power",
            HelicsDataType.COMPLEX,
            units="kW"
        )
        self._federate = federate
        logging.debug("federate initialized")

    def run(self, hours):
        """Step the federate.

        Parameters
        ----------
        hours : float
            Number of hours to run.
        """
        time = 0
        while time < hours * 3600:
            time = self._federate.request_time(self._model.next_update())
            power = self._model.step(time)
            self._power_pub.publish(power)


def run_storage_federate(storage_name, kwh_rated, kw_rated, loglevel):
    logging.basicConfig(format="[storage] %(levelname)s - %(message)s",
                        level=loglevel)
    fedinfo = helicsCreateFederateInfo()
    fedinfo.core_name = storage_name
    fedinfo.core_type = "zmq"
    fedinfo.core_init = "-f1"
    federate = helicsCreateValueFederate(storage_name, fedinfo)
    storage = StorageControllerFederate(
        federate, IdealStorageModel(storage_name, kwh_rated, kw_rated)
    )
    logging.debug("entering executing mode")
    federate.enter_executing_mode()
    logging.debug("in executing mode")
    storage.run(1000)
    logging.debug("finalizing")
    federate.finalize()
    logging.debug("done")
