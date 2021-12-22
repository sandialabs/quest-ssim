import logging

from ssim import ems
from ssim.grid import (
    PVStatus,
    GeneratorStatus,
    StorageStatus,
    LoadStatus
)


class CompositeHeuristicEMS(ems.Dispatcher):
    """Energy Management system designed to operate on a fractured grid.

    For each connected grid component a separate HeuristicEMS instance
    is created to dispatch the grid elements connected to it. The
    CompositeHeuristicEMS manages the set of EMS sub-instances and
    allows them to be simulated as if they are a single EMS.

    Parameters
    ----------
    grid_model : GridModel
        Model of the initial state of the grid.
    """

    def __init__(self, grid_model):
        self._time = 0.0
        self._grid_model = grid_model
        self._component_ems = {
            frozenset(component): self._new_ems(component)
            for component in grid_model.components()
        }

    def _new_ems(self, component):
        """Create a new EMS to manage a subset of the grid.

        Parameters
        ----------
        component : frozenset
            The set up busses in the component managed by this EMS instance.

        Returns
        -------
        HeuristicEMS
            A new HeuristicEMS instance to manage the storage devices
            connected to `component`.
        """
        return HeuristicEMS(
            self._grid_model.storage_spec(device)
            for device in self._grid_model.connected_storage(component)
        )

    def _update_components(self, grid_model):
        self._grid_model = grid_model
        old_ems_instances = self._component_ems
        self._component_ems = {}
        for component in map(frozenset, self._grid_model.components()):
            if component in old_ems_instances:
                self._component_ems[component] = old_ems_instances[component]
            else:
                self._component_ems[component] = self._new_ems(component)

    def update(self, time, inputs, grid_model, plan=None):
        # For each component sum the generation and demand, then pass
        # it to the HeuristicEMS instance responsible for that component.
        self._time = time
        self._update_components(grid_model)
        components = self._component_ems.keys()
        load = {component: 0.0 for component in components}
        pv_generation = {component: 0.0 for component in components}
        ess_status = {component: [] for component in components}
        for message in inputs:
            if isinstance(message, PVStatus):
                component = frozenset(
                    grid_model.component_from_element(
                        f"pvsystem.{message.name}"
                    )
                )
                pv_generation[component] += message.kw
            elif isinstance(message, StorageStatus):
                component = frozenset(
                    grid_model.component_from_element(
                        f"storage.{message.name}"
                    )
                )
                ess_status[component].append(message)
            elif isinstance(message, LoadStatus):
                component = frozenset(
                    grid_model.component_from_element(
                        f"load.{message.name}"
                    )
                )
                load[component] += message.kw
            elif isinstance(message, GeneratorStatus):
                print(f"got generator status message: {message}")
                # TODO update generator statuses
            else:
                logging.warning(f"unexpected status message: {message}")
        for component, component_ems in self._component_ems.items():
            component_ems.update_actual_demand(load[component])
            component_ems.update_actual_generation(pv_generation[component])
            for ess in ess_status[component]:
                component_ems.update_storage(ess.name.lower(), ess.soc)

    def output(self):
        for component_ems in self._component_ems.values():
            for device, dispatch in component_ems.dispatch_storage().items():
                yield device, dispatch

    def next_update(self):
        # return min(ems.next_update() for ems in self._component_ems.values())
        return self._time + 300.0


class HeuristicEMS:
    """Rule-based energy management system for storage devices.

    Parameters
    ----------
    storage_devices : Iterable of grid.StorageSpecification
        Storage devices that will managed by this ems.
    minimum_soc : float, default 0.2
        Minimum state of charge allowed for any storage device.
    """
    def __init__(self, storage_devices, minimum_soc=0.2):
        self._minimum_soc = minimum_soc
        self._actual_demand = 0.0
        self._actual_generation = 0.0
        self._storage_soc = {}
        self._storage_kw_rated = {}
        self._excess_generation = 0.0
        for device in storage_devices:
            self._storage_soc[device.name.lower()] = device.soc
            self._storage_kw_rated[device.name.lower()] = device.kw_rated

    @classmethod
    def from_existing(cls, storage_devices, ems_instances):
        """Create a new HeuristicEMS instance based on existing instances.

        The state of charge of each storage device is copied from one of the
        instances in `ems_instances`.

        Parameters
        ----------
        storage_devices : Iterable of StorageSpecification
            Storage devices that are to be managed by this EMS.
        ems_instances : Iterable of HeuristicEMS
            Existing EMS instances to get storage state from.

        Returns
        -------
        HeuristicEMS
            New EMS instance.
        """
        new_ems = cls(
            storage_devices,
            minimum_soc=min(
                component_ems._minimum_soc for component_ems in ems_instances
            )
        )
        for device in storage_devices:
            for component_ems in ems_instances:
                if device in component_ems._storage_soc:
                    name = device.name.lower()
                    soc = component_ems._storage_soc[name]
                    new_ems._storage_soc[name] = soc

    def update_actual_generation(self, generation):
        self._actual_generation = generation

    def update_actual_demand(self, demand):
        self._actual_demand = demand

    def update_storage(self, name, storage_soc):
        self._storage_soc[name] = storage_soc

    def _charge_device(self, device):
        if self._storage_soc[device] < 1.0:
            target_power = min(
                self._storage_kw_rated[device], self._excess_generation
            )
            self._excess_generation -= target_power
            return ems.StorageControlMessage.charge(target_power)
        return ems.StorageControlMessage.idle()

    def _discharge_device(self, device):
        if self._storage_soc[device] > self._minimum_soc:
            target_power = min(
                self._storage_kw_rated[device], abs(self._excess_generation)
            )
            self._excess_generation += target_power
            return ems.StorageControlMessage.discharge(target_power)
        return ems.StorageControlMessage.idle()

    def _dispatch_device(self, storage_name):
        if self._excess_generation > 0.0:
            return self._charge_device(storage_name)
        if self._excess_generation == 0.0:
            return ems.StorageControlMessage.idle()
        if self._excess_generation < 0.0:
            return self._discharge_device(storage_name)

    def dispatch_storage(self):
        """Dispatch storage devices in a fixed, arbitrary order based on excess
        generation.
        """
        self._excess_generation = self._actual_generation - self._actual_demand
        return {
            name: self._dispatch_device(name) for name in self._storage_soc
        }
