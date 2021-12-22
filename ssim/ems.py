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
import abc
import json

import opendssdirect as dssdirect

import networkx as nx

from ssim.grid import GridSpecification
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


class EMS:
    """Basic EMS consisting of a planner and a dispatcher.

    An EMS has three primary components:

    1. A grid model
    2. A planner
    3. A dispatch model

    The planner sets long or medium term goals that are used by the
    dispatcher to inform its dispatch decisions. The dispatcher is
    responsible for sending control messages to grid elements
    in response to real time conditions on the grid.

    Parameters
    ----------
    grid : GridModel
        The grid model
    dispatcher : Dispatcher
        The dispatcher.
    planner : Planner, optional
        The planner.
    """

    def __init__(self, grid, dispatcher, planner=None):
        self.grid = grid
        self.dispatcher = dispatcher
        self.planner = planner

    def next_update(self):
        if self.planner is None:
            return self.dispatcher.next_update()
        return min(self.planner.next_update(),
                   self.dispatcher.next_update())

    def update(self, time, inputs, forecast_manager):
        inputs = list(inputs)
        if self.planner is not None:
            self.planner.update(time, inputs, forecast_manager, self.grid)
            self.dispatcher.update(
                time,
                inputs,
                self.planner.plan,
                self.grid
            )
        else:
            self.dispatcher.update(time, inputs, self.grid)

    def output(self):
        return self.dispatcher.output()


class Planner(abc.ABC):
    """Abstract base class for EMS Planners."""

    @abc.abstractmethod
    def next_update(self) -> float:
        """Return the time of the next planning iteration."""

    @abc.abstractmethod
    def update(self, time, inputs, forecast_manager, grid_model):
        """Update the plan.

        Parameters
        ----------
        time : float
            Current time
        inputs : Iterable of StatusMessage
        forecast_manager : ForecastManager
        grid_model : GridModel
        """

    @property
    @abc.abstractmethod
    def plan(self) -> dict:
        """The current dispatch plan.

        A dispatch plan is a dict where keys are dispatchable grid
        elements (e.g. conventional generators, or energy storage
        systems). The dict values are time series of target values for
        each element, energy storage, for example might have a plan
        that specifies the state of charge that should be achieved at
        various times.
        """


class Dispatcher(abc.ABC):
    """Abstract base class for EMS Dispatchers."""

    @abc.abstractmethod
    def next_update(self):
        """Return the time that the dispatcher needs to do its next update."""

    @abc.abstractmethod
    def update(self, time, inputs, grid_model, plan=None):
        """Make new dispatch decisions based on the current plan and inputs.

        Parameters
        ----------
        time : float
            Current time.
        inputs : Iterable of StatusMessage
        grid_model : GridModel
        plan : DispatchPlan, optional
            A dispatch plan returned from a Planner instance.
        """

    def output(self):
        """Return the latest control output."""


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


class GeneratorControlMessage:
    """Representation of a generator control command.

    Parameters
    ----------
    action : str
        The action being commanded. One of "on", "off", "setpoint"
    kw : float, optional
        The commanded real power setpoint. Only valid when `aciton` is
        "setpoint". [kW]
    kvar : float, optional
        The commanded reactive power setpoint. Only valid when `action` is
        "setpoint". [kVAR]
    """
    def __init__(self, action, kw=None, kvar=None):
        if action not in {"on", "off", "setpoint"}:
            raise ValueError(
                "action must be one of 'on', 'off', or 'setpoint' "
                f"(got '{action}')"
            )
        if (kw is not None or kvar is not None) and action != "setpoint":
            raise ValueError(
                "kw and kvar can only be specified for action='setpoint' "
                f"(got action='{action}')"
            )
        self.action = action
        self.kw = None
        self.kvar = None
        if action == "setpoint":
            self.kw = kw or 0.0
            self.kvar = kvar or 0.0

    def to_json(self):
        if self.action == "setpoint":
            return json.dumps({'action': self.action,
                               'kw': self.kw,
                               'kvar': self.kvar})
        return json.dumps({'action': self.action})

    @classmethod
    def from_json(cls, jsonstr):
        return cls(**json.loads(jsonstr))


def _node_to_bus(node_name):
    """Return an OpenDSS bus name, stripped of all node names."""
    return node_name.split(".", maxsplit=1)[0]
