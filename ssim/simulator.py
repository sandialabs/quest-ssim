"""Functions for initializing and running the simulation."""
import logging
import time
from multiprocessing import Process
from typing import Optional

from helics import (
    helicsCreateBroker,
    helicsCreateFederateInfo,
    helicsCreateValueFederate,
    HelicsFederateInfo,
    HelicsValueFederate
)

from ssim.grid import GridSpecification, StorageSpecification
from ssim.federates import storage, opendss, logger, reliability


_BROKER_NAME = "ssimbroker"


def _helics_broker(num_federates):
    """Start the helics broker"""
    logging.basicConfig(format="[broker] %(levelname)s - %(message)s",
                        level=logging.DEBUG)
    logging.debug(f"starting broker {_BROKER_NAME}")
    broker = helicsCreateBroker("zmq", "", f"-f{num_federates}"
                                           f" --name={_BROKER_NAME}")
    logging.debug(f"created broker: {broker}")
    logging.debug(f"broker connected: {broker.is_connected()}")
    while broker.is_connected():
        # busy wait until the broker exits.
        time.sleep(1)


def _create_fedinfo(core_name: str,
                    core_type: str = "zmq",
                    num_federates: int = 1) -> HelicsFederateInfo:
    """Return a new HELICS federate info structure.

    Parameters
    ----------
    core_name : str
        Name of the helics core responsible for this federate.
    core_type : str, default "zmq"
        HELICS core type.
    num_federates : int, default 1
        Number of federates under the core responsible for this federate.

    Returns
    -------
    HelicsFederateInfo
        HelicsFederateInfo structure. The returned structure is sufficiently
        initialized to be used to construct a federate, but may be modified
        if further customization is needed.
    """
    fedinfo = helicsCreateFederateInfo()
    fedinfo.core_name = core_name
    fedinfo.core_type = core_type
    fedinfo.core_init = f"-f{num_federates}"
    return fedinfo


def _create_value_federate(name: str,
                           core_name: Optional[str] = None,
                           core_type: str = "zmq",
                           num_federates: int = 1) -> HelicsValueFederate:
    """Create a new core and a new federate.

    Parameters
    ----------
    name : str
        Name of the federate.
    core_name : str, optional
        Name of the core the federate belongs to.
    core_type : str, default "zmq"
        Core type.
    num_federates : int, default 1
        Number of federates that will be started under the new core.
    """
    fedinfo = _create_fedinfo(
        core_name or f"{name}_core",
        core_type,
        num_federates
    )
    return helicsCreateValueFederate(name, fedinfo)


def _start_federate(name: str,
                    target: callable,
                    federate_args: tuple = tuple(),
                    federate_kwargs: dict = None,
                    loglevel: int = logging.WARN):
    """Start a value federate.

    Parameters
    ----------
    name : str
        Name of the federate.
    target : callable
        Invoked to run the federate. Must accept a HELICS federate handle
        as its first argument, `federate_args` are passed as positional
        arguments following the federate handle.
    federate_kwargs : dict
        Additional keyword arguments to be passed to `target`.
    loglevel : int
        Log level for the federate.
    """
    if federate_kwargs is None:
        federate_kwargs = {}
    logging.basicConfig(format=f"[{name}] %(levelname)s - %(message)s",
                        level=loglevel)
    fedinfo = _create_fedinfo(f"{name}_core")
    logging.debug("federate info: %s", fedinfo)
    logging.debug("federate_args: %s", federate_args)
    logging.debug("federate_kwargs: %s", federate_kwargs)
    target(name, fedinfo, *federate_args, **federate_kwargs)


class Simulation:
    """Representation of a full simulation.

    Parameters
    ----------
    grid_description : grid.GridSpecification
        Description of the grid and connected devices to simulate.
    show_plots : bool
        If true then the logger displays figures showing the values
        that were recorded while the simulation was running.
    loglevel : int, default logging.WARN
        Log level for all federates.
    """
    def __init__(self,
                 grid_description: GridSpecification,
                 show_plots: bool = False,
                 loglevel: int = logging.WARN):
        self.grid = grid_description
        self.num_federates = 4  # grid, storage, logger, reliability
        self._broker_process = None
        self._logger_process = None
        self._grid_process = None
        self._storage_process = None
        self._reliability_process = None
        self._show_plots = show_plots
        self._loglevel = loglevel

    def _start_broker(self):
        """Start the HELICS borker for the simulation."""
        self._broker_process = Process(
            target=_helics_broker,
            args=(self.num_federates,),
            name="ssim_broker"
        )

    def _init_grid_federate(self, hours):
        """Initialize the grid federate process."""
        self._grid_process = Process(
            target=_start_federate,
            kwargs={"name": "grid",
                    "target": opendss.run_federate,
                    "federate_kwargs": {"grid": self.grid,
                                        "hours": hours},
                    "loglevel": self._loglevel},
            name="grid_federate"
        )

    def _init_storage_federate(self, hours):
        """Initialize the storage controller federate process."""
        self._storage_process = Process(
            target=_start_federate,
            kwargs={"name": "storage",
                    "target": storage.run_federate,
                    "federate_kwargs": {"devices": self.grid.storage_devices,
                                        "hours": hours},
                    "loglevel": self._loglevel},
            name="storage_federate"
        )

    def _init_logger_federate(self, hours):
        """Initialize the logger federate process."""
        self._logger_process = Process(
            target=_start_federate,
            kwargs={"name": "logger",
                    "target": logger.run_federate,
                    "federate_kwargs": {
                        "busses": set(
                            device.bus for device in self.grid.storage_devices
                        ),
                        "storage_devices": set(
                            device.name for device in self.grid.storage_devices
                        ),
                        "hours": hours,
                        "show_plots": self._show_plots},
                    "loglevel": self._loglevel},
            name="logger_federate"
        )

    def _init_reliability_federate(self, hours):
        """Initialize the reliabilty federate process."""
        self._reliability_process = Process(
            target=_start_federate,
            kwargs={"name": "reliability",
                    "target": reliability.run_federate,
                    "federate_kwargs": {"lines": {"671680", "632633"},  # TODO specify lines
                                        "hours": hours},
                    "loglevel": logging.DEBUG},
            name="reliability_federate"
        )

    def _run(self):
        self._broker_process.start()
        self._logger_process.start()
        self._reliability_process.start()
        self._grid_process.start()
        self._storage_process.start()
        # Wait for federates to finish
        self._logger_process.join()
        self._reliability_process.join()
        self._grid_process.join()
        self._storage_process.join()
        self._broker_process.join()

    def run(self, hours: float):
        """Run the simulation.

        Parameters
        ----------
        hours : float
            Number of hours to run.
        """
        self._start_broker()
        self._init_grid_federate(hours)
        self._init_storage_federate(hours)
        self._init_reliability_federate(hours)
        self._init_logger_federate(hours)
        self._run()


def run_simulation(opendss_file, storage_devices, hours,
                   loglevel=logging.WARN):
    """Simulate the performance of the grid with attached storage.

    Parameters
    ----------
    opendss_file : PathLike
        Grid model file.
    storage_devices : dict
        Dictionary keys are storage names, values are dictionaries with
        keys 'kwhrated', 'kwrated', and 'bus' which specify the kWh rating,
        the maximum kW rating, and the bus where the device is connected
        respectively.
    hours : float
        Number of hours to simulate.
    loglevel : int, default logging.WARN
        Loglevel for all federates
    """
    grid_spec = GridSpecification(opendss_file)
    for name, device_specs in storage_devices.items():
        specs = device_specs.copy()
        grid_spec.add_storage(
            StorageSpecification(
                name,
                bus=specs.pop('bus'),
                kwh_rated=specs.pop('kwhrated'),
                kw_rated=specs.pop('kwrated'),
                phases=specs.pop('phases', 3),
                soc=specs.pop('%stored', 50) / 100,
                controller=specs.pop('controller', 'droop'),
                controller_params=specs.pop('controller_params', {}),
                params=specs
            )
        )
    simulation = Simulation(grid_spec, show_plots=True, loglevel=loglevel)
    simulation.run(hours)
