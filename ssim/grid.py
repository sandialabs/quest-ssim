"""Representation of the electric grid.

Contains a grid specification that can be used to construct
data structures and models used by the various simulation federates.
"""
import json
import pathlib
from dataclasses import dataclass, field
from os import PathLike
from typing import Optional, List, Tuple


#: Type for a curve specified as x, y pairs.
Curve = Tuple[Tuple[float, float], ...]


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
            controller_params=params.pop("controller_params"),
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

    #: Number of phases the inverter is connected to.
    phases: int = 3

    #: Additional parameters
    params: dict = field(default_factory=dict)

    #: Inverter efficiency relative to power output (per-unit of `kva_rated`).
    inverter_efficiency: Optional[Curve] = None

    # Maximum DC array output at changing temperature relative to `pmpp`.
    pt_curve: Optional[Curve] = None


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
        for device in self.storage_devices:
            if device.name == name:
                return device
        raise KeyError(f"no storage device named '{name}'")

    @classmethod
    def from_json(cls, file: str):
        with open(file) as f:
            spec = json.load(f)
        grid = cls(pathlib.Path(spec["dss_file"]))
        for device in spec["storage"]:
            grid.add_storage(
                StorageSpecification.from_dict(device)
            )
        return grid
