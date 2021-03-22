from abc import ABC, abstractmethod
import logging
from typing import Set

from helics import (
    HelicsFederate,
    HelicsValueFederate,
    helicsCreateFederateInfo,
    helicsCreateValueFederate,
    helics_time_maxtime
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


def run_logger(loglevel, bus_voltage, show_plots=False):
    logging.basicConfig(format="[PowerLogger] %(levelname)s - %(message)s",
                        level=loglevel)
    logging.info("starting federate")
    fedinfo = helicsCreateFederateInfo()
    fedinfo.core_name = "power_logger"
    fedinfo.core_type = "zmq"
    fedinfo.core_init = "-f1"
    logging.debug(f"federate info: {fedinfo}")
    federate = helicsCreateValueFederate("power_logger", fedinfo)
    logging.debug("federate created")
    logging_federate = LoggingFederate(federate)
    power_logger = PowerLogger()
    voltage_logger = VoltageLogger(bus_voltage)
    logging_federate.add_logger("power", power_logger)
    logging_federate.add_logger("voltage", voltage_logger)
    logging_federate.initialize()
    logging_federate.run(1000)
    if show_plots:
        plt.figure()
        plt.plot(power_logger.time, power_logger.active_power,
                 label="active power")
        plt.plot(power_logger.time, power_logger.reactive_power,
                 label="reactive power")
        plt.ylabel("Power (kW)")
        plt.xlabel("time (s)")
        plt.legend()
        plt.figure()
        for bus in voltage_logger.bus_voltage:
            plt.plot(voltage_logger.time,
                     voltage_logger.bus_voltage[bus],
                     label=bus)
        plt.ylabel("Voltage (PU)")
        plt.xlabel("time (s)")
        plt.legend()
        plt.show()
