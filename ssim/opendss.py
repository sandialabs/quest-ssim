"""Interface for devices that are part of an OpenDSS model."""
from __future__ import annotations
from collections import namedtuple
import csv
import enum
from functools import lru_cache, cached_property
import logging
import math
import os
from os import PathLike, path
from pathlib import Path
import re
from typing import Any, List, Dict, Optional

import opendssdirect as dssdirect

from ssim import grid
from ssim.grid import GridSpecification, StorageSpecification
from ssim.storage import StorageDevice, StorageState
from ssim import dssutil


ControlEvent = namedtuple("ControlEvent", ("time", "element", "action"))


def _parse_control_event(event_record: str) -> ControlEvent:
    """Parse a string containing an opendss event record."""
    m = re.match(r"Hour=(?P<hour>\d+), "
                 r"Sec=(?P<sec>\d+(\.\d*)?), "
                 r"ControlIter=\d+, "
                 r"Element=(?P<element>[a-zA-Z0-9._/]+), "
                 r"([a-zA-Z0-9._/]+, )?Action=(?P<action>.*)",
                 event_record)
    if m is None:
        logging.error("Could not parse control event record: '%s'",
                      event_record)
        return None
    hours = float(m.group("hour"))
    seconds = float(m.group("sec"))
    time = hours * 3600 + seconds
    element = m.group("element")
    action = m.group("action")
    return ControlEvent(time, element, action)


class ControlLog:
    """Record of control actions that have been executed by OpenDSS."""

    def __init__(self):
        self._log_index = 0
        self.events = []

    def update(self):
        """Add any new control actions to the control log."""
        event_log = dssdirect.Solution.EventLog()
        while self._log_index < len(event_log):
            event = _parse_control_event(event_log[self._log_index])
            self._log_index += 1
            if event is None:
                continue
            self.events.append(event)

    def to_csv(self, output_file):
        """Save the control log to a CSV file.

        Parameters
        ----------
        output_file : str or PathLike
            Path to the output file. If the file exists it will be truncated
            before writing.
        """
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(ControlEvent._fields)
            writer.writerows(self.events)


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
        dssutil.run_command(
            f"New Storage.{name}",
            {"bus1": bus, "phases": phases, "state": state,
             "dispmode": "external", **device_parameters}
        )

    @property
    def state(self) -> StorageState:
        return StorageState(self._get('state').lower())

    @state.setter
    def state(self, new_state):
        self._set('state', new_state)

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

    @property
    def status(self) -> grid.StorageStatus:
        return grid.StorageStatus(self.name, self.soc)

    def state_change(self) -> float:
        """Return the time until the storage device will change state.

        A state change is any change in the power output or input
        caused by the state of charge reaching either its upper or
        lower limit.

        Returns
        -------
        float
            Seconds until the device must change state.
        """
        if self.state is StorageState.IDLE or self.kw == 0.0:
            return math.inf
        if self.state is StorageState.DISCHARGING:
            kwh_minimum = self.kwh_rated * float(self._get("%reserve")) / 100
            kwh_remaining = float(self._get("kwhstored")) - kwh_minimum
            kw = self.kw
            kw_discharge = (
                    kw + (1.0 - (float(self._get("%effdischarge")) / 100)
                          - (float(self._get("%idlingkw")) / 100)) * kw)
            return 3600.0 * (kwh_remaining / kw_discharge)
        if self.state is StorageState.CHARGING:
            kwh_remaining = self.kwh_rated - float(self._get("kwhstored"))
            kw_charge = (float(self._get("%effcharge")) / 100
                         - float(self._get("%idlingkw")) / 100) * abs(self.kw)
            return 3600.0 * (kwh_remaining / kw_charge)


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
        # temporarily attaches a PQ monitor to each PV system
        # no need to merge this edit, we will add the functionality to add
        # monitors later
        monitor_name = "pvsystem_" + name
        element_name = "PVSystem." + name
        dssutil.run_command(f"new monitor.{monitor_name}",
                            {"element": element_name, "terminal": 1,
                             "mode": 1, "ppolar": "no"})

    def _activate(self):
        """Make this the active PV system in OpenDSS."""
        dssdirect.PVsystems.Name(self.name)

    @property
    def kw(self) -> float:
        """Current real power output. [kW]"""
        self._activate()
        return dssdirect.PVsystems.kW()

    @property
    def kvar(self) -> float:
        """Current reactive power output/consumption system. [kVAR]"""
        self._activate()
        return dssdirect.PVsystems.kvar()


class Generator:
    """Interface for OpenDSS Generator objects.

    Parameters
    ----------
    name : str
        Name of the generator.
    """

    def __init__(self, name):
        if name not in dssdirect.Generators.AllNames():
            raise ValueError(f"Generator {name} does not exist.")
        self.name = name
        self._activate()
        self.type = int(
            dssutil.get_property(f"generator.{self.name}.class")
        )
        self.is_operational = True

    def _activate(self):
        dssdirect.Generators.Name(self.name)

    @property
    def kw(self):
        self._activate()
        return dssdirect.Generators.kW()

    @kw.setter
    def kw(self, kw):
        self._activate()
        dssdirect.Generators.kW(kw)

    @property
    def kvar(self) -> float:
        self._activate()
        return dssdirect.Generators.kvar()

    @kvar.setter
    def kvar(self, kvar: float):
        self._activate()
        dssdirect.Generators.kvar(kvar)

    @property
    def online(self) -> bool:
        self._activate()
        return dssdirect.CktElement.Enabled()

    def turn_on(self):
        if self.is_operational:
            self._activate()
            dssdirect.CktElement.Enabled(True)

    def turn_off(self):
        if self.is_operational:
            self._activate()
            dssdirect.CktElement.Enabled(False)

    def change_setpoint(self, kw, kvar):
        """Update the generator setpoint.

        The setpoint is only changed if `self.is_operational` is True,
        otherwise the method does nothing.

        Parameters
        ----------
        kw : float
            Real power set point [kW].
        kvar : float
            Reactive power set point [kVAR].

        """
        if self.is_operational:
            self.kw = kw
            self.kvar = kvar

    def _read_meter(self) -> dict:
        self._activate()
        return dict(
            zip(dssdirect.Generators.RegisterNames(),
                dssdirect.Generators.RegisterValues())
        )

    @property
    def hours_operating(self) -> float:
        """Return the total hours the generator has been in operation."""
        meter = self._read_meter()
        return meter["Hours"]

    @property
    def status(self):
        return grid.GeneratorStatus(
            self.name,
            self.kw,
            self.kvar,
            self.hours_operating,
            self.online
        )


class Load:
    """Interface to an OpenDSS load object.

    Parameters
    ----------
    name : str
        Name of the load.
    """

    def __init__(self, name):
        self.name = name

    def _activate(self):
        dssdirect.Loads.Name(self.name)

    @property
    def kw_rated(self) -> float:
        """Nominal maximum kW of the laod."""
        self._activate()
        return dssdirect.Loads.kW()

    @property
    def kvar_rated(self) -> float:
        """Nominal maximum kVAR of the load"""
        self._activate()
        return dssdirect.Loads.kvar()

    @property
    def kw(self) -> float:
        """Actual real power demand from the load.

        Accounts for load shapes etc.
        """
        self._activate()
        return sum(dssdirect.CktElement.Powers()[0::2])

    @property
    def kvar(self) -> float:
        """Actual reactive power fom the load."""
        self._activate()
        return sum(dssdirect.CktElement.Powers()[1::2])

    @property
    def status(self) -> grid.LoadStatus:
        return grid.LoadStatus(self.name, self.kw, self.kvar)


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


class InvControl:
    """Representation of an inverter controller in OpenDSS.

    Parameters
    ----------
    name : str
        Name of the Inv Control element. Must be unique among all Inv
        Control elements on the model.
    der_list :
        List of PV system elements to be controlled. If not specified all
        PVSystem (and Storage) in the grid model are controlled by this
        InvControl.
    inv_control_mode: str
        Inverter control mode.
    system_parameters : dict
        Additional parameters.
    """

    def __init__(self, name: str, der_list, inv_control_mode: str,
                 system_parameters: dict):
        self.name = name
        self.der_list = der_list
        self.inv_control_mode = inv_control_mode
        if inv_control_mode.lower() == "vv_vw":
            dssutil.run_command(f"new invcontrol.{name}",
                                {"derlist": der_list,
                                 "combimode": inv_control_mode,
                                 **system_parameters})
        else:
            dssutil.run_command(f"new invcontrol.{name}",
                                {"derlist": der_list, "mode": inv_control_mode,
                                 **system_parameters})


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


class BusRecorder:
    """Recorder for data from a subset of busses.

    Records the following information from all specified busses:

    - minimum voltage [pu]
    - maximum voltage [pu]
    - name of bus with maximum voltage
    - name of bus with minimum voltage
    - total load [kW]
    - total PV generation [kW]

    Parameters
    ----------
    name : str
        Name of the recorder.
    busses : Iterable of str, optional
        Set of busses to record. If None, then all busses are used.
    """

    def __init__(self, name, busses=None):
        if busses is None:
            self.busses = set(dssdirect.Circuit.AllBusNames())
        else:
            self.busses = set(busses)
        self._times = []
        self._min_voltage = []
        self._max_voltage = []
        self._min_node = []
        self._max_node = []
        self._load_kw = []
        self._load_kvar = []
        self._pv_kw = []
        self._pv_kvar = []
        self.name = name

    @cached_property
    def pvsystems(self):
        pvsystems = []
        for bus in self.busses:
            dssdirect.Circuit.SetActiveBus(bus)
            for pce in dssdirect.Bus.AllPCEatBus():
                if pce.startswith("PVSystem."):
                    pvsystems.append(pce.split(".")[1])
        return pvsystems

    @cached_property
    def loads(self):
        loads = []
        for bus in self.busses:
            dssdirect.Circuit.SetActiveBus(bus)
            for pce in dssdirect.Bus.AllPCEatBus():
                if pce.startswith("Load."):
                    loads.append(pce.split(".")[1])
        return loads

    @cached_property
    def nodes(self):
        nodes = []
        for bus in self.busses:
            dssdirect.Circuit.SetActiveBus(bus)
            bus_nodes = dssdirect.Bus.Nodes()
            nodes.extend(f"{bus}.{node}" for node in bus_nodes)
        return nodes

    def sample(self, time):
        """Record data at the given time.

        Parameters
        ----------
        time : float
            The current time in seconds.
        """
        self._times.append(time)
        total_kw = 0.0
        total_kvar = 0.0
        for load in self.loads:
            dssdirect.Loads.Name(load)
            kw, kvar = dssdirect.CktElement.TotalPowers()
            total_kw += kw
            total_kvar += kvar
        self._load_kw.append(total_kw)
        self._load_kvar.append(total_kvar)
        pv_kw = 0.0
        pv_kvar = 0.0
        for pvsystem in self.pvsystems:
            dssdirect.PVsystems.Name(pvsystem)
            pv_kw += dssdirect.PVsystems.kW()
            pv_kvar += dssdirect.PVsystems.kvar()
        self._pv_kw.append(pv_kw)
        self._pv_kvar.append(pv_kvar)
        node_voltages = all_node_voltages(time)
        select_voltage = {node: node_voltages[node] for node in self.nodes}
        minimum_voltage = 10.0
        maximum_voltage = 0.0
        minimum_node = None
        maximum_node = None
        for node, voltage in select_voltage.items():
            if voltage < 0.1:
                # ignore any busses that are not energized
                continue
            if voltage < minimum_voltage:
                minimum_voltage = voltage
                minimum_node = node
            if voltage > maximum_voltage:
                maximum_voltage = voltage
                maximum_node = node
        self._min_node.append(minimum_node)
        self._min_voltage.append(minimum_voltage)
        self._max_node.append(maximum_node)
        self._max_voltage.append(maximum_voltage)

    def to_csv(self, output_file):
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(("time", "vmin", "vmax", "vmin_node", "vmax_node",
                             "load_kw", "load_kvar",
                             "pv_kw", "pv_kvar"))
            writer.writerows(
                zip(self._times, self._min_voltage, self._max_voltage,
                    self._min_node, self._max_node,
                    self._load_kw, self._load_kvar,
                    self._pv_kw, self._pv_kvar)
            )


class PDERecorder:
    """Record loading across power delivery elements.

    Parameters
    ----------
    names : Iterable of str, optional
        Names of the power delivery elements to monitor.
    """

    def __init__(self, names=None):
        if names is None:
            names = dssdirect.PDElements.AllNames()
        self._names = tuple(names)
        self._loading = []

    def to_csv(self, output_file):
        """Save the data to a CSV file.

        Parameters
        ----------
        output_file : str or pathlike
            Path to the output file.
        """
        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(("time", *self._names))
            writer.writerows(self._loading)

    def _pde_loading(self):
        loading = dict(zip(dssdirect.PDElements.AllNames(),
                           dssdirect.PDElements.AllPctNorm()))
        for name in self._names:
            yield loading[name]

    def sample(self, time):
        self._loading.append(
            (time, *self._pde_loading())
        )


class VoltageRecorder:
    """Record voltages at a set of busses.

    Unlike :py:class:`BusRecorder` this records the voltage at every bus
    without any aggregation.

    Parameters
    ----------
    busses : Iterable of str
        Set of busses to record.
    """

    def __init__(self, busses):
        self.times = []
        self.voltage = {bus: [] for bus in busses}

    def _voltage(self, bus):
        """Return the average voltage over all nodes at `bus`."""
        return _mean_node_voltage(bus)

    def sample(self, time):
        self.times.append(time)
        for bus, voltages in self.voltage.items():
            voltages.append(self._voltage(bus))

    def to_csv(self, output_path):
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(("time", *self.voltage.keys()))
            writer.writerows(zip(self.times, *self.voltage.values()))


@lru_cache(maxsize=1)
def all_node_voltages(time):
    """Return a dict of per-unit voltage at all nodes in the active circuit."""
    # NOTE the parameter `time` is unused. it is provided only to facilitate
    #      caching the results.
    return dict(
        zip(dssdirect.Circuit.AllNodeNames(),
            dssdirect.Circuit.AllBusMagPu())
    )


class Monitor:
    """Extended API for OpenDSS Monitor objects.

    Parameters
    ----------
    name : str
        Name of the monitor object.
    """

    def __init__(self, name):
        self.name = name

    def to_csv(self, directory=None, filename=None):
        """Save the monitor data to a csv file.

        Parameters
        ----------
        directory: PathLike, optional
            Path to the directory where the ouput file should be
            written. If not specified the data is written to the file
            name specified in OpenDSS.
        filename: str, optional
            Name of the output CSV file. If not specified the file
            name is extracted from the monitor's FileName property in
            OpenDSS. This argument is only valid if `directory` is
            specified.
        """
        dssdirect.Monitors.Name(self.name)
        dssdirect.Monitors.Save()
        if directory is None:
            output_file = Path(dssdirect.Monitors.FileName())
        elif filename is None:
            filename = path.basename(dssdirect.Monitors.FileName())
            output_file = directory / filename
        else:
            output_file = directory / filename
        print(f"saving monitor {self.name} data in {output_file}")
        with open(output_file, 'w', newline="") as f:
            writer = csv.writer(f)
            writer.writerow(("time", *dssdirect.Monitors.Header()))
            writer.writerows(
                zip(map(lambda hour: hour * 3600.0,
                        dssdirect.Monitors.dblHour()),
                    *(dssdirect.Monitors.Channel(x)
                      for x in range(1, dssdirect.Monitors.NumChannels() + 1)))
            )


class DSSModel:
    """Wrapper around OpenDSSDirect."""

    def __init__(self,
                 dss_file: PathLike,
                 loadshape_class: LoadShapeClass = LoadShapeClass.DAILY):
        dssutil.load_model(dss_file)
        dssutil.run_command("calcv")
        dssutil.run_command(
            "set mode=time controlmode=time number=1 stepsize=15m"
        )
        self._model_file = dss_file
        self.loadshapeclass = loadshape_class
        self._last_solution_time = None
        self._storage = {}
        self._pvsystems = {}
        self._invcontrols = {}
        self.generators = {
            name: Generator(name) for name in dssdirect.Generators.AllNames()
        }
        self._failed_elements = set()
        self._recorder = BusRecorder("all-busses")
        self._loading_recorder = None
        self._max_step = 15 * 60  # 15 minutes
        self._control_log = ControlLog()

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
        :py:attr:`PVSpecification.params`. The irradiance profile for the PV
        may be specified through a csv file in the
        :py:attr: `grid.PVSpecification.irradiance_profile` field or as a
        parameter in :py:attr:`grid.PVSpecification.params`. Either way a new
        LoadShape will be created in the OpenDSS model named
        "irrad_pv_<pvsystem-name>".

        Similarly, for the storage device, the efficiency curve may be
        specified as a parameter in :py:attr:`grid.StorageSpecification.params`
        or in the :py:attr:`StorageSpecification.inverter_efficiency'. If
        either of these fields are specified then a new XYCurve will be
        created in the OpenDSS model named "eff_storage_<storagedevice-name>".
        Curve specified this way overrides the value provided in
        :py:attr:`StorageSpecification.params`.

        For Inv controls, the function curve may be specified
        either as a parameter in :py:attr:`grid.InvControlSpecification` or
        in the :py:attr:`InvControlSpecification.function_curve` field. If
        this field is specified then a new XYCurve will be created in the
        OpenDSS model names "func_<invcontrol-name>". Curve specified this
        way will override the value provided in
        :py:attr:`InvControlSpecification.params`

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
        model.add_voltage_recorder(
            gridspec.busses_to_log.union(
                set(bus["name"] for bus in gridspec.busses_to_measure)
            )
        )
        model.add_loading_recorder()
        for storage_device in gridspec.storage_devices:
            storage_params = _opendss_storage_params(storage_device)
            if storage_device.inverter_efficiency is not None:
                model.add_xycurve(f"eff_storage_{storage_device.name}",
                                  *zip(*storage_device.inverter_efficiency))
                storage_params["EffCurve"] = \
                    f"eff_storage_{storage_device.name}"
            model.add_storage(
                storage_device.name,
                storage_device.bus,
                storage_device.phases,
                storage_params
            )
        for pv_system in gridspec.pv_systems:
            system_params = pv_system.params.copy()
            if pv_system.irradiance_profile is not None:
                npts = _count_lines(pv_system.irradiance_profile)
                model.add_loadshape(f"irrad_pv_{pv_system.name}",
                                    pv_system.irradiance_profile, 0, npts)
                loadshape_class = str(model.loadshapeclass)
                system_params[loadshape_class] = f"irrad_pv_{pv_system.name}"
            if pv_system.inverter_efficiency is not None:
                model.add_xycurve(f"eff_pv_{pv_system.name}",
                                  *zip(*pv_system.inverter_efficiency))
                system_params["EffCurve"] = f"eff_pv_{pv_system.name}"
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
        for inv_control in gridspec.inv_control:
            control_params = inv_control.params.copy()
            if inv_control.function_curve_1 is not None:
                # single inverter control functions
                # add function_curve_1 to the model
                model.add_xycurve(f"func_{inv_control.name}_1",
                                  *zip(*inv_control.function_curve_1))
                # volt-var function
                if inv_control.inv_control_mode.lower() == "voltvar":
                    control_params["vvc_curve1"] = \
                        f"func_{inv_control.name}_1"
                # volt-watt function
                elif inv_control.inv_control_mode.lower() == "voltwatt":
                    control_params["voltwatt_curve"] = \
                        f"func_{inv_control.name}_1"
                # watt-pf function
                elif inv_control.inv_control_mode.lower() == "wattpf":
                    control_params["wattpf_curve"] = \
                        f"func_{inv_control.name}_1"
                # watt-var function
                elif inv_control.inv_control_mode.lower() == "wattvar":
                    control_params["wattvar_curve"] = \
                        f"func_{inv_control.name}_1"
                elif inv_control.inv_control_mode.lower() == "vv_vw":
                    if inv_control.function_curve_2 is None:
                        raise ValueError("vv_vw control mode requires two "
                                         "function curves. Add a value for "
                                         "'function_curve_2'.")
                    model.add_xycurve(f"func_{inv_control.name}_2",
                                      *zip(*inv_control.function_curve_2))
                    control_params["vvc_curve1"] = \
                        f"func_{inv_control.name}_1"
                    control_params["voltwatt_curve"] = \
                        f"func_{inv_control.name}_2"

            model.add_inverter_controller(
                inv_control.name,
                inv_control.der_list,
                inv_control.inv_control_mode,
                control_params
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

    def _set_time(self, time):
        time_delta = time - (self._last_solution_time or 0)
        logging.debug("[%s] - delta: %s", time, time_delta)
        # This is done using the opendssdirect.run_command() function rather
        # than the opendssdirect.Solution API because of a bug with the
        # Solution API that results in anomalous spikes in the total power
        # and voltage. When all three values are set in a single command
        # the anomalous values go away.
        #
        # Note that we set the step size to ensure that the state of charge of
        # storage devices are updated correctly.
        dssdirect.run_command(
            f"set hour={time // 3600} sec={time % 3600} stepsize={time_delta}s"
        )

    def next_update(self) -> float:
        """Return the time of the next simulation step in seconds."""
        if self._last_solution_time is None:
            # The model has never been solved, its next step should be at 0 s.
            return 0
        return min(
            self._last_solution_time + self._max_step,
            self.next_event()
        )

    def last_update(self) -> Optional[float]:
        """Return the time of the most recent power flow calculation."""
        return self._last_solution_time

    def solve(self, time: float):
        """Calculate the power flow on the circuit.

        Parameters
        ----------
        time : float
            Time at which to solve. [seconds]
        """
        self._set_time(time)
        try:
            dssdirect.Solution.Solve()
        except dssdirect.DSSException as e:
            max_iter = dssdirect.Solution.MaxControlIterations()
            if dssdirect.Solution.ControlIterations() < max_iter:
                raise e
            else:
                logging.info("Max control iterations exceeded.")
        self._last_solution_time = time

    def add_voltage_recorder(self, busses):
        """Monitor voltage at each bus in `busses`."""
        self._voltage_recorder = VoltageRecorder(busses)

    def record_state(self):
        """Record the values of interest at the last solution."""
        self._recorder.sample(self._last_solution_time)
        self._control_log.update()
        if self._voltage_recorder is not None:
            self._voltage_recorder.sample(self._last_solution_time)
        if self._loading_recorder is not None:
            self._loading_recorder.sample(self._last_solution_time)

    def save_record(self, output_dir: Optional[PathLike] = None):
        """Save the recorded simulation values to a file.

        Saves the recorded values from the simulation to a CSV file
        named "grid_state.csv" in `output_dir`.

        Parameters
        ----------
        output_dir : PathLike, optional
            Directory to save the record in. If not specified then the
            current directory is used.
        """
        if output_dir is None:
            output_dir = Path(".")
        self._recorder.to_csv(output_dir / "grid_state.csv")
        self._control_log.to_csv(output_dir / "control_log.csv")
        if self._voltage_recorder is not None:
            self._voltage_recorder.to_csv(output_dir / "bus_voltage.csv")
        if self._loading_recorder is not None:
            self._loading_recorder.to_csv(output_dir / "pde_loading.csv")
        # Save the data recorded by any internal OpenDSS monitors
        for monitor in self.monitors():
            monitor.to_csv(directory=output_dir, filename=f"monitor_{monitor.name}.csv")

    def monitors(self):
        for monitor_name in dssdirect.Monitors.AllNames():
            yield Monitor(monitor_name)

    def add_storage(self, name: str, bus: str, phases: Optional[int],
                    device_parameters: Dict[str, Any],
                    state: StorageState = StorageState.IDLE) -> Storage:
        """Add a storage device to OpenDSS.

        Parameters
        ----------
        name : str
            Name of the storage device.
        bus : str
            Name of the bus where the device is connected.
        phases : int or None
            Number of connected phases. If None the device is connected to all
            phases present at `bus`
        device_parameters : dict
            Dictionary of additional OpenDSS storage device parameters.
        state : StorageState
            Initial operating state of the device.

        """
        nodes = self.available_phases(bus)
        if phases is None:
            bus = ".".join([bus] + [str(n) for n in nodes])
            phases = len(nodes)
        device = Storage(name, bus, device_parameters, phases, state)
        self._storage[name] = device
        return device

    def add_pvsystem(self, name: str, bus: str, phases: Optional[int],
                     kva_rating: float, pmpp_kw: float,
                     system_parameters: Optional[dict] = None) -> PVSystem:
        """Add a PV System to OpenDSS.

        Parameters
        ----------
        name : str
            Name of the system.
        bus : str
            Name of the bus where the system is connected.
        phases : int or None
            Number of connected phases. If None the system is connected to all
            phases present at `bus`
        kva_rating : float
            Rated kVA of the PV system [kVA].
        pmpp_kw : float
            Power output of PV system at MPP [kW].
        system_parameters : dict, optional
            Additional parameters. Keys must be valid OpenDSS PVSystem object
            parameters.
        """
        nodes = self.available_phases(bus)
        if phases is None:
            bus = ".".join([bus] + [str(n) for n in nodes])
            phases = len(nodes)
        system = PVSystem(name, bus, phases, pmpp_kw, kva_rating,
                          system_parameters)
        self._pvsystems[name] = system
        return system

    def add_inverter_controller(self, name: str, der_list: List,
                                inv_control_mode: str,
                                system_parameters: Optional[dict]
                                = None) -> InvControl:
        """Add an Inverter Controller to OpenDSS.

        Parameters
        ----------
        name: str
            Name of the inverter controller.
        der_list : list
            List of DERs that will be controlled by this inverter controller.
        inv_control_mode : str
            Inverter control mode to activate.
        system_parameters : dict, optional
            Additional parameters. Keys must be valid OpenDSS InvControl
            object parameters.
        """
        control = InvControl(name, der_list, inv_control_mode,
                             system_parameters)
        self._invcontrols[name] = control
        return control

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

    @property
    def invcontrols(self):
        """Return the InvControls that have been added to the grid model.

        Does not return inverter controls that are defined in the opendss
        model, only those that were added with
        :py:meth:`DSSModel.add_invcontrol`.
        """
        return self._invcontrols

    def loads(self):
        """Return an iterator over all loads in the model.

        Returns
        -------
        Iterable of Load
        """
        for load in dssdirect.Loads.AllNames():
            yield Load(load)

    def available_phases(self, bus):
        dssdirect.Circuit.SetActiveBus(bus)
        return dssdirect.Bus.Nodes()

    @property
    def bus_names(self):
        return dssdirect.Circuit.AllBusNames()

    @property
    def line_names(self):
        return dssdirect.Lines.AllNames()

    @staticmethod
    def node_voltage(bus):
        """Return a list of node voltage magnitudes at `bus` [pu]."""
        dssdirect.Circuit.SetActiveBus(bus)
        voltages = dssdirect.Bus.VMagAngle()
        base_voltage = dssdirect.Bus.kVBase() * 1000
        return list(voltage / base_voltage for voltage in voltages[::2])
    
    @staticmethod
    def nominal_voltage(bus):
        """Return a list of node voltage magnitudes at `bus` [pu]."""
        dssdirect.Circuit.SetActiveBus(bus)
        nNodes = dssdirect.Bus.NumNodes()
        kvb = dssdirect.Bus.kVBase()        
        if nNodes == 1: return round(kvb, 4)
        return round(kvb / math.sqrt(3.0) * nNodes, 4)
    
    @staticmethod
    def all_base_voltages():
        return {DSSModel.nominal_voltage(bus) for bus in dssdirect.Circuit.AllBusNames()}

    @staticmethod
    def mean_node_voltage(bus):
        """Return the mean per-unit node voltage for all nodes at `bus`.

        Parameters
        ----------
        bus : str
            Name of the bus. Must not include any node names.

        Returns
        -------
        float
            Per-unit voltage.
        """
        return _mean_node_voltage(bus)

    @staticmethod
    def positive_sequence_voltage(bus):
        """Return positive sequence voltage at `bus` [pu]."""
        dssdirect.Circuit.SetActiveBus(bus.split('.')[0])  # remove node names
        zero, positive, negative = dssdirect.Bus.SeqVoltages()
        return positive / (dssdirect.Bus.kVBase() * 1000)

    @staticmethod
    def complex_voltage(bus):
        """Return a list of complex voltages of each node at 'bus' [pu]. """
        dssdirect.Circuit.SetActiveBus(bus)
        pu_voltages = dssdirect.Bus.PuVoltage()
        return list(
            complex(real, imag) for real, imag in zip(pu_voltages[::2],
                                                      pu_voltages[1::2]))

    @staticmethod
    def total_power() -> [float]:
        """Return the total power on the circuit.

        Returns
        -------
        active_power : float
            Active power [kW]
        reactive_power : float
            Reactive power [kVAR]
        """
        return dssdirect.Circuit.TotalPower()

    def next_event(self):
        """Return the time of the next event that will change the grid state.

        Events include control actions, depletion of a storage device,
        or a storage device reaching its full state of charge.

        Returns
        -------
        float
            Time when the next event will occur. [seconds]
        """
        if len(self.storage_devices) == 0:
            storage_change = math.inf
        else:
            storage_change = min(
                storage.state_change()
                for storage in self.storage_devices.values()
            )
        control_time = self.next_action()
        return min(self._last_solution_time + storage_change, control_time)

    def next_action(self):
        """Return the time of the next control action.

        If no pending action, :py:attr:`math.inf` is returned.
        """
        if dssdirect.CtrlQueue.QueueSize() > 0:
            # OpenDSS rounds the scheduled action times when they are
            # returned by the CtrlQueue API. To ensure the simulation moves
            # forward we detect when the next action time is in the past
            # (i.e. it is less than or equal to the last solution time).
            # In this case the only way to ensure we evaluate a solution at
            # the scheduled control time is to step the simulation forward by
            # 1 second intervals. This results in a few extra solutions, but
            # the number is bounded by the longest control delay so it is not
            # too bad.
            next_action = min(
                _action_time(action)
                for action in dssdirect.CtrlQueue.Queue()[1:]
            )
            if self._last_solution_time >= next_action:
                return self._last_solution_time + 1.0
            return next_action
        return math.inf

    @staticmethod
    def _switch_terminal(full_name: str, terminal: int, how: str):
        if how not in {'open', 'closed', 'current'}:
            raise ValueError("`how` must be one of 'open', 'closed', "
                             f"or 'current'. Got '{how}'.")
        if how == 'open':
            dssutil.open_terminal(full_name, terminal)
        elif how == 'closed':
            dssutil.close_terminal(full_name, terminal)

    def _fail_element(self, full_name: str, terminal: int, how: str):
        """Fail an element in the OpenDSS model.

        Fail an element by opening or closing the switch at `terminal` and
        lock out all switch controls associated with the element.

        Parameters
        ----------
        full_name : str
            Full name of the OpenDSS circuit element (e.g. 'line.l123').
        terminal : int
            Terminal of the element to operate on.
        how : str
            How to fail the element. Can be 'open' (the terminal is opened),
            'closed' (the terminal is closed), or 'current' (the
            element/terminal is locked out in its current state).
        """
        self._switch_terminal(full_name, terminal, how)
        dssutil.lock_switch_control(full_name)
        self._failed_elements.add(full_name)

    def _restore_element(self, full_name: str, terminal: int, how: str):
        """Restore a failed element.

        Sets the terminal switch for the element as specified by `how` and
        unlocks all switch controllers associated with the element.

        Parameters
        ----------
        full_name : str
            Full name of the OpenDSS circuit element (e.g. 'line.l123')
        terminal : int
            Terminal of the device to operate on.
        how : str
            State to return the terminal to. Can be 'open' (terminal is
            switched opened), 'closed' (terminal is switched closed), or
            'current' (terminal is kept in its current state).
        """
        if full_name not in self._failed_elements:
            raise ValueError(f"Element '{full_name}' is not failed.")
        self._switch_terminal(full_name, terminal, how)
        dssutil.unlock_switch_control(full_name)
        self._failed_elements.remove(full_name)

    def fail_line(self, name: str, terminal: int, how: str = 'open'):
        """Fail a line.

        This is also used to fail switches, which are modeled in OpenDSS as
        lines with negligible impedance. As opposed to the "normal" way of
        operating switches (through switch controls), this method operates
        directly on implicit switches at each terminal of the line. If any
        switch controllers are associated with the line they are locked out
        to prevent normal operation while the line is out of service.

        Parameters
        ----------
        name : str
            Name of the line to fail.
        terminal : int
            Which terminal of the line to fail (i.e. which end).
        how : str, default 'open'
            State to fail the line in. Must be one of 'current', 'open', or
            'closed'.
        """
        self._fail_element(f"line.{name}", terminal, how)

    def restore_line(self, name: str, terminal: int, how: str = 'current'):
        """Restore a failed line.

        Sets the switch at `terminal` to the state specified by `how` and
        unlocks any switch controllers associated with the line.

        Parameters
        ----------
        name : str
            Name of the line to restore.
        terminal : int
            Terminal to restore.
        how : str, default 'current'
            State to restore the line to. By default the line is restored to
            its current state. This effectively does nothing other than allow
            switch controls (if present) to operate again. Can be any of
            'open', 'closed', or 'current'.
        """
        self._restore_element(f"line.{name}", terminal, how)

    def fail_generator(self, name: str):
        """Fail a generator.

        Disables the generator so it cannot produce power and marks it as
        failed to prevent its activation until it has been repaired.

        Parameters
        ----------
        name : str
            Name of the generator
        """
        self._fail_element(f"generator.{name}", 1, 'open')
        # Disable the generator so it does not accumulate run-time while it
        # is out of service.
        self.generators[name].turn_off()
        self.generators[name].is_operational = False

    def restore_generator(self, name: str, enable=False):
        """Repair a generator.

        The repaired generator is reconnected to the grid, but it remains
        disabled. The generator will remain disabled until it is explicitly
        turned on (i.e. by the EMS).

        Parameters
        ----------
        name : str
            Name of the generator
        enable : bool, default False
            If True, the generator is re-enabled. If False the generator
            remains disabled, leaving it to some other system to turn it back
            on now that it is back in operation.
        """
        self._restore_element(f"generator.{name}", 1, 'closed')
        self.generators[name].is_operational = True
        if enable:
            self.generators[name].turn_on()

    def add_loading_recorder(self):
        self._loading_recorder = PDERecorder()

    def export_model(self, output_dir):
        """Write the grid model as a connonical set of files.

        Parameters
        ----------
        output_dir : str
            Directory where the output files will be written.
        """
        os.makedirs(output_dir, exist_ok=True)
        source_dir = path.dirname(self._model_file)
        dssutil.export(source_dir, output_dir)


def _count_lines(file_path):
    """Return the number of lines in the file."""
    with open(file_path, "r") as f:
        return len(f.readlines())


def _mean_node_voltage(bus):
    """Return the mean voltage at every node in `bus`. [pu]"""
    dssdirect.Circuit.SetActiveBus(bus)
    v_complex_pu = dssdirect.Bus.puVmagAngle()
    num_nodes = len(v_complex_pu) // 2
    return sum(v_complex_pu[::2]) / num_nodes


def _action_time(action):
    """Get the scheduled time from an OpenDSS control queue entry

    Parameters
    ----------
    action : str
        OpenDSS control queue entry. Comma separated string.

    Returns
    -------
    float
        Scheduled time [seconds].
    """
    _, hour, second, _, _, _ = action.split(",")
    return float(hour) * 3600 + float(second)
