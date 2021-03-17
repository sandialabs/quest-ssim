import logging

from helics import (
    HelicsValueFederate,
    helicsCreateFederateInfo,
    helicsCreateValueFederate,
    helics_time_maxtime
)

import matplotlib.pyplot as plt


class PowerLogger:
    """Logging federate state for logging total power on the grid.

    Parameters
    ----------
    federate : HelicsValueFederate
        HELICS federate.
    """
    def __init__(self, federate):
        self._federate = federate
        self._total_power = self._federate.register_subscription(
            "grid/total_power",
            units="kW"
        )
        self.time = []
        self.active_power = []
        self.reactive_power = []

    def _step(self):
        time = self._federate.request_time(helics_time_maxtime - 1)
        logging.debug(f"granted time: {time}")
        self.active_power.append(self._total_power.complex.real)
        self.reactive_power.append(self._total_power.complex.imag)
        self.time.append(time)
        return time

    def run(self, hours):
        """Loop for `hours`, logging active and reactive power"""
        while self._step() < hours * 3600:
            logging.info(f"total power: {self.active_power[-1]}")
            pass


def run_power_logger(loglevel, show_plots=False):
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
    logger = PowerLogger(federate)
    federate.enter_executing_mode()
    logger.run(1000)
    if show_plots:
        plt.figure()
        plt.plot(logger.time, logger.active_power)
        plt.plot(logger.time, logger.reactive_power)
        plt.ylabel("Power (kW)")
        plt.xlabel("time (s)")
        plt.show()
