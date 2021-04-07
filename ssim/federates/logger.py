from abc import ABC, abstractmethod
import logging
from typing import Set, List

from helics import (
    HelicsFederate,
    HelicsValueFederate,
    helics_time_maxtime,
    HelicsFederateInfo,
    helicsCreateValueFederate
)

import matplotlib.pyplot as plt


class HelicsLogger(ABC):
    """Base class for loggers that record values from HELICS federates."""
    @abstractmethod
    def initialize(self, federate: HelicsFederate):
        """Initialize the logger by setting up its subscriptions.

        Parameters
        ----------
        federate : HelicsFederate
            HELICS federate handle to use for for registering subscriptions.
        """

    @abstractmethod
    def log(self, time: float):
        """Record the data at time `time`.

        Parameters
        ----------
        time : float
            Current time from HELICS.
        """

    @abstractmethod
    def finalize(self):
        """Done recording data.

        This can be overridden to save data to file or a database, produce
        visualizations, or whatever else needs to be done.
        """


class LoggingFederate:
    """Manager for loggers that record values from other HELICS federates.

    Parameters
    ----------
    federate : HelicsFederate
        HELICS federate.
    """
    def __init__(self, federate):
        self._federate = federate
        self._loggers = {}

    def initialize(self):
        """Initialize all loggers."""
        for logger in self._loggers.values():
            logger.initialize(self._federate)
        self._federate.enter_executing_mode()

    def finalize(self):
        """Finalize all loggers."""
        for logger in self._loggers.values():
            logger.finalize()
        self._federate.finalize()

    def add_logger(self, name: str, logger: HelicsLogger):
        """Add a logger to the federate.

        Parameters
        ----------
        name : str
            Unique identifier for the logger. If a logger already exists
            with the same name an exception is raised.
        logger : HelicsLogger
            The logger itself.

        Raises
        ------
        ValueError
            If the name is already associated with a logger.
        """
        if name in self._loggers:
            raise ValueError(
                "Logger names must be unique. A logger already"
                f" exists with the name {name}. Try using a"
                f" different name"
            )
        self._loggers[name] = logger

    def _step(self):
        """Request the maximum time from HELICS and invoke loggers whenever
        a time is granted."""
        time = self._federate.request_time(helics_time_maxtime - 1)
        logging.debug(f"granted time: {time}")
        for logger in self._loggers.values():
            logger.log(time)
        return time

    def run(self, hours: float):
        """Run for `hours` and invoke loggers whenever HELICS grants a time.

        Parameters
        ----------
        hours : float
            Total time to log. [hours]
        """
        while self._step() < hours * 3600:
            pass


class PowerLogger(HelicsLogger):
    """Logging federate state for logging total power on the grid."""
    def __init__(self):
        self.time = []
        self.active_power = []
        self.reactive_power = []
        self._total_power = None

    def initialize(self, federate: HelicsValueFederate):
        self._total_power = federate.register_subscription(
            "grid/total_power",
            units="kW"
        )
        self.time = []
        self.active_power = []
        self.reactive_power = []

    def log(self, time: float):
        self.time.append(time)
        self.active_power.append(
            self._total_power.complex.real
        )
        self.reactive_power.append(
            self._total_power.complex.imag
        )

    def finalize(self):
        pass


class VoltageLogger(HelicsLogger):
    """Record voltage at a set of busses.

    Parameters
    ----------
    busses : Set[str]
        Set of busses to monitor.
    """
    def __init__(self, busses: Set[str]):
        self.time = []
        self.bus_voltage = {bus: [] for bus in busses}
        self._voltage_subs = {}

    def initialize(self, federate: HelicsValueFederate):
        self._voltage_subs = {
            bus: federate.register_subscription(
                f"grid/voltage.{bus}",
                units="pu"
            )
            for bus in self.bus_voltage
        }

    def log(self, time: float):
        """Record the voltages at `time`."""
        self.time.append(time)
        for bus in self.bus_voltage:
            self.bus_voltage[bus].append(
                self._voltage_subs[bus].double
            )

    def finalize(self):
        pass


class StorageLogger(HelicsLogger):
    """Logger for storage device state.

    Records charging power, discharging power, and state of charge.

    Parameters
    ----------
    device_names : Set[str]
        Names of the devices to monitor.
    """
    def __init__(self, device_names):
        self.device_names = device_names
        self._soc_subs = None
        self._power_subs = None
        self.time = []
        self.power_out = {device: [] for device in device_names}
        self.power_in = {device: [] for device in device_names}
        self.reactive_power = {device: [] for device in device_names}
        self.soc = {device: [] for device in device_names}

    def initialize(self, federate: HelicsValueFederate):
        self._soc_subs = {
            device: federate.register_subscription(
                f"grid/soc.{device}"
            )
            for device in self.device_names
        }
        self._power_subs = {
            device: federate.register_subscription(
                f"grid/power.{device}",
                "kW"
            )
            for device in self.device_names
        }

    def _log_soc(self):
        for device, soc in self.soc.items():
            soc.append(self._soc_subs[device].double)

    def _log_power(self):
        for device in self.device_names:
            reactive_power = self._power_subs[device].complex.imag
            active_power = self._power_subs[device].complex.real
            self.power_in[device].append(
                0 if active_power >= 0 else abs(active_power)
            )
            self.power_out[device].append(
                0 if active_power <= 0 else active_power
            )
            self.reactive_power[device].append(reactive_power)

    def log(self, time):
        self.time.append(time)
        self._log_soc()
        self._log_power()

    def finalize(self):
        pass


def to_hours(seconds: List[float]) -> List[float]:
    """Convert seconds to hours.

    Parameters
    ----------
    seconds : list

    Returns
    -------
    list
        Timestamps in `seconds` converted to `hours`.
    """
    return list(map(lambda x: x / 3600, seconds))


def run_federate(name: str,
                 fedinfo: HelicsFederateInfo,
                 busses: Set[str],
                 storage_devices: Set[str],
                 hours: float,
                 show_plots: bool):
    """Run a logging federate as `federate`.

    Parameters
    ----------
    name : str
        Federate name.
    fedinfo : HelicsFederateInfo
        Federate info structure to use for initializing the federate.
    busses : Set[str]
        Names of busses at which voltage is to be logged.
    storage_devices : Set[str]
        Names of storage devices to monitor.
    hours : float
        Number of hours to run before exiting.
    show_plots : bool
        If true figures are displayed for each logger before exiting.
    """
    federate = helicsCreateValueFederate(name, fedinfo)
    logging.debug("federate: %s", federate)
    logging.debug("busses: %s", busses)
    logging.debug("storage: %s", storage_devices)
    power_logger = PowerLogger()
    voltage_logger = VoltageLogger(busses)
    storage_logger = StorageLogger(storage_devices)
    logging_federate = LoggingFederate(federate)
    logging_federate.add_logger("power", power_logger)
    logging_federate.add_logger("voltage", voltage_logger)
    logging_federate.add_logger("storage", storage_logger)
    logging_federate.initialize()
    logging_federate.run(hours)
    if show_plots:
        _power_plot(power_logger)
        _voltage_plot(voltage_logger)
        _storage_plots(storage_logger)
        plt.show()


def _power_plot(power_logger: PowerLogger):
    plt.figure()
    plt.plot(to_hours(power_logger.time), power_logger.active_power,
             label="active power")
    plt.plot(to_hours(power_logger.time), power_logger.reactive_power,
             label="reactive power")
    plt.ylabel("Power (kW)")
    plt.xlabel("time (h)")
    plt.legend()


def _voltage_plot(voltage_logger: VoltageLogger):
    plt.figure()
    for bus in voltage_logger.bus_voltage:
        plt.plot(to_hours(voltage_logger.time),
                 voltage_logger.bus_voltage[bus],
                 label=bus)
    plt.ylabel("Voltage (PU)")
    plt.xlabel("time (h)")
    plt.legend()


def _storage_plots(storage_logger: StorageLogger):
    for device in storage_logger.device_names:
        plt.figure()
        plt.title(device)
        plt.plot(
            to_hours(storage_logger.time),
            storage_logger.power_in[device],
            label='charging power'
        )
        plt.plot(
            to_hours(storage_logger.time),
            storage_logger.power_out[device],
            label='discharging power'
        )
        plt.plot(
            to_hours(storage_logger.time),
            storage_logger.reactive_power[device],
            label='reactive power (kVAR)'
        )
        plt.xlabel('time (h)')
        plt.ylabel('Power (kW)')
        plt.legend()
        plt.figure()
        plt.title(device + " SOC")
        plt.plot(
            to_hours(storage_logger.time),
            storage_logger.soc[device]
        )
