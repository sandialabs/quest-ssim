"""Manage federate timing"""
from helics import (
    HelicsValueFederate,
    HelicsMessageFederate,
    HelicsCombinationFederate,
    HelicsLogLevel,
    helics_time_maxtime
)


def schedule(federate, next_update=None, max_time=None):
    """Yield times that the federate must evaluate a solution.

    federate : helics.HelicsFederate
        The federate handle.
    next_update : Callable, optional
        A callable that returns the next time the federate wants to
        evaluate. If not specified the requested time is fixed at
        :py:attr:`helics.helics_time_maxtime`. This facilitates
        creating schedules for federates that are entirely
        event-driven by input from other federates.
    max_time : float, optional
        Maximum time that will be returned.

    """
    granted_time = 0.0
    max_time = max_time or helics_time_maxtime
    request_time = helics_time_maxtime
    while granted_time < max_time:
        if next_update is not None:
            request_time = next_update()
        if request_time > max_time:
            request_time = max_time
        federate.log_message(f"requesting time: {request_time}",
                             HelicsLogLevel.TRACE)
        granted_time = federate.request_time(request_time)
        if request_time > granted_time:
            log_preemption(federate, request_time, granted_time)
        else:
            federate.log_message(f"granted requested time: {granted_time}",
                                 HelicsLogLevel.TRACE)
        yield granted_time


def log_preemption(federate, requested, granted):
    """Log information about why the federate was preempted.

    Parameters
    ----------
    federate : helics.HelicsFederate
    requested : float
        Time that was requested
    granted : float
        Time that was granted
    """
    federate.log_message(
        f"preempted by updates on: "
        + ", ".join(updated_inputs(federate)),
        HelicsLogLevel.TRACE)


def _updated_inputs(federate):
    updated = []
    for name, subscription in federate.subscriptions.items():
        if subscription.is_updated():
            federate.log_message(
                f"subscription {name} updated",
                HelicsLogLevel.TRACE
            )
            updated.append(name)
    return updated


def _updated_endpoints(federate):
    updated = []
    for name, endpoint in federate.endpoints.items():
        if endpoint.has_message():
            federate.log_message(
                f"endpoint {name} updated",
                HelicsLogLevel.TRACE
            )
            updated.append(name)
    return updated


def updated_inputs(federate):
    updated_subscriptions = []
    updated_endpoints = []
    if isinstance(federate, HelicsValueFederate):
        updated_subscriptions = _updated_inputs(federate)
    if isinstance(federate, HelicsMessageFederate):
        updated_endpoints = _updated_endpoints(federate)
    return updated_subscriptions + updated_endpoints
