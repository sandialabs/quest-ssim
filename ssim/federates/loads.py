import argparse
import logging
import csv

#from ssim.loads import (
#)

from helics import (
    HelicsFederate,
    helics_time_maxtime,
    helicsCreateMessageFederateFromConfig
)

from ssim.federates import timing

from ssim.grid import (
    GridSpecification,
    StatusMessage
)


class LoadsFederate:
    """Manager for metrics and accumulators that record values from other HELICS federates.

    Parameters
    ----------
    federate : HelicsMessageFederate
        HELICS federate.
    """
    def __init__(self, federate, grid_config):
        self._federate = federate
        self.endpoint = federate.get_endpoint_by_name("loads")
        g_spec = GridSpecification.from_json(grid_config)

        #self.csv_file = open("load_log.csv", 'w', newline='')
        #self.csv_writer = csv.writer(self.csv_file)
        #self.csv_fields = ["time"]

    def initialize(self):
        self._federate.enter_executing_mode()

    def finalize(self):
        """Finalize all loggers."""
        #self.csv_writer.writerow([str(self._metricMgr.get_total_accumulation)])
        #self.csv_file.close()
        #self._federate.disconnect()

    def run(self):
        """Run for `hours` and invoke loggers whenever HELICS grants a time.

        Parameters
        ----------
        hours : float
            Total time to log. [hours]
        """
        schedule = timing.schedule(self._federate)
        for time in schedule:
            if time == helics_time_maxtime:
                # Don't update since this is the signal that all other federates
                # have finished
                return
            #self._update_metrics(time)


def run_federate(federate, grid_config):
    """Run a metrics federate as `federate`.

    Parameters
    ----------
    federate : HelicsFederate
        HELICS federate handle.
    grid_config:
    """
    logging.debug("federate: %s", federate)
    loads_federate = LoadsFederate(federate, grid_config)
    loads_federate.initialize()
    loads_federate.run()
    loads_federate.finalize()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "grid_config",
        type=str,
        help="path to loads config file"
    )
    parser.add_argument(
        "federate_config",
        type=str,
        help="path to the federate config file"
    )
    # parser.add_argument(
    #    "--hours",
    #    type=float,
    #    help="how long to log"
    # )

    args = parser.parse_args()
    federate = helicsCreateMessageFederateFromConfig(args.federate_config)
    run_federate(federate, args.grid_config)


if __name__ == '__main__':
    run()
