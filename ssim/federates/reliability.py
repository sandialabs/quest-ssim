"""Federate interface for a grid reliability simulation."""
import logging
from typing import List

from helics import (
    HelicsMessageFederate,
    HelicsFederateInfo,
    helicsCreateMessageFederate
)

from ssim.reliability import GridReliabilityModel, LineReliability


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
        self._federate = federate
        self._reliability_model = reliability_model
        self._endpoint = federate.register_endpoint(
            "reliability"
        )

    def _event_message(self, event):
        message = self._endpoint.create_message()
        message.destination = "grid/reliability"
        message.data = event.to_json()
        return message

    def step(self, time):
        """Advance the time of the reliability model to `time`."""
        for event in self._reliability_model.events(time):
            message = self._event_message(event)
            logging.debug("sending message: %s", message)
            self._endpoint.send_data(message)

    def run(self, hours: float):
        logging.info("Running reliability federate.")
        logging.info("endpoints: %s", self._federate.endpoints)
        current_time = 0.0
        while current_time < hours * 3600:
            current_time = self._federate.request_time(
                self._reliability_model.peek()
            )
            self.step(current_time)


def run_federate(name: str,
                 fedinfo: HelicsFederateInfo,
                 lines: List[str],
                 hours: float):
    """Run the reliability federate.

    Parameters
    ----------
    name : str
        Federate name.
    fedinfo : HelicsFederateInfo
        Federate info structure to use when initializing the federate.
    lines : List[str]
        Names of lines that are subject to failure.
    hours : float
        How many hours to simulate.
    """
    federate = helicsCreateMessageFederate(name, fedinfo)
    model = GridReliabilityModel(
        [LineReliability(line, 1.0 / 3600, 3*3600, 10*3600) for line in lines]
    )
    reliability_federate = ReliabilityFederate(federate, model)
    federate.enter_executing_mode()
    reliability_federate.run(hours)
