"""Energy Management System Federate."""
import argparse
import json
import logging

from helics import (
    helicsCreateMessageFederateFromConfig, helics_time_maxtime
)

from ssim import reliability
from ssim.ems import EMS


class EMSFederate:
    """Class for managing the EMS and its HELICS interface.

    Parameters
    ----------
    federate : HelicsMessageFederate
        HELICS federate handle. Must have a registered endpoint named
        "control".
    config : str
        Path to the grid configuration file.
    """
    def __init__(self, federate, config):
        self._ems = EMS(config)
        self.federate = federate
        self.control_endpoint = federate.get_endpoint_by_name("control")
        self.reliability_endpoint = federate.get_endpoint_by_name(
            "reliability"
        )

    def pending_control_messages(self):
        while self.control_endpoint.has_message():
            yield json.loads(self.control_endpoint.get_message().data)

    def pending_reliability_messages(self):
        while self.reliability_endpoint.has_message():
            yield reliability.Event.from_json(
                self.reliability_endpoint.get_message().data
            )

    def _update_control_inputs(self):
        for message in self.pending_control_messages():
            self.federate.log_message(
                f"processing message: {message}", logging.DEBUG
            )
            self._ems.update_control(message)

    def _update_reliability(self):
        for message in self.pending_reliability_messages():
            self.federate.log_message(
                f"got reliability message: {message}",
                logging.DEBUG
            )
            self._ems.update_reliability(message)

    def _send_control_messages(self):
        for device, action in self._ems.control_actions():
            self.federate.log_message(
                f"sending control message: {action}", logging.DEBUG
            )
            self.control_endpoint.send_data(
                action.to_json(),
                destination=f"{device}/control"
            )

    def _step(self, time):
        """Step the EMS to `time`.

        Parameters
        ----------
        time : float
            Time to advance to in seconds.
        """
        self._update_reliability()
        self._update_control_inputs()
        self._ems.step(time)
        self._send_control_messages()

    def run(self, hours):
        """Run the federate for `hours` hours.

        Parameters
        ----------
        hours : float
            How long to run the EMS federate. [hours]
        """
        time = 0.0
        while time < hours * 3600:
            self._step(time)
            time = self.federate.request_time(self._ems.next_update())


def run():
    """Run the EMS federate."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "grid_config",
        type=str,
        help="path to JSON file specifying the grid configuration"
    )
    parser.add_argument(
        "federate_config",
        type=str,
        help="path to federate config file"
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=helics_time_maxtime / 3600,
        help="how many hours to run for."
    )
    args = parser.parse_args()
    federate = helicsCreateMessageFederateFromConfig(args.federate_config)
    federate.log_message(
        f"created federate with endpoints: {federate.endpoints}",
        logging.DEBUG
    )
    ems_federate = EMSFederate(federate, args.grid_config)
    federate.enter_executing_mode()
    ems_federate.run(args.hours)
