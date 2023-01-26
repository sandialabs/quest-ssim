"""Core classes and functions for the user interface."""
import functools
import itertools
import json
import tempfile
from os import path
from pathlib import Path
import pkg_resources
import subprocess

from ssim import grid
from ssim.opendss import DSSModel
from ssim.metrics import MetricManager, MetricTimeAccumulator

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


_DEFAULT_RELIABILITY = {
    # "seed": 1234567,
    "line": {
        "mtbf": 1000000,
        "min_repair": 1,
        "max_repair": 10
    },
    "switch": {
        "mtbf": 100,
        "min_repair": 5,
        "max_repair": 8,
        "p_open": 1.0,
        "p_closed": 0.0,
        "p_current": 0.0
    },
    "generator":
    {
        "aging": {
            "mtbf": 5000,
            "min_repair": 1.0,
            "max_repair": 1.0
        },
        "operating_wear_out": {
            "mtbf": 1000,
            "min_repair": 2.0,
            "max_repair": 2.0
        }
    }
}


class Project:
    """A set of grid configurations that make up a complete study."""

    def __init__(self, name: str):
        self.name = name
        self._grid_model_path = None
        self._grid_model = None
        self.storage_devices = []
        self._pvsystems = []
        self._metricMgrs = {}

    @property
    def bus_names(self):
        return self._grid_model.bus_names

    @property
    def storage_names(self):
        return set(device.name for device in self.storage_devices)

    @property
    def grid_model(self):
        return self._grid_model

    def phases(self, bus):
        return self._grid_model.available_phases(bus)

    def set_grid_model(self, model_path):
        self._grid_model_path = model_path
        self._grid_model = DSSModel(model_path)

    def write_toml(self) -> str:
        """Writes the properties of this class instance to a string in TOML
           format.

        Returns
        -------
        Limit
            A TOML formatted string with the properties of this project instance.
        """
        ret = "[Project]\n"
        ret += f"name = \'{self.name}\'\n"
        ret += f"grid_model_path = \'{self._grid_model_path}\'\n"

        for so in self.storage_devices:
            ret += so.write_toml()

        for mgrKey in self._metricMgrs:
            mgr = self._metricMgrs[mgrKey]
            ret += mgr.write_toml(mgrKey)

        return ret

    def read_toml(self, tomlData):
        """Reads the properties of this class instance from a TOML formated dictionary.

        Parameters
        -------
        tomlData
            A TOML formatted dictionary from which to read the properties of this class
            instance.
        """
        projdict = tomlData["Project"]
        self.name = projdict["name"]
        self._grid_model_path = projdict["grid_model_path"]
        self._grid_model = DSSModel(self._grid_model_path)

        sodict = tomlData["storage-options"]
        #for sokey in sodict:
        #    so

        for mkey in tomlData:
            if mkey == "metrics":
                self.__read_metric_map(tomlData[mkey])

    def __read_metric_map(self, mdict):
        for ckey in mdict:
            self.__read_metric_values(mdict[ckey], ckey)

    def __read_metric_values(self, cdict, ckey):
        for bus in cdict:
            mta = MetricTimeAccumulator.read_toml(cdict[bus])
            self.add_metric(ckey, bus, mta)

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

        Returns
        -------
        Success
            True if a removal took place and false if not.  Removal may fail if the
            supplied category does not map to an existing metric manager or if key
            does not map to a metric in the identified manager.
        """
        cat_mgr = self.get_manager(category)
        if cat_mgr is None:
            cat_mgr= MetricManager()
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
        Success
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
        MetricTimeAccumulator
            The found metric or None.  Retrieval may fail if the supplied category does
            not map to an existing metric manager or if key does not map to a metric
            in the identified manager.
        """
        cat_mgr = self.get_manager(category)
        if cat_mgr is None: return None
        return cat_mgr.get_accumulator(key)
    
    def clear_metrics(self):
        """Removes all metrics from all managers and removes all managers.
        """
        self._metricMgrs.clear();

    def get_manager(self, category: str) -> MetricManager:
        """Retrieves the metric manager identified by the supplied category.

        Parameters
        ----------
        category : str
            The category of the metric manager to be retrieved.

        Returns
        -------
        MetricManager
            The found metric manager or None.  Retrieval may fail if the supplied category
            does not map to an existing metric manager.
        """
        return self._metricMgrs.get(category)

    def add_storage_option(self, storage_options):
        self.storage_devices.append(storage_options)

    def configurations(self):
        """Return an iterator over all grid configurations to be evaluated."""
        for storage_configuration in self._storage_configurations():
            yield Configuration(
                self._grid_model_path,
                self._metrics,
                self._pvsystems,
                storage_configuration
            )

    def _storage_configurations(self):
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


class StorageControl:
    """Container for information about how a storage device is controlled.

    Parameters
    ----------
    mode : str
        Name of the control mode (valid choices are 'constantpf',
        'voltvar', 'voltwatt', 'droop')
    params : dict, optional
        Control-specific parameters
    """

    def __init__(self, mode, params):
        self.mode = mode
        self.params = params

    def write_toml(self, name: str)->str:
        """Writes the properties of this class instance to a string in TOML
           format.

        Parameters
        ----------
        name : str
            The name of the storage asset for which this is the control
            configuration.

        Returns
        -------
        Limit
            A TOML formatted string with the properties of this instance.
        """
        ret = f"\n\n[{name}.control-mode]\n"
        ret += f"mode = \'{self.mode}\'\n"

        #ret += f"\n\n[{name}.control-mode.params]\n"
        for key in self.params:
            ret += f"{key} = {str(self.params[key])}\n"

        return ret

    def read_toml(self, name: str, tomlData):
        """Reads the properties of this class instance from a TOML formated dictionary.

        Parameters
        -------
        tomlData
            A TOML formatted dictionary from which to read the properties of this class
            instance.
        """
        keytag = f"{name}.control-mode"

        if keytag in tomlData:
            tomlDat = tomlData[keytag]
            for key in tomlDat:
                if key == "mode":
                    self.mode = tomlDat[key]
                else:
                    self.params[key] = float(tomlDat[key])

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
        self.control = control or StorageControl(
            'droop',
            {'p_droop': 500.0, 'q_droop': -300.0}  # completely arbitrary
        )
        self.soc_model = soc_model
        self.required = required

    def write_toml(self)->str:
        """Writes the properties of this class instance to a string in TOML
           format.

        Returns
        -------
        Limit
            A TOML formatted string with the properties of this instance.
        """
        tag = "storage-options." + self.name
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
        tomlData
            A TOML formatted dictionary from which to read the properties of this class
            instance.
        """
        keytag = f"{name}.control-mode"

        if keytag in tomlData:
            tomlDat = tomlData[keytag]
            for key in tomlDat:
                if key == "mode":
                    self.mode = tomlDat[key]
                else:
                    self.params[key] = float(tomlDat[key])

    def add_bus(self, bus):
        self.busses.add(bus)

    def add_power(self, power: float) -> bool:
        """Adds a new power value (kW) to the list of allowed power values
        for this storage configuration.

        If the supplied power value already exists, then nothing happens.
        Duplicates are not added.

        Returns
        -------
        Success
            True if the power value is successfully added and false otherwise.
        """
        initlen = len(self.power)
        self.power.add(power)
        return initlen != len(self.power)

    def add_duration(self, duration):
        """Adds a new duration value (hours) to the list of allowed duration values
        for this storage configuration.

        If the supplied duration value already exists, then nothing happens.
        Duplicates are not added.

        Returns
        -------
        Success
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
        Success
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
        Error String
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
        Error String
            A string indicating any errors in the name input or None
            if there are no issues.
        """
        return None if self.name_valid else \
            "Storage asset name is invalid.  The name can contain no spaces, " + \
            "newlines, periods, tabs, or equal signs.  It also cannot be empty."

    def validate_power_value(self, value: float) -> str:
        return None if value > 0.0 \
            else "Power values cannot be less than or equal to 0 kW."

    def validate_duration_value(self, value) -> str:
        return None if value > 0.0 \
            else "Duration values cannot be less than or equal to 0 hours."

    def validate_power_values(self) -> str:
        if len(self.power) == 0:
            return "No power values provided."

        for val in self.power:
            vv = self.validate_power_value(val)
            if vv: return vv

        return None

    def validate_duration_values(self) -> str:
        if len(self.duration) == 0:
            return "No duration values provided."

        for val in self.duration:
            vv = self.validate_duration_value(val)
            if vv: return vv

        return None

    def validate_busses(self) -> str:
        if len(self.busses) == 0:
            return "No busses selected"

        # Don't have access to the master bus list here (I don't think)
        # but it would be good to check them all against that list.

        return None

    @property
    def valid(self):
        return (self.name_valid
                and len(self.power) > 0
                and len(self.duration) > 0
                and len(self.busses) > 0)

    @property
    def num_configurations(self):
        """Total number of possible configurations for this device."""
        cfgs = len(self.busses) * len(self.power) * len(self.duration)
        if self.required:
            return cfgs
        return cfgs + 1

    def configurations(self):
        """Return a generator that yields all possible configurations."""
        for bus in self.busses:
            for power in self.power:
                for duration in self.duration:
                    # TODO need to add other parameters (e.g. min/max soc)
                    yield grid.StorageSpecification(
                        self.name,
                        bus,
                        duration * power,
                        power,
                        self.control.mode,
                        soc=self.initial_soc,
                        controller_params=self.control.params
                    )
        if not self.required:
            yield None


class MetricCongifuration:
    """Configuration of a single metric.

    .. note::
       Only voltage metrics are supported at this time.
    """

    def __init__(self, bus, objective, limit):
        self.bus = bus
        self.limit = limit
        self.objective = objective

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
                 storage_devices, sim_duration=24):
        self.results = None
        self.grid = grid
        self.metrics = metrics
        self.pvsystems = pvsystems
        self.storage = storage_devices
        self.sim_duration = sim_duration
        self._id = None
        self._grid_path = None
        self._federation_path = None
        self._workdir = Path(".")

    def evaluate(self, basepath=None):
        """Run the simulator for this configuration"""
        self._workdir = Path(tempfile.mkdtemp(dir=basepath))
        self._id = path.basename(self._workdir)
        self._grid_path = self._workdir / "grid.json"
        self._federation_path = self._workdir / "federation.json"
        self._write_configuration()
        self._run()
        return self._load_results()

    def _write_configuration(self):
        with open(self._grid_path) as grid_file:
            json.dump(self._grid_config(), grid_file)
        with open(self._federation_path) as federation_file:
            json.dump(self._federation_config(), federation_file)

    def _run(self):
        self._proc = subprocess.Popen(
            ["helics", "run", "--path", str(self._federation_path)],
            cwd=self._workdir
        )

    def _load_results(self):
        # TODO load the output files/data into a results object (maybe
        # just create a results object that load the data lazily to
        # keep memory usage low)'
        pass

    def _grid_config(self):
        config = {}
        self._configure_grid_model(config)
        self._configure_storage(config)
        self._configure_pv(config)
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

    def _configure_reliability(self, config):
        # TODO user specified reliability params
        config["reliability"] = _DEFAULT_RELIABILITY
        return config

    def _configure_metrics(self, config):
        config["busses_to_measure"] = [metric.to_dict()
                                       for metric in self.metrics]
        return config

    def _federation_config(self):
        config = {"name": str(self._id)}
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
                f"metrics-federate --hours {self.sim_duration}"
                f" {self._grid_path}"
                f" {_get_federate_config('metrics')}"
            ),
            _federate_spec(
                "logger",
                f"logger-federate --hours {self.sim_duration}"
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
    return pkg_resources.resource_filename(
        "ssim.federates", f"{federate}.json")


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

    def __init__(self):
        pass
