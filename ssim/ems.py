"""Energy Management System.

The EMS executes at a fixed interval to determine power set-points for all
storage devices and generators connected to the grid. To determine these
set points the EMS needs to know the following:

- Actual load
- Forecasted load
- Actual renewable generation
- Forecasted renewable generation
- Actual state of all devices on the grid (and grid topology)
- Fuel levels for fossil generators

The goal is to develop a framework into which we can plug in different
EMS realizations, without needing to do any work to reinvent the data
management components. To get to this point we should define some
manager classes to handle the data streams.

"""
import json
import logging

import opendssdirect as dssdirect

import networkx as nx

from ssim.grid import (
    GridSpecification,
    PVStatus, LoadStatus, StorageStatus, GeneratorStatus
)
from ssim.opendss import DSSModel
from ssim import dssutil, reliability


class GridModel:
    """Network model of the state of the grid.

    Represents the grid as an undirected graph. Vertexes correspond to
    busses, edges to power delivery elements (lines, switches, and
    transformers). Internally maintains a mapping between component
    names and edges or nodes in the grid as well as indexes to look up
    the node to which grid components are connected.

    The network is initialized by loading the grid specification into
    an OpenDSS model and iterating the power delivery and power conversion
    elements in the OpenDSS model.

    Parameters
    ----------
    gridspec : GridSpecification
        Specification of the grid and connected devices.
    """

    def __init__(self, gridspec):
        self._model = DSSModel.from_grid_spec(gridspec)
        self._gridspec = gridspec
        self._network = nx.Graph()
        self._devices = {}
        self._edges = {}
        self._initialize_network()

    @classmethod
    def from_json(cls, config):
        """Construct a grid model based on the configuration in `config`.

        Parameters
        ----------
        config : str or PathLike
            Path to a JSON config file.

        Returns
        -------
        GridModel
            Initialized model of the grid and extra devices specified
            in `config`
        """
        spec = GridSpecification.from_json(config)
        return cls(spec)

    def _initialize_devices_and_loads(self):
        for element in dssdirect.Circuit.AllElementNames():
            dssdirect.Circuit.SetActiveElement(element)
            node = dssdirect.CktElement.BusNames()[0]
            bus = _node_to_bus(node)
            element = element.lower()
            element_type, name = element.split(".", maxsplit=1)
            element_set = self._network.nodes[bus].get(element_type, None)
            if element_set is not None:
                element_set.add(name)
                self._devices[element] = bus

    def _initialize_network(self):
        self._edges = {
            f"line.{name}": tuple(map(_node_to_bus, nodes))
            for name, nodes in dssutil.iterate_properties(
                dssdirect.Lines, ("Bus1", "Bus2")
            )
        }
        # TODO Identify switches and do NOT add an edge if the switch is open
        self._network.add_edges_from(self._edges.values())
        transformer_number = dssdirect.Transformers.First()
        while transformer_number > 0:
            name = dssdirect.Transformers.Name()
            bus1, bus2 = map(_node_to_bus, dssdirect.CktElement.BusNames())
            # add the edge, removing node names
            self._network.add_edge(bus1, bus2)
            self._edges[f"transformer.{name}"] = (bus1, bus2)
            transformer_number = dssdirect.Transformers.Next()
        # initialize the sets of connected devices at each node
        for node in self._network.nodes.values():
            node["storage"] = set()
            node["generator"] = set()
            node["pvsystem"] = set()
            node["failed_devices"] = set()
            node["load"] = set()
        self._initialize_devices_and_loads()

    def node(self, element):
        """Return the name of the node that `element` is associated with.

        Parameters
        ----------
        element : str
            Name of the element. Should be formatted in opendss-style, with
            the element type, a '.', and the element name. For example,
            'storage.foo'.

        Returns
        -------
        str
            Name of the node `element` is connected to.
        """
        return self._devices[element.lower()]

    @property
    def num_components(self):
        """Return the number of distinct connected components."""
        return nx.number_connected_components(self._network)

    def components(self):
        """Return an iterator over the connected components.

        Return
        ------
        Iterable of set
            Each component is represented by a set of busses that are
            connected to that component.
        """
        return nx.connected_components(self._network)

    def component_from_element(self, element):
        """Return the connected component that contains element.

        Parameters
        ----------
        element : str
            Name of the element.

        Returns
        -------
        set
            Set of nodes in the component tha includes `element`
        """
        return nx.node_connected_component(
            self._network,
            self.node(element)
        )

    def _connected_elements(self, component, element_type):
        for node_name in component:
            node = self._network.nodes[node_name]
            for element in node.get(element_type, set()):
                yield element

    def connected_generators(self, component):
        """Iterator over all generators connected to busses in a component.

        Parameters
        ----------
        component : Iterable of str
            Set of busses that form a connected component in the grid.

        Returns
        -------
        Generator
            Names of generators connected to busses in `component`.
        """
        return self._connected_elements(component, "generator")

    def connected_storage(self, component):
        """Iterator over all storage devices connected to busses in `component`

        Parameters
        ----------
        component : Iterable of str
            Set of busses that from a connected component in the grid.

        Returns
        -------
        Generator
            Names of all the storage devices connected to nodes in `component`.
        """
        return self._connected_elements(component, "storage")

    def storage_spec(self, storage_name):
        """Return the specs for the storage device.

        Parameters
        ----------
        storage_name : str
            Name of the storage device.

        Returns
        -------
        grid.StorageSpecification
            Specification of the storage device.
        """
        return self._gridspec.get_storage_by_name(storage_name)

    def connected_pvsystems(self, component):
        """Iterator over all PV systems connected to busses in `component`.

        Parameters
        ----------
        component : Iterable of str
            Set of busses that form a connected component in the grid.

        Returns
        -------
        Generator
            Names of PVSystems connected to busses in `component`
        """
        return self._connected_elements(component, "pvsystem")

    def connected_loads(self, component):
        """Iterator over all loads connected to busses in `component`.

        Parameters
        ----------
        component: Iterable of str
            Set of busses that form a connected component in the grid.

        Returns
        -------
        Generator
            Names of loads connected to busses in `component`.
        """
        return self._connected_elements(component, "load")

    def connect(self, bus1, bus2):
        """Connect `bus1` to `bus2`."""
        self._network.add_edge(bus1, bus2)

    def disconnect(self, bus1, bus2):
        """Remove the direct connection between `bus1` and `bus2`"""
        self._network.remove_edge(bus1, bus2)

    def is_edge(self, name):
        """Return true if `name` is the name of an edge in the network.

        Parameters
        ----------
        name : str
            Name of the grid element.

        Returns
        -------
        bool
            True if the `name` is the name of an edge, otherwise False.
        """
        return name in self._edges.keys()

    def disable_edge(self, edge):
        """Remove the edge from the network.

        Parameters
        ----------
        edge : str
            Name of the edge to remove. (i.e. line or transformer name).
        """
        bus1, bus2 = self._edges[edge]
        self.disconnect(bus1, bus2)

    def enable_edge(self, edge):
        """Restore the edge, if it has been disabled.

        Parameters
        ----------
        edge : str
            Name of the edge to remove. (i.e. line or transformer name).
        """
        bus1, bus2 = self._edges[edge]
        self.connect(bus1, bus2)

    def disable_element(self, element):
        element = element.lower()
        element_node = self._network.nodes[self._devices[element]]
        element_type, element_name = element.split(".", maxsplit=1)
        devices = element_node.get(element_type, None)
        if devices is not None:
            devices.remove(element_name)
            element_node["failed_devices"].add(element)

    def enable_element(self, element):
        element = element.lower()
        element_node = self._network.nodes[self._devices[element]]
        element_type, element_name = element.split(".", maxsplit=1)
        devices = element_node.get(element_type, None)
        if devices is not None:
            devices.add(element_name)
            element_node["failed_devices"].remove(element)

    def _apply_event(self, event):
        """Apply a single reliability event to the grid model.

        Parameters
        ----------
        event : reliability.Event
        """
        if self.is_edge(event.element):
            self._apply_topology_event(event)
        else:
            self._apply_component_event(event)

    def _apply_component_event(self, event):
        if event.type is reliability.EventType.FAIL:
            self.disable_element(event.element)
        else:
            self.enable_element(event.element)

    def _apply_topology_event(self, event):
        if event.mode is reliability.Mode.OPEN:
            self.disable_edge(event.element)
        else:
            self.enable_edge(event.element)

    def apply_reliability_events(self, events):
        """Apply all reliability events in `events` to the grid model.

        Parameters
        ----------
        events : Iterable of reliability.Event
        """
        for event in events:
            self._apply_event(event)


def _node_to_bus(node_name):
    """Return an OpenDSS bus name, stripped of all node names."""
    return node_name.split(".", maxsplit=1)[0]


class CompositeHeuristicEMS:
    """A collection of HeuristicEMS instances.

    For each connected component in the grid there is a
    :py:class:`HeuristicEMS` instance to manage the generators and storage
    connected to that component. As the grid topology changes new EMS
    instances are constructed (when a component splits), and old EMS
    instances are combined (when components merge).

    Parameters
    ----------
    grid_spec : GridSpecification
        Grid specification
    """
    def __init__(self, grid_spec):
        self._grid_model = GridModel(grid_spec)
        self._component_ems = {
            tuple(component): self._new_ems(component)
            for component in self._grid_model.components()
        }
        self._time = 0.0

    def _new_ems(self, component):
        """Create a new EMS to manage a subset of the grid.

        Parameters
        ----------
        component : tuple of str
            The set up busses the EMS will be responsible for.

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

    def apply_reliability_events(self, events):
        """Notify the EMS of a set of reliability events.

        Parameters
        ----------
        events : Iterable of ReliabilityEvent
            Set of events to apply.
        """
        self._grid_model.apply_reliability_events(events)
        old_ems_instances = self._component_ems
        self._component_ems = {}
        for component in map(tuple, self._grid_model.components()):
            if component in self._component_ems:
                # the component still exists in the grid, unchanged
                self._component_ems[component] = old_ems_instances[component]
            else:
                self._component_ems[component] = self._new_ems(component)

    def update(self, messages):
        """Update EMS state based on status updates and other control messages.

        Parameters
        ----------
        messages : Iterable of dict
        """
        # For each component sum the generation and demand, then pass
        # it to the HeuristicEMS instance responsible for that component.
        components = self._component_ems.keys()
        load = {component: 0.0 for component in components}
        pv_generation = {component: 0.0 for component in components}
        ess_status = {component: [] for component in components}
        # make inverted indexes for each message type
        loads = {load: component
                 for component in components
                 for load in self._grid_model.connected_loads(component)}
        pvsystems = {
            pvsystem: component
            for component in components
            for pvsystem in self._grid_model.connected_pvsystems(component)
        }
        storage = {
            ess: component
            for component in components
            for ess in self._grid_model.connected_storage(component)
        }
        for message in messages:
            if isinstance(message, PVStatus):
                pv_generation[pvsystems[message.name.lower()]] += message.kw
            elif isinstance(message, StorageStatus):
                ess_status[storage[message.name.lower()]].append(message)
            elif isinstance(message, LoadStatus):
                load[loads[message.name.lower()]] += message.kw
            elif isinstance(message, GeneratorStatus):
                print(f"got generator status message: {message}")
            else:
                logging.warning(f"unnexpected status message: {message}")
        for component, ems in self._component_ems.items():
            ems.update_actual_demand(load[component])
            ems.update_actual_generation(pv_generation[component])
            for ess in ess_status[component]:
                ems.update_storage(ess.name.lower(), ess.soc)

    def next_update(self):
        """TODO Return the next time the EMS needs to update."""
        return self._time + 300  # 5 minutes

    def control_actions(self):
        """Return the set of control actions to be applied in the grid."""
        for ems in self._component_ems.values():
            for device, dispatch in ems.dispatch_storage().items():
                print(f"dispatch: {device} - {dispatch}")
                yield device, dispatch

    def step(self, time):
        """Generate a new set of control actions at `time`."""
        self._time = time


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
            minimum_soc=min(ems._minimum_soc for ems in ems_instances)
        )
        for device in storage_devices:
            for ems in ems_instances:
                if device in ems._storage_soc:
                    name = device.name.lower()
                    new_ems._storage_soc[name] = ems._storage_soc[name]

    def update_actual_generation(self, generation):
        self._actual_generation = generation

    def update_actual_demand(self, demand):
        self._actual_demand = demand

    def update_generation_forecast(self, generation_forecast):
        # not using forecasts yet
        pass

    def update_demand_forecast(self, demand_forecast):
        # not using forecasts yet
        pass

    def update_storage(self, name, storage_soc):
        self._storage_soc[name] = storage_soc

    def _charge_device(self, device):
        if self._storage_soc[device] < 1.0:
            target_power = min(
                self._storage_kw_rated[device], self._excess_generation
            )
            self._excess_generation -= target_power
            return StorageControlMessage.charge(target_power)
        return StorageControlMessage.idle()

    def _discharge_device(self, device):
        if self._storage_soc[device] > self._minimum_soc:
            target_power = min(
                self._storage_kw_rated[device], abs(self._excess_generation)
            )
            self._excess_generation += target_power
            return StorageControlMessage.discharge(target_power)
        return StorageControlMessage.idle()

    def _dispatch_device(self, storage_name):
        if self._excess_generation > 0.0:
            return self._charge_device(storage_name)
        if self._excess_generation == 0.0:
            return StorageControlMessage.idle()
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


class StorageControlMessage:
    """Control messages for storage devices.

    Parameters
    ----------
    action : str
        Control action. Can be 'charge', 'discharge', or 'idle'
    real_power : float
        Real power for charging or discharging. Should be positive for
        both, the direction is determined by `action`. If charging
        `real_power` is the power flowing into the device, if discharging
        it is the power flowing out of the device. [kW]
    reactive_power : float
        Reactive power setting for the device. Sign determines the direction
        of flow. [kVAR]
    """
    def __init__(self, action, real_power, reactive_power):
        if action not in {'charge', 'discharge', 'idle'}:
            raise ValueError(f"Unknown action {action}. Action must be one of "
                             "'charge', 'discharge', or 'idle'.")
        if action == 'idle' and real_power != 0:
            raise ValueError("If action is 'idle' real_power must be 0 (got "
                             f"{real_power}")
        self.action = action
        self.real_power = real_power
        self.reactive_power = reactive_power

    def __repr__(self):
        return f"StorageControlMessage({self.action}, " \
               f"kw={self.real_power}, " \
               f"kvar={self.reactive_power})"

    @classmethod
    def from_json(cls, data):
        """Construct a StorageControlMessage from a JSON string."""
        action = json.loads(data)
        return cls(action['action'], action['kW'], action['kVAR'])

    @classmethod
    def charge(cls, kw, kvar=0.0):
        return cls('charge', kw, kvar)

    @classmethod
    def discharge(cls, kw, kvar=0.0):
        return cls('discharge', kw, kvar)

    @classmethod
    def idle(cls):
        return cls('idle', 0.0, 0.0)

    def to_json(self):
        return json.dumps({'action': self.action,
                           'kW': self.real_power,
                           'kVAR': self.reactive_power})
