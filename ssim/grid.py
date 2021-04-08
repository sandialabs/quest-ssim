"""Representation of the electric grid.

Contains a grid specification that can be used to construct
data structures and models used by the various simulation federates.
"""
from dataclasses import dataclass, field
from os import PathLike
from typing import Optional


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

    #: Additional storage parameters passed to the grid model.
    params: dict = field(default_factory=dict)

    #: Additional parameters to be passed to the controller constructor.
    controller_params: dict = field(default_factory=dict)


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
        self.storage_devices = []

    def add_storage(self, specs: StorageSpecification):
        """Add a storage device to the grid specification.

        Parameters
        ----------
        specs : StorageSpecification
            Specifications for the device.
        """
        self.storage_devices.append(specs)
