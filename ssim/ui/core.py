"""Core classes and functions for the user interface."""
import functools
import itertools
import json
import os
import pandas as pd
import matplotlib.pyplot as plt
import tempfile
from os import path
from pathlib import Path, PurePosixPath
import pkg_resources
import subprocess

from ssim import grid
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
        self._metrics = []

    @property
    def base_dir(self):
        return Path(os.path.abspath(self.name))

    @property
    def bus_names(self):
        return self._grid_model.bus_names

    def phases(self, bus):
        return self._grid_model.available_phases(bus)

    def set_grid_model(self, model_path):
        self._grid_model_path = model_path
        self._grid_model = DSSModel(model_path)

    def add_metric(self, metric):
        self._metrics.append(metric)

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
            {'p_droop': 500, 'q_droop': -300}  # completely arbitrary
        )
        self.soc_model = soc_model
        self.required = False

    def add_bus(self, bus):
        self.busses.add(bus)

    def add_power(self, power):
        self.power.add(power)

    def add_duration(self, duration):
        self.duration.add(duration)

    @property
    def valid(self):
        return (len(self.power) > 0
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
        self._proc = None
        self._workdir = Path(".")

    def evaluate(self, basepath=None):
        """Run the simulator for this configuration"""
        if basepath is not None:
            os.makedirs(basepath, exist_ok=True)
        self._workdir = Path(os.path.abspath(tempfile.mkdtemp(dir=basepath)))
        self._id = path.basename(self._workdir)
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
        config["invcontrol"] = []
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
        data = df_extracted_data.iloc[0:num_rows-1]
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
        storage_states, storage_state_data = self._extract_data("storage_power.csv")
        return storage_states, storage_state_data

    def storage_voltages(self):
        """Returns name of the columns (buses) where storage is placed and 
        voltages at those buses as a pandas dataframe"""
        storage_buses, storage_voltages = self._extract_data("storage_voltage.csv")
        return storage_buses, storage_buses

    def metrics_log(self):
        """Returns name of columns of the logged metrics, the accumulated value
        of the metric, and the time-series log as a pandas dataframe."""
        df_metrics = pd.read_csv(self.config_dir / "metric_log.csv")
        # extract column names
        col_names = list(df_metrics.columns)
        num_rows = df_metrics.shape[0]
        # extract accumulated value of the metric from the last row
        accumulated_metric = df_metrics.iloc[-1:].loc[num_rows - 1,'time']
        # extract all the datapoints as a pandas dataframe
        data = df_metrics.iloc[0 : num_rows-1]
        return col_names, accumulated_metric, data