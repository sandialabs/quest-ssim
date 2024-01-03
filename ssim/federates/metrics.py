import argparse
import logging
import csv

from ssim.metrics import (
    Metric,
    MetricManager,
    MetricTimeAccumulator
)

from helics import (
    HelicsFederate,
    helics_time_maxtime,
    helicsCreateMessageFederateFromConfig
)

from ssim.federates import timing

from ssim.grid import (
    BusVoltageStatus,
    GridSpecification,
    StatusMessage
)

from ssim.metrics import ImprovementType


class MetricsFederate:
    """Manager for metrics and accumulators that record values from other
       HELICS federates.

    Parameters
    ----------
    federate : HelicsMessageFederate
        HELICS federate.
    """
    def __init__(self, federate, grid_config):
        self._federate = federate
        self._metricMgr = MetricManager()
        self.endpoint = federate.get_endpoint_by_name("metrics")
        g_spec = GridSpecification.from_json(grid_config)
        
        self.csv_file = open("metric_log.csv", 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_fields = ["time"]

        for bv_dict in g_spec.busses_to_measure:
            self.add_accumulator(
                bv_dict["name"],
                MetricTimeAccumulator(
                    Metric(
                        bv_dict["lower_limit"], bv_dict["upper_limit"],
                        bv_dict["objective"],
                        ImprovementType.parse(bv_dict["sense"])
                        ),
                    0.0
                )
            )
            self.csv_fields.append(bv_dict["name"])

        self.csv_writer.writerow(self.csv_fields)

    def initialize(self):
        self._federate.enter_executing_mode()

    def finalize(self):
        """Finalize all loggers."""
        self.csv_writer.writerow([str(self._metricMgr.get_total_accumulation)])
        self.csv_file.close()
        self._federate.disconnect()

    def add_accumulator(self, name: str, accumulator: MetricTimeAccumulator):
        """Add a metric to the federate.

        Parameters
        ----------
        name : str
            Unique identifier for the metric accumulator. If a metric
            accumulator already exists with the same name an exception is
            raised.
        accumulator : MetricTimeAccumulator
            The metric accumulator to add.

        Raises
        ------
        ValueError
            If the name is already associated with a metric accumulator.
        """
        self._metricMgr.add_accumulator(name, accumulator)

    def _update_metrics(self, time):
        values = [0.0] * len(self.csv_fields)
        values[0] = time
        while self.endpoint.has_message():
            message = self.endpoint.get_message()
            bv_msg: BusVoltageStatus = StatusMessage.from_json(message.data)  # noqa
            curr_metric: MetricTimeAccumulator = self._metricMgr.get_accumulator(bv_msg.name)
            met_val = curr_metric.accumulate(bv_msg.voltage, bv_msg.time)
            index = self.csv_fields.index(bv_msg.name)
            values[index] = met_val

        self.csv_writer.writerow(values)

    def run(self, hours):
        """Run for `hours` and invoke loggers whenever HELICS grants a time.

        Parameters
        ----------
        hours : float
            Total time to log. [hours]
        """
        schedule = timing.schedule(self._federate, max_time=hours * 3600)
        for time in schedule:
            if time == helics_time_maxtime:
                # Don't update since this is the signal that all other
                # federates have finished
                return
            self._update_metrics(time)


def run_federate(federate, grid_config, hours):
    """Run a metrics federate as `federate`.

    Parameters
    ----------
    federate : HelicsFederate
        HELICS federate handle.
    grid_config:
    """
    logging.debug("federate: %s", federate)
    metrics_federate = MetricsFederate(federate, grid_config)
    metrics_federate.initialize()
    metrics_federate.run(hours)
    metrics_federate.finalize()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "grid_config",
        type=str,
        help="path to metrics config file"
    )
    parser.add_argument(
        "federate_config",
        type=str,
        help="path to the federate config file"
    )
    parser.add_argument(
        "--hours",
        type=float,
        help="how long to log",
        default=helics_time_maxtime
    )

    args = parser.parse_args()
    federate = helicsCreateMessageFederateFromConfig(args.federate_config)
    run_federate(federate, args.grid_config, args.hours)


if __name__ == '__main__':
    run()
