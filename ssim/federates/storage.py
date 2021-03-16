"""Storage device federate"""
import logging

from helics import (
    HelicsValueFederate,
    HelicsDataType,
    helicsCreateFederateInfo, helicsCreateValueFederate
)

from ssim.storage import StorageState


class IdealStorageModel:
    """Model of an idea storage device.

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
        self._charging_power = -kw_rated
        self._discharging_power = kw_rated

    @property
    def complex_power(self):
        return complex(self.power, 0.0)

    def time_to_change(self):
        """Return how long until the device changes state. [hours]"""
        logging.debug(f"getting time to charge: state={self.state}")
        if self.state is StorageState.CHARGING:
            charge_remaining = self._kwh_rated * (1.0 - self._soc)
            time_remaining = charge_remaining / abs(self.power)
            logging.info(f"CHARGING: charge_remaining={charge_remaining} kWh, "
                         f"time_remaining={time_remaining} h")
            return time_remaining
        elif self.state is StorageState.DISCHARGING:
            capacity_remaining = self._kwh_rated * (self._soc - self._soc_min)
            time_remaining = capacity_remaining / abs(self.power)
            logging.info(f"DISCHARGING: "
                         f"capacity_remaining={capacity_remaining} kWh, "
                         f"time_remaining={time_remaining} h")
            return time_remaining
        return 0.0001

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

    def step(self, delta_t):
        """Advance the model `delta_t` hours.

        Parameters
        ----------
        delta_t : float
            Time to advance [hours]

        Returns
        -------
        float
            Hours until the battery must change state (i.e. until it is
            full or depleted).
        """
        if self.state is StorageState.IDLE:
            if self._soc <= self._soc_min:
                self.state = StorageState.CHARGING
                self.power = self._charging_power
            else:
                self.state = StorageState.CHARGING
                self.power = self._discharging_power
        elif self.state is StorageState.CHARGING:
            self._step_charging(delta_t)
        elif self.state is StorageState.DISCHARGING:
            self._step_discharging(delta_t)


class StorageFederate:
    """Simple storage device federate.

    Has a kWh rating and a maximum kW rating. Currently there
    are no losses modeled (100% efficiency).
    """
    def __init__(self, federate: HelicsValueFederate,
                 storage_model: IdealStorageModel):
        self._model = storage_model
        self._power_pub = federate.register_publication(
            "power",
            HelicsDataType.COMPLEX,
            units="kW"
        )
        self._state_pub = federate.register_publication(
            "state",
            HelicsDataType.STRING
        )
        self._federate = federate
        logging.debug("federate initialized")

    def step(self, time):
        """Step the federate.

        Parameters
        ----------
        time : float
            Current time in seconds.
        """
        logging.debug(f"stepping @ {time}")
        granted_time = self._federate.request_time_advance(
            self._model.time_to_change() * 3600
        )
        state = self._model.state
        self._model.step((granted_time - time) / 3600)
        if self._model.state is not state:
            logging.debug(f"state: {self._model.state}")
            self._state_pub.publish(str(self._model.state))
            self._power_pub.publish(self._model.complex_power)
        return granted_time


def run_storage_federate(storage_name, kwh_rated, kw_rated, loglevel):
    logging.basicConfig(format="[storage] %(levelname)s - %(message)s",
                        level=loglevel)
    fedinfo = helicsCreateFederateInfo()
    fedinfo.core_name = storage_name
    fedinfo.core_type = "zmq"
    fedinfo.core_init = "-f1"
    federate = helicsCreateValueFederate(storage_name, fedinfo)
    storage = StorageFederate(
        federate, IdealStorageModel(kwh_rated, kw_rated)
    )
    time = 0
    logging.debug("entering executing mode")
    federate.enter_executing_mode()
    logging.debug("in executing mode")
    while time < 1000 * 3600:
        time = storage.step(time)
    logging.debug("finalizing")
    federate.finalize()
    logging.debug("done")
