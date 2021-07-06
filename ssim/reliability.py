"""Reliability models for the electric grid."""
from __future__ import annotations
import abc
import enum
import itertools
import json
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Union

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
class Repair:
    """Representation of a repair."""

    #: State of the connection to the grid following the repair.
    connection: Mode

    #: Additional repair information to be passed to the grid.
    data: dict = field(default_factory=dict)


@dataclass
class Failure:
    """Representation of an ongoing failure."""

    #: Time required to repair the failure.
    repair_time: float

    #: Data for the repair event
    repair: Repair

    #: Status of the component's connection to the grid following the failure.
    connection: Mode = Mode.OPEN

    #: Additional failure information to be passed to the grid.
    data: dict = field(default_factory=dict)


class FailureMode(abc.ABC):
    """Base class for failure modes."""
    @abc.abstractmethod
    def next_update(self) -> float:
        """Next time to update the model and check for a failure.

        Returns
        -------
        float
            Next update time. [seconds]
        """

    @abc.abstractmethod
    def update(self, time, **kwargs):
        """Update the model.

        Parameters
        ----------
        time : float
            Current time. [seconds]
        kwargs :
            Additional state information for the model.
        """

    @property
    @abc.abstractmethod
    def failure(self) -> Optional[Failure]:
        """Active failure, or None if no failure at the current time"""


class AgingFailure(FailureMode):
    """Generic aging-related failure mode.

    Failures are sampled from an exponential distribution with the given mean
    time before failure (`mtbf`). Repair times are sampled from a uniform
    distribution between `min_repair` and `max_repair`.

    Parameters
    ----------
    mtbf : float
        Mean time before failure. [seconds]
    min_repair : float
        Minimum repair time. [seconds]
    max_repair : float
        Maximum repair time. [seconds]
    failure_state : Mode or callable, defualt Mode.OPEN
        State of the connection to the grid following a failure. If a callable
        must accept no arguments and return a :py:class:`Mode`.
    repair_state : Mode of callable, default Mode.CLOSED
        State of the connection to the grid following repair.  If a callable
        must accept no arguments and return a :py:class:`Mode`.
    """
    def __init__(self, mtbf, min_repair, max_repair,
                 failure_state=Mode.OPEN,
                 repair_state=Mode.CLOSED):
        self.mtbf = mtbf
        self.min_repair = min_repair
        self.max_repair = max_repair
        self._failure_state = failure_state
        self._repair_state = repair_state
        self._failure_time = 0.0
        self._time = 0.0
        self._sample_failure()

    def _sample_failure(self):
        self._failure_time = self._time + random.expovariate(
            1.0 / self.mtbf
        )
        self._next_failure = Failure(
            repair_time=random.uniform(self.min_repair, self.max_repair),
            connection=self._get_failure_state(),
            repair=Repair(connection=self._get_repair_state())
        )

    def _get_repair_state(self):
        if callable(self._repair_state):
            return self._repair_state()
        return self._repair_state

    def _get_failure_state(self):
        if callable(self._failure_state):
            return self._failure_state()
        return self._failure_state

    def _repair_completion_time(self):
        return self._failure_time + self._next_failure.repair_time

    def next_update(self) -> float:
        if self._time < self._failure_time:
            return self._failure_time
        return self._repair_completion_time()

    def update(self, time, **kwargs):
        self._time = time
        if time >= self._repair_completion_time():
            self._sample_failure()

    @property
    def failure(self) -> Optional[Failure]:
        if self._time >= self._failure_time:
            return self._next_failure
        return None


class MultiModeReliabilityModel:
    """A reliability model for a single component with multiple failure modes.

    The model consists of a collection of failure modes that operate
    concurrently. In other words, during normal operation every failure mode is
    active and can trigger a failure of the component. When a failure mode is
    triggered it returns a :py:class:`Failure` object and failures from all
    other failure modes are suppressed until the restoration time specified by
    :py:class:`Failure`. At that time all failure modes are reinstated and any
    failures that would have occurred while the device was inoperable are
    immediately applied.
    """
    def __init__(self):
        self.time = 0.0
        self._failure_time = None
        self.active_failure: Optional[Failure] = None
        self._pending_failures: deque[Failure] = deque()
        self._failure_modes: List[FailureMode] = []

    def add_failure_mode(self, mode: FailureMode):
        """Add a new failure mode to the reliability model."""
        self._failure_modes.append(mode)

    def update(self, time, **kwargs):
        """Advance the failure mode models to the current time.

        Parameters
        ----------
        time : float
            Current time. [seconds]
        kwargs
            Can be used to pass additional information to the failure mode models.
        """
        self.time = time
        for failure_mode in self._failure_modes:
            failure_mode.update(time, **kwargs)
            failure = failure_mode.failure
            if failure is not None:
                self._pending_failures.appendleft(failure)

    def next_update(self) -> float:
        """Return the time when the model needs to update next.

        This may or may not correspond to the time of a reliability event,
        if the reliability model needs information about the operation of the
        component then this can be used to ensure that information is
        periodically updated.

        Returns
        -------
        float
            Time of the next update [seconds].
        """
        next_failure_mode_update = min(
            mode.next_update() for mode in self._failure_modes
        )
        if self.active_failure is not None:
            return min(
                next_failure_mode_update,
                self._failure_time + self.active_failure.repair_time
            )
        return next_failure_mode_update

    def repair_complete(self) -> bool:
        """Return True if the repair time for the active failure has passed."""
        if self.active_failure is None:
            return True
        repair_time = self.active_failure.repair_time + self._failure_time
        return repair_time <= self.time

    def next_event(self) -> Optional[Union[Repair, Failure]]:
        """Return the next reliability event affecting this component.

        Returns
        -------
        Failure or Repair or None
            If no events are scheduled at the present time, then None is
            returned, otherwise a :py:class:`Failure` or :py:class`Repair`
            event is returned.
        """
        if self.active_failure is None and self.has_pending_failure():
            # make the first pending failure active and return it
            self._failure_time = self.time
            self.active_failure = self._pending_failures.pop()
            return self.active_failure
        if self.active_failure is not None and self.repair_complete():
            repair = self.active_failure.repair
            self.active_failure = None
            self._failure_time = None
            return repair
        # no repair and no failure
        return None

    def has_pending_failure(self):
        """Return True if one of the failure modes has generated a failure."""
        return len(self._pending_failures) > 0

    def is_failed(self) -> bool:
        """Return True if there is an active failure or a pending failure."""
        return ((self.active_failure is not None)
                or (len(self._pending_failures) > 0))


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


class GridReliabilityModel:
    def __init__(self, config_file):
        with open(config_file) as f:
            config = json.load(f)
        self._model_params = config["reliability"]
        dssutil.load_model(config["dss_file"])
        lines = list(
            dssutil.iterate_properties(opendssdirect.Lines, ["IsSwitch"])
        )
        self._lines = {
            line: self._make_line_reliability_model()
            for line, properties in lines if not properties.IsSwitch
        }
        self._switches = {
            switch: self._make_switch_reliability_model(switch)
            for switch, properties in lines if properties.IsSwitch
        }

    def _make_line_reliability_model(self):
        """Construct a line reliability model"""
        rm = MultiModeReliabilityModel()
        rm.add_failure_mode(
            AgingFailure(
                self._model_params["line"]["mtbf"]*3600,
                self._model_params["line"]["min_repair"]*3600,
                self._model_params["line"]["max_repair"]*3600
            )
        )
        return rm

    def _make_switch_reliability_model(self, switch):
        rm = MultiModeReliabilityModel()
        print(f"making reliability model for switch: {switch}")
        rm.add_failure_mode(
            AgingFailure(
                self._model_params["switch"]["mtbf"]*3600,
                self._model_params["switch"]["min_repair"]*3600,
                self._model_params["switch"]["max_repair"]*3600,
                failure_state=lambda: _random_mode(
                    self._model_params["switch"]["p_open"],
                    self._model_params["switch"]["p_closed"]
                ),
                repair_state=_switch_state_normal(switch)
            )
        )
        return rm

    def peek(self):
        return min(
            model.next_update() for model in self.all_models()
        )

    def events(self):
        for component, model in self._all_components():
            event = model.next_event()
            if event is not None:
                yield _make_event(event, f"{component}")

    def _all_components(self):
        return itertools.chain(
            self._lines.items(),
            self._switches.items()
        )

    def all_models(self):
        return itertools.chain(
            self._lines.values(),
            self._switches.values()
        )

    def update(self, time):
        for model in self.all_models():
            model.update(time)


def _make_event(event, element):
    if isinstance(event, Failure):
        return Event(EventType.FAIL, event.connection, element, event.data)
    return Event(EventType.RESTORE, event.connection, element, event.data)


def _random_mode(p_open, p_closed):
    p = random.uniform(0, 1)
    if p < p_open:
        return Mode.OPEN
    if p < p_open + p_closed:
        return Mode.CLOSED
    return Mode.CURRENT


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
