"""Utilities for working with OpenDSSDirect."""
import warnings
from collections import namedtuple
from collections.abc import Iterable
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


def run_command(command: str, warn: bool = False) -> str:
    """Run an opendss command.

    Wrapper around the :py:func:`opendssdirect.run_command`
    function that provides error checking and transforms errors into
    exceptions (or warnings).

    Parameters
    ----------
    command : str
        OpenDSS command to execute.
    warn : bool, default False
        If True errors are reported as warnings instead of exceptions.
    """
    return _check_result(dssdirect.run_command(command), warn)


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
