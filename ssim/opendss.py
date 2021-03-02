"""Interface for devices that are part of an OpenDSS model."""
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
    initila_soc : float, default 1.0
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

    def _edit(self, option_str):
        """Edit the storage object in OpenDSS.

        Parameters
        ----------
        option_str : str
            Options to pass to the OpenDSS "Edit" command. For example,
            to set the active power and power factor pass "kw=2.1 pf=0.3".
        """
        dssutil.run_command(
            f"Edit Storage.{self.name} {option_str}"
        )

    def set_state(self, state: StorageState):
        self._edit(f"state={state}")
        self.state = state

    def set_power(self, kw: float, kvar: float = None, pf: float = None):
        kvar_str = f" kvar={kvar}" if kvar is not None else ""
        pf_str = f" pf={pf}" if pf is not None else ""
        self._edit(
            f"kW={kw}" + kvar_str + pf_str
        )
        self.kw = kw
        self.kvar = kvar
        self.pf = pf

    @property
    def soc(self):
        return self._soc

    @soc.setter
    def soc(self, new_soc):
        # TODO set the SOC in OpenDSS
        # QUESTION Should we update the power output if the SOC
        # drops to 0 (when discharging) or rises to 1 (when charging)?
        self._soc = new_soc
