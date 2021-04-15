"""Interface for devices that are part of an OpenDSS model."""
from __future__ import annotations
import enum
import math
from os import PathLike
from typing import Any, List, Dict, Optional

import opendssdirect as dssdirect

from ssim.grid import GridSpecification, StorageSpecification
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
    phases : int
        Number of phases the device is connected to.
    state : StorageState, default StorageState.IDLING
        Initial state of storage device.
    """
    def __init__(self, name, bus, device_parameters, phases,
                 state=StorageState.IDLE):
        self.name = name
        self.bus = bus
        self._device_parameters = device_parameters
        self.state = state
        dssutil.run_command(
            f"New Storage.{name}",
            {"bus1": bus, "phases": phases, "state": state,
             "dispmode": "external", **device_parameters}
        )

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
        self._set('kW', kw)
        if pf is not None:
            self._set('pf', pf)
        if kvar is not None:
            self._set('kvar', kvar)

    @property
    def soc(self) -> float:
        return float(self._get("%stored")) / 100.0

    @soc.setter
    def soc(self, new_soc: float):
        self._set("%stored", new_soc * 100)

    @property
    def kw(self):
        return float(self._get("kw"))

    @property
    def kvar(self):
        return float(self._get("kvar"))

    @property
    def kw_rated(self) -> float:
        return float(self._get("kwrated"))

    @property
    def kwh_rated(self) -> float:
        return float(self._get("kwhrated"))


class PVSystem:
    """Representation of a PV system in OpenDSS.

    Parameters
    ----------
    name : str
        Name of the PV system. Must be unique among all PV systems on the grid.
    bus : str
        Bus where the PV system is connected to the grid.
    phases : int
        Number of phases the PV system is connected to.
    pmpp : float
        Maximum power output of the PV Array.
    inverter_kva : float
        Maximum kVA rated for the inverter.
    system_parameters : dict
        Additional parameters
    """
    def __init__(self, name: str, bus: str, phases: int, pmpp: float,
                 inverter_kva: float, system_parameters: dict):
        self.name = name
        self.bus = bus
        self.inverter_kva = inverter_kva
        self.pmpp = pmpp
        self.phases = phases
        dssutil.run_command(f"new pvsystem.{name}",
                            {"bus1": bus, "phases": phases,
                             "Pmpp": pmpp, "kVA": inverter_kva,
                             **system_parameters})


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

    def __str__(self):
        return self.value

    @classmethod
    def from_str(cls, value: str):
        return cls(value.lower())


def _opendss_storage_params(storage_spec: StorageSpecification) -> dict:
    """Return a dictionary of opendss storage object parameters.

    Extracts the parameters from the storage specification and returns a
    dictionary with keys that are the corresponding names of the opendss
    storage object parameters. Parameters 'bus' and 'phases' are excluded
    from the returned dictionary.

    Returns
    -------
    dict
        Dictionary with str keys that are names of opendss Storage Object
        paramters.
    """
    params = {'kwhrated': storage_spec.kwh_rated,
              'kwrated': storage_spec.kw_rated,
              '%stored': storage_spec.soc * 100}
    return {**params, **storage_spec.params}


class DSSModel:
    """Wrapper around OpenDSSDirect."""
    def __init__(self,
                 dss_file: PathLike,
                 loadshape_class: LoadShapeClass = LoadShapeClass.DAILY):
        dssutil.load_model(dss_file)
        dssutil.run_command(
            "set mode=time controlmode=time number=1 stepsize=15m"
        )
        self.loadshapeclass = loadshape_class
        self._last_solution_time = None
        self._storage = {}
        self._pvsystems = {}
        self._max_step = 15 * 60  # 15 minutes

    @classmethod
    def from_grid_spec(cls, gridspec: GridSpecification) -> DSSModel:
        """Construct an DSSModel from a grid specification.

        The OpenDSS model is initialized by loading ``gridspec.file``. After
        the model is loaded the storage devices in ``gridspec.storage_devices``
        are added to the model. After all storage devices have been added, the
        pv systems are added.

        For PV systems, the efficiency curve and the p-t curve may be specified
        either as a parameter in :py:attr:`grid.PVSpecification.params` or
        in the :py:attr:`PVSpecification.inverter_efficiency` and
        :py:attr:`PVSpecification.pt_curve` fields. If either of these fields
        are specified then a new XYCurve will be created in the OpenDSS model
        named "eff_<pvsystem-name>" or "pt_<pvsystem-name>". Curve specified
        this way override the value provided in
        :py:attr:`PVSpecification.params`.

        Parameters
        ----------
        gridspec : GridSpecification
            Grid specification.

        Returns
        -------
        DSSModel
            An opendss grid model that matches the specification in `gridspec`.
        """
        model = DSSModel(gridspec.file)
        for storage_device in gridspec.storage_devices:
            model.add_storage(
                storage_device.name,
                storage_device.bus,
                storage_device.phases,
                _opendss_storage_params(storage_device)
            )
        for pv_system in gridspec.pv_systems:
            system_params = pv_system.params.copy()
            if pv_system.inverter_efficiency is not None:
                model.add_xycurve(f"eff_{pv_system.name}",
                                  *zip(*pv_system.inverter_efficiency))
                system_params["EffCurve"] = f"eff_{pv_system.name}"
            if pv_system.pt_curve is not None:
                model.add_xycurve(f"pt_{pv_system.name}",
                                  *zip(*pv_system.pt_curve))
                system_params["P-TCurve"] = f"pt_{pv_system.name}"
            model.add_pvsystem(
                pv_system.name,
                pv_system.bus,
                pv_system.phases,
                pv_system.kva_rated,
                pv_system.pmpp,
                system_params
            )
        return model

    @property
    def loadshapeclass(self) -> LoadShapeClass:
        """The OpenDSS LoadShape class used for loads and generators."""
        return LoadShapeClass.from_str(
            dssdirect.run_command('get loadshapeclass')
        )

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

    @property
    def current_time(self):
        """The current OpenDSS time in seconds."""
        hour = dssdirect.Solution.Hour()
        return hour * 3600 + dssdirect.Solution.Seconds()

    def next_update(self) -> float:
        """Return the time of the next simulation step in seconds."""
        return self.current_time + self._max_step

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
            time_delta = time - (self._last_solution_time or 0)
            dssutil.run_command(f"set stepsize={time_delta}s")
            self._set_time(time)
        solution_time = self.current_time
        dssdirect.Solution.Solve()
        dssdirect.Circuit.SaveSample()
        self._last_solution_time = solution_time

    def add_storage(self, name: str, bus: str, phases: int,
                    device_parameters: Dict[str, Any],
                    state: StorageState = StorageState.IDLE) -> Storage:
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
        """
        device = Storage(name, bus, device_parameters, phases, state)
        self._storage[name] = device
        return device

    def add_pvsystem(self, name: str, bus: str, phases: int,
                     kva_rating: float, pmpp_kw: float,
                     system_parameters: Optional[dict] = None):
        """Add a PV System to OpenDSS.

        Parameters
        ----------
        name : str
            Name of the system.
        bus : str
            Name of the bus where the system is connected.
        phases : int
            Number of phases to connect
        kva_rating : float
            Rated kVA of the PV system [kVA].
        pmpp_kw : float
            Power output of PV system at MPP [kW].
        system_parameters : dict, optional
            Additional parameters. Keys must be valid OpenDSS PVSystem object
            parameters.
        """
        system = PVSystem(name, bus, phases, pmpp_kw, kva_rating,
                          system_parameters)
        self._pvsystems[name] = system

    @staticmethod
    def add_loadshape(name: str, file: PathLike,
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

    @staticmethod
    def add_xycurve(name: str, x_values: List[float], y_values: List[float]):
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
        q_kvar : float
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
        return self._storage

    @property
    def pvsystems(self):
        """Return the PV systems that have been added to the grid model.

        Similarly to :py:attr:`DSSModel.storage_devices`, only systems added
        to the model with :py:meth:`DSSModel.add_pvsystem` are returned.
        """
        return self._pvsystems

    @staticmethod
    def node_voltage(node):
        """Return the voltage at `node` [pu]."""
        node_voltages = dict(zip(dssdirect.Circuit.AllNodeNames(),
                                 dssdirect.Circuit.AllBusMagPu()))
        return node_voltages[node]

    @staticmethod
    def positive_sequence_voltage(bus):
        """Return positive sequence voltage at `bus` [pu]."""
        dssdirect.Circuit.SetActiveBus(bus.split('.')[0])  # remove node names
        zero, positive, negative = dssdirect.Bus.SeqVoltages()
        return positive / (dssdirect.Bus.kVBase() * 1000)

    @staticmethod
    def total_power():
        """Return the total power on the circuit.

        Returns
        -------
        active_power : float
            Active power [kW]
        reactive_power : float
            Reactive power [kVAR]
        """
        return dssdirect.Circuit.TotalPower()
