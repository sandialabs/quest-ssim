"""Interface for devices that are part of an OpenDSS model."""
import enum
import math
from os import PathLike
from typing import Any, List, Dict, Optional

import opendssdirect as dssdirect

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
    def __init__(self, name, bus, device_parameters, phases,
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
            f" phases={phases}"
            f" dispmode=external"
            f" {self._make_dss_args(device_parameters)}"
            f" state={state}"
        )

    @staticmethod
    def _make_dss_args(device_parameters):
        return " ".join(f"{param}={value}"
                        for param, value in device_parameters.items())

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


@enum.unique
class SolutionMode(enum.Enum):
    """OpenDSS solution modes."""
    #: snapshot powerflow (present state, no controls or loadshapes)
    SNAPSHOT = 'snap'

    #: time based solution at possible irregular time steps.
    TIME = 'time'

    #: Follow daily load shape at the fixed simulation interval.
    DAILY = 'daily'

    #: Follow yearly load shape at the fixed simulation interval.
    YEARLY = 'yearly'

    def __str__(self):
        return self.value


@enum.unique
class LoadShapeClass(enum.Enum):
    """Enum of OpenDSS load shape classes."""
    DAILY = 'daily'
    YEARLY = 'yearly'
    DUTY = 'duty'


class DSSModel:
    """Wrapper around OpenDSSDirect."""
    def __init__(self, dss_file):
        dssutil.load_model(dss_file)
        dssutil.run_command(
            "set mode=time controlmode=time number=1 loadshapeclass=daily"
        )
        self._last_solution_time = None
        self._storage = {}

    @property
    def loadshapeclass(self) -> LoadShapeClass:
        """The OpenDSS LoadShape class used for loads and generators."""
        return LoadShapeClass(dssdirect.run_command('get loadshapeclass'))

    @loadshapeclass.setter
    def loadshapeclass(self, lsclass: LoadShapeClass):
        """Set the OpenDSS LoadShape class used for loads and generators."""
        dssutil.run_command(f'set loadshapeclass={lsclass}')

    @staticmethod
    def _set_time(time):
        hours = math.floor(time) // 3600
        seconds = time - hours * 3600
        dssdirect.Solution.Hour(hours)
        dssdirect.Solution.Seconds(seconds)

    def next_update(self) -> float:
        """Return the time of the next simulation step in seconds."""
        hour = dssdirect.Solution.Hour()
        return hour * 3600 + dssdirect.Solution.Seconds()

    def last_update(self) -> Optional[float]:
        """Return the time of the most recent power flow calculation."""
        return self._last_solution_time

    def solve(self, time: float = None):
        """Calculate the power flow on the circuit.

        Parameters
        ----------
        time : float, optional
            Time at which to solve, if not specified then the circuit
            is solved at the current time in OpenDSS. [seconds]
        """
        if time is not None:
            self._set_time(time)
        solution_time = self.next_update()
        dssdirect.Solution.Solve()
        dssdirect.Circuit.SaveSample()
        self._last_solution_time = solution_time

    def add_storage(self, name: str, bus: str, phases: int,
                    device_parameters: Dict[str, Any],
                    state: StorageState = StorageState.IDLE,
                    initial_soc: float = 1.0) -> Storage:
        """Add a storage device to OpenDSS.

        Parameters
        ----------
        name : str
            Name of the storage device.
        bus : str
            Name of the bus where the device is connected.
        phases : int
            Number of connected phases.
        device_parameters : dict
            Dictionary of additional OpenDSS storage device parameters.
        state : StorageState
            Initial operating state of the device.
        initial_soc : float
            Initial state of charge as a fraction of the capacity of the
            device (0.0 being empty, 1.0 being full).
        """
        device = Storage(name, bus, device_parameters, phases,
                         state, initial_soc)
        self._storage[name] = device
        return device

    def add_pvsystem(self, name: str, bus: str, phases: int,
                     bus_kv: float, kva_rating: float, connection_type: str,
                     irrad_scale, pmpp_kw: float, temperature: float,
                     pf: float, profile_name: str):
        """Add a PV System to OpenDSS.

        Parameters
        ----------
        name : str
            Name of the system.
        bus : str
            Name of the bus where the system is connected.
        phases : int
            Number of phases to connect
        bus_kv : float
            Rated voltage of the bus [kV].
        kva_rating : float
            Rated kVA of the PV system [kVA].
        irrad_scale : float
            Irradiance scale factor.
        pmpp_kw : float
            Power output of PV system at MPP [kW].
        temperature : float
            Temperature of operation [C].
        pf : float
            Power factor.
        profile_name : str
            Name of the load shape to use as the irradiance profile.
        """
        dssutil.run_command(
            f"New PVSystem.{name}"
            f" bus1={bus}"
            f" phases={phases}"
            f" kV={bus_kv}"
            f" kVA={kva_rating}"
            f" conn={connection_type}"
            f" irrad={irrad_scale}"
            f" Pmpp={pmpp_kw}"
            f" temperature={temperature}"
            f" pf={pf}"
            f" daily={profile_name}"
        )

    def add_loadshape(self, name: str, file: PathLike,
                      interval: float, npts: int):
        """Create a Load Shape in OpenDSS.

        Parameters
        ----------
        name : str
            Name of the load shape.
        file : PathLike
            Path to a CSV file containing the values of the load shape.
        interval : float
            Time between points in hours.
        npts : int
            Number of points in the load shape.
        """
        dssutil.run_command(
            f"New LoadShape.{name}"
            f" npts={npts}"
            f" interval={interval}"
            f" csvfile={file}"
        )

    def add_xycurve(self, name: str,
                    x_values: List[float], y_values: List[float]):
        """Create an XY curve in OpenDSS.

        Parameters
        ----------
        name : str
            Name of the curve.
        x_values : List[float]
            X-values of the curve.
        y_values : List[float]
            Y-values of the curve.
        """
        if len(x_values) != len(y_values):
            raise ValueError(
                "`x_values` and `y_values` must be the same length."
            )
        dssutil.run_command(
            f"New XYCurve.{name}"
            f" npts={len(x_values)}"
            f" xarray={x_values}"
            f" yarray={y_values}"
        )

    def update_storage(self, name: str, p_kw: float, q_kvar: float):
        """Update active and reactive power set-points for a storage device.

        The actual output of the device is subject to the state of the
        OpenDSS model. If the state of charge is 0.0 and the device is
        set to a positive `p_kw` not power will be produced by the device.
        Similarly if the device is fully charged, but `p_kw` is negative,
        the actual power consumed by the device will be 0.0 kW. The reactive
        power consumed or injected by the device is also subject to the
        inverter ratings in the OpenDSS model.

        Parameters
        ----------
        name : str
            Name of the device.
        p_kw : float
            Active power output from the device. A negative value indicates
            the device is charging, while a positive value indicates the device
            is discharging. [kW]
        q_var : float
            Reactive power from the device. [kVAR]
        """
        self._storage[name].set_power(p_kw, q_kvar)

    @property
    def storage_devices(self):
        """The storage devices that have been added to the model.

        Does not return storage devices that are defined in the opendss
        model, only those that were added with
        :py:meth:`DSSModel.add_storage`.
        """
        return self._storage.values()

    def node_voltage(self, node):
        """Return the voltage at `node` [pu]."""
        node_voltages = dict(zip(dssdirect.Circuit.AllNodeNames(),
                                 dssdirect.Circuit.AllBusMagPu()))
        return node_voltages[node]

    def total_power(self):
        """Return the total power on the circuit.

        Returns
        -------
        active_power : float
            Active power [kW]
        reactive_power : float
            Reactive power [kVAR]
        """
        return dssdirect.Circuit.TotalPower()
