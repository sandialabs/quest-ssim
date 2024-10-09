"""Kivy elements for configuring DER controls."""
from abc import ABC, abstractmethod
from typing import Union

import matplotlib.pyplot as plt
from kivy.properties import ListProperty, ObjectProperty
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.tab import MDTabs, MDTabsBase

from ssim.ui import StorageControl, InverterControl
from ssim.ui.kivy.xygrid import make_xy_grid_data, make_xy_matlab_plot


class ControlTab(ABC):
    """This defines the interface required for contol configuration tabs.

    Because of how abstract classes work in python and how layouts are
    implemented in Kivy, we can't actually inherit from this class. However, for
    the sake of documentation the definition is retained even though it is
    unused.

    """

    @property
    @staticmethod
    @abstractmethod
    def control_name() -> str:
        """Return the human readable name of the control mode."""

    @property
    @staticmethod
    @abstractmethod
    def control_id() -> str:
        """Return the internal identifier of the control mode."""

    @abstractmethod
    def activate(self, control: Union[StorageControl, InverterControl]):
        """Activate the control mode represented by this tab in `control`.

        Also update the state of subordinate widgets to reflect parameters
        already present in `control`.
        """

    @abstractmethod
    def set_data(self, control: Union[StorageControl, InverterControl]):
        """Update the data in the tab without activating it."""


class VoltVarTabContent(BoxLayout, MDTabsBase):
    """The class that stores the content for the Volt-Var tab in the storage
     option control tabs."""

    @property
    def control_name(self):
        return "Volt-Var"

    @property
    def control_id(self):
        return "voltvar"

    def on_add_button(self):
        """A callback function for the button that adds a new value to the volt-var grid"""
        self.ids.grid.data.append({'x': 1.0, 'y': 1.0})
        Clock.schedule_once(lambda dt: self.rebuild_plot(), 0.05)

    def on_sort_button(self):
        """A callback function for the button that sorts the volt-var grid by voltage"""
        xs, ys = self.ids.grid.extract_data_lists()
        self.ids.grid.data = make_xy_grid_data(xs, ys)

    def on_reset_button(self):
        """A callback function for the button that resets the volt-var grid data to defaults"""
        xs = [0.5, 0.95, 1.0, 1.05, 1.5]
        ys = [1.0, 1.0, 0.0, -1.0, -1.0]
        self.ids.grid.data = make_xy_grid_data(xs, ys)
        Clock.schedule_once(lambda dt: self.rebuild_plot(), 0.05)

    def set_data(self, control):
        control.ensure_param("voltvar")
        vvs = control.params["voltvar"]["volts"]
        var = control.params["voltvar"]["vars"]
        self.ids.grid.set_data(vvs, var)
        self.rebuild_plot()

    def activate(self, control):
        """Prepare the tab content to be foregrounded."""
        self.set_data(control)
        control.mode = "voltvar"

    def rebuild_plot(self):
        """A function to reset the plot of the volt var data.

        This method extracts the volt var data out of the UI grid and then, if
        the data exists, plots it in the associated plot.
        """
        xs, ys = self.ids.grid.extract_data_lists()

        if len(xs) == 0:
            self.ids.plot_box.display_plot_error("No Data")

        else:
            make_xy_matlab_plot(
                self.ids.plot_box, xs, ys, 'Voltage (p.u.)',
                'Reactive Power (p.u.)', 'Volt-Var Control Parameters'
            )


class VoltWattTabContent(BoxLayout, MDTabsBase):
    """The class that stores the content for the Volt-Watt tab in the storage
     option control tabs"""

    @property
    def control_name(self):
        return "Volt-Watt"

    @property
    def control_id(self):
        return "voltwatt"

    def on_add_button(self):
        """A callback function for the button that adds a new value to the volt-watt grid"""
        self.ids.grid.data.append({'x': 1.0, 'y': 1.0})
        Clock.schedule_once(lambda dt: self.rebuild_plot(), 0.05)

    def on_sort_button(self):
        """A callback function for the button that sorts the volt-watt grid by voltage"""
        xs, ys = self.ids.grid.extract_data_lists()
        self.ids.grid.data = make_xy_grid_data(xs, ys)

    def on_reset_button(self):
        """A callback function for the button that resets the volt-var grid data to defaults"""
        xs = [0.5, 0.95, 1.0, 1.05, 1.5]
        ys = [1.0, 1.0, 0.0, -1.0, -1.0]
        self.ids.grid.data = make_xy_grid_data(xs, ys)
        Clock.schedule_once(lambda dt: self.rebuild_plot(), 0.05)

    def set_data(self, control):
        control.ensure_param("voltwatt")
        vvs = control.params["voltwatt"]["volts"]
        watts = control.params["voltwatt"]["watts"]
        self.ids.grid.set_data(vvs, watts)
        self.rebuild_plot()

    def activate(self, control):
        control.mode = "voltwatt"
        self.set_data(control)

    def rebuild_plot(self):
        """A function to reset the plot of the volt watt data.

        This method extracts the volt watt data out of the UI grid and then, if
        the data exists, plots it in the associated plot.
        """
        xs, ys = self.ids.grid.extract_data_lists()

        if len(xs) == 0:
            self.ids.plot_box.display_plot_error("No Data")

        else:
            make_xy_matlab_plot(
                self.ids.plot_box, xs, ys, 'Voltage (p.u.)',
                'Watts (p.u.)', 'Volt-Watt Control Parameters'
            )


class VarWattTabContent(BoxLayout, MDTabsBase):
    """The class that stores the content for the Var-Watt tab in the storage
     option control tabs"""

    @property
    def control_name(self):
        return "Var-Watt"

    @property
    def control_id(self):
        return "varwatt"

    def on_add_button(self):
        """A callback function for the button that adds a new value to the var-watt grid"""
        self.ids.grid.data.append({'x': 1.0, 'y': 1.0})
        Clock.schedule_once(lambda dt: self.rebuild_plot(), 0.05)

    def on_sort_button(self):
        """A callback function for the button that sorts the var-watt grid by reactive power"""
        xs, ys = self.ids.grid.extract_data_lists()
        self.ids.grid.data = make_xy_grid_data(xs, ys)

    def on_reset_button(self):
        """A callback function for the button that resets the volt-var grid data to defaults"""
        xs = [0.5, 0.95, 1.0, 1.05, 1.5]
        ys = [1.0, 1.0, 0.0, -1.0, -1.0]
        self.ids.grid.data = make_xy_grid_data(xs, ys)
        Clock.schedule_once(lambda dt: self.rebuild_plot(), 0.05)

    def set_data(self, control):
        control.ensure_param("varwatt")
        var = control.params["varwatt"]["vars"]
        watts = control.params["varwatt"]["watts"]
        self.ids.grid.set_data(var, watts)
        self.rebuild_plot()

    def activate(self, control):
        control.mode = "varwatt"
        self.set_data(control)

    def rebuild_plot(self):
        """A function to reset the plot of the var watt data.

        This method extracts the var watt data out of the UI grid and then, if
        the data exists, plots it in the associated plot.
        """
        xs, ys = self.ids.grid.extract_data_lists()

        if len(xs) == 0:
            self.ids.plot_box.display_plot_error("No Data")

        else:
            make_xy_matlab_plot(
                self.ids.plot_box, xs, ys, 'Reactive Power (p.u.)',
                'Watts (p.u.)', 'Var-Watt Control Parameters'
            )


class VoltVarVoltWattTabContent(BoxLayout, MDTabsBase):
    """The class that stores the content for the Volt-Var & Volt-Watt tab in the storage
     option control tabs"""

    @property
    def control_name(self):
        return "Volt-Var & Volt-Watt"

    @property
    def control_id(self):
        return "vv_vw"

    def on_add_vv_button(self):
        """A callback function for the button that adds a new value to the volt-var grid"""
        self.ids.vv_grid.data.append({'x': 1.0, 'y': 1.0})
        Clock.schedule_once(lambda dt: self.rebuild_plot(), 0.05)

    def on_add_vw_button(self):
        """A callback function for the button that adds a new value to the volt-watt grid"""
        self.ids.vw_grid.data.append({'x': 1.0, 'y': 1.0})
        Clock.schedule_once(lambda dt: self.rebuild_plot(), 0.05)

    def on_reset_vv_button(self):
        """A callback function for the button that resets the volt-var grid data to defaults"""
        xs = [0.5, 0.95, 1.0, 1.05, 1.5]
        ys = [1.0, 1.0, 0.0, -1.0, -1.0]
        self.ids.vv_grid.data = make_xy_grid_data(xs, ys)
        Clock.schedule_once(lambda dt: self.rebuild_plot(), 0.05)

    def on_reset_vw_button(self):
        """A callback function for the button that resets the volt-var grid data to defaults"""
        xs = [0.5, 0.95, 1.0, 1.05, 1.5]
        ys = [1.0, 1.0, 0.0, -1.0, -1.0]
        self.ids.vw_grid.data = make_xy_grid_data(xs, ys)
        Clock.schedule_once(lambda dt: self.rebuild_plot(), 0.05)

    def on_sort_vv_button(self):
        """A callback function for the button that sorts the volt-var grid by voltage"""
        xs, ys = self.ids.vv_grid.extract_data_lists()
        self.ids.vv_grid.data = make_xy_grid_data(xs, ys)

    def on_sort_vw_button(self):
        """A callback function for the button that sorts the volt-watt grid by voltage"""
        xs, ys = self.ids.vw_grid.extract_data_lists()
        self.ids.vw_grid.data = make_xy_grid_data(xs, ys)

    def set_data(self, control):
        control.ensure_param("vv_vw")
        vv_volts = control.params["vv_vw"]["vv_volts"]
        vv_vars = control.params["vv_vw"]["vv_vars"]
        vw_volts = control.params["vv_vw"]["vw_volts"]
        vw_watts = control.params["vv_vw"]["vw_watts"]
        self.ids.vv_grid.set_data(vv_volts, vv_vars)
        self.ids.vw_grid.set_data(vw_volts, vw_watts)
        self.rebuild_plot()

    def activate(self, control):
        control.mode = "vv_vw"
        self.set_data(control)

    def rebuild_plot(self):
        """A function to reset the plot of the volt var and volt watt data.

        This method extracts the volt var and volt watt data out of the UI grids and then, if
        the data exists, plots them in the associated plot, 1 on each of two y axes.
        """
        vxs, vys = self.ids.vv_grid.extract_data_lists()
        wxs, wys = self.ids.vw_grid.extract_data_lists()

        if len(vxs) == 0 and len(wxs) == 0:
            self.ids.plot_box.display_plot_error("No Data")

        else:
            fig, ax1 = plt.subplots(1, 1, layout="constrained")
            l1, = ax1.plot(vxs, vys, marker='o')
            ax1.set_xlabel('Voltage (p.u.)')
            ax1.set_ylabel('Reactive Power (p.u.)')

            ax2 = ax1.twinx()
            l2, = ax2.plot(wxs, wys, color="red", marker='o')
            ax2.set_ylabel('Watts (p.u.)', color="red")
            ax2.tick_params(axis='y', labelcolor="red")

            ax1.legend([l1, l2], ["Volt-Var", "Volt-Watt"])
            plt.title('Volt-Var & Volt-Watt Control Parameters')
            self.ids.plot_box.reset_plot()


class ConstPFTabContent(BoxLayout, MDTabsBase):
    # See ssim.kv for definition

    @property
    def control_name(self):
        return "Constant Power Factor"

    @property
    def control_id(self):
        return "constantpf"

    def set_data(self, control):
        control.ensure_param("constantpf")
        self.ids.pf_value.text = str(control.params["constantpf"]["pf_val"])
        _focus_defocus(self.ids.pf_value)

    def activate(self, control):
        control.mode = "constantpf"
        self.set_data(control)


class DroopTabContent(BoxLayout, MDTabsBase):
    # See ssim.kv for definition

    @property
    def control_name(self):
        return "Droop"

    @property
    def control_id(self):
        return "droop"

    def set_data(self, control):
        control.ensure_param("droop")
        self.ids.p_value.text = str(control.params["droop"]["p_droop"])
        self.ids.q_value.text = str(control.params["droop"]["q_droop"])
        _focus_defocus(self.ids.p_value)
        _focus_defocus(self.ids.q_value)

    def activate(self, control):
        control.mode = "droop"
        self.set_data(control)


class NoControl(BoxLayout, MDTabsBase):
    """A tab that represents the abscence of a controller."""

    @property
    def control_name(self):
        return "Uncontrolled"

    @property
    def control_id(self):
        return None

    def set_data(self, control):
        pass

    def activate(self, control):
        control.mode = None


class ControlTabFactory:
    """Factory that ceates tab content used to configure DER control modes."""

    _MODES = {
        None: NoControl,
        "droop": DroopTabContent,
        "voltvar": VoltVarTabContent,
        "voltwatt": VoltWattTabContent,
        "varwatt": VarWattTabContent,
        "vv_vw": VoltVarVoltWattTabContent,
        "constantpf": ConstPFTabContent
    }

    @staticmethod
    def new(mode):
        """Construct a new control mode configuration tab."""
        if mode not in ControlTabFactory._MODES:
            raise ValueError(f"unknown control mode '{mode}'")
        return ControlTabFactory._MODES[mode]()


class ControlTabs(MDTabs):
    """Generic UI element for configuring PV and Storage controllers."""

    enabled_controls = ListProperty()
    active_tab = ObjectProperty()  # TODO set the default
    control = ObjectProperty()

    def __init__(self, *args, **kwargs):
        self._tabs = {}
        super().__init__(*args, **kwargs)

    def on_control(self, instance, control):
        for tab in self.get_tab_list():
            self._tabs[tab.text].set_data(control)

    def on_tab_switch(self, tab, tablabel, tabtext):
        tab.activate(self.control)
        self.active_tab = tab

    def on_enabled_controls(self, instance, value):
        for tab in self.get_tab_list():
            del self._tabs[tab.text.text]
            self.remove_widget(tab)
        first = True
        for mode in value:
            tab = ControlTabFactory.new(mode)
            if first:
                self.active_tab = tab
                first = False
            self.add_widget(tab)
            self._tabs[tab.tab_label.text] = tab


def _focus_defocus(widget, dt=0.05):
    """Focus and defocus a widget after a delay.

    This is used to work around the quirks of the TextField widgets that cause
    them to display overlapping text when initialized directly instead of by
    user input.

    """
    widget.focus = True
    Clock.schedule_once(lambda _: widget.cancel_selection(), dt)
