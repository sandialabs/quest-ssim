"""Manage federate timing"""
from helics import (
    HelicsValueFederate,
    HelicsMessageFederate,
    HelicsLogLevel,
    helics_time_maxtime
)


def schedule(federate, next_update, max_time=None):
    """Yield times that the federate must evaluate a solution.

    federate : helics.HelicsFederate
        The federate handle.
    next_update : Callable
        A callable that returns the next time the federate wants to
        evaluate.
    max_time : float, optional
        Maximum time that will be returned.
    """
    granted_time = 0.0
    max_time = max_time or helics_time_maxtime
    while granted_time <= max_time:
        request_time = next_update()
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
        f"preempted @ {granted} (requested: {requested}) - "
        + ", ".join(updated_inputs(federate)),
        HelicsLogLevel.TRACE)


def _updated_inputs(federate):
    updated = []
    for name, subscription in federate.subscriptions.items():
        if subscription.is_updated():
            federate.log_message(
                f"subscription {subscription.key} updated",
                HelicsLogLevel.TRACE
            )
            updated.append(name)
    return updated


def _updated_endpoints(federate):
    updated = []
    for name, endpoint in federate.endpoints.items():
        if endpoint.has_message():
            federate.log_message(
                f"endpoint {endpoint.name} updated",
                HelicsLogLevel.TRACE
            )
            updated.append(name)
    return updated


def updated_inputs(federate):
    if isinstance(federate, HelicsValueFederate):
        return _updated_inputs(federate)
    if isinstance(federate, HelicsMessageFederate):
        return _updated_endpoints(federate)
    return _updated_inputs(federate) + _updated_endpoints(federate)
