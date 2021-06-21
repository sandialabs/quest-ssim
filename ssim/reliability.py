"""Reliability models for the electric grid."""
from __future__ import annotations
import abc
import enum
import functools
import itertools
import json
import logging
import random
from dataclasses import dataclass, field
from typing import Collection, Iterator

import opendssdirect

from ssim import dssutil


@enum.unique
class Mode(str, enum.Enum):
    """Failure- or Restoration-mode."""
    OPEN = 'open'
    CLOSED = 'closed'
    CURRENT = 'current'


@enum.unique
class EventType(str, enum.Enum):
    FAIL = 'fail'
    RESTORE = 'restore'


@dataclass
class Event:
    """A reliability event can be eiter a failure or a restoration."""

    #: Whether this is a failure or a restoration event.
    type: EventType

    #: Failure/restoration mode.
    mode: Mode

    #: Name of the element affected by the event.
    element: str

    #: Additional data about the event.
    data: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, json_str: str) -> Event:
        """Construct an ``Event`` from a JSON string.

        Parameters
        ----------
        json_str : str
            JSON string representation of an event.
        """
        data = json.loads(json_str)
        return cls(
            EventType(data["type"]),
            Mode(data["mode"]),
            data["element"],
            data["data"]
        )

    def to_json(self) -> str:
        """Return a JSON string representing this event."""
        return json.dumps({
            "type": self.type,
            "mode": self.mode,
            "element": self.element,
            "data": self.data}
        )


class ReliabilityModel(abc.ABC):
    """Abstract base class for reliability models."""

    @abc.abstractmethod
    def peek(self) -> float:
        """Return the time of the next event."""

    @abc.abstractmethod
    def events(self, time) -> Iterator[Event]:
        """Return all events that occur at or prior to `time`.

        Events should only be returned once.
        """


class GridReliabilityModel(ReliabilityModel):
    """Overarching model of reliability for the full grid.

    Subsumes reliability models for all components that make up the
    grid.
    """
    def __init__(self, components: Collection[ReliabilityModel]):
        self._components = components

    @classmethod
    def from_json(cls, file: str):
        """Build a grid reliability model from the grid config.

        To build a grid reliability model we need to iterate over every
        grid component and construct a wear-out model for it.
        """
        with open(file) as f:
            config = json.load(f)
        dssutil.load_model(config["dss_file"])
        reliability = config["reliability"]
        lines = list(
            dssutil.iterate_properties(opendssdirect.Lines, ["IsSwitch"])
        )
        line_reliability_models = [
            LineReliability(
                name,
                reliability["line"]
            )
            for name, properties in lines if not properties.IsSwitch
        ]
        switch_reliability_models = [
            SwitchReliability(
                name,
                reliability["switch"],
                _switch_state_normal(name)
            )
            for name, properties in lines if properties.IsSwitch
        ]
        logging.warning("created line reliability model for %s lines",
                        len(line_reliability_models))
        return cls(
            line_reliability_models + switch_reliability_models
        )

    def peek(self):
        return min(component.peek() for component in self._components)

    def events(self, time: float) -> Iterator[Event]:
        """Return an iterator over tne events that occur at `time`.

        Parameters
        ----------
        time : float
            Time in seconds.
        """
        component_events = itertools.chain(
            *(component.events(time) for component in self._components)
        )
        for event in component_events:
            yield event


class WearOutModel:
    """Generic wear-out model.

    Parameters
    ----------
    failure_rate : float
        Failure rate.
    min_repair_time : float
        Minimum time to repair
    max_repair_time : float
        Maximum time to repair
    """
    def __init__(self, failure_rate, min_repair_time, max_repair_time):
        self._failure_distribution = functools.partial(
            random.expovariate, failure_rate
        )
        self._repair_distribution = functools.partial(
            random.uniform, min_repair_time, max_repair_time
        )
        self._next_event_time = self._failure_distribution()
        self._next_event_type = EventType.FAIL

    @property
    def events(self):
        """Iterate over all events"""
        while True:
            yield self._next_event_type, self._next_event_time
            self._sample_next_event()

    def _sample_next_event(self):
        if self._next_event_type is EventType.FAIL:
            self._next_event_type = EventType.RESTORE
            self._next_event_time += self._repair_distribution()
        else:
            self._next_event_type = EventType.FAIL
            self._next_event_time += self._failure_distribution()

    def reset(self, time):
        """Reset the model by sampling a new failure event at `time`."""
        self._next_event_time = time + self._failure_distribution()
        self._next_event_type = EventType.FAIL


class SwitchReliability(ReliabilityModel):
    """Model of switch wear-out.

    Parameters
    ----------
    name : str
        Name of the switch.
    params : dict
        Failure model parameters. Must contain keys 'mtbf', 'p_open', and
        'p_closed', 'min_repair', 'max_repair'

        - 'mtbf' is the mean time before failure [hours]
        - 'p_open' is the probability the switch will fail open
        - 'p_closed' is the probability the switch will fail closed
        - 'p_current' is the probability the switch will fail in its current
           state
        - 'min_repair' is the minimum time to repair the switch [hours]
        - 'max_repair' is the maximum time to repair the switch [hours]
    normal_state : Mode
        State of the switch during normal operation. This is the state the
        switch will be returned to when it is restored following a failure.
    """
    def __init__(self, name, params, normal_state):
        if params['p_open'] + params['p_closed'] + params['p_current'] != 1.0:
            raise ValueError(
                "params 'p_open', 'p_closed', and 'p_current' must sum to 1.0."
            )
        self.switch_name = name
        self._wear_out = WearOutModel(
            1.0 / (params['mtbf'] * 3600.0),
            params['min_repair'] * 3600.0,
            params['max_repair'] * 3600.0
        )
        self._p_open = params['p_open']
        self._p_closed = params['p_closed']
        self._p_current = params['p_current']
        self._repair_state = normal_state
        if params.get('repair_state') == 'closed':
            self._repair_state = Mode.CLOSED
        elif params.get('repair_state') == 'current':
            self._repair_state = Mode.CURRENT
        elif params.get('repair_state') == 'open':
            self._repair_state = Mode.OPEN

    def _sample_failure_mode(self):
        # return a random failure mode
        p = random.uniform(0, 1)
        if p < self._p_open:
            return Mode.OPEN
        if p < self._p_open + self._p_closed:
            return Mode.CLOSED
        return Mode.CURRENT

    def peek(self) -> float:
        return next(self._wear_out.events)[1]

    def _make_event(self, event_type):
        if event_type is EventType.FAIL:
            return Event(
                event_type, self._sample_failure_mode(), self.switch_name
            )
        return Event(event_type, self._repair_state, self.switch_name)

    def events(self, time) -> Iterator[Event]:
        for event, t in self._wear_out.events:
            if t > time:
                break
            yield self._make_event(event)


class LineReliability(ReliabilityModel):
    """Model of the reliability of a line.

    Line failure times are sampled from an exponential distribution.

    Line repair times are sampled from a uniform distribution plus a fixed
    offset.

    Parameters
    ----------
    line_name : str
        Name of the line. Used to construct the reliability events.
    params : dict
        Must have keys 'mtbf', 'min_repair', and 'max_repair'.

        - 'mtbf' mean time before failure [hours]
        - 'min_repair' minimum time to repair the line [hours]
        - 'max_repair' maximum time required to repair the line [hours]
    """
    def __init__(self,
                 line_name: str,
                 params: dict):
        failure_rate = 1.0 / (3600.0 * params["mtbf"])
        min_repair_time = params["min_repair"] * 3600.0
        max_repair_time = params["max_repair"] * 3600.0
        self._wear_out = WearOutModel(
            failure_rate, min_repair_time, max_repair_time
        )
        self.line_name = line_name

    def peek(self):
        return next(self._wear_out.events)[1]

    def _make_event(self, event_type):
        if event_type is EventType.FAIL:
            return Event(event_type, Mode.OPEN, self.line_name)
        return Event(event_type, Mode.CLOSED, self.line_name)

    def events(self, time):
        # Sample new events until the time of the next event is in the future.
        for event, t in self._wear_out.events:
            if t > time:
                break
            yield self._make_event(event)


def _switch_state_normal(name):
    """Return the "normal" state of the switch.

    If the switch is controlled by a SwtControl object, this is the NormalState
    value of the controller, otherwise the current state of the switch is
    returned.

    Parameters
    ----------
    name : str
        Name of the switch.

    Returns
    -------
    Mode
        Returns Mode.OPEN if the normal state is open, or Mode.CLOSED if it
        is closed.
    """
    opendssdirect.Lines.Name(name)
    if opendssdirect.CktElement.HasSwitchControl():
        for c in opendssdirect.CktElement.NumControls():
            controller_type, controller_name = \
                opendssdirect.CktElement.Controller(c).split('.')
            if controller_type == "SwtControl":
                opendssdirect.SwtControls.Name(controller_name)
                normal_state = opendssdirect.SwtControls.NormalState()
                if normal_state == 1:
                    return Mode.OPEN
                return Mode.CLOSED
    # No switch control. If either terminal is open return OPEN, otherwise
    # return CLOSED
    if opendssdirect.CktElement.IsOpen(1, 1) \
            or opendssdirect.CktElement.IsOpen(2, 1):
        return Mode.OPEN
    return Mode.CLOSED
