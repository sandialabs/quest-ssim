"""Energy Management System.

The EMS executes at a fixed interval to determine power set-points for all
storage devices and generators connected to the grid. To determine these
set points the EMS needs to know the following:

- Current demand
- Forecasted demand
- Current renewable generation
- Forecasted renewable generation
"""
import json

import opendssdirect as dssdirect

import networkx as nx

from ssim.grid import GridSpecification
from ssim.opendss import DSSModel
from ssim import dssutil


class GridModel:
    """Model of the state of the grid.

    Parameters
    ----------
    config : Pathlike
        Path to the grid configuration file.
    """
    def __init__(self, config):
        self._model = DSSModel.from_grid_spec(
            GridSpecification.from_json(config)
        )
        self._network = nx.Graph()
        self._devices = {}
        self._edges = {}
        self._initialize_network()

    def _initialize_devices(self):
        for element in dssdirect.Circuit.AllElementNames():
            dssdirect.Circuit.SetActiveElement(element)
            node = dssdirect.CktElement.BusNames()[0]
            bus = _node_to_bus(node)
            element_type, name = element.split(".", maxsplit=1)
            element = element.lower()
            element_set = self._network[bus].get(element_type, None)
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
            print(f"adding edge: {bus1}--{bus2}")
            self._network.add_edge(bus1, bus2)
            self._edges[f"transformer.{name}"] = (bus1, bus2)
            transformer_number = dssdirect.Transformers.Next()
        # TODO Look for other power-delivery elements that have two busses
        #      specified. Transformers are the most common, but
        #      capacitors, reactors can be connected in series or as shunts.
        #      PD Elements that are shunts do not need to be included in the
        #      grid topology model.
        # initialize the sets of connected devices at each node
        for node in self._network.nodes.values():
            node["storage"] = set()
            node["generator"] = set()
            node["pvsystem"] = set()
            node["failed_devices"] = set()
        self._initialize_devices()

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

    def _connected_elements(self, component, element_type):
        for node_name in component:
            node = self._network.nodes[node_name]
            for generator in node.get(element_type, set()):
                yield generator

    def connected_generators(self, component):
        """Iterator over all generators connected to busses in a component.

        Parameters
        ----------
        component : set
            Set of busses that form a connected component in the grid.
        """
        return self._connected_elements(component, "generator")

    def connected_storage(self, component):
        """Iterator over all storage devices connected to busses in `component`

        Parameters
        ----------
        component : set
            Set of busses that from a connected component in the grid.
        """
        return self._connected_elements(component, "storage")

    def connected_pvsystems(self, component):
        """Iterator over all PV systems connected to busses in `component`.

        Parameters
        ----------
        component : set
            Set of busses that form a connected component in the grid.
        """
        return self._connected_elements(component, "pvsystem")

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


def _node_to_bus(node_name):
    """Return an OpenDSS bus name, stripped of all node names."""
    return node_name.split(".", maxsplit=1)[0]


class HeuristicEMS:
    def __init__(self, storage_devices, minimum_soc=0.2):
        self._minimum_soc = minimum_soc
        self._actual_demand = 0.0
        self._actual_generation = 0.0
        self._storage_soc = {
            device.name: device.soc for device in storage_devices
        }
        self._storage_kw = {
            device.name: device.kw for device in storage_devices
        }
        self._storage_kw_rated = {
            device.name: device.kwrated for device in storage_devices
        }

    def update_actual_generation(self, generation):
        self._actual_generation = sum(generation.values())

    def update_actual_demand(self, demand):
        self._actual_demand = sum(demand.values())

    def update_generation_forecast(self, generation_forecast):
        # not using forecasts yet
        pass

    def update_demand_forecast(self, demand_forecast):
        # not using forecasts yet
        pass

    def update_storage(self, name, storage_kw, storage_soc):
        self._storage_soc[name] = storage_soc
        self._storage_kw[name] = storage_kw

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


class EMS:
    """Energy Management System.

    Parameters
    ----------
    config : str
        Path to the grid configuration file.
    """
    def __init__(self, config):
        with open(config) as f:
            grid_config = json.load(f)
        self.storage = {
            storage["name"]: {"capacity": storage["kwhrated"],
                              "kw": storage["kwrated"]}
            for storage in grid_config["storage"]
        }
        self.soc = {
            storage["name"]: storage["%stored"] / 100
            for storage in grid_config["storage"]
        }
        self.peak_start = grid_config["ems"]["peak_start"]
        self.peak_end = grid_config["ems"]["peak_end"]
        self._actions = {}
        self.time = 0.0

    def update_reliability(self, event):
        """Update the state of the EMS in response to a reliability event.

        Parameters
        ----------
        event : reliability.Event
            Information about a single reliability event.
        """
        # TODO we don't actually have a model to update at this point.
        pass

    def update_control(self, message):
        """Update the state of the EMS.

        Parameters
        ----------
        message : dict
            Dict with keys "name" and "soc" specifying the name of a storage
            device and its state of charge respectively.
        """
        self.soc[message["name"]] = message["soc"]

    def _do_discharge(self):
        for device, soc in self.soc.items():
            if soc > 0:
                self._actions[device] = \
                    StorageControlMessage(
                        "discharge",
                        self.storage[device]["kw"],
                        0.0
                    )
            else:
                self._actions[device] = StorageControlMessage("idle", 0.0, 0.0)

    def _do_charge(self):
        for device, soc in self.soc.items():
            if soc < 1.0:
                self._actions[device] = \
                    StorageControlMessage(
                        "charge",
                        self.storage[device]["kw"],
                        0.0
                    )
            else:
                self._actions[device] = StorageControlMessage("idle", 0.0, 0.0)

    def _on_peak(self, time):
        if self.peak_start < self.peak_end:
            return self.peak_start <= time % 24 <= self.peak_end
        return not(self.peak_end < time % 24 < self.peak_start)

    def step(self, time):
        """Determine what control actions to take next."""
        self.time = time
        if self._on_peak(time / 3600):
            self._do_discharge()
        else:
            self._do_charge()

    def control_actions(self):
        return self._actions.items()

    def next_update(self):
        return self.time + 300
