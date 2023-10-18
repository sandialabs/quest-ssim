"""Core classes and functions for the user interface."""
from copy import deepcopy
import functools
import hashlib
import itertools
import json
import os
import subprocess
from os import path, makedirs
from pathlib import Path, PurePosixPath

import matplotlib.pyplot as plt
import pandas as pd
import pkg_resources
import tomli
from ssim import grid
from ssim.metrics import MetricManager, MetricTimeAccumulator
from ssim.opendss import DSSModel


# To Do
#
# 1. Add attributes to Project that will be used to generate Configurations
#    - iterator over storage sizes
#    - iterator over storage locations
#    - set of metrics for all configurations
#    - how is each storage device controlled?
# 1.5. Gereric MetricConfiguration class?
# 2. Add basic Configuration implementation
# 3. Implement Configuration.evaluate()

def __eq_maybe_none(v1, v2) -> bool:
    """Compares two objects for equality where 0, 1, or both of the arguments
    may be None.

    Parameters
    ----------
    v1:
        The first of two objects to compare.  This argument may be None.
    v2:
        The second of the two objects to compare.  This argument may be None.

    Return
    ------
    bool:
        True if both arguments are None.  False if 1 is None and the other is
        not. Otherwise, the result of v1 == v2.
    """
    if v1 is None:
        return v2 is None

    if v2 is None:
        return False  # we already know v1 is not None.

    return v1 == v2


_DEFAULT_RELIABILITY = {
    # "seed": 1234567,
    "line": {
        "enabled": False
    },
    "switch": {
        "enabled": False
    },
    "generator": {
        "enabled": False,
        "aging": {
            "enabled": False
        },
        "operating_wear_out": {
            "enabled": False
        }
    }
}


class Project:
    """A set of grid configurations that make up a complete study."""

    def __init__(self, name: str):
        self.name = name
        self._grid_model_path = None
        self._grid_model = None
        self._input_file_path = None
        self.storage_devices = []
        self.pvsystems = []
        self._metricMgrs = {}
        self.reliability_params = _DEFAULT_RELIABILITY

    def __eq__(self, other):

        # Should input file path be included?  Maybe not.
        if self.name != other.name or \
            not __eq_maybe_none(self._grid_model_path == other._grid_model_path):  # or \
            # not __eq_maybe_none(self._input_file_path == other._input_file_path):
            return False;

        if len(self.storage_devices) != len(other.storage_devices): return False
        if len(self.pvsystems) != len(other.pvsystems): return False
        if len(self._metricMgrs) != len(other._metricMgrs): return False

        for so in self.storage_devices:
            if not so in other.storage_devices: return False

        for pv in self.pvsystems:
            if not pv in other.pvsystems: return False

        for k, v in self._metricMgrs:
            if k not in other._metricMgrs: return False
            if v != other._metricMgrs[k]: return False

        return True

    def __hash__(self):
        """Produces a hash value for this instance of a Project.

        This only takes into account the core properties of the object, not
        values that store current state during usage.  This is so that inputs
        can be found to be equal or not based only on object "genetics".

        The value produced will be consistent across multiple invocations of
        the python interpeter (non-salted).
        """
        m = hashlib.sha256()

        m.update(self.name.encode())
        if self._grid_model_path is not None:
            m.update(self._grid_model_path.encode())
                
        self.storage_devices.sort(key=lambda x: x.name)
        for so in self.storage_devices:
            m.update(repr(hash(so)).encode())

        self.pvsystems.sort(key=lambda x: x.name)
        for pv in self.pvsystems:
            m.update(repr(hash(pv)).encode())

        for k, v in sorted(self._metricMgrs.items()):
            m.update(k.encode())
            m.update(repr(hash(v)).encode())
            
        h = m.digest()
        return int.from_bytes(h, byteorder='big', signed=False)

    def load_toml_file(self, filename: str):
        """Reads data for this Project from the supplied TOML file.

        Parameters
        ----------
        filename: str
            The full path to the TOML file from which input is to be loaded.
        """
        self._input_file_path = filename
        self.clear_metrics()
        self.clear_options()
        self.clear_pv()

        with open(filename, 'r') as f:
            toml = f.read()

        tdat = tomli.loads(toml)
        self.read_toml(tdat)

    @property
    def base_dir(self):
        return Path(os.path.abspath(self.name))

    @property
    def bus_names(self):
        """Returns a collection of all bus names stored in the current DSS model.

        Returns
        ----------
        list:
            The collection of all bus names contained in the current grid model.
        """
        return [] if self._grid_model is None else self._grid_model.bus_names

    @property
    def line_names(self):
        """Returns a collection of all line names stored in the current DSS model.

        Returns
        ----------
        list:
            The collection of all line names contained in the current grid model.
        """
        return [] if self._grid_model is None else self._grid_model.line_names

    @property
    def storage_names(self):
        return set(device.name for device in self.storage_devices)
    
    @property
    def storage_options(self):
        return self.storage_devices

    @property
    def pv_assets(self):
        return [] if self._grid_model is None else self._grid_model.pvsystems

    @property
    def grid_model(self) -> DSSModel:
        return self._grid_model

    def phases(self, bus):
        return self._grid_model.available_phases(bus)

    def set_grid_model(self, model_path):
        self._grid_model_path = model_path
        if model_path and path.exists(model_path):
            self._grid_model = DSSModel(model_path)

    def write_toml(self) -> str:
        """Writes the properties of this class instance to a string in TOML
           format.

        Returns
        -------
        str:
            A TOML formatted string with the properties of this project instance.
        """
        ret = "[Project]\n"
        ret += f"name = \'{self.name}\'\n"
        ret += f"grid_model_path = \'{self._grid_model_path}\'\n"

        ret += self._reliability_to_toml()

        for so in self.storage_devices:
            ret += so.write_toml()

        for mgrKey in self._metricMgrs:
            mgr = self._metricMgrs[mgrKey]
            ret += mgr.write_toml(mgrKey)

        return ret

    def read_toml(self, tomlData: dict):
        """Reads the properties of this class instance from a TOML formated dictionary.

        Parameters
        -------
        tomlData
            A TOML formatted dictionary from which to read the properties of
            this class instance.
        """
        projdict = tomlData["Project"]
        self.name = projdict["name"]
        self.set_grid_model(projdict["grid_model_path"])

        sodict = tomlData["storage-options"]
        for sokey in sodict:
            so = StorageOptions(sokey, 3, [], [], [])
            so.read_toml(sokey, sodict[sokey])
            self.add_storage_option(so)

        if "metrics" in tomlData:
            self.__read_metric_map(tomlData["metrics"])

        self.reliability_params = tomlData.get(
            "reliability",
            _DEFAULT_RELIABILITY
        )
        
    def __read_metric_map(self, mdict: dict):
        """Reads the metrics information out of the supplied dictionary.

        The dictionary keys should be manager names and the values shoudl be
        the dictionaries that can be passed to the MetricManager.read_toml
        method.
                
        Parameters
        -------
        mdict: dict
            A TOML formatted dictionary from which to read the properties of
            the metric managers to be contined in this class.
        """
        for ckey in mdict:
            cat_mgr = self.get_manager(ckey)
            if cat_mgr is None:
                cat_mgr = MetricManager()
                self._metricMgrs[ckey] = cat_mgr
            cat_mgr.read_toml(mdict[ckey])

    def _reliability_to_toml(self):
        # Return a toml string containing the reliability params
        top_level_table = ["reliability"]
        ret = [f"[{'.'.join(top_level_table)}]"]
        for model, params in self.reliability_params.items():
            ret.append(f"[{'.'.join(top_level_table + [model])}]")
            for param, value in params.items():
                ret.append(_to_toml(param, value))
        return "\n".join(ret)

    def add_metric(self, category: str, key: str, metric: MetricTimeAccumulator):
        """Adds the supplied metric identified by the supplied key to an existing or
         new metric manager with the supplied category.

        If there is already a metric associated with the category and key, it is
        replaced by the supplied one.  If the supplied metric is None, then any
        existing metric keyed on category and key is removed.

        Parameters
        ----------
        category : str
            The category of the metric manager to which a metric is to be added.
        key : str
            The key of the metric to add.
        metric : MetricTimeAccumulator
            The metric to add to this project keyed on the supplied category and key.
        """
        cat_mgr = self.get_manager(category)
        if cat_mgr is None:
            cat_mgr = MetricManager()
            self._metricMgrs[category] = cat_mgr

        cat_mgr.add_accumulator(key, metric)

    def remove_metric(self, category: str, key: str) -> bool:
        """Removes the metric identified by the supplied key in the supplied category.

        Parameters
        ----------
        category : str
            The category of the metric manager from which a metric is to be removed.
        key : str
            The key of the metric to remove.

        Returns
        -------
        bool:
            True if a removal took place and false if not.  Removal may fail if the
            supplied category does not map to an existing metric manager or if key
            does not map to a metric in the identified manager.
        """
        cat_mgr = self.get_manager(category)
        if cat_mgr is None: return False
        return cat_mgr.remove_accumulator(key)

    def get_metric(self, category: str, key: str) -> MetricTimeAccumulator:
        """Retrieves the metric identified by the supplied key in the supplied category.

        Parameters
        ----------
        category : str
            The category of the metric manager from which a metric is to be retrieved.
        key : str
            The key of the metric to retrieve.

        Returns
        -------
        MetricTimeAccumulator:
            The found metric or None.  Retrieval may fail if the supplied category does
            not map to an existing metric manager or if key does not map to a metric
            in the identified manager.
        """
        cat_mgr = self.get_manager(category)
        if cat_mgr is None: return None
        return cat_mgr.get_accumulator(key)

    def clear_metrics(self):
        """Removes all metrics from all managers and removes all managers."""
        self._metricMgrs.clear();

    def clear_options(self):
        """Removes all storage options from this project."""
        self.storage_devices.clear();

    def clear_pv(self):
        """Removes all storage options from this project."""
        self.pvsystems.clear();

    def get_manager(self, category: str) -> MetricManager:
        """Retrieves the metric manager identified by the supplied category.

        Parameters
        ----------
        category : str
            The category of the metric manager to be retrieved.

        Returns
        -------
        MetricManager:
            The found metric manager or None.  Retrieval may fail if the supplied category
            does not map to an existing metric manager.
        """
        return self._metricMgrs.get(category)

    def remove_storage_option(self, storage_options):
        """Removes the supplied storage option from this project if found.
        
        Parameters
        ----------
        storage_options
            The storage option object to be removed.
        """
        self.storage_devices.remove(storage_options)

    def add_storage_option(self, storage_options):
        self.storage_devices.append(storage_options)

    def configurations(self):
        """Return an iterator over all grid configurations to be evaluated."""
        for storage_configuration in self._storage_configurations():
            storage_devices, inv_controls = _safe_unzip(storage_configuration)
            inv_controls = list(
                filter(lambda ic: ic is not None, inv_controls)
            )
            yield Configuration(
                self._grid_model_path,
                self._metricMgrs,
                self.pvsystems,
                storage_devices,
                inv_controls,
                reliability=self.reliability_params
            )

    def _storage_configurations(self):
        print(f"Project._storage_configurations() - device list: {self.storage_devices}")
        return itertools.product(
            *(storage_options.configurations()
              for storage_options in self.storage_devices)
        )

    def num_configurations(self):
        """Return the total number of configurations in this project."""
        return functools.reduce(
            lambda ess, acc: ess.num_configurations * acc,
            self.storage_devices,
            1
        )

    def evaluated_configurations(self):
        """Return the number of configurations that have been evaluated."""
        raise NotImplementedError()

    def add_reliability_model(self, name: str, params: dict):
        self.reliability_params[name] = params


class StorageControl:
    """Container for information about how a storage device is controlled.

    Parameters
    ----------
    mode : str
        Name of the control mode (valid choices are 'constantpf',
        'voltvar', 'varwatt', 'vv_vw', or 'droop')
    params : dict, optional
        Control-specific parameters.  This dictionary, if provided, should contain
        keys for control modes and each should be paired with a dictionary of parameters.
    """

    _INVERTER_CONTROLS = {'voltvar', 'voltwatt', 'varwatt', 'vv_vw',
                          'constantpf'}

    _EXTERNAL_CONTROLS = {'droop'}

    _CURVE_NAME_X = {
        "voltvar": ("volts",),
        "voltwatt": ("volts",),
        "varwatt": ("vars",),
        "vv_vw": ("vv_volts", "vw_volts")
    }

    _CURVE_NAME_Y = {
        "voltvar": ("vars",),
        "voltwatt": ("watts",),
        "varwatt": ("watts",),
        "vv_vw": ("vv_vars", "vw_watts")
    }

    _CURVE_DESC = {
        "voltvar": "Volt-Var",
        "voltwatt": "Volt-Watt",
        "varwatt": "Var-Watt",
        "vv_vw": "Volt-Var + Var-Watt"
    }

    # Required parameters for each control mode.
    _MODE_PARAMS = {
        "droop": {"p_droop", "q_droop"},
        "voltvar": {"volts", "vars"},
        "voltwatt": {"volts", "watts"},
        "varwatt": {"vars", "watts"},
        "vv_vw": {"vv_volts", "vv_vars", "vw_volts", "vw_watts"},
        "constantpf": {"pf_val"}
    }

    _DEFAULT_PARAMS = {
        "droop": {"p_droop": 500.0, "q_droop": -300.0},
        "voltvar": {"volts": [0.5, 0.95, 1.0, 1.05, 1.5],
                    "vars": [1.0, 1.0, 0.0, -1.0, -1.0]},
        "voltwatt": {"volts": [0.5, 0.95, 1.0, 1.05, 1.5],
                     "watts": [1.0, 1.0, 0.0, -1.0, -1.0]},
        "varwatt": {"vars": [0.5, 0.95, 1.0, 1.05, 1.5],
                    "watts": [1.0, 1.0, 0.0, -1.0, -1.0]},
        "vv_vw": {"vv_volts": [0.5, 0.95, 1.0, 1.05, 1.5],
                  "vv_vars": [1.0, 1.0, 0.0, -1.0, -1.0],
                  "vw_volts": [0.5, 0.95, 1.0, 1.05, 1.5],
                  "vw_watts": [1.0, 1.0, 0.0, -1.0, -1.0]},
        "constantpf": {"pf_val": 0.99}
    }

    def __init__(self, mode, params=None):
        self.mode = mode
        self.params = params or {mode: StorageControl.default_params(mode)}

    @classmethod
    def default_params(cls, mode):
        """Return the default parameters for control mode `mode`.

        Parameters
        ----------
        mode : str
            Control mode for which to return defaults.

        Returns
        -------
        dict
            Dictionary of default control mode parameters.
        """
        return deepcopy(StorageControl._DEFAULT_PARAMS.get(mode, {}))

    @property
    def is_external(self):
        return self.mode not in StorageControl._INVERTER_CONTROLS

    def get_invcontrol(self, storage_name):
        """Return a specification of an InvControl implementing the control.

        Parameters
        ----------
        storage_name : str
            Name of the storage device the inverter control is to be
            applied to.

        Returns
        -------
        grid.InvControlSpecification

        Raises
        ------
        ValueError
            If the control mode cannot be implemented by an inverter
            control.

        """
        if self.mode not in StorageControl._INVERTER_CONTROLS:
            raise ValueError(
                "Cannot convert external control to inverter control."
            )
        curve1, curve2 = self._active_curves()
        return grid.InvControlSpecification(
            name=f"{storage_name}_control",
            der_list=[f"Storage.{storage_name}"],
            inv_control_mode=self.mode,
            function_curve_1=curve1,
            function_curve_2=curve2,
        )

    def _active_curves(self):
        x_names = StorageControl._CURVE_NAME_X[self.mode]
        y_names = StorageControl._CURVE_NAME_Y[self.mode]
        curves = tuple(
            tuple(zip(self.active_params[x],
                      self.active_params[y]))
            for x, y in zip(x_names, y_names)
        )
        return curves[0], curves[1] if len(curves) == 2 else None

    @property
    def active_params(self):
        """Return only the params relevant to the active mode.

        Returns
        -------
        dict
            Dictionary of parameters thar are relevant the the
            currently active control mode.
        """
        return self.params[self.mode]

    def __eq__(self, other):

        if self.mode != other.mode: return False

        smp = self.mode in self.params
        omp = self.mode in other.params
        if smp != omp: return False

        # if it's not in 1, it's not in either and we are done and equal.
        if not smp: return True

        # if we're here, then there are params for the mode in each of self and other
        # compare them now, only for the chosen mode.
        return self.active_params == other.active_params

    def __hash__(self):
        """Produces a hash value for this instance of a StorageControl.

        This only takes into account the core properties of the object, not
        values that store current state during usage.  This is so that inputs
        can be found to be equal or not based only on object "genetics".

        The value produced will be consistent across multiple invocations of
        the python interpeter (non-salted).
        """
        m = hashlib.sha256()
        m.update(self.mode.encode())

        # Iterate in sorted order to make a functional rather than literal hash.
        if self.mode in self.params:
            for k, v in sorted(self.params[self.mode].items()):
                m.update(k.encode())
                m.update(repr(v).encode())

        h = m.digest()
        return int.from_bytes(h, byteorder='big', signed=False)
    
    def write_toml(self, name: str) -> str:
        """Writes the properties of this class instance to a string in TOML
           format.

        Parameters
        ----------
        name : str
            The name of the storage asset for which this is the control
            configuration.

        Returns
        -------
        str:
            A TOML formatted string with the properties of this instance.
        """
        ret = f"\n\n[{name}.control-params]\n"
        ret += f"mode = \'{self.mode}\'\n"

        # ret += f"\n\n[{name}.control-mode.params]\n"
        for key in self.params:
            ret += f"\n\n[{name}.control-params.{key}]\n"

            kmap = self.params[key]
            for pkey in kmap:
                ret += f"\"{pkey}\" = {str(kmap[pkey])}\n"

        return ret

    def read_toml(self, tomlData):
        """Reads the properties of this class instance from a TOML formated dictionary.

        Parameters
        -------
        tomlData
            A TOML formatted dictionary from which to read the properties of this class
            instance.
        """
        for key in tomlData:
            if key == "mode":
                self.mode = tomlData[key]
            else:
                self.params[key] = tomlData[key]

    def validate(self) -> str:
        if self.mode not in StorageControl._INVERTER_CONTROLS:
            return None
        return self._check_curves()

    def _check_curves(self):
        names_x = StorageControl._CURVE_NAME_X[self.mode]
        names_y = StorageControl._CURVE_NAME_Y[self.mode]
        curvedesc = StorageControl._CURVE_DESC[self.mode]
        for name_x, name_y in zip(names_x, names_y):
            if name_x not in self.active_params:
                return (f'Unable to find control param list named "{name_x}".'
                        '  This is an application error.')
            if name_y not in self.active_params:
                return (f'Unable to find control param list named "{name_y}".'
                        '  This is an application error.')
            xs = self.active_params[name_x]
            ys = self.active_params[name_y]
            error = self._check_curve(curvedesc, xs, ys)
            if error is not None:
                return error

    def _check_curve(self, curvedesc, xs, ys):
        if not isinstance(xs, list):
            return (f'Expected a list of x-values for "{curvedesc}".'
                    ' Found value is not a list')
        if not isinstance(ys, list):
            return (f'Expected a list of y-values for "{curvedesc}".'
                    ' Found value is not a list')
        if len(xs) != len(ys):
            return (f"There is a different number of x-values ({len(xs)})"
                    f" and y-values ({len(ys)})")
        if len(xs) < 2:
            return ('There must be at least 2 points defined for '
                    f' a "{curvedesc}" control curve')
        if any(x is None for x in xs):
            return (f'There is at least 1 null x value in the "{curvedesc}" '
                    'control curve.  There can be none.')
        if any(y is None for y in ys):
            return (f'There is at least 1 null y value in the "{curvedesc}" '
                    'control curve.  There can be none.')
        if len(set(xs)) != len(xs):
            return (f'There are duplicate x values in the "{curvedesc}" '
                    'control curve.  They must be unique')


class StorageOptions:
    """Set of configuration options available for a specific device.

    Parameters
    ----------
    name : str
        Name of the device.
    num_phases: int
        Number of phases this device must be connected to.
    power : iterable of float
        Options for maximum power capacity of the device. [kW]
    duration : iterable of float
        Options for how long this device can sustain its maximum power
        output before it is depleted. [hours]
    busses : iterable of str
        Busses where this device can be connected.
    min_soc : float, default 0.2
        Minimum state of charge this device will be allowed to
        discharge to.
    max_soc : float, default 0.8
        Maximum state of charge this device will be allowed to
        charge to.
    initial_soc : float, default 0.5
        State of charge at the begining of the simulation.
    soc_model : str, optional
        External model used for device state of charge.
    control : StorageControl, optional
        Controls applied to the device. Defaults to 'droop'.
    required : bool, default True
        If True the device will be included in every configuration.
        Otherwise, the configurations without this device will be
        evaluated.
    """

    def __init__(self, name, num_phases, power, duration, busses,
                 min_soc=0.2,
                 max_soc=0.8,
                 initial_soc=0.5,
                 soc_model=None,
                 control=None,
                 required=True):
        self.name = name
        self.phases = num_phases
        self.power = set(power)
        self.duration = set(duration)
        self.busses = set(busses)
        self.min_soc = min_soc
        self.max_soc = max_soc
        self.initial_soc = initial_soc
        self.control = control or StorageControl('droop')
        self.soc_model = soc_model
        self.required = required

    def __eq__(self, other):

        return self.name == other.name and \
            self.phases == other.phases and \
            self.min_soc == other.min_soc and \
            self.max_soc == other.max_soc and \
            self.initial_soc == other.initial_soc and \
            self.power == other.power and \
            self.duration == other.duration and \
            self.busses == other.busses and \
            self.soc_model == other.soc_model and \
            not __eq_maybe_none(self.control, other.control) and \
            self.required == other.required

    def __hash__(self):
        """Produces a hash value for this instance of a StorageOptions.

        This only takes into account the core properties of the object, not
        values that store current state during usage.  This is so that inputs
        can be found to be equal or not based only on object "genetics".

        The value produced will be consistent across multiple invocations of
        the python interpeter (non-salted).
        """        
        m = hashlib.sha256()
        
        if self.control is not None:
           m.update(repr(hash(self.control)).encode())

        m.update(repr(self.name).encode())
        m.update(repr(self.phases).encode())
        m.update(repr(self.min_soc).encode())
        m.update(repr(self.max_soc).encode())
        m.update(repr(self.initial_soc).encode())
        m.update(repr(self.soc_model).encode())
        m.update(repr(self.required).encode())
        m.update(repr(sorted(self.power)).encode())
        m.update(repr(sorted(self.duration)).encode())
        m.update(repr(sorted(self.busses)).encode())
        h = m.digest()
        return int.from_bytes(h, byteorder='big', signed=False)

    def write_toml(self) -> str:
        """Writes the properties of this class instance to a string in TOML format.

        Returns
        -------
        str:
            A TOML formatted string with the properties of this instance.
        """
        tag = f"storage-options.\"{self.name}\""
        ret = f"\n\n[{tag}]\n"
        ret += f"phases = {str(self.phases)}\n"
        ret += f"required = {str(self.required).lower()}\n"
        ret += f"min_soc = {str(self.min_soc)}\n"
        ret += f"max_soc = {str(self.max_soc)}\n"
        ret += f"initial_soc = {str(self.initial_soc)}\n"
        buslst = "'" + "','".join(self.busses) + "'"
        ret += f"busses = [{str(buslst)}]\n"
        ret += f"power = [{str(', '.join(map(str, self.power)))}]\n"
        ret += f"duration = [{str(', '.join(map(str, self.duration)))}]\n"

        if self.control: ret += self.control.write_toml(tag)
        return ret

    def read_toml(self, name: str, tomlData):
        """Reads the properties of this class instance from a TOML formated dictionary.

        Parameters
        -------
        name: str
            The name of the storage asset for which this is the option description.
        tomlData
            A TOML formatted dictionary from which to read the properties of this class
            instance.
        """
        self.phases = tomlData["phases"]
        self.required = tomlData["required"]
        self.min_soc = tomlData["min_soc"]
        self.max_soc = tomlData["max_soc"]
        self.initial_soc = tomlData["initial_soc"]
        self.busses = set(tomlData["busses"])
        self.power = set(tomlData["power"])
        self.duration = set(tomlData["duration"])

        if "control-params" in tomlData:
            self.control.read_toml(tomlData["control-params"])

    def add_bus(self, bus: str):
        """Adds the supplied bus name to the list of bus names in this storage
            option.

        Parameters
        ----------
        bus
            The name of the bus to add to this storage options bus list.
        """
        self.busses.add(bus)
        
    def remove_bus(self, bus: str):
        """Removes the supplied bus name from the list of bus names in this
            storage option.

        Parameters
        ----------
        bus
            The name of the bus to remove from this storage options bus list.
        """
        self.busses.discard(bus)

    def add_power(self, power: float) -> bool:
        """Adds a new power value (kW) to the list of allowed power values
        for this storage configuration.

        If the supplied power value already exists, then nothing happens.
        Duplicates are not added.

        Parameters
        -------
        power: float
            The power value to add to the list of possible power values for this
            storage element.

        Returns
        -------
        bool:
            True if the power value is successfully added and false otherwise.
        """
        initlen = len(self.power)
        self.power.add(power)
        return initlen != len(self.power)

    def add_duration(self, duration: float) -> bool:
        """Adds a new duration value (hours) to the list of allowed duration values
        for this storage configuration.

        If the supplied duration value already exists, then nothing happens.
        Duplicates are not added.

        Parameters
        -------
        power: float
            The duration value to add to the list of possible duration values for this
            storage element.

        Returns
        -------
        bool:
            True if the duration value is successfully added and false otherwise.
        """
        initlen = len(self.duration)
        self.duration.add(duration)
        return initlen != len(self.duration)

    @property
    def name_valid(self) -> bool:
        """Tests to see if the name stored in this class is valid.

        To be valid, the name must be a vaild OpenDSS name.  See the
        is_valid_opendss_name function for more details.

        Returns
        -------
        bool:
            True if self.name is a valid name for a storage object and
            False otherwise.
        """
        return is_valid_opendss_name(self.name)

    def validate_soc_values(self) -> str:
        """Checks to see that the SOC values stored in this class are valid values.

        To be valid, the min SOC must be less than the max and all values
        (min, max, and initial) must be in the range [0, 1].

        Returns
        -------
        str:
            A string indicating any errors in the SOC inputs or None
            if there are no issues.
        """
        if self.min_soc >= self.max_soc:
            return "The minimum SOC must be less than the maximum."

        if self.initial_soc > 1.0:
            return "The initial SOC must be less than 100%."

        if self.initial_soc < 0.0:
            return "The initial SOC must be greater than 0%."

        if self.max_soc > 1.0:
            return "The maximum SOC must be less than 100%."

        if self.max_soc < 0.0:
            return "The maximum SOC must be greater than 0%."

        if self.min_soc > 1.0:
            return "The minimum SOC must be less than 100%."

        if self.min_soc < 0.0:
            return "The minimum SOC must be greater than 0%."

        return None

    def validate_name(self) -> str:
        """Checks to see that the name stored in this class is valid.

        To be valid, the name must be a vaild OpenDSS name.  See the
        name_valid property for more details.

        Returns
        -------
        str:
            A string indicating any errors in the name input or None
            if there are no issues.
        """
        return None if self.name_valid else \
            "Storage asset name is invalid.  The name can contain no spaces, " + \
            "newlines, periods, tabs, or equal signs.  It also cannot be empty."

    def validate_power_value(self, value: float) -> str:
        """Checks to see that the supplied power value is valid for use in this class.

        To be valid, the supplied power value must be greater than 0.  No check is done
        here to be sure that the supplied value is not already in the list.

        Parameters
        ----------
        value: float
            The value to test for usability as a power value for this class.

        Returns
        -------
        str:
            A string indicating the any error with the supplied power value or None
            if there are no issues.
        """
        return None if value > 0.0 \
            else "Power values cannot be less than or equal to 0 kW."

    def validate_duration_value(self, value: float) -> str:
        """Checks to see that the supplied duration value is valid for use in this class.

        To be valid, the supplied duration value must be greater than 0.  No check is done
        here to be sure that the supplied value is not already in the list.

        Parameters
        ----------
        value: float
            The value to test for usability as a duration value for this class.

        Returns
        -------
        str:
            A string indicating the any error with the supplied duration value or None
            if there are no issues.
        """
        return None if value > 0.0 \
            else "Duration values cannot be less than or equal to 0 hours."

    def validate_power_values(self) -> str:
        """Checks to see that the power values stored in this class are valid.

        To be valid, there must be at least 1 power value and all power values must
        pass the test in validate_power_value.

        Returns
        -------
        str:
            A string indicating the first error found in the power values or None
            if there are no issues.
        """
        if len(self.power) == 0:
            return "No power values provided."

        for val in self.power:
            vv = self.validate_power_value(val)
            if vv: return vv

        return None

    def validate_duration_values(self) -> str:
        """Checks to see that the duration values stored in this class are valid.

        To be valid, there must be at least 1 duration value and all duration values must
        pass the test in validate_duration_value.

        Returns
        -------
        str:
            A string indicating the first error found in the duration values or None
            if there are no issues.
        """
        if len(self.duration) == 0:
            return "No duration values provided."

        for val in self.duration:
            vv = self.validate_duration_value(val)
            if vv: return vv

        return None

    def validate_controls(self) -> str:
        return self.control.validate()

    def validate_busses(self) -> str:
        """Checks to see that the list of busses stored in this class is valid.

        To be valid, there must be at least 1 bus.

        Returns
        -------
        str:
            A string indicating the first error found while checking the bus list
            or None if there are no issues.
        """
        if len(self.busses) == 0:
            return "No busses selected"

        # Don't have access to the master bus list here (I don't think)
        # but it would be good to check them all against that list.

        return None

    @property
    def valid(self):
        return (self.name_valid
                and self.validate_duration_values() is None
                and self.validate_power_values() is None
                and self.validate_busses() is None)

    @property
    def num_configurations(self):
        """Total number of possible configurations for this device."""
        cfgs = len(self.busses) * len(self.power) * len(self.duration)
        if self.required:
            return cfgs
        return cfgs + 1

    @property
    def _inverter_control(self):
        if self.control.is_external:
            return None
        return self.control.get_invcontrol(self.name)

    def configurations(self):
        """Return a generator that yields all possible configurations.

        Yields tuples where the first element is a
        :py:class:`grid.StorageSpecification` and the second element
        is a :py:class:`grid.InvControlSpecification`. If no inverter
        control is defined then the sencond element will be None.

        """
        inv_control = self._inverter_control
        for bus in self.busses:
            for power in self.power:
                for duration in self.duration:
                    # TODO need to add other parameters (e.g. min/max soc)
                    yield (
                        grid.StorageSpecification(
                            self.name,
                            bus,
                            duration * power,
                            power,
                            self.control.mode if inv_control is None else None,
                            soc=self.initial_soc,
                            controller_params=self.control.active_params,
                            params={"kva": power}
                        ),
                        self._inverter_control
                    )
        if not self.required:
            yield None, None


class MetricCongifuration:
    """Configuration of a single metric.

    .. note::
       Only voltage metrics are supported at this time.
    """

    def __init__(self, bus, objective, lower_limit, upper_limit):
        """Constructs a new MetricConfiguration object.

        Parameters
        ----------
        bus
            The bus for which this metric configuration is being defined.
        objective
            The objective value for this metric configuration.  This is the target
            value which if achieved, results in full satisfaction.
        lower_limit
            The worst acceptable value for this metric on the low side of the objective.
        upper_limit
            The worst acceptable value for this metric on the high side of the objective.
        """
        self.bus = bus
        self.upper_limit = upper_limit
        self.lower_limit = lower_limit
        self.objective = objective

    def __eq__(self, other):
        return __eq_maybe_none(self.bus, other.bus) and \
            self.lower_limit == other.lower_limit and \
            self.upper_limit == other.upper_limit and \
            self.objective == other.objective

    def __hash__(self):
        """Produces a hash value for this instance of a MetricCongifuration.

        This only takes into account the core properties of the object, not
        values that store current state during usage.  This is so that inputs
        can be found to be equal or not based only on object "genetics".

        The value produced will be consistent across multiple invocations of
        the python interpeter (non-salted).
        """
        m = hashlib.sha256()

        if self.bus is not None:
            m.update(self.bus.encode())

        m.update(repr(self.upper_limit).encode())
        m.update(repr(self.lower_limit).encode())
        m.update(repr(self.objective).encode())
        h = m.digest()
        return int.from_bytes(h, byteorder='big', signed=False)

    def to_dict(self):
        """Return a dict representation of this metric."""
        return {
            "name": self.bus,
            "objective": self.objective,
            "limit": self.limit
        }


class Configuration:
    """A specific grid configuration to be evaluated."""

    def __init__(self, grid, metrics, pvsystems,
                 storage_devices, inverter_controls,
                 reliability=None,
                 sim_duration=24):
        self.results = None
        self.grid = grid
        self.metrics = metrics
        self.pvsystems = pvsystems
        self.storage = storage_devices
        self.inv_controls = inverter_controls
        self.sim_duration = sim_duration
        self.reliability = reliability
        self._grid_path = None
        self._federation_path = None
        self._proc = None
        self._workdir = Path(".")

    def __eq__(self, other):
        """Compares this instance of a Configuration to another for functional
        equality.

        Funcitonal equality means "effectively equal", not necessarily literaly equal.
        As an example, in some cases, it may not matter if the order of some objects
        in a collection be the same, as long as there is an equivalent object in each.

        The intent is to ensure that if this returns true, then an analysis using this
        object will result in the same answer as an analysis using the other.

        Parameters
        ----------
        other:
            The other configuration to compare to this one for equality.

        Return
        ------
        bool:
            True if the other is functionally equal to this and false otherwise.
        """
        if self.grid != other.grid or \
                self.sim_duration != other.sim_duration or \
                not __eq_maybe_none(self._grid_path, other._grid_path) or \
                not __eq_maybe_none(self._federation_path, other._federation_path) or \
                not __eq_maybe_none(self._workdir, other._workdir):
            return False

        if len(self.metrics) != len(other.metrics): return False
        if len(self.pvsystems) != len(other.pvsystems): return False
        if len(self.storage) != len(other.storage): return False

        for k, v in self.metrics:
            if k not in other.metrics: return False
            if v != other._metricMgrs[k]: return False

        for pv in self.pvsystems:
            if not pv in other.pvsystems: return False

        for ss in self.storage:
            if not ss in other.storage: return False

    def __hash__(self):
        """Produces a hash value for this instance of a Configuration.

        This only takes into account the core properties of the object, not
        values that store current state during usage.  This is so that inputs
        can be found to be equal or not based only on object "genetics".

        The value produced will be consistent across multiple invocations of
        the python interpeter (non-salted).
        """
        m = hashlib.sha256()

        if self.grid is not None:
            m.update(self.grid.encode())

        m.update(repr(self.sim_duration).encode())
        
        if self._grid_path is not None:
            m.update(self._grid_path.encode())
            
        if self._federation_path is not None:
            m.update(self._federation_path.encode())
    
        if self._workdir is not None:
            m.update(self._workdir.encode())
    
        for k, v in sorted(self._metricMgrs.items()):
            m.update(k.encode())
            m.update(repr(hash(v)).encode())
            
        for so in self.storage.sort(key=lambda x: x.name):
            m.update(repr(hash(so)).encode())
            
        for pv in self.pvsystems.sort(key=lambda x: x.name):
            m.update(repr(hash(pv)).encode())

        h = m.digest()
        return int.from_bytes(h, byteorder='big', signed=False)

    @property
    def id(self):
        h = hashlib.sha1()
        for ess in self.storage:
            if ess is None:
                h.update(b"None")
            else:
                h.update(
                    bytes(
                        str((ess.name,
                             ess.bus,
                             ess.phases,
                             ess.kwh_rated,
                             ess.kw_rated,
                             ess.controller)),
                        "utf-8"
                    )
                )
        return str(h.hexdigest())

    def evaluate(self, basepath="."):
        """Run the simulator for this configuration"""
        self._workdir = Path(basepath).absolute() / self.id
        makedirs(self._workdir, exist_ok=True)
        self._grid_path = PurePosixPath(self._workdir / "grid.json")
        self._federation_path = self._workdir / "federation.json"
        self._write_configuration()
        self._run()
        self._mark_done()
        return self._load_results()

    def wait(self):
        if self._proc is None:
            raise RuntimeError(
                "Tried to wait on evaluation, but no evaluation running"
            )
        return self._proc.wait()

    def _write_configuration(self):
        with open(self._grid_path, 'w') as grid_file:
            json.dump(self._grid_config(), grid_file)
        with open(self._federation_path, 'w') as federation_file:
            json.dump(self._federation_config(), federation_file)

    def _run(self):
        self._proc = subprocess.Popen(
            ["helics", "run", "--path", str(self._federation_path)],
            cwd=self._workdir
        )

    def _mark_done(self):
        (self._workdir / "evaluated").touch()

    def _load_results(self):
        # TODO load the output files/data into a results object (maybe
        # just create a results object that load the data lazily to
        # keep memory usage low)'
        pass

    def _grid_config(self):
        config = {}
        self._configure_grid_model(config)
        self._configure_storage(config)
        self._configure_inverters(config)
        self._configure_pv(config)
        self._configure_inverters(config)
        self._configure_reliability(config)
        self._configure_metrics(config)
        return config

    def _configure_grid_model(self, config):
        config["dss_file"] = self.grid
        return config

    def _configure_storage(self, config):
        config["storage"] = list(
            ess.to_dict()
            for ess in self.storage if ess is not None
        )
        return config

    def _configure_pv(self, config):
        config["pvsystem"] = list(
            pv.to_dict()
            for pv in self.pvsystems
        )
        return config

    def _configure_inverters(self, config):
        config["invcontrol"] = list(
            inv.to_dict()
            for inv in self.inv_controls
        )
        return config

    def _configure_reliability(self, config):
        config["reliability"] = self.reliability
        return config

    def _configure_metrics(self, config):
        voltage_metrics = self.metrics.get("Bus Voltage")
        if voltage_metrics is not None:
            config["busses_to_measure"] = voltage_metrics.to_dicts()
        return config

    def _federation_config(self):
        config = {"name": str(self.id)}
        self._configure_broker(config)
        self._configure_federates(config)
        return config

    def _configure_broker(self, config):
        # Simplest possible configuration: tell helics cli to
        # automatically start the broker.
        config["broker"] = True
        return config

    def _configure_federates(self, config):
        # specify the EMS federate ?
        # lookup and specify the path(s) the the federate config files
        config["federates"] = [
                                  _federate_spec(
                                      "metrics",
                                      f"metrics-federate"
                                      f" {self._grid_path}"
                                      f" {_get_federate_config('metrics')}"
                                  ),
                                  _federate_spec(
                                      "logger",
                                      f"logger-federate --hours {self.sim_duration}"
                                      f" {self._grid_path}"
                                      f" {_get_federate_config('logger')}"
                                  ),
                                  _federate_spec(
                                      "grid",
                                      f"grid-federate --hours {self.sim_duration}"
                                      f" {self._grid_path}"
                                      f" {_get_federate_config('grid')}"
                                  ),
                                  _federate_spec(
                                      "reliability",
                                      f"reliability-federate --hours {self.sim_duration}"
                                      f" {self._grid_path}"
                                      f" {_get_federate_config('reliability')}"
                                  )
                              ] + list(
            _storage_federate_spec(
                ess.name, self._grid_path, self.sim_duration)
            for ess in self.storage if ess is not None
        )
        return config

    def is_evaluated(self):
        return self.results is not None


def _to_toml(key, value):
    # turn a key, value pair into a valid one-line toml string
    if isinstance(value, dict):
        value = _dict_to_toml(value)
    if isinstance(value, bool):
        value = str(value).lower()
    return f"{key} = " + str(value)


def _dict_to_toml(value):
    table = ", ".join(
        _to_toml(key, val)
        for key, val in value.items()
    )
    return "{" + table + "}"


def _storage_federate_spec(name, grid_path, sim_duration):
    return _federate_spec(
        name,
        f"storage-federate {name} --hours {sim_duration}"
        f" {grid_path} {_get_federate_config('storage')}"
    )


def _federate_spec(name, cmd, directory=".", host="localhost"):
    return {
        "directory": directory,
        "host": host,
        "name": name,
        "exec": cmd
    }


def _safe_unzip(xs):
    if len(xs) == 0:
        return [], []
    return zip(*xs)


def _get_federate_config(federate):
    """Return the path to the configuration file for the federate type.

    Parameters
    ----------
    federate : str
        Type of federate ('metrics', 'storage', 'reliability', 'logger',
        'grid', 'ems').
    """
    if federate not in {'metrics', 'storage', 'reliability',
                        'logger', 'grid', 'ems'}:
        raise ValueError(f"invalid federate type '{federate}'.")
    return PurePosixPath(
        Path(pkg_resources.resource_filename(
            "ssim.federates", f"{federate}.json"))
    )


class ProjectResults:
    """Container of all results for a project.

    Parameters
    ----------
    project : Project
       Project that the results belong to.
    """

    def __init__(self, project):
        self.base_dir = project.base_dir

    def results(self):
        # Iterate over the resulted configurations and yield iterator of Results
        for configuration_dir in self._resulted_configurations():
            yield Results(self.base_dir / configuration_dir)

    def _resulted_configurations(self):
        # results from each configuration has its own directory
        for item in os.listdir(self.base_dir):
            # check to see if the directory is from a configuration
            if not self._is_configuration_dir(item):
                continue
            # check to see if the configuration has been completely evaluated
            if self._is_evaluated(item):
                yield item

    def _is_configuration_dir(self, item):
        if item in {'.', '..'}:
            return False
        return (
                os.path.exists(self.base_dir / item / "federation.json")
                and os.path.exists(self.base_dir / item / "grid.json")
        )

    def _is_evaluated(self, item):
        return os.path.exists(self.base_dir / item / "evaluated")

    # TO DO: Add methods for the plotting function
    def plot_metrics(self):
        for result in self.results():
            col_names, metric_value, df_metrics = result.metrics_log()
            return col_names, metric_value, df_metrics

    def plot_accumulated_metrics(self):
        config_count = 0
        for result in self.results():
            _, metric_value, _ = result.metrics_log()
            fig = plt.figure()
            plt.plot(config_count, metric_value)
            plt.xlabel('Configuration ID')
            plt.ylabel('Accumated Metric')
            plt.title('Comparison of Metric for Different Configurations')
            config_count += 1
            return fig


_OPENDSS_ILLEGAL_CHARACTERS = "\t\n .="


def is_valid_opendss_name(name: str) -> bool:
    """Return true if `name` is a valid name in OpenDSS.

    OpenDSS names may not contain whitespace, '.', or '='.
    """
    return (
            len(name) > 0
            and not any(c in _OPENDSS_ILLEGAL_CHARACTERS for c in name)
    )


class Results:
    """Results from simulating a specific configuration."""

    def __init__(self, config_dir):
        self.config_dir = config_dir

    def _extract_data(self, csv_file):
        df_extracted_data = pd.read_csv(self.config_dir / csv_file)
        # extract column names
        col_names = list(df_extracted_data.columns)
        # extract all datapoints as a pandas dataframe
        num_rows = df_extracted_data.shape[0]
        data = df_extracted_data.iloc[0:num_rows - 1]
        return col_names, data

    def bus_voltages(self):
        """Returns name of columns (bus names) and the time-series bus
        voltages as a pandas dataframe."""
        bus_names, bus_voltages = self._extract_data("bus_voltage.csv")
        return bus_names, bus_voltages

    def grid_state(self):
        """Returns name of columns (grid states) and the time-series data
        as a pandas dataframe."""
        states, state_data = self._extract_data("grid_state.csv")
        return states, state_data

    def pde_loading(self):
        """Returns name of the columns (power delivery elements with
        the OpenDSS model) and the loading of the power delievery elements
        as a pandas dataframe."""
        pde_elements, pde_loading = self._extract_data("pde_loading.csv")
        return pde_elements, pde_loading

    def storage_state(self):
        """Returns name of the columns (states specific to storage devices
        in OpendDSS model) and the time-series data as a pandas dataframe."""
        storage_state_file = Path(self.config_dir / "storage_power.csv")
        if storage_state_file.is_file():
            storage_states, storage_state_data = self._extract_data("storage_power.csv")
        else:
            storage_states, storage_state_data = [], []
        return storage_states, storage_state_data

    def storage_voltages(self):
        """Returns name of the columns (buses) where storage is placed and
        voltages at those buses as a pandas dataframe"""
        storage_voltages_file = Path(self.config_dir / "storage_voltage.csv")
        if storage_voltages_file.is_file():
            storage_buses, storage_voltages = self._extract_data("storage_voltage.csv")
        else:
            storage_buses, storage_voltages = [], []
        return storage_buses, storage_voltages

    def metrics_log(self):
        """Returns name of columns of the logged metrics, the accumulated value
        of the metric, and the time-series log as a pandas dataframe."""
        df_metrics = pd.read_csv(self.config_dir / "metric_log.csv")
        # extract column names
        col_names = list(df_metrics.columns)
        num_rows = df_metrics.shape[0]
        # extract accumulated value of the metric from the last row
        accumulated_metric = df_metrics.iloc[-1:].loc[num_rows - 1, 'time']
        # extract all the datapoints as a pandas dataframe
        data = df_metrics.iloc[0: num_rows - 1]
        return col_names, accumulated_metric, data
