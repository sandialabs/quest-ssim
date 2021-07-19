"""Federate interface for a grid reliability simulation."""
import argparse
import logging

from helics import (
    HelicsMessageFederate,
    helicsCreateMessageFederateFromConfig
)

from ssim import grid
from ssim.reliability import GridReliabilityModel


class ReliabilityFederate:
    """Federate interfacing a reliability simulation with a grid simulation.

    The federate has a :py:class:`ssim.reliability.GridReliabilityModel`
    instance. When the grid reliability model indicates a reliability
    event occurs, a message is published to the "grid/reliability" endpoint
    from the local "reliability" endpoint. One message is published for each
    event, which may result in many messages being sent at the same time (e.g.
    many grid components fail at the same time).

    Parameters
    ----------
    federate : HelicsMessageFederate
        Federate handle for interacting with HELICS.
    reliability_model : GridReliabilityModel
        Model that determines when grid components fail and are restored.
    """
    def __init__(self, federate: HelicsMessageFederate,
                 reliability_model: GridReliabilityModel):
        print(f"endpoints: {federate.endpoints}")
        self._federate = federate
        self._reliability_model = reliability_model
        self._endpoint = federate.get_endpoint_by_name("reliability")

    def _event_message(self, event):
        message = self._endpoint.create_message()
        message.destination = "grid/reliability"
        message.data = event.to_json()
        return message

    def _pending_messages(self):
        while self._endpoint.has_message():
            yield self._endpoint.get_message()

    def _generator_status_messages(self):
        for message in self._pending_messages():
            status = grid.GeneratorStatus.from_json(message.data)
            self._federate.log_message(f"generator status: {status}",
                                       logging.DEBUG)
            yield grid.GeneratorStatus.from_json(message.data)

    def step(self, time):
        """Advance the time of the reliability model to `time`."""
        self._federate.log_message(f"stepping @ {time}", logging.DEBUG)
        self._reliability_model.update(
            time,
            list(self._generator_status_messages())
        )
        for event in self._reliability_model.events():
            self._federate.log_message(
                f"publishing event {event} @ {time}", logging.DEBUG)
            message = self._event_message(event)
            logging.debug("sending message: %s", message)
            self._endpoint.send_data(message)

    def run(self, hours: float):
        logging.info("Running reliability federate.")
        logging.info("endpoints: %s", self._federate.endpoints)
        current_time = 0.0
        while current_time < hours * 3600:
            self.step(current_time)
            self._federate.log_message(
                f"next update: {self._reliability_model.peek()}",
                logging.DEBUG
            )
            current_time = self._federate.request_time(
                self._reliability_model.peek()
            )


def _make_reliability_model(grid_config: str) -> GridReliabilityModel:
    """Construct a reliability model for the grid.

    Parameters
    ----------
    grid_config : str
        Path the the JSON grid configuration file.

    Returns
    -------
    GridReliabilityModel
    """
    return GridReliabilityModel(grid_config)


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "grid_config",
        type=str,
        help="path to grid config file"
    )
    parser.add_argument(
        "federate_config",
        type=str,
        help="path to federate config file"
    )
    parser.add_argument(
        "--hours",
        type=float,
        help="number of hours to simulate"
    )
    args = parser.parse_args()
    federate = helicsCreateMessageFederateFromConfig(args.federate_config)
    reliability_model = _make_reliability_model(args.grid_config)
    fed = ReliabilityFederate(federate, reliability_model)
    federate.enter_executing_mode()
    fed.run(args.hours)
