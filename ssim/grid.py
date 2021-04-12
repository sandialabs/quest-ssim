"""Representation of the electric grid.

Contains a grid specification that can be used to construct
data structures and models used by the various simulation federates.
"""
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

    #: Additional parameters to be passed to the controller constructor.
    controller_params: dict = field(default_factory=dict)


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
    inverter_efficiency: Optional[Curve] = field(default=None)

    # Maximum DC array output at changing temperature relative to `pmpp`.
    pt_curve: Optional[Curve] = field(default=None)


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
