"""Utilities for working with OpenDSSDirect."""
import warnings
from collections import namedtuple
from collections.abc import Iterable
from typing import Optional

import pandas as pd
import opendssdirect as dssdirect


class OpenDSSError(Exception):
    """Exception raised when an OpenDSSDirect command has failed
    without raising an exception itself.

    This can happen when using the :py:func:`opendssdirect.run_command`
    function which reports errors by returning a non-empty string.
    """


def _check_result(result: str, warn: bool) -> str:
    """Raise an exception if result indicates an error.

    Returns
    -------
    str
        `result` unchanged.

    Raises
    ------
    OpenDSSError
        If `result` is not an empty string. `result` is assigned as the
        error message.
    """
    if result:
        if not warn:
            raise OpenDSSError(result)
        warnings.warn(
            f"OpenDSS command returned error: '{result}'",
            stacklevel=2
        )
    return result


def make_opendss_params(params: dict):
    """Return a string of OpenDSS paramters in `dict`.

    The returned string has the form "key1=value1 key2=value2 ..." for all
    items in `dict`.
    """
    return " ".join(
        f"{param}={value}" for param, value in params.items()
    )


def run_command(command: str,
                extra_args: Optional[dict] = None,
                warn: bool = False) -> str:
    """Run an opendss command.

    Wrapper around the :py:func:`opendssdirect.run_command`
    function that provides error checking and transforms errors into
    exceptions (or warnings).

    Parameters
    ----------
    command : str
        OpenDSS command to execute.
    extra_args : dict
        Extra parameters to be passed with the command. The dictionary is
        expanded to a string of the form "key1=value1 key2=value2 ..." and
        appended to `command` before command is executed.
    warn : bool, default False
        If True errors are reported as warnings instead of exceptions.
    """
    if extra_args is not None:
        command = f"{command} {make_opendss_params(extra_args)}"
    return _check_result(dssdirect.run_command(command), warn)


def get_property(property) -> str:
    result = dssdirect.run_command(f"? {property}")
    if result == "Property Unknown":
        raise OpenDSSError(f"Property Unknown: {property}")
    return result


def load_model(file):
    """Load the OpenDSS model described in `file`.

    Parameters
    ----------
    file : pathlike
        Path to the OpenDSS file containing the circuit description.

    Raises
    ------
    OpenDSSErrror
        If the file does not exist
    """
    run_command(f"redirect {file}")


def _get_properties(property_accessors: Iterable) -> Iterable:
    """Return the results of calling each element of `property_accessors`.

    Parameters
    ----------
    property_accessors : Iterable of Callable
        The accessor functions for the properties. Each function takes
        no arguments.

    Returns
    -------
    Iterable
        The results of evaluating each property accessor function.
    """
    return (property() for property in property_accessors)


def iterate_properties(element_type, properties=None):
    """Iterate over the elements of type `element_type` yielding a named tuple
    containing the values of all attributes for each element.

    This is an extended version of ``opendssdirect.utils.Iterator``. The
    main differences are that this iterator can query multiple properties and
    is eager whereas the opendss iterator is lazy, returning a function that
    will return the requested attribute when invoked.

    Parameters
    ----------
    element_type : module
        OpenDSS module for the elemet type to iterate over (i.e.
        ``opendssdirect.Loads``)
    properties : iterable of str, optional
        The names of the properties to querey for each element.
        If not specified then all properties specified by
        ``opendssdirect.utils.getmembers(element_type)`` are used.

    Examples
    --------
    >>> lines = iterate_properties(
    ...     opendssdirect.Lines, ("Bus1", "Bus2", "Length")
    ... )
    >>> next(lines)
    ("line1", properties(Bus1="b1.1.2.3", Bus2="b2.1.2.3", Length=2.3))
    >>> next(lines)
    ("line2", properties(Bus1="b1.1.2.3", Bus2="b2.1.2.3", Length=2.7))

    Raises
    ------
    AttributeError
        If one of the requested properties does not exist for the given
        element type.
    """
    if not properties:
        properties, accessors = zip(
            *dssdirect.utils.getmembers(element_type)
        )
    else:
        accessors = tuple(getattr(element_type, property)
                          for property in properties)
    # by using a named tuple we ensure the caller can identify the order
    # of the fields easily. A standard tuple would work well, and might be
    # slightly more efficient if `properties` is always specified by the
    # caller
    properties_tuple = namedtuple('properties', properties)
    element_type.First()
    yield element_type.Name(), properties_tuple(*_get_properties(accessors))
    while element_type.Next():
        yield element_type.Name(), properties_tuple(
            *_get_properties(accessors)
        )


def to_dataframe(element_type, properties=None):
    """Return a dataframe with the properties of all elements of type
    `element_type`.

    Parameters
    ----------
    element_type
        OpenDSSDirect module for the element type you are querying.
    properties
        Names of the properties to return. These names will be the columns
        of the returned DataFrame.

    Returns
    -------
    DataFrame
        DataFrame indexed by element name with a column for each property in
        `properties`.

    Raises
    ------
    AttributeError
        For the same reasons as :py:meth:`ssim.dssutil.iterate_properties`

    See Also
    --------
    ssim.dssutil.iterate_properties
    """
    if not properties:
        properties = tuple(
            name for name, _ in dssdirect.utils.getmembers(element_type)
        )
    names, props = zip(*iterate_properties(element_type, properties))
    return pd.DataFrame(props, index=names, columns=properties)


def open_terminal(full_name: str, terminal: int,
                  conductor: Optional[int] = None):
    """Open the conductor(s) connecting to `terminal`.

    Parameters
    ----------
    full_name : str
        Full name of the element to operate on (e.g. 'storage.stor1').
    terminal : int
        Terminal to open.
    conductor : int, optional
        Conductor to open. If not specified, all conductors are opened.

    Raises
    ------
    ValueError
        If the terminal is not a valid terminal for the circuit element
        specified by `full_name`.
    """
    dssdirect.Circuit.SetActiveElement(full_name)
    if terminal > dssdirect.CktElement.NumTerminals():
        raise ValueError("Invalid terminal. Attempt to open terminal "
                         f"{terminal}, but {full_name} has only "
                         f"{dssdirect.CktElement.NumTerminals()} terminals.")
    if conductor is not None:
        dssdirect.CktElement.Open(terminal, conductor)
    else:
        for conductor in dssdirect.CktElement.NodeOrder():
            dssdirect.CktElement.Open(terminal, conductor)


def close_terminal(full_name: str, terminal: int,
                   conductor: Optional[int] = None):
    """Close the conductor(s) connecting to `terminal`.

    Parameters
    ----------
    full_name : str
        Full name of the element to operate on (e.g. 'storage.stor1').
    terminal : int
        Terminal to close.
    conductor : int, optional
        Conductor to close. If not specified, all conductors are closed.

    Raises
    ------
    ValueError
        If the terminal is not a valid terminal for the circuit element
        specified by `full_name`.
    """
    dssdirect.Circuit.SetActiveElement(full_name)
    if terminal > dssdirect.CktElement.NumTerminals():
        raise ValueError("Invalid terminal. Attempt to close terminal "
                         f"{terminal}, but {full_name} has only "
                         f"{dssdirect.CktElement.NumTerminals()} terminals.")
    if conductor is not None:
        dssdirect.CktElement.Close(terminal, conductor)
    else:
        for conductor in dssdirect.CktElement.NodeOrder():
            dssdirect.CktElement.Close(terminal, conductor)


def _set_switch_control_lock(element: str, locked: bool,
                             terminal: Optional[int] = None):
    """Lock/unlock switch controls associated with `element`.

    Parameters
    ----------
    element : str
        Name of the circuit element that is being controlled.
    locked : bool
        Lock state to set. If True the controller is locked, if False the
        controller is unlocked.
    terminal : int, optional
        If specified, only switch controllers that switch `terminal` are
        locked/unlocked. If not specified, all switch controllers associated
        with `element` are locked/unlocked.
    """
    dssdirect.Circuit.SetActiveElement(element)
    if not dssdirect.CktElement.HasSwitchControl():
        return
    all_controllers = [dssdirect.CktElement.Controller(index)
                       for index in range(
                           1, dssdirect.CktElement.NumControls()+1)]
    switch_controllers = [controller for controller in all_controllers
                          if controller.startswith("SwtControl.")]
    for controller in switch_controllers:
        if (terminal is None
                or terminal == dssdirect.SwtControls.SwitchedTerm()):
            dssdirect.Circuit.SetActiveElement(controller)
            dssdirect.SwtControls.IsLocked(locked)


def lock_switch_control(element: str, terminal: Optional[int] = None):
    """Lock any switch controllers for `terminal`.

    If there is no switch control object for `element` then no action is
    taken. If the terminal is specified then only switch controllers that
    switch `terminal` of `element` are locked.

    Parameters
    ----------
    element : str
        Full name of the controlled opendss element.
    terminal : int, optional
        The terminal of `element` that the switch control is connected to.
    """
    _set_switch_control_lock(element, locked=True, terminal=terminal)


def unlock_switch_control(element: str, terminal: Optional[int] = None):
    """Unlock any switch controllers for `terminal`.

    If there is no switch control object for `element` then no action is
    taken. If the terminal is specified then only switch controllers that
    switch `terminal` of `element` are unlocked.

    Parameters
    ----------
    element : str
        Full name of the controlled opendss element.
    terminal : int, optional
        The terminal of `element` that the switch control is connected to.
    """
    _set_switch_control_lock(element, locked=False, terminal=terminal)
