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
        self._grid_model = None
        self._storage_devices = []
        self._pvsystems = []
        self._metrics = []

    @property
    def bus_names(self):
        return self._grid_model.bus_names

    def set_grid_model(self, model_path):
        self._grid_model = DSSModel(model_path)

    def add_metric(self, metric):
        self._metrics.append(metric)

    def add_storage_option(self, storage_options):
        self._storage_devices.append(storage_options)

    def configurations(self):
        """Return an iterator over all grid configurations to be evaluated."""
        for storage_configuration in self._storage_configurations():
            yield Configuration(
                self._grid_model,
                self._metrics,
                self._pvsystems,
                storage_configuration
            )

    def _storage_configurations(self):
        return itertools.product(
            *(storage_options.configurations()
              for storage_options in self._storage_devices)
        )

    def num_configurations(self):
        """Return the total number of configurations in this project."""
        return functools.reduce(
            lambda ess, acc: ess.num_configurations * acc,
            self._storage_devices,
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
        self.power = power
        self.duration = duration
        self.busses = busses
        self.min_soc = min_soc
        self.max_soc = max_soc
        self.initial_soc = initial_soc
        self.control = control or StorageControl(
            'droop',
            {'real_gain': 500, 'reactive_gain': -300}  # completely arbitrary
        )
        self.soc_model = soc_model
        self.required = False

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
        config = {}
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
            for ess in self.storage
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


class Results:
    """Results from simulating a specific configuration."""

    def __init__(self):
        pass
