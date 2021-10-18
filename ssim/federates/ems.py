"""Energy Management System Federate."""
import argparse
import json
import logging

from helics import (
    helicsCreateMessageFederateFromConfig, helics_time_maxtime
)

from ssim import reliability
from ssim.grid import GridSpecification, PVStatus, StorageStatus
from ssim.ems import CompositeHeuristicEMS


class EMSFederate:
    """Class for managing the EMS and its HELICS interface.

    Parameters
    ----------
    federate : HelicsMessageFederate
        HELICS federate handle. Must have a registered endpoint named
        "control".
    grid_spec : GridSpecification
    """
    def __init__(self, federate, grid_spec):
        self._ems = CompositeHeuristicEMS(grid_spec)
        self.federate = federate
        self.control_endpoint = federate.get_endpoint_by_name("control")
        self.reliability_endpoint = federate.get_endpoint_by_name(
            "reliability"
        )

    @staticmethod
    def _parse_control_message(message):
        """Parse a message received on the control endpoint.
        
        Possible messages:
        - StorageStatus
        - PVStatus
        - GenertatorStatus
        - ? 

        Each of these should be comming from a distinct endpoint. For PV status
        messages the endpoint is 'grid/pvsystem.{name}.control'. For Storage
        status messages the endpoint is in the storage controller: 
        '{name}/control' - this makes identifying storage messages a bit more
        difficult. 

        Parameters
        ----------
        message : HelicsMessage

        Returns
        -------
        PVStatus or StorageStatus
        """
        if message.source.startswith("storage"):
            return StorageStatus.from_json(message.data)
        elif message.source.startswith("pvsystem"):
            return PVStatus.from_json(message.data)

    def pending_control_messages(self):
        """Iterator over messages received on the control endpoint."""
        while self.control_endpoint.has_message():
            yield self._parse_control_message(
                self.control_endpoint.get_message()
            )

    def pending_reliability_messages(self):
        """Iterator over messages received on the reliability endpoint."""
        while self.reliability_endpoint.has_message():
            yield reliability.Event.from_json(
                self.reliability_endpoint.get_message().data
            )

    def _update_control_inputs(self):
        self._ems.update(self.pending_control_messages())

    def _update_reliability(self):
        self._ems.apply_reliability_events(
            self.pending_reliability_messages()
        )

    def _send_control_messages(self):
        # TODO extend this to work for control messages to the grid federate
        #      as well as storage control federates (as currently implemented)
        for device, action in self._ems.control_actions():
            self.federate.log_message(
                f"sending control message: {action}", logging.DEBUG
            )
            self.control_endpoint.send_data(
                action.to_json(),
                destination=f"storage.{device}.control"
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
    ems_federate = EMSFederate(federate,
                               GridSpecification.from_json(args.grid_config))
    federate.enter_executing_mode()
    ems_federate.run(args.hours)


if __name__ == '__main__':
    run()
