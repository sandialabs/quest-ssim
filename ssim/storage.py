"""API for storage devices."""
from abc import ABC, abstractmethod
import enum


@enum.unique
class StorageState(enum.Enum):
    """Enumeration of the states a storage device can be in."""
    #: Device is in the charging state.
    CHARGING = "charging"
    #: Device is in the discharging state.
    DISCHARGING = "discharging"
    #: Device is neither charging nor discharging.
    IDLE = "idling"

    def __str__(self):
        return str(self.value)


class StorageDevice(ABC):
    """Abstract storage device"""

    @property
    @abstractmethod
    def soc(self) -> float:
        """Return the state of charge as a float between 0.0 and 1.0."""

    @soc.setter
    @abstractmethod
    def soc(self, new_soc: float):
        """Set the current state of charge of the device.

        Parameters
        ----------
        new_soc : float
            New state of charge as a fraction of the total capacity.
        """

    @property
    @abstractmethod
    def kwh_rated(self) -> float:
        """Return the rated kWh of the device."""

    @property
    @abstractmethod
    def kw_rated(self) -> float:
        """Return kW rating of the device when in `state`."""

    @property
    @abstractmethod
    def state(self) -> StorageState:
        """State of the storage device"""

    @state.setter
    @abstractmethod
    def state(self, new_state: StorageState):
        """Change the state of the storage device."""

    @abstractmethod
    def set_power(self, kw, kvar=None, pf=None):
        """Set the power of this storage device.

        Parameters
        ----------
        kw : float
            Active power. A positive value indicates power coming out
            of the device (i.e. discharging). [kW]
        kvar : float, optional
            Reactive power. Specifying this also updates the power factor.
            [kVAR]
        pf : float, optional
            Power factor. Float in the range [0, 1]. Specifying this also
            updates the reactive power at the device.
        """
