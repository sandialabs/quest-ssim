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
        line_reliability_models = [
            LineReliability(
                name,
                # 100 hours on average between line failures
                1.0 / (3600 * 100),
                1 * 3600,
                10 * 3600
            )
            for name, _
            in dssutil.iterate_properties(opendssdirect.Lines, ['Name'])
        ]
        logging.warning("created line reliability model for %s lines",
                        len(line_reliability_models))
        return cls(
            line_reliability_models
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


class LineReliability(ReliabilityModel):
    """Model of the reliability of a line.

    Line failure times are sampled from an exponential distribution.

    Line repair times are sampled from a uniform distribution plus a fixed
    offset.

    Parameters
    ----------
    failure_rate : float
        Line failure rate (the rate parameter for an exponential distribution).
    min_repair_time : float
        Minimum time required to repair a line after it has failed. [seconds]
    max_repair_time : float
        Maximum time required to repair a line after it has failed. [seconds]
    """
    def __init__(self,
                 line_name: str,
                 failure_rate: float,
                 min_repair_time: float,
                 max_repair_time: float):
        self.line_name = line_name
        self._failure_distribution = functools.partial(
            random.expovariate, failure_rate
        )
        self._repair_distribution = functools.partial(
            random.uniform, min_repair_time, max_repair_time
        )
        self._next_event_time = self._failure_distribution()
        self._next_event = Event(EventType.FAIL, Mode.OPEN, line_name)

    def peek(self):
        return self._next_event_time

    def events(self, time):
        # Sample new events until the time of the next event is in the future.
        while self._next_event_time <= time:
            yield self._next_event
            self._sample_next_event()

    def _sample_next_event(self):
        if self._next_event.type is EventType.FAIL:
            self._next_event = Event(
                EventType.RESTORE, Mode.CLOSED, self.line_name
            )
            self._next_event_time += self._repair_distribution()
        else:
            self._next_event = Event(
                EventType.FAIL, Mode.OPEN, self.line_name
            )
            self._next_event_time += self._failure_distribution()
