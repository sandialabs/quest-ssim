"""Representation of the electric grid.

Contains a grid specification that can be used to construct
data structures and models used by the various simulation federates.
"""
import dataclasses
import json
import pathlib
from dataclasses import dataclass, field
from os import PathLike
from typing import Optional, List, Tuple


#: Type for a curve specified as x, y pairs.
Curve = Tuple[Tuple[float, float], ...]


def _curve_from_dict(curve):
    if curve.keys() < {"x", "y"}:
        raise ValueError("Invalid curve specification. Must include keys "
                         f"'x' and 'y', got {set(curve.keys())}.")
    return tuple(zip(curve["x"], curve["y"]))


def _get_curve(name, params):
    """Return the curve associated with name in params.

    Looks for a dictionary with keys "x" and "y" associated with the key
    `name` in `params`. If `name` exists in `params` it is removed before
    this function returns.

    Parameters
    ----------
    name : str
        Name of the curve in params.
    params : dict
        Dictionary of parameters.

    Returns
    -------
    None or Curve
        If `name` is found in `params` its value is used to construct a curve
        that is returned. If `name` is not a key in `params` then None is
        returned.
    """
    if name not in params:
        return None
    return _curve_from_dict(params.pop(name))


@dataclass
class StorageSpecification:
    """Description of a storage device connected to the grid."""

    #: Device name. Should be unique among all storage devices.
    name: str

    #: Bus where the device is connected.
    bus: str

    #: Rated capacity of the device [kWh].
    kwh_rated: float

    #: Rated maximum power output [kW].
    kw_rated: float

    #: Type of the controller for this device.
    controller: str

    #: Number of phases to which the device is connected.
    phases: int = 3

    #: State of charge (between 0 and 1).
    soc: float = field(default=1.0)

    #: Additional storage parameters passed to the grid model.
    params: dict = field(default_factory=dict)

    #: Inverter efficiency relative to power output (per-unit of `kva_rated`).
    inverter_efficiency: Optional[Curve] = None

    #: Additional parameters to be passed to the controller constructor.
    controller_params: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, params: dict):
        """Build a StorageSpecification instance from a dict with OpenDSS keys.

        Parameters
        ----------
        params : dict
            Dictionary with keys that have the same names as OpenDSS storage
            device parameters. Some additional keys are also expected that have
            the same names as the StorageSpecification fields they represent
            (e.g. "controller" and "controller_params").
        """
        # copy the dict so we can modify it with impunity
        params = params.copy()
        # pop the keys off so we are left with only the extra OpenDSS params.
        return cls(
            params.pop("name"),
            params.pop("bus"),
            params.pop("kwhrated"),
            params.pop("kwrated"),
            params.pop("controller"),
            params.pop("phases", 3),
            params.pop("%stored", 50) / 100,
            inverter_efficiency=_get_curve("inverter_efficiency", params),
            controller_params=params.pop("controller_params", dict()),
            params=params
        )


@dataclass
class InvControlSpecification:

    #: Name of the InvControl element.
    name: str

    #: List of PVSystem and/or Storage elements to be controlled.
    der_list: List[str]

    #: Control mode to be enabled (should be based on OpenDSS)
    inv_control_mode: str

    #: Curve that defines behavior of the specified mode (define this when
    # implementing a single inverter function)
    function_curve_1: Optional[Curve] = None

    #: Curve that defines behavior of the specified mode (define this in
    # addition to function_curve_1 when implementing combined inverter
    # functions)
    function_curve_2: Optional[Curve] = None

    #: Additional parameters
    params: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, params: dict):
        """Build a InvControlSpecification from a dict with OpenDSS keys.

        Parameters
        ----------
            Dictionary with keys that have the same names as OpenDSS
            InvControl parameters.
        """
        # copy the dict so we can modify it with impunity
        params = params.copy()
        # pop the keys off so we are left with only the extra OpenDSS params.
        return cls(
            params.pop("name"),
            params.pop("der_list"),
            params.pop("inv_control_mode"),
            function_curve_1=_get_curve("function_curve_1", params),
            function_curve_2=_get_curve("function_curve_2", params),
            params=params
        )


@dataclass
class PVSpecification:

    #: Name of the PV system.
    name: str

    #: Bus where the PV system is connected to the grid.
    bus: str

    #: Maximum power output of the PV Array at :math:`1.0kW/m^2`
    pmpp: float

    #: Inverter kVA rating [kVA].
    kva_rated: float

    #: List of irradiance values for PV system in :math:`kW/m^2`
    irradiance_profile: Optional[PathLike] = None

    #: Number of phases the inverter is connected to.
    phases: int = 3

    #: Additional parameters
    params: dict = field(default_factory=dict)

    #: Inverter efficiency relative to power output (per-unit of `kva_rated`).
    inverter_efficiency: Optional[Curve] = None

    #: Maximum DC array output at changing temperature relative to `pmpp`.
    pt_curve: Optional[Curve] = None

    @classmethod
    def from_dict(cls, params: dict):
        """Build a PVSpecification instance from a dict with OpenDSS keys.

        Parameters
        ----------
        params: dict
            Dictionary with keys that have the same names as OpenDSS PVSystem
            parameters. Some additional keys are also expected that have the
            same names as the PVSpecification fields they represent
            (e.g. "inverter_efficiency" and "pt_curve").
        """
        # copy the dict so we can modify it with impunity
        params = params.copy()
        # pop the keys off so we are left with only the extra OpenDSS params
        return cls(
            params.pop("name"),
            params.pop("bus"),
            params.pop("pmpp"),
            params.pop("kva_rated"),
            params.pop("irradiance_profile"),
            params.pop("phases", 3),
            inverter_efficiency=_get_curve("inverter_efficiency", params),
            pt_curve=_get_curve("pt_curve", params),
            params=params
        )


class GridSpecification:
    """Specification of the grid.

    Parameters
    ----------
    file : PathLike, optional
        Path to a file containing a grid description that can be loaded by
        the grid simulator (for example "circuit.dss").
    """
    def __init__(self, file: Optional[PathLike] = None):
        self.file = file
        self.storage_devices: List[StorageSpecification] = []
        self.pv_systems: List[PVSpecification] = []
        self.inv_control: List[InvControlSpecification] = []
        self.busses_to_log: List[str] = []

    def add_storage(self, specs: StorageSpecification):
        """Add a storage device to the grid specification.

        Parameters
        ----------
        specs : StorageSpecification
            Specifications for the device.
        """
        self.storage_devices.append(specs)

    def add_pvsystem(self, specs: PVSpecification):
        """Add a PV system to the grid specification.

        Parameters
        ----------
        specs : PVSpecification
            Specifications for the PV system.
        """
        self.pv_systems.append(specs)

    def add_inv_control(self, specs: InvControlSpecification):
        """Add a InvControl element to the grid specification.

        Parameters
        ----------
        specs : InvControlSpecification
            Specifications for the InvControl element.
        """
        self.inv_control.append(specs)

    def get_storage_by_name(self, name):
        """Return the specification of the storage device named `name`.

        Parameters
        ----------
        name : str
            Name of the device.

        Returns
        -------
        StorageSpecification
            Specification of the storage device named `name`.

        Raises
        ------
        KeyError
            If the device is not found.
        """
        name = name.lower()
        for device in self.storage_devices:
            if device.name.lower() == name:
                return device
        raise KeyError(f"no storage device named '{name}'")

    @classmethod
    def from_json(cls, file: str):
        with open(file) as f:
            spec = json.load(f)
        grid = cls(pathlib.Path(spec["dss_file"]))
        grid.busses_to_log = set(spec.get("busses_to_log", []))
        for device in spec["storage"]:
            grid.add_storage(
                StorageSpecification.from_dict(device)
            )
        for device in spec["pvsystem"]:
            grid.add_pvsystem(
                PVSpecification.from_dict(device)
            )
        for device in spec["invcontrol"]:
            grid.add_inv_control(
                InvControlSpecification.from_dict(device)
            )
        return grid


class StatusMessage:
    """Base class for status messages.

    Provides methods for serializing status messages to JSON strings
    and for de-serializing JSON strings to status messages.
    """

    __slots__ = []

    def to_json(self):
        """Get a JSON representation of the status message.

        Returns
        -------
        str
            JSON encoding of the status message.
        """
        message_type = type(self).__name__
        message_data = dataclasses.asdict(self)
        return json.dumps({"message_type": message_type, **message_data})

    @classmethod
    def from_json(self, jsonstr):
        """Parse a JSON string and return the status message it represents.

        Parameters
        ----------
        jsonstr : str
            String containing the JSON representation of a status message.

        Returns
        -------
        StatusMessage
        """
        message = json.loads(jsonstr)
        message_type = message.pop("message_type")
        if message_type == "StorageStatus":
            return StorageStatus(**message)
        if message_type == "PVStatus":
            return PVStatus(**message)
        if message_type == "GeneratorStatus":
            return GeneratorStatus(**message)
        if message_type == "LoadStatus":
            return LoadStatus(**message)


@dataclass
class StorageStatus(StatusMessage):
    """Status of a storage system."""

    __slots__ = ['name', 'soc']

    name: str
    soc: float


@dataclass
class PVStatus(StatusMessage):
    """Status of a PV System."""

    __slots__ = ['name', 'kw', 'kvar']

    name: str
    kw: float
    kvar: float


@dataclass
class GeneratorStatus(StatusMessage):
    """Status of a Fossil Generator."""

    __slots__ = ['name', 'kw', 'kvar', 'operating_time', 'online']

    name: str

    #: Real power output from the generator
    kw: float

    #: Reactive power output from the generator.
    kvar: float

    #: Cumulative time the generator has been in operation. [hours]
    operating_time: float

    #: True if the generator is online and can respond to dispatch commands.
    online: bool


@dataclass
class LoadStatus(StatusMessage):
    """Status of a single load"""

    __slots__ = ['name', 'kw', 'kvar']

    name: str
    kw: float
    kvar: float
