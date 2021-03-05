"""Interface for devices that are part of an OpenDSS model."""
from typing import Any
from ssim.storage import StorageDevice, StorageState
from ssim import dssutil


class Storage(StorageDevice):
    """Implementation of a storage device in OpenDSS.

    Parameters
    ----------
    name : str
        Name of the storage device.
    bus : int or str
        Bus where the device is connected to the grid.
    device_parameters : dict
        Dictionary of device parameters. Keys must be valid OpenDSS storage
        object options such as 'kVA', and 'kWhrated'. Keys are not case
        sensitive
    state : StorageState, default StorageState.IDLING
        Initial state of storage device.
    initial_soc : float, default 1.0
        Initial state of charge as a fraction of the total capacity.
    """
    def __init__(self, name, bus, device_parameters,
                 state=StorageState.IDLE, initial_soc=1.0):
        self.name = name
        self.bus = bus
        self._device_parameters = device_parameters
        self.state = state
        self.kw = 0
        self.kvar = 0
        self.pf = 0
        self._soc = initial_soc
        dssutil.run_command(
            f"New Storage.{name}"
            f" bus1={bus}"
            f" dispmode=external"
            f" {self._make_dss_args(device_parameters)}"
            f" state={state}"
        )

    @staticmethod
    def _make_dss_args(device_parameters):
        " ".join(f"{param}={value}" for param, value in device_parameters)

    def get_state(self) -> StorageState:
        return self.state

    def set_state(self, state: StorageState):
        self._set('state', state)
        self.state = state

    def _set(self, property: str, value: Any):
        """Set `property` to `value` in OpenDSS.

        Parameters
        ----------
        property : str
            Name of the property.
        value : Any
            New value.

        Raises
        ------
        OpenDSSError
            If the property could not be set.
        """
        dssutil.run_command(f"storage.{self.name}.{property}={value}")

    def _get(self, property: str) -> str:
        return dssutil.get_property(f"storage.{self.name}.{property}")

    def set_power(self, kw: float, kvar: float = None, pf: float = None):
        # TODO prevent impossible states
        #      (e.g. kw > 0, soc == 0/min, state=discharging)
        self._set('kW', kw)
        if pf is not None:
            self._set('pf', pf)
        if kvar is not None:
            self._set('kvar', kvar)
        # XXX risk that these could get out of sync if an OpenDSSError is
        #     raised when one of these is set. It may be a good idea to
        #     query OpenDSS when these params are needed, rather than keeping
        #     them cached here.
        self.kw = kw
        self.kvar = kvar
        self.pf = pf

    @property
    def soc(self):
        return self._soc

    @soc.setter
    def soc(self, new_soc):
        self._soc = new_soc

    def get_kw_rated(self, state: StorageState) -> float:
        return float(self._get("kwrated"))

    @property
    def kwh_rated(self) -> float:
        return float(self._get("kwhrated"))
