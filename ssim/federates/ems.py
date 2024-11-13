"""Energy Management System Federate."""
import argparse

from helics import (
    helicsCreateMessageFederateFromConfig, helics_time_maxtime,
    HelicsLogLevel
)

from ssim import reliability
from ssim.grid import GridSpecification, StatusMessage
from ssim.ems import GridModel, EMS
from ssim.heuristicems import CompositeHeuristicEMS
from ssim.federates import timing


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
        grid = GridModel(grid_spec)
        self._ems = EMS(grid,
                        dispatcher=CompositeHeuristicEMS(grid))
        self.federate = federate
        self.control_endpoint = federate.get_endpoint_by_name("control")
        self.reliability_endpoint = federate.get_endpoint_by_name(
            "reliability"
        )

    @staticmethod
    def _parse_control_message(message):
        """Parse a message received on the control endpoint.

        Accepts the following messages:
        - StorageStatus
        - PVStatus
        - GenertatorStatus
        - LoadStatus

        The message type is determined by the name of the source
        endpoint. Each message type comes from a global enpoint named
        with the type followed by identifying information. For
        generators, pvsystems, and storage devices there is one
        endpoint per device (for example, "generator.gen1.control", or
        "pvsystem.pv1.control" where "gen1" and "pv1" are names of
        specific PV systems). For loads, there is only one endpoint
        which sends a single status message containing information
        about all the loads connected to the grid.

        Parameters
        ----------
        message : HelicsMessage
            A message received on the "ems/control" endpoint.

        Returns
        -------
        StatusMessage
            The parsed status message.

        """
        return StatusMessage.from_json(message.data)

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

    def _update_reliability(self):
        self._ems.grid.apply_reliability_events(
            self.pending_reliability_messages()
        )

    def _send_control_messages(self):
        # TODO extend this to work for control messages to the grid federate
        #      as well as storage control federates (as currently implemented)
        for device, action in self._ems.output():
            self.federate.log_message(
                f"sending control message: {action}",
                HelicsLogLevel.TRACE
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
        self._ems.update(time, self.pending_control_messages(), None)
        self._send_control_messages()

    def run(self, hours):
        """Run the federate for `hours` hours.

        Parameters
        ----------
        hours : float
            How long to run the EMS federate. [hours]
        """
        schedule = timing.schedule(
            self.federate,
            self._ems.next_update,
            hours * 3600
        )
        for time in schedule:
            self._step(time)


def _create_ems(grid_spec):
    if grid_spec.ems is None:
        raise ValueError("no ems configured")
    if grid_spec.ems.ems_type == 'composite-heuristic':
        return CompositeHeuristicEMS(grid_spec)
    raise ValueError(f"Unknown ems type: {grid_spec.ems.ems_type}."
                     " Valid EMS types are: 'composite-heuristic'.")


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
        HelicsLogLevel.TRACE
    )
    ems_federate = EMSFederate(federate,
                               GridSpecification.from_json(args.grid_config))
    federate.enter_executing_mode()
    ems_federate.run(args.hours)
    federate.disconnect()


if __name__ == '__main__':
    run()
