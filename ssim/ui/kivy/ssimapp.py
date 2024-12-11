"""Storage Sizing and Placement Kivy application"""
import inspect
import itertools
import logging
import math
import os
import re
import sys
from collections import defaultdict
from contextlib import ExitStack
from copy import deepcopy
from math import cos, hypot
from threading import Thread
from typing import List

import dss.plot
import kivy
import kivy.garden
import matplotlib as mpl
import matplotlib.colors as mplcolors
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import opendssdirect as dssdirect
import pandas as pd
from importlib_resources import as_file, files
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.logger import LOG_LEVELS, Logger
from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.textinput import TextInput
from kivymd.app import MDApp
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.list import (
    ILeftBodyTouch,
    MDList,
    OneLineIconListItem,
    OneLineRightIconListItem,
    ThreeLineIconListItem,
    TwoLineAvatarIconListItem,
    TwoLineIconListItem
)
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.tab import MDTabsBase
from kivymd.uix.textfield import MDTextField
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.offsetbox import OffsetImage
from matplotlib.path import Path

import ssim.ui
from ssim.metrics import ImprovementType, Metric, MetricTimeAccumulator
from ssim.opendss import DSSModel
from ssim.ui import (
    Configuration,
    InverterControl,
    Project,
    PVOptions,
    StorageOptions,
    is_valid_opendss_name
)
from ssim.ui.kivy import util

kivy.garden.garden_system_dir = os.path.join(
    os.path.dirname(inspect.getfile(ssim.ui)), "libs/garden"
)
from kivy.garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg

_FONT_FILES = {
    "exo_regular": "Exo2-Regular.ttf",
    "exo_bold": "Exo2-Bold.ttf",
    "exo_italic": "Exo2-Italic.ttf",
    "opensans_regular": "OpenSans-Regular.ttf",
    "opensans_bold": "OpenSans-Bold.ttf",
    "opensans_italic": "OpenSans-Italic.ttf"
}

_IMAGE_FILES = [
    "button_down.png", "button_normal.png", "gray.png", "white.png"
]

_KV_FILES = ["common.kv", "ssim.kv"]

logging.getLogger('matplotlib.font_manager').disabled = True

def make_xy_grid_data(xs: list, ys: list) -> list:
    """A utility method to create a list of dictionaries suitable for use by an
    XYGrid.

    Parameters
    ----------
    xs : list
        The x value list to be the x values in the resulting dictionary.
    ys : list
        The y value list to be the y values in the resulting dictionary.

    Returns
    -------
    list:
        A list of dictionaries of the form
        [{x: x1, y: y1}, {x: x2, y: y2}, ..., {x: xn, y: yn}] which is what's
        required by an XY grid.
    """
    return [{'x': xs[i], 'y': ys[i]} for i in range(len(xs))]


def parse_float(strval) -> float:
    """A utility method to parse a string into a floating point value.

    This differs from a raw cast (float(strval)) in that it swallows
    exceptions.

    Parameters
    ----------
    strval
        The string to try and parse into a floating point number.

    Returns
    -------
    float:
        The value that resulted from parsing the supplied string to a float
        or None if the cast attempt caused an exception.
    """
    try:
        return float(strval)
    except ValueError:
        return None


def parse_float_or_str(strval):
    """A utility method to parse a string into a floating point value or leave
     it as is if the cast fails.

    This used parse_float and if that fails, this returns the supplied input
    string.

    Parameters
    ----------
    strval : Optional[str]
        The string to try and parse into a floating point number, or None.

    Returns
    -------
    float or str or None:
        This returns None if the supplied input string is None.  Otherwise, it
        tries to cast the input string to a float.   If that succeeds, then the
        float is returned.  If it doesn't, then the supplied string is returned
        unaltered.
    """
    if strval is None:
        return None
    flt = parse_float(strval)
    if flt is None:
        return strval
    return flt


def try_co_sort(xl: list, yl: list) -> (list, list):
    """Attempts to co-sort the supplied lists using the x-list as the sort index

    Parameters
    ----------
    xl : list
        The list of "x" values in this grid view to be sorted and treated as
        the index.
    yl: list
        The list of "y" values in this grid view to be sorted in accordance
        with the x-list.

    Returns
    -------
    tuple:
        If the two lists can be co-sorted, then the co-sorted versions of them
        will be returned.  If they cannot b/c an exception occurs, then they
        are returned unmodified.
    """
    if len(xl) < 2: return (xl, yl)

    try:
        return (list(t) for t in zip(*sorted(zip(xl, yl))))
    except:
        return (xl, yl)

    
def refocus_text_field(field):
    """A method that does nothing more than set the focus property of the
    supplied widget to true.
        
    This is often scheduled for call to manage the focus state of widgets
    as a form is being initialized.

    Parameters
    ----------
    field
        The widget to set the focus value of.
    """
    field.focus = True


class BusFilters:
    
    '''
    A class that stores filters that can be applied to a list of busses.
    '''

    def __init__(self, *args, **kwargs):
        ''' Initializes a new BusFilters object to an empty set of filters.
        '''
        self.name_filter = ""
        self.must_have_phases = set()
        self.cant_have_phases = set()
        self.allowed_phase_cts = set()
        self.voltages = set()
        self.selected_only = False    

    def is_empty(self) -> bool:
        ''' A method to indicate whether or not this BusFilters item will
        actually filter anything.

        Filtering will only take place if a name is given, some voltages ar
        chosen, phase restrictions are given, etc.

        Returns
        -------
        True if this filter will result in any filtering and false otherwise.
        '''
        if self.name_filter: return False
        if len(self.voltages) > 0: return False
        if self.selected_only: return False
        if len(self.must_have_phases) > 0: return False
        if len(self.allowed_phase_cts) > 0: return False
        return len(self.cant_have_phases) == 0

    def summary(self) -> str:
        ''' Creates a string indicating what active filters are part of this
        BusFilters object.

        The components of the resulting string will include:
        1 - Any name filter entered in quotes.
        2 - +Selected if the selected only filter is active.
        3 - +P# for each "must have" phase.
        4 - -P# for each "can't have" phase.
        5 - #-phase for each allowed phase count specified.
        6 - +V for any specified required voltage levels separated by " or ".
            If only 1 voltage, then +V#, if more, then +V(#1 or #2 or... ).

        The final string will have all appropriate elements above separated by
        semicolons.

        Returns
        -------
        str
            The summary string representing the filters stored in this object.
        '''
        elems = []
        if self.name_filter: elems += ["\"" + self.name_filter + "\""]
        if self.selected_only: elems += ["+Selected"]
        elems += ["+P"+str(p) for p in self.must_have_phases]
        elems += ["-P"+str(p) for p in self.cant_have_phases]
        elems += [str(c) + "-phase" for c in self.allowed_phase_cts]

        vstr = ""
        if len(self.voltages) > 1:
            vstr = "(" + " or ".join(self.voltages) + ")"
        elif len(self.voltages) == 1:
            vstr = str(next(iter(self.voltages)))
        
        if vstr: elems += ["+V"+vstr]
        
        return ("[" if len(elems) > 0 else "") + "; ".join(elems) + \
            ("]" if len(elems) > 0 else "")

    
    def test_bus(self, bus, project, sel_bus_list) -> bool:
        ''' A method to test a given bus against the filters represented by this
        BusFilters item.

        This will check the bus properties against all filters to see if it
        passes or should be filtered out.

        Parameters
        ----------
        bus
            The name of the bus to test.
        project
            The current project object.  This is used to access aspects of the
            DSSModel.
        sel_bus_list
            The list of all currently selected busses.  This is used only if the
            selected_only filter is active.

        Returns
        -------
        True if the bus passes all filters and should not be filtered out and
        false if it triggered at least one filter and thus should be filtered
        out.
        '''
        nameFilter = self.name_filter
        if (nameFilter and not nameFilter in bus): return False
        
        sel_only = self.selected_only
        if sel_only and not bus in sel_bus_list: return False        

        phases = project.phases(bus)

        if len(self.allowed_phase_cts) > 0:
            if len(phases) not in self.allowed_phase_cts: return False

        for mhp in self.must_have_phases:
            if mhp not in phases: return False

        for chp in self.cant_have_phases:
            if chp in phases: return False
        
        bv = DSSModel.nominal_voltage(bus)
        selvs = self.voltages
        if len(selvs) > 0 and str(bv) not in selvs: return False

        return True


class ConfigurationFilters:

    def __init__(self, *args, **kwargs):
        self.storage_name = ""
        self.kw_filter = {"min": None, "max": None}
        self.kwh_filter = {"min": None, "max": None}

    def is_empty(self) -> bool:
        if self.storage_name: return False
        if any(self.kw_filter.values()): return False
        if any(self.kwh_filter.values()): return False
        return True

    def is_empty_name(self) -> bool:
        if self.storage_name: return False
        return True

    def is_empty_kW(self) -> bool:
        if any(self.kw_filter.values()): return False
        return True

    def is_empty_kWh(self) -> bool:
        if any(self.kwh_filter.values()): return False
        return True


class BusSearchPanelContent(BoxLayout):

    """ A panel that houses controls for configuring a BusFilters object.
    """

    def __init__(self, *args, **kwargs):
        """ Constructs a new BusSearchPanelContent with an empty set of bus
        filters.
        """
        super().__init__(*args, **kwargs)
        self.register_event_type("on_filter_applied")
        self.filters = BusFilters()

    def apply_filters(self, filters: BusFilters):
        """ Updates the fields on this panel to display the status of the
        supplied filters object.

        Parameters
        ----------
        filters
            The bus filters to display in this form.
        """
        self.ids.txt_bus_name_filter.text = filters.name_filter
        self.set_selected_voltages(filters.voltages)
        self.ids.ckb_yes_phase_1.active = 1 in filters.must_have_phases
        self.ids.ckb_yes_phase_2.active = 2 in filters.must_have_phases
        self.ids.ckb_yes_phase_3.active = 3 in filters.must_have_phases
        self.ids.ckb_no_phase_1.active = 1 in filters.cant_have_phases
        self.ids.ckb_no_phase_2.active = 2 in filters.cant_have_phases
        self.ids.ckb_no_phase_3.active = 3 in filters.cant_have_phases
        self.ids.ckb_1_phase_ct.active = 1 in filters.allowed_phase_cts
        self.ids.ckb_2_phase_ct.active = 2 in filters.allowed_phase_cts
        self.ids.ckb_3_phase_ct.active = 3 in filters.allowed_phase_cts
        self.ids.ckb_sel_only.active = filters.selected_only

    def extract_filters(self) -> BusFilters:
        """ Reads the status of the fields of this form and stores the
        information in a new BusFilters object and returns it.

        Returns
        -------
        BusFilters
            A new BusFilters object created and loaded with the information
            entered in this form.
        """
        ret = BusFilters()
        ret.name_filter = self.ids.txt_bus_name_filter.text
        ret.voltages = self.get_selected_voltages()
        if self.ids.ckb_yes_phase_1.active: ret.must_have_phases.add(1)
        if self.ids.ckb_yes_phase_2.active: ret.must_have_phases.add(2)
        if self.ids.ckb_yes_phase_3.active: ret.must_have_phases.add(3)
        if self.ids.ckb_no_phase_1.active: ret.cant_have_phases.add(1)
        if self.ids.ckb_no_phase_2.active: ret.cant_have_phases.add(2)
        if self.ids.ckb_no_phase_3.active: ret.cant_have_phases.add(3)
        if self.ids.ckb_1_phase_ct.active: ret.allowed_phase_cts.add(1)
        if self.ids.ckb_2_phase_ct.active: ret.allowed_phase_cts.add(2)
        if self.ids.ckb_3_phase_ct.active: ret.allowed_phase_cts.add(3)
        ret.selected_only = self.ids.ckb_sel_only.active
        return ret

    def clear_text_filter(self):
        """ Clears the content of the text filter field in this form.
        """
        self.ids.txt_bus_name_filter.text  = ""
        self.ids.txt_bus_name_filter.on_text_validate()
        
    def changed_phase_filter(self, instance):
        """ A callback that is used whenever a change to phase filter inputs
        occurs.

        This includes both the must have, can't have, and number of phase
        requirements.

        This method just dispatches the "on_filter_applied" callback.

        Parameters
        ----------
        instance
            The widget instance that was used to cause this callback.
        """
        self.__raise_filter_applied(instance)

    def changed_sel_only_filter(self, instance):
        """ A callback that is used whenever a change to the "selected only"
        filter occurs.

        This method just dispatches the "on_filter_applied" callback.

        Parameters
        ----------
        instance
            The widget instance that was used to cause this callback.
        """
        self.__raise_filter_applied(instance)

    def changed_text_filter(self, instance):
        """ A callback that is used whenever a change to the bus name text
        filter occurs.

        This method just dispatches the "on_filter_applied" callback.

        Parameters
        ----------
        instance
            The widget instance that was used to cause this callback.
        """
        self.__raise_filter_applied(instance)
        Clock.schedule_once(lambda dt: refocus_text_field(instance), 0.05)

    def changed_voltage_check(self, instance, active):
        """ A callback that is used whenever the check state of a voltage
        level check box changes.

        This method just dispatches the "on_filter_applied" callback.

        Parameters
        ----------
        instance
            The check box instance that was used to cause this callback.
        """
        self.__raise_filter_applied(instance)

    def get_selected_voltages(self) -> set:
        """ Gathers the voltages of all checked voltage boxes and returns them
        as a set.

        Returns
        -------
        set
           The set of all chosen voltages.  That is, those for which the
           corresponding check boxes are checked.  The set will contain text
           objects but they will represent numeric values.
        """
        ret = set()
        add_next_label = False
        
        for w in reversed(self.ids.voltage_check_panel.children):
            if isinstance(w, CheckBox) and w.active:
                add_next_label = True
            elif isinstance(w, Label) and add_next_label:
                ret.add(w.text)
                add_next_label = False
        
        return ret

    def set_selected_voltages(self, voltages):
        """ Sets the check state of the check boxes associated with the voltages
        in the provided list.
        
        Parameters
        ----------
        voltages
            The list of voltages that are to be checked as the only ones allowed
            through a filter.
        """
        if voltages is None: return
        next_check_val = None
        
        for w in self.ids.voltage_check_panel.children:
            if isinstance(w, CheckBox):
                if next_check_val is not None:
                    w.active = next_check_val
                next_check_val = None
            elif isinstance(w, Label):
                next_check_val = w.text in voltages

    def get_name_filter_text(self) -> str:
        """ Returns the text currently in the bus name filter field.

        Returns
        -------
        str
            The current bus name filter which may be a null or empty string.
        """
        return self.ids.txt_bus_name_filter.text
    
    def get_yes_phase_1_active(self) -> bool:
        """ Returns true if the check box indicating that phase 1 is required
        is checked and false otherwise.

        Returns
        -------
        bool
            True if phase 1 is marked as required and false otherwise.
        """
        return self.ids.ckb_yes_phase_1.active
    
    def get_yes_phase_2_active(self) -> bool:
        """ Returns true if the check box indicating that phase 2 is required
        is checked and false otherwise.

        Returns
        -------
        bool
            True if phase 2 is marked as required and false otherwise.
        """
        return self.ids.ckb_yes_phase_2.active

    def get_yes_phase_3_active(self) -> bool:
        """ Returns true if the check box indicating that phase 3 is required
        is checked and false otherwise.

        Returns
        -------
        bool
            True if phase 3 is marked as required and false otherwise.
        """
        return self.ids.ckb_yes_phase_3.active
    
    def get_no_phase_1_active(self) -> bool:
        """ Returns true if the check box indicating that busses with phase 1
        are not allowed is checked and false otherwise.

        Returns
        -------
        bool
            True if phase 1 busses are not allowed and false otherwise.
        """
        return self.ids.ckb_no_phase_1.active
    
    def get_no_phase_2_active(self) -> bool:
        """ Returns true if the check box indicating that busses with phase 2
        are not allowed is checked and false otherwise.

        Returns
        -------
        bool
            True if phase 2 busses are not allowed and false otherwise.
        """
        return self.ids.ckb_no_phase_2.active

    def get_no_phase_3_active(self) -> bool:
        """ Returns true if the check box indicating that busses with phase 3
        are not allowed is checked and false otherwise.

        Returns
        -------
        bool
            True if phase 3 busses are not allowed and false otherwise.
        """
        return self.ids.ckb_no_phase_3.active
    
    def get_1_phase_allowed_active(self) -> bool:
        """ Returns true if the check box indicating that busses with 1 phases
        are allowed is checked and false otherwise.

        Returns
        -------
        bool
            True if 1 phase busses are allowed and false otherwise.
        """
        return self.ids.ckb_1_phase_ct.active
    
    def get_2_phase_required_active(self) -> bool:
        """ Returns true if the check box indicating that busses with 2 phases
        are allowed is checked and false otherwise.

        Returns
        -------
        bool
            True if 2 phase busses are allowed and false otherwise.
        """
        return self.ids.ckb_2_phase_ct.active

    def get_3_phase_allowed_active(self) -> bool:
        """ Returns true if the check box indicating that busses with 3 phases
        are allowed is checked and false otherwise.

        Returns
        -------
        bool
            True if 3 phase busses are allowed and false otherwise.
        """
        return self.ids.ckb_3_phase_ct.active
    
    def get_selected_only_active(self) -> bool:
        """ Returns true if the check box indicating that only selected busses
        are to pass the filter is checked and false otherwise.

        Returns
        -------
        bool
            True if the "selected only" check box is marked and false otherwise.
        """
        return self.ids.ckb_sel_only.active
    
    def __raise_filter_applied(self, instance):
        """Dispatches the on_filter_applied method to anything bound to it.

        Parameters
        ----------
        instance
            The widget that was changed resulting in the call to this method.
        """
        self.dispatch("on_filter_applied", instance)
        
    def on_filter_applied(self, instance):
        """ The required stub of the on_filter_applied method that will be the
        callback to any changes to the widgets on this form.

        Parameters
        ----------
        instance
            The widget that was changed resulting in the call to this method.
        """
        pass

    def load_voltage_checks(self, voltages):
        """ Creates voltage check boxes, 1 for each value in the supplied list
        of voltages.

        Parameters
        ----------
        voltages
            The list of all voltages for which there should be a check box in
            this panel.
        """
        for v in voltages:
            ckb = CheckBox(active=False)
            ckb.bind(active=self.changed_voltage_check)
            self.ids.voltage_check_panel.add_widget(ckb)
            self.ids.voltage_check_panel.add_widget(
                Label(text=str(v), color=(0,0,0))
                )


class ConfigurationPanelContent(BoxLayout):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters = ConfigurationFilters()

    def extract_filters(self) -> ConfigurationFilters:
        ret = ConfigurationFilters()

        if self.ids.txt_min_kw_filter.text_valid():
            ret.kw_filter['min'] = float(self.ids.txt_min_kw_filter.text)

        if self.ids.txt_max_kw_filter.text_valid():
            ret.kw_filter['max'] = float(self.ids.txt_max_kw_filter.text)

        if self.ids.txt_min_kwh_filter.text_valid():
            ret.kwh_filter['min'] = float(self.ids.txt_min_kwh_filter.text)

        if self.ids.txt_max_kwh_filter.text_valid():
            ret.kwh_filter['max'] = float(self.ids.txt_max_kwh_filter.text)

        return ret


class SSimApp(MDApp):

    def __init__(self, *args, **kwargs):
        self.project = Project("unnamed")
        super().__init__(*args, **kwargs)
        
    def on_start(self):
        if len(sys.argv) >= 2:
            Clock.schedule_once(lambda dt: self.load_initial_file(dt), 3)

    def load_initial_file(self, dt):
        if len(sys.argv) < 2: return
        
        screen = self.root.current_screen
        if hasattr(screen, 'load_toml_file'):
            screen.load_toml_file('', [sys.argv[1]])

    def build(self):
        Window.size = (1000, 800)

        screen_manager = ScreenManager()
        screen_manager.add_widget(SSimScreen(self.project, name="ssim"))
        screen_manager.add_widget(
            DERConfigurationScreen(self.project, name="der-config"))
        screen_manager.add_widget(
            LoadConfigurationScreen(self.project, name="load-config"))
        screen_manager.add_widget(
            MetricConfigurationScreen(self.project, name="metric-config"))
        screen_manager.add_widget(
            ReliabilityConfigurationScreen(self.project, name="reliability-config"))
        screen_manager.add_widget(
            RunSimulationScreen(self.project, name="run-sim"))
        screen_manager.add_widget(
            ResultsVisualizeScreen(self.project, name="results-visualize"))
        screen_manager.add_widget(
            ResultsDetailScreen(self.project, name="results-detail"))
        screen_manager.current = "ssim"

        return screen_manager


class SSimBaseScreen(Screen):
    """Base class for screens that holds the fundamental ssim data structures.

    Attributes:
        project : :py:class:`ssim.ui.Project`

    Parameters
    ----------
    project : ssim.ui.Project
        Project object where the simulation configuration is being constructed.
    """

    def __init__(self, project, *args, **kwargs):
        self.project = project
        self.configurations_to_eval: List[str] = []
        self.config_id_to_name= {} # sets up concrete mappings
        self.selected_configurations = {}
        super().__init__(*args, **kwargs)


class MatlabPlotBox(BoxLayout):

    def reset_plot(self):
        """Clears the current diagram widget and draws a new one using the
        current figure (plt.gcf())"""
        self.clear_widgets()
        fig = plt.gcf()
        canvas = FigureCanvasKivyAgg(fig)
        #nav = NavigationToolbar2Kivy(canvas)
        #nav.actionbar.color = "white"
        self.add_widget(canvas)
        #self.add_widget(nav.actionbar)

    def display_plot_error(self, msg):
        """Puts a label with a supplied message in place of the diagram when
        there is a reason a diagram can't be displayed.

        Parameters
        ----------
        msg : str
            The message to show in place of the diagram when one can't be
            displayed.
        """
        self.clear_widgets()
        self.add_widget(MDLabel(text=msg))


class LeftCheckBox(ILeftBodyTouch, MDCheckbox):
    pass


class CheckedListItemOwner:
    def on_selection_changed(self, name, selected):
        pass


class BusListItem(TwoLineIconListItem, RecycleDataViewBehavior):
    
    '''
    A class that serves as a list item representing a bus for use in a
    RecycleView.

    Attributes
    ----------
    active : bool
        An indicator of the checked state of this item.
    owner : CheckedListItemOwner, optional
        If supplied, the owner receives call-backs about selection changes on
        this item.
    '''

    active = False
    owner: CheckedListItemOwner = None 

    def __init__(self, **kwargs):
        ''' Initializes a new instance of a BusListItem.
        '''
        super().__init__(**kwargs)
        self.register_event_type("on_selected_changed")
        self.ids.selected.active = self.active
        
    def __raise_value_changed(self):
        ''' Dispatches the on_selected_changed message and also calls the
        on_selection_changed method of the owner if an owner is known.
        '''
        self.dispatch("on_selected_changed", self.text, self.active)
        if self.owner: self.owner.on_selection_changed(self.text, self.active)

    def on_selected_changed(self, bus, selected):
        ''' This is the stub method required to register an event of this name.
        It doesn't do anything.

        Parameters
        ----------
        bus
            The name of the bus represented by this list item and supplied to
            handlers of this message.
        selected
            True if this item is now selected and false otherwise.
        '''
        pass

    def mark(self, check, value):
        ''' Sets the active state of this item to the supplied value and raises
        the value changed message.

        This method is used as a callback for the a check box on_active message.

        Parameters
        ----------
        check
            The check box that called this method with it's on_active message.
        value
            The current value of the check box.  True if checked and false
            otherwise.
        '''
        self.active = value
        self.__raise_value_changed()
            
    def refresh_view_attrs(self, rv, index, data):
        """A method of the RecycleView called automatically to refresh the
            content of the view.

        Parameters
        ----------
        rv : RecycleView
            The RecycleView that owns this row and wants it refreshed (not used
            in this function).
        index: int
            The index of this row.
        data: dict
            The dictionary of data that constitutes this row.  Not needed here.
        """
        super().refresh_view_attrs(rv, index, data)
        self.ids.selected.active = self.active


class ResultsListItem(OneLineIconListItem, RecycleDataViewBehavior):
    
    active = False
    owner: CheckedListItemOwner = None 

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type("on_selected_changed")
        self.ids.selected.active = self.active

    def __raise_value_changed(self):
        self.dispatch("on_selected_changed", self.text, self.active)
        if self.owner: self.owner.on_selection_changed(self.text, self.active)

    def on_selected_changed(self, result_list_item, selected):
        pass

    def mark(self, check, value):
        self.active = value
        self.__raise_value_changed()
            
    def refresh_view_attrs(self, rv, index, data):
        """A method of the RecycleView called automatically to refresh the
            content of the view.

        Parameters
        ----------
        rv : RecycleView
            The RecycleView that owns this row and wants it refreshed (not used
            in this function).
        index: int
            The index of this row.
        data: dict
            The dictionary of data that constitutes this row.  Not needed here.
        """
        super().refresh_view_attrs(rv, index, data)
        self.ids.selected.active = self.active


class ConfigListItem(ThreeLineIconListItem, RecycleDataViewBehavior):

    active = False
    owner: CheckedListItemOwner = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type("on_selected_changed")
        self.ids.selected.active = self.active

    def __raise_value_changed(self):
        self.dispatch("on_selected_changed", self.text, self.active)
        if self.owner: self.owner.on_selection_changed(self.text, self.active)

    def on_selected_changed(self, bus, selected):
        pass

    def mark(self, check, value):
        self.active = value
        self.__raise_value_changed()

    def refresh_view_attrs(self, rv, index, data):
        """A method of the RecycleView called automatically to refresh the
            content of the view.

        Parameters
        ----------
        rv : RecycleView
            The RecycleView that owns this row and wants it refreshed (not used
            in this function).
        index: int
            The index of this row.
        data: dict
            The dictionary of data that constitutes this row.  Not needed here.
        """
        super().refresh_view_attrs(rv, index, data)
        self.ids.selected.active = self.active


class ResultsDetailListItem1(OneLineIconListItem, RecycleDataViewBehavior):
    
    active = False
    owner: CheckedListItemOwner = None 

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type("on_selected_changed")
        self.ids.selected.active = self.active
        
    def __raise_value_changed(self):
        self.dispatch("on_selected_changed", self.text, self.active)
        if self.owner: self.owner.on_selection_changed_1(self.text, self.active)

    def on_selected_changed(self, result_list_item, selected):
        pass

    def mark(self, check, value):
        self.active = value
        self.__raise_value_changed()
            
    def refresh_view_attrs(self, rv, index, data):
        """A method of the RecycleView called automatically to refresh the
            content of the view.

        Parameters
        ----------
        rv : RecycleView
            The RecycleView that owns this row and wants it refreshed (not used
            in this function).
        index: int
            The index of this row.
        data: dict
            The dictionary of data that constitutes this row.  Not needed here.
        """
        super().refresh_view_attrs(rv, index, data)
        self.ids.selected.active = self.active


class ResultsDetailListItem2(OneLineIconListItem, RecycleDataViewBehavior):
    
    active = False
    owner: CheckedListItemOwner = None 

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type("on_selected_changed")
        self.ids.selected.active = self.active
        
    def __raise_value_changed(self):
        self.dispatch("on_selected_changed", self.text, self.active)
        if self.owner: self.owner.on_selection_changed_2(self.text, self.active)

    def on_selected_changed(self, result_list_item, selected):
        pass

    def mark(self, check, value):
        self.active = value
        self.__raise_value_changed()
            
    def refresh_view_attrs(self, rv, index, data):
        """A method of the RecycleView called automatically to refresh the
            content of the view.

        Parameters
        ----------
        rv : RecycleView
            The RecycleView that owns this row and wants it refreshed (not used
            in this function).
        index: int
            The index of this row.
        data: dict
            The dictionary of data that constitutes this row.  Not needed here.
        """
        super().refresh_view_attrs(rv, index, data)
        self.ids.selected.active = self.active


class TextFieldFloat(MDTextField):
    SIMPLE_FLOAT = re.compile(r"(\+|-)?\d*(\.\d*)?$")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper_text_mode = "on_focus"
        self.helper_text = "Input value and press enter"

    def text_valid(self):
        return TextFieldFloat.SIMPLE_FLOAT.match(self.text) is not None

    def set_text(self, instance, value):
        if value == "":
            return
        self.set_error_message()

    def set_error_message(self):
        if not self.text_valid():
            self.error = True
            self.helper_text = "You must enter a number."
        else:
            self.error = False
            self.helper_text = "Input value and press enter"


class TextFieldMultiFloat(MDTextField):
    SIMPLE_FLOAT = re.compile(r"(\+|-)?\d*(\.\d*)?$")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper_text_mode = "on_focus"
        self.helper_text = "Input numeric value"

    def text_valid(self):
        return TextFieldMultiFloat.SIMPLE_FLOAT.match(self.text) is not None

    def set_text(self, instance, value):
        if value == "":
            return
        self.set_error_message()

    def set_varied_mode(self):
        self.text = ""
        self.helper_text = "Multiple varied values"
        self.error = False

    def set_not_set_mode(self):
        self.text = ""
        self.helper_text = "No values set"
        self.error = False

    def set_error_message(self):
        if not self.text_valid():
            self.error = True
            self.helper_text = "You must enter a number."
        else:
            self.error = False
            self.helper_text = "Input numeric value"


class TextFieldPositiveFloat(MDTextField):
    """An input field that only accepts positive floating point numbers.

    Parameters
    ----------
    minimum : float, default 0.0
        Impose a lower limit (inclusive) on the acceptable values.
    maximum : float, default inf
        Impose an upper limit (inclusive) on the acceptable values.
    kwargs
        Additional arguments for initializing the text field. See
        :py:class:`MDTextField` for allowed parameters
    """

    POSITIVE_FLOAT = re.compile(r"((\d+(\.\d*)?)|(\d*(\.\d+)))$")

    def __init__(self, minimum=0.0, maximum=math.inf, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper_text_mode = "on_focus"
        self.helper_text = "Input value and press enter"
        if (minimum < 0.0) or (maximum < minimum):
            raise ValueError(
                "minimum and maximum must be non-negative "
                "numbers with `minimum` <= `maximum`"
            )
        self.minimum = minimum
        self.maximum = maximum

    def text_valid(self):
        if TextFieldPositiveFloat.POSITIVE_FLOAT.match(self.text) is None:
            return False
        value = float(self.text)
        return self.minimum <= value <= self.maximum

    def set_text(self, instance, value):
        if value == "":
            return
        self.set_error_message()

    @property
    def _error_message(self):
        if self.minimum == 0.0 and self.maximum == math.inf:
            return "You must enter a non-negative number."
        if self.maximum == math.inf:
            return f"You must enter a number greater than {self.minimum}"
        return f"You must enter a number between {self.minimum} and {self.maximum}"

    def set_error_message(self):
        if not self.text_valid():
            self.error = True
            self.helper_text = self._error_message
        else:
            self.error = False
            self.helper_text = "Input value and press enter"


class ControlModelTab(FloatLayout, MDTabsBase):
    pass


class TextFieldPositivePercentage(MDTextField):
    POSITIVE_FLOAT = re.compile(r"\d*(\.\d*)?$")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper_text_mode = "on_focus"
        self.helper_text = "Input percentage value (0-100)"

    def text_valid(self):
        if TextFieldPositivePercentage.POSITIVE_FLOAT.match(self.text) is None:
            return False

        value = float(self.text)
        if value < 0.0: return False
        if value > 100: return False
        return True

    def set_text(self, instance, value):
        if value == "":
            return
        self.set_error_message()

    def set_error_message(self):
        if not self.text_valid():
            self.error = True
            self.helper_text = "You must enter a value between 0 and 100."
        else:
            self.error = False
            self.helper_text = "Input percentage value"

    def percentage(self):
        return float(self.text)

    def fraction(self):
        return self.percentage() / 100.0


class EditableSetList(MDList):
    options = ObjectProperty(set())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bind(
            options=self._update_display
        )

    def _update_display(self, instance, options):
        self.clear_widgets()
        for item in sorted(options):
            self.add_widget(
                EditableSetListItem(item, text=str(item))
            )

    def add_item(self, item):
        """Add an item to the set."""
        self.options = self.options.union(set([item]))

    def remove_item(self, item):
        """Remove an item from the set."""
        # Don't use set.remove() since we must return a new object
        # to trigger the _update_display callback throug kivy
        self.options = self.options - set([item])


class EditableSetListItem(OneLineRightIconListItem):
    """List item with one line and a delete button"""

    def __init__(self, item, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value = item
        self.ids.delete.bind(
            on_release=self._delete_item
        )

    def _delete_item(self, item):
        self.parent.remove_item(self._value)
        

class TextFieldListFilter(MDTextField):
    """Text field that filters the elements of an MDList."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper_text_mode = "on_focus"
        #self.helper_text = "Input text and press enter to filter"
        self.register_event_type("on_filter_applied")
    
    def on_text_validate(self):
        self.__raise_filter_applied()
                   
    def __raise_filter_applied(self):
        """Dispatches the on_filter_applied method to anything bound to it.
        """
        self.dispatch("on_filter_applied", self)
        
    def on_filter_applied(self, instance):
        pass
    

class TextFieldOpenDSSName(MDTextField):
    """Text field that enforces OpenDSS name requirements."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def text_valid(self):
        return is_valid_opendss_name(self.text)

    def set_text(self, instance, value):
        if value == "":
            self.error = True
        else:
            self.set_error_message()

    def set_error_message(self):
        if not self.text_valid():
            self.error = True
        else:
            self.error = False


class FilterableBusList(BoxLayout):

    _bus_filters = BusFilters()
    project = ObjectProperty(None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reload_bus_list()
        self._selected = set()
        # XXX The naming of this event overlaps with events in BusListItem.
        #     I would like to use "on_selection_changed" but that clashes with
        #     the API method on CheckedListItemOwner.
        self.register_event_type("on_selected_changed")

    def on_project(self, instance, proj):
        self.reload_bus_list()

    def on_selected_changed(self, buslist, selected):
        pass

    @property
    def data(self):
        return self.ids.bus_list.data

    @data.setter
    def data(self, value):
        self.ids.bus_list.data = value

    def reload_bus_list(self):
        if self.project is None:
            return
        self.data = [
            {"text": bus,
             "secondary_text": (
                 f"{self.project.phases(bus)}, "
                 f"{DSSModel.nominal_voltage(bus)} kV"),
             "active": bus in self._selected,
             "owner": self}
            for bus in filter(self._check_bus_filters, self.project.bus_names)
        ]
        button_label = " ".join(
            filter(lambda x: x,
                   ["Filter Busses", self._bus_filters.summary()])
        )
        self.ids.filter_busses_btn.text = button_label

    def _check_bus_filters(self, bus):
        return self._bus_filters.test_bus(bus, self.project, self._selected)

    def open_bus_filters(self):
        content = BusSearchPanelContent()
        content.load_voltage_checks(
            self.project.grid_model.all_base_voltages()
        )
        content.apply_filters(self._bus_filters)
        popup = Popup(
            title='Filter Busses',
            content=content,
            auto_dismiss=False,
            size_hint=(0.7, 0.7),
            background_color=(224,224,224),
            title_color=(0,0,0)
        )

        def apply(*args):
            self._bus_filters = content.extract_filters()
            self.reload_bus_list()
            popup.dismiss()

        def clear(*args):
            self._bus_filters = BusFilters()
            self.reload_bus_list()
            popup.dismiss()

        content.ids.okBtn.bind(on_press=apply)
        content.ids.clearBtn.bind(on_press=clear)
        content.ids.cancelBtn.bind(on_press=popup.dismiss)
        popup.open()

    def on_selection_changed(self, bus, selected):
        Logger.debug(f"selection_changed - {bus}:{selected}")
        if selected:
            self._selected.add(bus)
        else:
            self._selected.discard(bus)
        self.dispatch("on_selected_changed", self, self._selected)

    @property
    def selected_busses(self):
        return self._selected

    @selected_busses.setter
    def selected_busses(self, new):
        self._selected = new
        self.dispatch("on_selected_changed", self, self._selected)
        self.reload_bus_list()


class ResultsListRecycleView(RecycleView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class ConfigurationRecycleView(RecycleView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class ResultsDetailListRecycleView1(RecycleView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class ResultsDetailListRecycleView2(RecycleView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class StorageConfigurationScreen(SSimBaseScreen, CheckedListItemOwner):
    """Configure a single energy storage device."""

    _bus_filters = BusFilters()

    def __init__(self, der_screen, ess: StorageOptions, *args,
                 editing=None, **kwargs):
        super().__init__(der_screen.project, *args, **kwargs)
        self._der_screen = der_screen
        self.ids.power_input.bind(
            on_text_validate=self._add_device_power
        )
        self.ids.duration_input.bind(
            on_text_validate=self._add_device_duration
        )
        self.ids.device_name.bind(
            on_text_validate=self._check_name
        )
        self.options = ess
        self.initialize_widgets()
        self._editing = editing
                
    def initialize_widgets(self):
        if self.options is None: return

        for power in self.options.power:
            self.ids.power_list.add_item(power)

        for duration in self.options.duration:
            self.ids.duration_list.add_item(duration)

        self.ids.select_busses.project = self._der_screen.project
        self.ids.select_busses.selected_busses = self.options.busses

        self.ids.device_name.text = self.options.name
        
        self.ids.required.active = self.options.required

        Clock.schedule_once(
            lambda dt: refocus_text_field(self.ids.device_name), 0.05
            )

    def on_selection_changed(self, bus, selected):
        if self.options is None:
            return
        for b in self.ids.bus_list.data:
            if b["text"] == bus:
                b["active"] = selected
        if selected:
            self.options.add_bus(bus)
        else:
            self.options.remove_bus(bus)

    def apply_bus_filters(self):
        self.reload_bus_list()

    def open_bus_filters(self):
        content = BusSearchPanelContent()

        content.load_voltage_checks(self.project.grid_model.all_base_voltages())

        content.apply_filters(self._bus_filters)

        popup = Popup(
            title="Filter Busses",
            content=content,
            auto_dismiss=False,
            size_hint=(0.7, 0.7),
            background_color=(224, 224, 224),
            title_color=(0, 0, 0),
        )

        def apply(*args):
            self._bus_filters = content.extract_filters()
            self.apply_bus_filters()
            popup.dismiss()

        def clear(*args):
            self._bus_filters = BusFilters()
            self.apply_bus_filters()
            popup.dismiss()

        content.ids.okBtn.bind(on_press=apply)
        content.ids.clearBtn.bind(on_press=clear)
        content.ids.cancelBtn.bind(on_press=popup.dismiss)
        popup.open()

    def on_bus_filter_applied(self, instance, value):
        self.reload_bus_list()

    def check_bus_filters(self, bus) -> bool:
        return self._bus_filters.test_bus(bus, self.project, self.options.busses)

    def check_need_bus_filtering(self) -> bool:
        return self._bus_filters is not None and not self._bus_filters.is_empty()

    def reload_bus_list(self):
        need_filter = self.check_need_bus_filtering()

        bus_data = []
        for bus in self.project.bus_names:
            if not need_filter or self.check_bus_filters(bus):
                phases = str(self.project.phases(bus))
                kv = str(DSSModel.nominal_voltage(bus))
                bus_data += [
                    {
                        "text": bus,
                        "secondary_text": phases + ", " + kv + " kV",
                        "active": bus in self.options.busses,
                        "owner": self,
                    }
                ]

        self.ids.bus_list.data = bus_data

        filtertxt = self._bus_filters.summary()
        self.ids.filter_busses_btn.text = "Filter Busses"
        if filtertxt:
            self.ids.filter_busses_btn.text += " " + filtertxt

    def _check_name(self, textfield):
        if not textfield.text_valid():
            textfield.helper_text = "Invalid name"
            textfield.error = True
            return False
        same_names = [so.name.lower() == textfield.text.lower()
                      for so in self.project.storage_options]
        if sum(same_names) > 1:
            textfield.helper_text = "Name already exists"
            textfield.error = True
            return False
        textfield.error = False
        return True

    def _add_option(self, optionlist, textfield):
        if textfield.text_valid():
            value = float(textfield.text)
            optionlist.add_item(value)
            textfield.text = ""
            Clock.schedule_once(lambda dt: refocus_text_field(textfield), 0.05)
        else:
            textfield.set_error_message()

    def _add_device_duration(self, textfield):
        self._add_option(self.ids.duration_list, textfield)

    def _add_device_power(self, textfield):
        self._add_option(self.ids.power_list, textfield)

    @property
    def _ess_powers(self):
        return set(self.ids.power_list.options)

    @property
    def _ess_durations(self):
        return set(self.ids.duration_list.options)

    @property
    def _selected_busses(self):
        return self.ids.select_busses.selected_busses

    def edit_control_params(self):
        self._record_option_data()

        self.manager.add_widget(
            StorageControlConfigurationScreen(
                self, self.project, self.options, name="configure-storage-controls"
            )
        )

        self.manager.current = "configure-storage-controls"

    def _record_option_data(self) -> StorageOptions:

        if self.options:
            self.options.power = self._ess_powers
            self.options.duration = self._ess_durations
            self.options.busses = self._selected_busses
            self.options.required = self.ids.required.active
            self.options.name = self.ids.device_name.text
            self.options.phases = 3
        else:
            self.options = StorageOptions(
                self.ids.device_name.text,
                3,
                self._ess_powers,
                self._ess_durations,
                self._selected_busses,
                required=self.ids.required.active
            )

    def __show_invalid_input_values_popup(self, msg):
        """Displays the popup box that indicates some invalid input for 
        a storage configuration.

        Parameters
        ----------
        msg
            The message to be shown.  Whatever it is, it must be convertible to
            a string using the str() function.
        """
        content = MessagePopupContent()

        popup = Popup(
            title='Invalid Storage Input', content=content, auto_dismiss=False,
            size_hint=(0.4, 0.4)
        )
        content.ids.msg_label.text = str(msg)
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        popup.open()
        return

    def show_error(self, msg):
        if msg:
            self.__show_invalid_input_values_popup(msg)
            return True

        return False

    def save(self):
        self._record_option_data()

        if not self.options.valid:
            Logger.error(
                "invalid storage configuration - "
                f"name: {self.options.name}, "
                f"powers: {self.options.power}, "
                f"durations: {self.options.duration}, "
                f"busses: {self.options.busses}"
            )

        if not self._check_name(self.ids.device_name):
            return

        if self.show_error(self.options.validate_name()): return
        if self.show_error(self.options.validate_soc_values()): return
        if self.show_error(self.options.validate_power_values()):  return
        if self.show_error(self.options.validate_duration_values()): return
        if self.show_error(self.options.validate_busses()): return
        if self.show_error(self.options.validate_controls()): return

        self._der_screen.add_ess(self.options)
        self.manager.current = "der-config"
        self.manager.remove_widget(self)

    def cancel(self):
        if self._editing is not None:
            # Restore the original device
            self._der_screen.add_ess(self._editing)
        self.manager.current = "der-config"
        self.manager.remove_widget(self)

    def on_enter(self, *args):
        return super().on_enter(*args)


class PVControlConfigurationScreen(SSimBaseScreen):

    def __init__(self, pvscreen, project, pvoptions, *args, **kwargs):
        super().__init__(project, *args, **kwargs)
        self._pvscreen = pvscreen
        self._pvoptions = pvoptions
        self._control = self._pvoptions.control or InverterControl("uncontrolled")
        self.ids.tabs.bind(active_tab=self._set_mode_label)
        if self._pvoptions is not None:
            self.ids.tabs.control = self._control
        self._set_mode_label()

    def save(self):
        self._pvoptions.control = self._control
        self.ids.tabs.save(self._pvoptions.control)
        self._close()

    def cancel(self):
        self._close()

    @property
    def device_name(self):
        if self._pvoptions is None:
            return ""
        return self._pvoptions.name

    def _close(self):
        self.manager.current = "configure-pv"
        self.manager.remove_widget(self)

    def _set_mode_label(self, *args):
        Logger.debug(f"-> PV...Screen._set_mode_label() {self.ids.tabs.active_tab}")
        txt = f"Select a control mode for this PV system: [b]{self.device_name}[/b]"
        if self.ids.tabs.active_tab is not None:
            pName = self.ids.tabs.active_tab.control_name
            txt += f", currently [b]{pName}[/b]"
        self.ids.mode_label.text = txt


class StorageControlConfigurationScreen(SSimBaseScreen):
    """Configure the control strategy of a single energy storage device."""

    def __init__(self, der_screen, project, options, *args, **kwargs):
        super().__init__(project, *args, **kwargs)
        self._der_screen = der_screen
        self._options = options

        self.ids.min_soc.text = str(self._options.min_soc * 100.0)
        self.ids.max_soc.text = str(self._options.max_soc * 100.0)
        self.ids.init_soc.text = str(self._options.initial_soc * 100.0)

        util.focus_defocus(self.ids.max_soc)
        util.focus_defocus(self.ids.min_soc)
        util.focus_defocus(self.ids.init_soc)

        if self._options is not None:
            self.ids.tabs.control = self._options.control

        self.ids.tabs.bind(active_tab=self.set_mode_label_text)

    def set_mode_label_text(self, *args):
        """ Adds the current device name to the label that informs a user to
        select a current control model.
        """
        txt = f"Select a control mode for this storage asset: [b]{self.device_name}[/b]"
        if self.ids.tabs.active_tab is not None:
            pName = self.ids.tabs.active_tab.control_name
            txt += f", currently [b]{pName}[/b]"
        self.ids.mode_label.text = txt

    @property
    def device_name(self) -> str:
        """Returns the name given to this storage device configuration or
        an empty string if none has been provided.

        Returns
        -------
        str:
            The name given to this storage option or an empty string if one has
            not been given.  This will not return None.
        """
        return "" if self._options is None else self._options.name

    def cancel(self):
        """Returns to the "configure-storage" form.

        This does not do anything with data.  It does not save any input data
        nor does it roll back any previously saved data.

        This is called when the user presses the "back" button.
        """
        self._close()

    def _close(self):
        self.manager.current = "configure-storage"
        self.manager.remove_widget(self)

    def save(self):
        result = self.ids.tabs.save(self._options.control)
        if result is not None:
            # TODO display an error message
            return
        self._options.min_soc = self.ids.min_soc.fraction()
        self._options.max_soc = self.ids.max_soc.fraction()
        self._options.initial_soc = self.ids.init_soc.fraction()
        self._close()


class PVConfigurationScreen(SSimBaseScreen):
    """Configure a single PV system."""

    _bus_filters = BusFilters()

    def __init__(self, der_screen, pvsystem, *args,
                 editing=None, **kwargs):
        super().__init__(der_screen.project, *args, **kwargs)
        self._pvsystem = pvsystem
        self._der_screen = der_screen
        self.ids.pmpp_input.bind(on_text_validate=self._add_pmpp)
        self.ids.device_name.bind(on_text_validate=self._check_name)
        self.ids.select_irradiance.bind(on_release=self._select_irradiance)
        self._initialize_widgets()
        self._editing = editing

    def _initialize_widgets(self):
        if self._pvsystem is None:
            return
        for pmpp in self._pvsystem.pmpp:
            self.ids.pmpp_list.add_item(pmpp)
        self.ids.select_busses.selected_busses = self._pvsystem.busses
        self.ids.select_busses.project = self._der_screen.project
        self.ids.device_name.text = self._pvsystem.name
        self.ids.required.active = self._pvsystem.required
        if self._pvsystem.irradiance is not None:
            self.ids.irradiance_path.text = self._pvsystem.irradiance
        Clock.schedule_once(
            lambda _: refocus_text_field(self.ids.device_name),
            0.05
        )

    def _check_name(self, textfield):
        if not textfield.text_valid():
            textfield.helper_text = "Invalid name"
            textfield.error = True
            return False
        same_name = (pv.name.lower() == textfield.text.lower()
                     for pv in self.project.pv_options
                     if pv is not self._pvsystem)
        if any(same_name):
            textfield.helper_text = "Name already exists"
            textfield.error = True
            return False
        textfield.error = False
        return True

    def _add_pmpp(self, textfield):
        if textfield.text_valid():
            value = float(textfield.text)
            self.ids.pmpp_list.add_item(value)
            textfield.text = ""
            Clock.schedule_once(lambda dt: refocus_text_field(textfield), 0.05)
        else:
            textfield.set_error_message()

    @property
    def _pmpp(self):
        return set(self.ids.pmpp_list.options)

    @property
    def _selected_busses(self):
        return self.ids.select_busses.selected_busses

    def _show_errors(self, errors):
        if len(errors) == 0:
            return True
        content = MessagePopupContent()
        popup = Popup(
            title="Invalid PV System Input",
            content=content,
            auto_dismiss=False,
            size_hint=(0.4, 0.4)
        )
        content.ids.msg_label.text = "\n".join(errors)
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        popup.open()
        return False

    def _validate(self):
        errors = [
            self._pvsystem.validate_name(),
            self._pvsystem.validate_pmpp(),
            self._pvsystem.validate_dcac_ratio(),
            self._pvsystem.validate_busses(),
            self._pvsystem.validate_controls(),
            self._pvsystem.validate_irradiance()
        ]
        errors = [error for error in errors if error]
        return self._show_errors(errors)

    def _record_options(self):
        self._pvsystem.pmpp = self._pmpp
        self._pvsystem.busses = self._selected_busses
        self._pvsystem.required = self.ids.required.active
        self._pvsystem.name = self.ids.device_name.text

    def _dismiss(self):
        self._popup.dismiss()

    def _selected(self, path, selection):
        if len(selection) != 1:
            Logger.debug("Invalid selection made for irradiance data")
            return
        self._pvsystem.irradiance = os.path.join(path, selection[0])
        self.ids.irradiance_path.text = self._pvsystem.irradiance
        self._popup.dismiss()

    def _select_irradiance(self, *args, **kwargs):
        content = SelectFileDialog(cancel=self._dismiss, load=self._selected)
        self._popup = Popup(content=content)
        self._popup.open()

    def edit_control_params(self):
        # self._record_option_data()
        self.manager.add_widget(
            PVControlConfigurationScreen(
                self, self.project, self._pvsystem,
                name="configure-pv-controls"
            )
        )
        self.manager.current = "configure-pv-controls"

    def save(self):
        self._record_options()
        if not self._validate():
            return
        self._der_screen.add_pv(self._pvsystem)
        self.manager.current = "der-config"
        self.manager.remove_widget(self)

    def cancel(self):
        if self._editing:
            self._der_screen.add_pv(self._editing)
        self.manager.current = "der-config"
        self.manager.remove_widget(self)


class DERConfigurationScreen(SSimBaseScreen):
    """Configure energy storage devices and PV generators."""

    def __init__(self, *args, **kwargs):
        # comes first so the manager is initialized
        super().__init__(*args, **kwargs)
        self.ids.delete_storage.bind(
            on_release=self.delete_ess
        )
        self.ids.delete_pv.bind(
            on_release=self.delete_pv
        )

    def load_project_data(self):
        self.ids.ess_list.clear_widgets()
        for so in self.project.storage_devices:
            self.ids.ess_list.add_widget(
                StorageListItem(so, self)
            )
        self.ids.pv_list.clear_widgets()
        for pv in self.project.pvsystems:
            self.ids.pv_list.add_widget(
                PVListItem(pv, self)
            )

    def new_storage(self):
        name = "NewBESS"
        existing_names = {n.lower() for n in self.project.storage_names}
        i = 1
        while name.lower() in existing_names:
            name = "NewBESS" + str(i)
            i += 1
        ess = StorageOptions(name, [], [], [])

        self.manager.add_widget(
            StorageConfigurationScreen(
                self, ess, name="configure-storage")
        )

        self.manager.current = "configure-storage"

    def new_pv_system(self):
        name = "NewPV"
        existing_names = {n.lower() for n in self.project.pv_names}
        i = 1
        while name.lower() in existing_names:
            name = "NewPV" + str(i)
            i += 1
        pv = PVOptions(name, [], [])
        self.manager.add_widget(
            PVConfigurationScreen(
                self, pv, name="configure-pv")
        )
        self.manager.current = "configure-pv"

    def add_pv(self, pv):
        self.project.add_pv_option(pv)
        self.ids.pv_list.add_widget(PVListItem(pv, self))

    def add_ess(self, ess):
        self.project.add_storage_option(ess)
        self.ids.ess_list.add_widget(
            StorageListItem(ess, self)
        )

    def delete_pv(self, button):
        to_remove = []
        for pv_list_item in self.ids.pv_list.children:
            if pv_list_item.selected:
                to_remove.append(pv_list_item)
                self.project.remove_pv_option(pv_list_item.pv)
        for widget in to_remove:
            self.ids.pv_list.remove_widget(widget)

    def delete_ess(self, button):
        to_remove = []
        for ess_list_item in self.ids.ess_list.children:
            if ess_list_item.selected:
                to_remove.append(ess_list_item)
                self.project.remove_storage_option(ess_list_item.ess)
        for widget in to_remove:
            self.ids.ess_list.remove_widget(widget)

    def on_pre_enter(self, *args):
        if self.project.grid_model is None:
            _show_no_grid_popup("ssim", self.manager)
        return super().on_pre_enter(*args)

    def edit_storage(self, ess_list_item):
        ess = ess_list_item.ess
        # Remove from the list so it can be re-added after editing
        self.project.remove_storage_option(ess)
        self.ids.ess_list.remove_widget(ess_list_item)
        self.manager.add_widget(
            StorageConfigurationScreen(
                self,
                deepcopy(ess),
                name="configure-storage",
                editing=ess
            )
        )
        self.manager.current = "configure-storage"

    def edit_pvsystem(self, pv_list_item):
        pv = pv_list_item.pv
        self.project.remove_pv_option(pv)
        self.ids.pv_list.remove_widget(pv_list_item)
        self.manager.add_widget(
            PVConfigurationScreen(
                self,
                deepcopy(pv),
                name="configure-pv",
                editing=pv
            )
        )
        self.manager.current = "configure-pv"


class StorageListItem(TwoLineAvatarIconListItem):
    def __init__(self, ess, der_screen, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ess = ess
        self.text = ess.name
        self.secondary_text = str(ess.power)
        self.ids.edit.bind(
            on_release=self.edit
        )
        self._der_screen = der_screen

    @property
    def selected(self):
        return self.ids.selected.active

    def edit(self, icon_widget):
        self._der_screen.edit_storage(self)


class PVListItem(TwoLineAvatarIconListItem):
    def __init__(self, pv, der_screen, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pv = pv
        self.text = pv.name
        self.secondary_text = str(pv.pmpp)
        self.ids.edit.bind(on_release=self.edit)
        self._der_screen = der_screen

    @property
    def selected(self):
        return self.ids.selected.active

    def edit(self, icon_widget):
        self._der_screen.edit_pvsystem(self)


class ResultsVariableListItemWithCheckbox(TwoLineAvatarIconListItem):
    def __init__(self, variable_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = variable_name

    @property
    def selected(self):
        return self.ids.selected.active


class ResultsMetricsListItemWithCheckbox(TwoLineAvatarIconListItem):
    def __init__(self, variable_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = variable_name
    
    @property
    def selected(self):
        return self.ids.metrics_selected.active


class VariableListItem(TwoLineAvatarIconListItem):
    def __init__(self, pk=None, **kwargs):
        super().__init__(**kwargs)
        self.pk = pk

    @property
    def selected(self):
        return self.ids.selected.active


class LoadConfigurationScreen(SSimBaseScreen):
    pass


class MetricsNoGridPopupContent(BoxLayout):
    pass


class NoGridPopupContent(BoxLayout):
    pass


class NoGridFilePopupContent(BoxLayout):
    pass


class NoFigurePopupContent(BoxLayout):
    pass


class MissingMetricValuesPopupContent(BoxLayout):
    pass


class MessagePopupContent(BoxLayout):
    pass


class MetricsInfoPopupContent(BoxLayout):
    pass


class MetricListItem(TwoLineAvatarIconListItem):

    def on_touch_up(self, touch):
        if touch.is_double_tap and not self.__has_popup():
            if self.collide_point(*touch.pos):
                self.__show_metric_details_popup()

    def __show_metric_details_popup(self):
        content = MetricsInfoPopupContent()

        self.popup = Popup(
            title='Details for ' + self.text, content=content,
            auto_dismiss=False, size_hint=(0.4, 0.4)
        )
        content.ids.msg_label.text = str(self.secondary_text)
        content.ids.dismissBtn.bind(on_press=self.dismiss_popup)
        self.popup.open()

    def dismiss_popup(self, *_args, **kwargs):
        if self.__has_popup():
            self.popup.dismiss(_args, kwargs)
            self.popup = None

    def __has_popup(self):
        return hasattr(self, "popup") and self.popup

class MetricConfigurationScreen(SSimBaseScreen, CheckedListItemOwner):
    _selBusses = []
    _currentMetricCategory = "None"
    _metricIcons = {
        "Bus Voltage": "lightning-bolt-circle", "Unassigned": "chart-line"
        }
    _bus_filters = BusFilters()
    _def_btn_color = '#005376'
    _filterButton = None

    def on_kv_post(self, base_widget):
        """Implemented to manage the states of the upper limit, lower limit,
        and objective fields.

        This schedules calls to "refocus_text_field" on each text box.  See that
        method for details.

        Parameters
        ----------
        base_widget:
           The base-most widget whose instantiation triggered the kv rules.
        """
        Clock.schedule_once(
            lambda dt: refocus_text_field(self.ids.upperLimitText), 0.05
            )
        Clock.schedule_once(
            lambda dt: refocus_text_field(self.ids.lowerLimitText), 0.05
            )
        Clock.schedule_once(
            lambda dt: refocus_text_field(self.ids.objectiveText), 0.05
            )

    def manage_store_button_enabled_state(self):
        """Enables or disables the "Store" button depending on how many busses
        are currently selected.

        If no busses are selected, the button is disabled.  Otherwise, it is
        enabled.
        """
        self.ids.btnStore.disabled = len(self._selBusses) == 0

    def reload_metric_values(self):
        metrics = []
        common_lower_limit = None
        common_upper_limit = None
        common_obj = None
        common_sense = None
        have_no_metric_busses = False

        self.ids.metricValueBox.disabled = len(self._selBusses) == 0
        self.ids.metricSenseBox.disabled = len(self._selBusses) == 0

        ''' Gather up the list of all metrics relevant to the selection'''
        for b in self._selBusses:
            m = self.project.get_metric(self._currentMetricCategory, b)
            if m is None:
                have_no_metric_busses = True
            else:
                metrics.append(m)

        if not have_no_metric_busses:
            for m in metrics:
                if common_lower_limit is None:
                    common_lower_limit = m.metric.lower_limit
                    common_upper_limit = m.metric.upper_limit
                    common_obj = m.metric.objective
                    common_sense = m.metric.improvement_type
                else:
                    if common_lower_limit != m.metric.lower_limit:
                        common_lower_limit = None
                        break
                    if common_upper_limit != m.metric.upper_limit:
                        common_upper_limit = None
                        break
                    if common_obj != m.metric.objective:
                        common_obj = None
                        break
                    if common_sense != m.metric.improvement_type:
                        common_sense = None
                        break
        else:
            common_lower_limit = None
            common_upper_limit = None
            common_obj = None
            common_sense = None

        is_varied = len(metrics) > 1

        if common_lower_limit is None:
            self.ids.lowerLimitText.set_varied_mode() if is_varied else \
                self.ids.lowerLimitText.set_not_set_mode()
        else:
            self.ids.lowerLimitText.text = str(common_lower_limit)
            Clock.schedule_once(lambda dt: refocus_text_field(self.ids.lowerLimitText), 0.05)

        if common_upper_limit is None:
            self.ids.upperLimitText.set_varied_mode() if is_varied else \
                self.ids.upperLimitText.set_not_set_mode()
        else:
            self.ids.upperLimitText.text = str(common_upper_limit)
            Clock.schedule_once(lambda dt: refocus_text_field(self.ids.upperLimitText), 0.05)

        if common_obj is None:
            self.ids.objectiveText.set_varied_mode() if is_varied else \
                self.ids.objectiveText.set_not_set_mode()
        else:
            self.ids.objectiveText.text = str(common_obj)
            Clock.schedule_once(lambda dt: refocus_text_field(self.ids.objectiveText), 0.05)

        if common_sense is None:
            self.manage_button_selection_states(None)
        else:
            self.__active_sense_button(common_sense)

    def __active_sense_button(self, sense: ImprovementType):
        """Sets the proper sense based on the provided sense argument.

        Parameters
        ----------
        sense: ImprovementType
            The improvement type to set as the currently active sense for any
            metrics to be created.
        """
        if sense == ImprovementType.Minimize:
            self.set_minimize_sense()
        elif sense == ImprovementType.Maximize:
            self.set_maximize_sense()
        else:
            self.set_seek_value_sense()

    def set_minimize_sense(self):
        """Sets the input state to indicate the Minimize sense.

        This manages the button selection states for the Minimize button.
        """
        self.manage_button_selection_states(self.ids.min_btn)
        self.ids.lowerLimitText.opacity, self.ids.lowerLimitText.disabled = 0, True
        self.ids.upperLimitText.opacity, self.ids.upperLimitText.disabled = 1, False

    def set_maximize_sense(self):
        """Sets the input state to indicate the Maximize sense.

        This manages the button selection states for the Maximize button.
        """
        self.manage_button_selection_states(self.ids.max_btn)
        self.ids.lowerLimitText.opacity, self.ids.lowerLimitText.disabled = 1, False
        self.ids.upperLimitText.opacity, self.ids.upperLimitText.disabled = 0, True

    def set_seek_value_sense(self):
        """Sets the input state to indicate the Seek Value sense.

        This manages the button selection states for the seek value button.
        """
        self.manage_button_selection_states(self.ids.seek_btn)
        self.ids.lowerLimitText.opacity, self.ids.lowerLimitText.disabled = 1, False
        self.ids.upperLimitText.opacity, self.ids.upperLimitText.disabled = 1, False

    def manage_button_selection_states(self, selButton):
        """Sets the state and color of all sense buttons in accordance with
        the supplied, desired selected button.

        Parameters
        ----------
        selButton:
            The button that is to be seleted and whose back color is to be that
            of the selected button.
        """
        self.ids.max_btn.selected = False
        self.ids.min_btn.selected = False
        self.ids.seek_btn.selected = False
        self.ids.max_btn.md_bg_color = self._def_btn_color
        self.ids.min_btn.md_bg_color = self._def_btn_color
        self.ids.seek_btn.md_bg_color = self._def_btn_color

        if selButton is self.ids.max_btn:
            self.ids.max_btn.md_bg_color = "red"
            self.ids.max_btn.selected = True

        elif selButton is self.ids.min_btn:
            self.ids.min_btn.md_bg_color = "red"
            self.ids.min_btn.selected = True

        elif selButton is self.ids.seek_btn:
            self.ids.seek_btn.md_bg_color = "red"
            self.ids.seek_btn.selected = True

    def store_metrics(self):
        """Extracts information from the input fields, creates the indicated
        metrics and stores them in the project.

        Inputs include limits, objective, sense, and list of selected busses.
        """
        lower_limit = parse_float(self.ids.lowerLimitText.text)
        upper_limit = parse_float(self.ids.upperLimitText.text)
        obj = parse_float(self.ids.objectiveText.text)
        sense = None

        if self.ids.max_btn.selected:
            sense = ImprovementType.Maximize
        elif self.ids.min_btn.selected:
            sense = ImprovementType.Minimize
        elif self.ids.seek_btn.selected:
            sense = ImprovementType.SeekValue

        err = Metric.validate_metric_values(
            lower_limit, upper_limit, obj, sense, False
            )

        if err:
            self.__show_invalid_metric_value_popup(err)
            return

        for bus in self._selBusses:
            accum = MetricTimeAccumulator(
                Metric(lower_limit, upper_limit, obj, sense)
                )
            self.project.add_metric(self._currentMetricCategory, bus, accum)

        self.reload_metric_list()

    def reset_metric_list_label(self):
        """Resets the label atop the list of all defined metrics to include, or
           not, the current metric category.
        """
        if self._currentMetricCategory is None:
            self.ids.currMetriclabel.text = "Defined Metrics"

        elif self._currentMetricCategory == "None":
            self.ids.currMetriclabel.text = "Defined Metrics"

        else:
            self.ids.currMetriclabel.text = \
                "Defined \"" + self._currentMetricCategory + "\" Metrics"

    def manage_selection_buttons_enabled_state(self):
        """Enables or disables the buttons for select all and deselect all
        based on whether or not there are any entries in the middle list of the
        form.

        If there are items in the list, the buttons are enabled.  If there are
        no items in the list, the buttons are disabled.
        """
        numCldrn = len(self.ids.interlist.data) == 0
        self.ids.btnSelectAll.disabled = numCldrn
        self.ids.btnDeselectAll.disabled = numCldrn

    def deselect_all_metric_objects(self):
        """Deselects all the items in the middle list on this form by setting
        the check box active values to False.
        """
        for wid in self.ids.interlist.data:
            # wid is a dictionary.  If it has an "active" entry, set it's value
            # to False.
            if "active" in wid: wid["active"] = False
            
        self.ids.interlist.refresh_from_data()
        
    def select_all_metric_objects(self):
        """Selects all the items in the middle list on this form.

        This clears the currently selected busses and then appends each
        back into the list of selected busses as the checks are set.
        """
        self._selBusses.clear()
        for wid in self.ids.interlist.data:
            if "active" in wid:
                wid["active"] = True
                self._selBusses.append(wid["text"])

        self.ids.interlist.refresh_from_data()
        
    def reload_metric_list(self):
        """Reloads the list of all defined metrics.

        This method creates a list item for all metrics previously defined for
        the current category.
        """
        self.ids.metriclist.clear_widgets()
        self.reset_metric_list_label()
        manager = self.project.get_metric_manager(self._currentMetricCategory)

        if manager is None: return

        list = self.ids.metriclist
        list.active = False
        for key, m in manager.all_metrics.items():
            txt = self._currentMetricCategory + " Metric for Bus \"" + key + "\""
            deets = ""

            if m.metric.improvement_type == ImprovementType.Minimize:
                deets = "Upper Limit=" + str(m.metric.upper_limit) + ", " + \
                        "Objective=" + str(m.metric.objective) + ", " + \
                        "Sense=Minimize"

            elif m.metric.improvement_type == ImprovementType.Maximize:
                deets = "Lower Limit=" + str(m.metric.lower_limit) + ", " + \
                        "Objective=" + str(m.metric.objective) + ", " + \
                        "Sense=Maximize"

            elif m.metric.improvement_type == ImprovementType.SeekValue:
                deets = "Lower Limit=" + str(m.metric.lower_limit) + ", " + \
                        "Upper Limit=" + str(m.metric.upper_limit) + ", " + \
                        "Objective=" + str(m.metric.objective) + ", " + \
                        "Sense=Seek Value"

            bItem = MetricListItem(text=txt, secondary_text=deets)
            bItem.bus = key
            bItem.ids.left_icon.icon = self._metricIcons[self._currentMetricCategory]
            bItem.ids.trash_can.bind(on_release=self.on_delete_metric)
            list.add_widget(bItem)

        list.active = True

    def on_delete_metric(self, data):
        """A callback function for the delete button of existing metric items.

        This method removes an existing metric from the current category and
        key identified by the data member in the metrics list item.
        """
        bus = data.listItem.bus
        self.project.remove_metric(self._currentMetricCategory, bus)
        self.reload_metric_list()
        self.reload_metric_values()

    def on_selection_changed(self, name, value):
        """A callback function for the list items to use when their check state
        changes.

        This method looks at the current check state (value) and either adds
        the text of the check box into the list of currently selected busses
        if value is true and removes it if value is false.

        This results in a resetting of the metric values and the associated
        fields.

        Parameters
        ----------
        ckb:
            The check box whose check state has changed.
        value:
            The current check state of the check box
            (true = checked, false = unchecked).
        """
        bus = name
        if value:
            self._selBusses.append(bus)
        else:
            if bus in self._selBusses: self._selBusses.remove(bus)

        self.reload_metric_values()
        self.manage_store_button_enabled_state()

    def configure_voltage_metrics(self):
        """Sets this form up for the creation, management, etc. of bus voltage
        metrics.

        This includes loading all necesary lists, setting the labels to
        indicate busses, and setting the enables state of the selection buttons
        appropriately.
        """
        self._currentMetricCategory = "Bus Voltage"
        self.ids.interlabel.text = "Busses"
        self._selBusses.clear()
        self.load_busses_into_list()
        self.reload_metric_list()
        self.reload_metric_values()
        self.manage_selection_buttons_enabled_state()

    def configure_some_other_metrics(self):
        """This method is a placeholder for future supported metrics.  It's not
        currently useful.
        """
        self._currentMetricCategory = "Unassigned"
        self._selBusses.clear()
        self.ids.interlist.data = []
        self.ids.interlabel.text = "Metric Objects"
        self.reload_metric_list()
        self.reload_metric_values()
        self.manage_selection_buttons_enabled_state()

    def _return_to_main_screen(self, dt):
        """Sets the current kivy screen to the main ssim screen.

        This is used as a callback for the popup menu that offers a user the
        action of returning to the main screen.
        """
        self.manager.current = "ssim"

    def __show_missing_metric_value_popup(self):
        """Displays the popup box indicating that there is a missing defining
        value for metrics.

        This uses the MissingMetricValuesPopupContent.
        """
        content = MissingMetricValuesPopupContent()

        popup = Popup(
            title='Missing Metric Values', content=content, auto_dismiss=False,
            size_hint=(0.4, 0.4)
        )
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        popup.open()

    def __show_invalid_metric_value_popup(self, msg: str):
        """Displays the popup box indicating that the values input to the
        metric values fields (limits, objective, and sense) are not usable.

        The text displayed is the supplied msg.  The popup content is the
        MessagePopupContent.

        Parameter
        ---------
        msg: str
           The message that is to be the primary content of the popup.
        """
        content = MessagePopupContent()

        popup = Popup(
            title='Invalid Metric Values', content=content, auto_dismiss=False,
            size_hint=(0.4, 0.4)
        )
        content.ids.msg_label.text = str(msg)
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        popup.open()

    def __show_no_grid_model_popup(self):
        """Displays the popup box indicating that there is no grid model so
        metrics cannot be defined.

        This uses the MetricsNoGridPopupContent.
        """
        content = MetricsNoGridPopupContent()

        popup = Popup(
            title='No Grid Model', content=content, auto_dismiss=False,
            size_hint=(0.4, 0.4)
        )
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        content.ids.mainScreenBtn.bind(on_press=popup.dismiss)
        content.ids.mainScreenBtn.bind(on_press=self._return_to_main_screen)
        popup.open()
        
    def apply_bus_filters(self):
        self.load_busses_into_list()
        
    def open_bus_filters(self, instance):
    
        content = BusSearchPanelContent()
        
        content.load_voltage_checks(
            self.project.grid_model.all_base_voltages()
            )

        content.apply_filters(self._bus_filters)

        popup = Popup(
            title='Filter Busses', content=content, auto_dismiss=False,
            size_hint=(0.7, 0.7), background_color=(224,224,224),
            title_color=(0,0,0)
        )

        def apply(*args):
            self._bus_filters = content.extract_filters()
            self.apply_bus_filters()
            popup.dismiss()
        
        def clear(*args):
            self._bus_filters = BusFilters()
            self.apply_bus_filters()
            popup.dismiss()            

        content.ids.okBtn.bind(on_press=apply)
        content.ids.clearBtn.bind(on_press=clear)
        content.ids.cancelBtn.bind(on_press=popup.dismiss)
        popup.open()

    def on_bus_filter_applied(self, instance, value):
        self.load_busses_into_list()

    def check_bus_filters(self, bus) -> bool:
        return self._bus_filters.test_bus(bus, self.project, self._selBusses)

    def check_need_bus_filtering(self) -> bool:
        return self._bus_filters is not None and \
            not self._bus_filters.is_empty()

    def load_busses_into_list(self):
        """Purposes the middle list in the form for busses and loads it with
        new BusListItem instances for each bus in the grid model.

        This method clears any current selected busses, clears any contents of
        the center list, and then reloads the list.  If there is no currently
        selected grid model, then __show_no_grid_model_popup is called and the
        method is aborted.
        """
        #self._selBusses.clear()
        list = self.ids.interlist
        list.viewclass = 'BusListItem'
        #list.clear_widgets()
        #list.text = "Busses"

        if self._filterButton is None:
            self._filterButton = Button(text="Filter Busses", size_hint_y=0.05)
            self._filterButton.bind(on_release=self.open_bus_filters)
            
        if self._filterButton not in self.ids.interlistheader.children:
            self.ids.interlistheader.add_widget(self._filterButton, 1)

        if self.project._grid_model is None:
            list.data = []
            self.__show_no_grid_model_popup()
            return
        
        need_filter = self.check_need_bus_filtering()      
        busses = self.project._grid_model.bus_names
        #list.active = False+
        bus_data = []
        for bus in busses:
            if not need_filter or self.check_bus_filters(bus):
                bus_data += [{
                    "text":bus,
                    "secondary_text":str(self.project.phases(bus)) +
                        ", " + str(DSSModel.nominal_voltage(bus)) + " kV",
                    "active":bus in self._selBusses,
                    "owner":self
                    }]
                
        list.data = bus_data
        
        filtertxt = self._bus_filters.summary()        
        self._filterButton.text = "Filter Busses"
        if filtertxt: self._filterButton.text += " " + filtertxt

        list.active = True


class RunProgressPopupContent(BoxLayout):
    """A popup that displays the progress of the running simulation(s)."""

    @property
    def max(self):
        """The maximum value for the progress bar."""
        return self.ids.progress.max

    @max.setter
    def max(self, value):
        self.ids.progress.max = value

    @property
    def text(self):
        """The text of the label above the progress bar."""
        return self.ids.info.text

    @text.setter
    def text(self, value):
        self.ids.info.text = value

    def cancel(self):
        """Change the progress bar label to 'canceling...'"""
        self.ids.info.text = "canceling..."

    def increment(self):
        """Tell the progress bar to advance its progress."""
        self.ids.progress.value += 1
        self.text = (
            f"Running simulation {self.ids.progress.value + 1} out of {self.max}."
        )


class RunSimulationScreen(SSimBaseScreen):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filtered_configurations: List[Configuration] = []
        self.storage_options: List[StorageOptions] = []
        self._config_filters = ConfigurationFilters()
        self._run_thread = None
        self._canceled = False
        # self.ids.simulation_runtime.bind(
        #     on_text_validate=self._set_simulation_time
        # )

    def on_enter(self):
        # establishes mappings between config id and config UI ids
        self._establish_mappings()

        # if no filtering has been applied
        if not self.filtered_configurations:
            for _, config in enumerate(
                    self.project.current_checkpoint.configurations()
            ):
                self.filtered_configurations.append(config)

        # recycle view setup
        self.populate_configurations_recycle_view()

        # update the configurations that are currently selected for 
        # evaluation
        self._update_configurations_to_eval()

        # enable/disable selection buttons
        self.manage_selection_buttons_enabled_state()

        # enable/disable run button
        self.manage_run_button_enabled_state()

    def populate_configurations_recycle_view(self):
        """Populates the recycle view with the list of configurations.
        """
        config_data = []

        # extract ids of filtered configurations
        filtered_config_ids = []
        for config in self.filtered_configurations:
            filtered_config_ids.append(config.id)

        for _, config in enumerate(
                self.project.current_checkpoint.configurations()
        ):
            if config.id in filtered_config_ids:
                secondary_detail_text = []
                tertiary_detail_text = []
                final_secondary_text = []
                final_tertiary_text = []

                for storage in config.storage:
                    if storage is not None:
                        secondary_detail_text.append(
                            f"name: {storage.name}, bus: {storage.bus}"
                        )
                        tertiary_detail_text.append(
                            f"kw: {storage.kw_rated}, kwh: {storage.kwh_rated}"
                        )
                    else:
                        secondary_detail_text.append('no storage')

                final_secondary_text = "\n".join(secondary_detail_text)
                final_tertiary_text = "\n".join(tertiary_detail_text)

                config_data += [{
                    "text": self.config_id_to_name[config.id],
                    "secondary_text": final_secondary_text,
                    "tertiary_text": final_tertiary_text,
                    "active": self.config_id_to_name[config.id] \
                        in self.selected_configurations.values(),
                    "owner": self
                }]

        self.ids.config_list_recycle.data = config_data
        self.ids.config_list_recycle.refresh_from_data()

    def _establish_mappings(self):
        """Creates mappings between internal configurations IDs and once that
           are displayed in the UI.
        """
        for i, config in enumerate(self.project.current_checkpoint.configurations()):
            # establish the mappings between config id and config UI_ids
            self.config_id_to_name[config.id] = f'Configuration {i+1}'

    def apply_config_filters(self):
        """Apply selected filters to the configurations list.
        """
        # clear the selected configurations and configurations
        # to evaluate lists
        self.selected_configurations.clear()
        self.configurations_to_eval.clear()
        # perform the filtering based on user selections
        self._perform_filtering()
        # update the UI based on user selections
        self.populate_configurations_recycle_view()

    def clear_config_filters(self):
        # clear the selected configurations and configurations
        # to evaluate lists
        self.selected_configurations.clear()
        self.configurations_to_eval.clear()
        # clear all the filters
        self._clear_filtering()
        self._perform_filtering()
        # update the UI based on user selections
        self.populate_configurations_recycle_view()

        Logger.debug('Configuration Filters Cleared ...')

    def _set_simulation_time(self):
        """Sets simulation time for each configuration. If the user
        does not provide a value, a 24 hour simulation is assumed
        by default.
        """
        sim_duration = 24.0
        if self.ids.simulation_runtime.text_valid():
            sim_duration = float(self.ids.simulation_runtime.text)
        self.project.sim_duration = sim_duration

    def _perform_filtering(self):
        """Performs filtering and repopulates the
           list filtered_configurations.
        """
        # reset filtered_configurations List every time a new filtering
        # action is performed
        filter_condition_kW = None
        filter_condition_kWh = None
        self.filtered_configurations = []

        Logger.debug(
            '> :::::::::::::::::::::::::::::::::::::::::::::::::::::::'
        )
        Logger.debug(self._config_filters.kw_filter["min"])
        Logger.debug(self._config_filters.kw_filter["max"])
        Logger.debug(self._config_filters.kwh_filter["min"])
        Logger.debug(self._config_filters.kwh_filter["max"])
        Logger.debug(type(self._config_filters.kw_filter["max"]))
        Logger.debug(self._config_filters.is_empty())
        Logger.debug(
            '::::::::::::::::::::::::::::::::::::::::::::::::::::::::::'
        )

        if not self._config_filters.is_empty():

            if self._config_filters.is_empty_kWh():
                for i, config in enumerate(
                        self.project.current_checkpoint.configurations()
                ):
                    # perform filtering based ONLY on kW range
                    filter_condition_kW = \
                        config.storage[0].kw_rated >= \
                            self._config_filters.kw_filter["min"] \
                                and config.storage[0].kw_rated <= \
                                    self._config_filters.kw_filter["max"]
                    if filter_condition_kW:
                        self.filtered_configurations.append(config)

            elif self._config_filters.is_empty_kW():
                for i, config in enumerate(
                        self.project.current_checkpoint.configurations()
                ):
                    # perform filtering based ONLY on kWh range
                    filter_condition_kWh = \
                        config.storage[0].kwh_rated >= \
                            self._config_filters.kwh_filter["min"] \
                                and config.storage[0].kwh_rated <= \
                                    self._config_filters.kwh_filter["max"]
                    if filter_condition_kWh:
                        self.filtered_configurations.append(config)
            else:
                for i, config in enumerate(
                        self.project.current_checkpoint.configurations()
                ):
                    # perform filtering based on kW and kWh range
                    filter_condition_kW = \
                        config.storage[0].kw_rated >= \
                            self._config_filters.kw_filter["min"] \
                                and config.storage[0].kw_rated <= \
                                    self._config_filters.kw_filter["max"]

                    filter_condition_kWh = \
                        config.storage[0].kwh_rated >= \
                            self._config_filters.kwh_filter["min"] \
                                and config.storage[0].kwh_rated <= \
                                    self._config_filters.kwh_filter["max"]

                    # populate self.filtered_configuration list
                    if filter_condition_kW and filter_condition_kWh:
                        self.filtered_configurations.append(config)
        else:
            Logger.debug('No Filters Specified. Filterting not performed!')
            for i, config in enumerate(
                    self.project.current_checkpoint.configurations()
            ):
                self.filtered_configurations.append(config)

    def _clear_filtering(self):
        self._config_filters.kw_filter["min"] = None
        self._config_filters.kw_filter["max"] = None
        self._config_filters.kwh_filter["min"] = None
        self._config_filters.kwh_filter["max"] = None

    def on_selection_changed(self, config, selected):
        """A callback function for the list items to use when their check state
        changes.

        This method looks at the current check state (value) and either adds
        the text of the check box into the list of currently selected
        configurations if value is true and removes it if value is false.

        This results in a resetting of the metric values and the associated
        fields.

        Parameters
        ----------
        ckb:
            The check box whose check state has changed.
        value:
            The current check state of the check box
            (true = checked, false = unchecked).
        """
        for c in self.ids.config_list_recycle.data:
            if c["text"] == config:
                c["active"] = selected

        # populate selected_configurations with current selection
        for c in self.ids.config_list_recycle.data:
            if c["active"]:
                config_key = self._get_config_key(self.config_id_to_name,
                                                  c["text"])
                self.selected_configurations[config_key] = c["text"]
            else:
                config_key = self._get_config_key(self.config_id_to_name,
                                                  c["text"])
                if config_key in self.selected_configurations:
                    del self.selected_configurations[config_key]

        # update the configurations that are currently selected for
        # evaluation
        self._update_configurations_to_eval()
        # enable/disable run button
        self.manage_run_button_enabled_state()

    def open_config_filters(self):
        """ Opens the configuration filter panel.
        """
        content = ConfigurationPanelContent()

        popup = Popup(
            title='Filter Configurations', content=content, auto_dismiss=False,
            size_hint=(0.7, 0.7), background_color=(224,224,224),
            title_color=(0,0,0)
        )

        def apply(*args):
            # extract the filter options based on user selection/entry
            self._config_filters = content.extract_filters()

            # apply the filters and update the displayed configurations
            self.apply_config_filters()

            Logger.debug('Configuration Filter Applied ... ')
            popup.dismiss()

        def clear(*args):
            # self._bus_filters = BusFilters()
            self.clear_config_filters()
            Logger.debug('Configuration Filters Cleared ...')
            popup.dismiss()

        content.ids.okBtn.bind(on_press=apply)
        content.ids.clearBtn.bind(on_press=clear)
        content.ids.cancelBtn.bind(on_press=popup.dismiss)
        popup.open()

    def _update_configurations_to_eval(self):
        """Updates the list (`self.configurations_to_eval`) that keeps 
        track of current selection in the UI for configurations to 
        be evaluated.
        """
        ctr = 0
        self.configurations_to_eval = []
        for wid in self.ids.config_list_recycle.data:
            if wid["active"]:
                self.configurations_to_eval.append(
                    self.filtered_configurations[ctr].id
                )
            ctr = ctr + 1

    def _get_config_key(self, config_dict, config_UI_id):
        """Returns the internal configuration ID.

        Parameters
        ----------
        config_dict : dict
            A dictionary that establishes mappings between internal 
            configration IDs and configuration IDs displayed in the
            UI.
        config_UI_id: str
            Configuration ID displayed in the UI whose internal ID
            is being queried.

        Returns
        -------
        str:
            Internal configuration ID corresponding to `config_UI_id`.
        """
        for key, value in config_dict.items():
            if value == config_UI_id:
                return key
        return('Configuration Not Found')
    
        Logger.debug("???????")
        Logger.debug(value)
        Logger.debug("Delete pressed")

    def manage_run_button_enabled_state(self):
        """Enables or disables the run simulation button. Esnures at least
        one configuration is selected before the UI allows the
        simulation to run.
        """
        numCldrn = len(self.configurations_to_eval) == 0
        self.ids.run_configuration_btn.disabled = numCldrn

    def manage_selection_buttons_enabled_state(self):
        """Enables or disables the buttons for select all and deselect all 
        based on whether or not there are any entries in the configuration 
        list.

        If there are items in the list, the buttons are enabled.  
        If there are no items in the list, the buttons are disabled.
        """
        numCldrn = len(self.ids.config_list_recycle.data) == 0
        self.ids.btnSelectAll.disabled = numCldrn
        self.ids.btnDeselectAll.disabled = numCldrn

    def deselect_all_configurations(self):
        """Deselects all the items in the configuration list."""
        for c in self.ids.config_list_recycle.data:
            if "active" in c:
                c["active"] = False

        # refresh the list to reflect all selection changes
        self.ids.config_list_recycle.refresh_from_data()

        # update the configurations that are currently selected for
        # evaluation
        self._update_configurations_to_eval()

    def select_all_configurations(self):
        """Selects all the items in configuration list.

        This clears the currently selected configs and then appends each
        back into the dictionary of selected configurations as the checks
        are set.
        """
        # clear configurations to eval and dictionary of
        # selected configurations
        self.configurations_to_eval.clear()
        self.selected_configurations.clear()

        # make all the configurations active and update
        # dictionary of selected configurations accordingly
        for c in self.ids.config_list_recycle.data:
            config_key = self._get_config_key(self.config_id_to_name,
                                              c["text"])
            if "active" in c:
                c["active"] = True
                self.selected_configurations[config_key] = c["text"]

        # refresh the list to reflect all selection changes
        self.ids.config_list_recycle.refresh_from_data()

        # update the configurations that are currently selected for 
        # evaluation
        self._update_configurations_to_eval()

    def _evaluate(self):
        """Initiates evaluation of configurations that are currently selected.
        """
        checkpoint = self.project.save_checkpoint()

        # step 1: get an update on the current selection
        self._update_configurations_to_eval()

        # step 2: evaluate the selected configurations
        for config in checkpoint.configurations():
            if config.id not in self.configurations_to_eval:
                continue
            if self._canceled:
                Logger.debug("evaluation canceled")
                break
            Logger.debug("Currently Running configuration:")
            Logger.debug(self.config_id_to_name[config.id])
            Logger.debug("==========================================")
            config.evaluate(basepath=checkpoint.checkpoint_dir)
            config.wait()
            self._progress_popup.content.increment()
        Logger.debug("clearing progress popup")
        self._canceled = False
        self._progress_popup.dismiss()

    def run_configurations(self):
        # acquire simulation time
        self._set_simulation_time()

        self._run_thread = Thread(target=self._evaluate)
        self._run_thread.start()
        self._progress = RunProgressPopupContent()
        self._progress.max = len(self.selected_configurations)
        self._progress.text = f"Running simulation 1 out of {self._progress.max}"
        self._progress.ids.dismissBtn.bind(on_press=self._cancel_run)
        self._progress_popup = Popup(title="simulation running...",
                                     content=self._progress)
        self._progress_popup.open()

    def _cancel_run(self, _dt):
        Logger.debug("Canceling simulation run.")
        self._canceled = True
        self._progress.cancel()

    def open_visualize_results(self):
        self.manager.current = "results-visualize"


class ResultsVisualizeScreen(SSimBaseScreen):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # keeps track of metrics that have been selected for plotting
        self.selected_metric_items = {}
        # stores the current configuration selected from the dropdown menu
        self.current_configuration = None
        self.metrics_figure = None
        self._show_voltage_status = True

    @property
    def project_results(self):
        return self.project.current_checkpoint.results()

    def on_enter(self):
        self.config_id_to_name = {}
        self._reset_selected_metrics_items()

    def _reset_selected_metrics_items(self):
        self.selected_metric_items = {}
        ctr = 1

        # extract base directory       
        _current_checkpoint_base_dir = \
            self.project.current_checkpoint.results().base_dir

        if not os.path.isdir(_current_checkpoint_base_dir):
            content = MessagePopupContent()
            popup = Popup(
                title="No Results",
                content=content,
                auto_dismiss=False,
                size_hint=(0.4, 0.4)
            )
            content.ids.msg_label.text = "No results found for this project"
            content.ids.dismissBtn.bind(on_press=popup.dismiss)
            self.manager.current = "run-sim"
            popup.open()
            return

        # a list that keep track of configurations that have
        # been evaluated
        _evaluated_configs = []       
        for item in os.listdir(_current_checkpoint_base_dir):
            if os.path.exists(_current_checkpoint_base_dir / item / "evaluated"):
                _evaluated_configs.append(item)

        for config in self.project.current_checkpoint.configurations():
            # check if the configuration has been completely evaluated
            # before creating the mapping
            if config.id in _evaluated_configs:
                self.config_id_to_name[config.id] = 'Configuration ' + str(ctr)
                self.selected_metric_items['Configuration ' + str(ctr)] = []
                ctr += 1 
    
    def dismiss_popup(self):
        self._popup.dismiss()
        
    def _create_metrics_figure(self):
        """Creates instance of matplotlib figure based on selections 
           made in the UI.
        
        Returns
        ----------
        matplotlib.Figure:
            Instance of matplotlib figure.
        """
        plt.style.use('ggplot')
        metrics_fig = plt.figure()
        if self._show_voltage_status:
            gs = metrics_fig.add_gridspec(2, hspace=0.05)
        else:
            gs = metrics_fig.add_gridspec(1, hspace=0.05)
        axs = gs.subplots(sharex=True)

        for result in self.project_results.results():
            config_dir = os.path.basename(os.path.normpath(result.config_dir))

            # obtain accumulated metric values and times-series 
            # data in a pandas dataframe for metrics
            _, accumulated_metric, data_metrics = result.metrics_log()
            config_key = self.config_id_to_name[config_dir]

            # obtain voltages
            _, all_bus_voltages = result.bus_voltages()

            # columns to plot
            columns_to_plot = self.selected_metric_items[config_key]

            # select the subset of data based on 'columns_to_plot'
            selected_data = data_metrics[columns_to_plot]
            x_data = data_metrics.loc[:, 'time']
            x_data_voltage = all_bus_voltages.loc[:, 'time']
            all_bus_voltages.drop(["time"], axis=1, inplace=True)

            # add the selected columns to the plot
            for column in selected_data.keys():
                if self._show_voltage_status:
                    axs[0].plot(x_data, selected_data[column], 
                                label=config_key + '-' + column + ' :' + str(accumulated_metric))
                    axs[1].plot(x_data_voltage, all_bus_voltages[column], 
                                label=config_key + '-' + column + ' :' + str(accumulated_metric))
                    axs[0].set(ylabel='Voltage Metric')
                    axs[1].set(ylabel='Voltage [p.u.]')
                else:
                    axs.plot(x_data, selected_data[column],
                             label=config_key + '-' + column + ' :' + str(accumulated_metric))
                    axs.set(ylabel='Voltage Metric')

        plt.legend()
        
        # x-axis label will always be time and seconds by default
        metrics_fig.supxlabel('time [s]')
        
        # update the title based on user input
        if self.ids.detail_figure_title.text is not None:
            metrics_fig.suptitle(self.ids.detail_figure_title.text)

        return metrics_fig

    def update_metrics_figure(self):
        """ Places the metrics figure in the UI canvas.
        """
        # check if at least one variable is selected for plotting
        if self._check_metrics_list_selection():
            self._show_error_popup('No Metrics(s) Selected!', 
                                   'Please select metrics(s) from the \
                                    dropdown menu to update the plot.')
        else:
            plt.clf()
            self.metrics_figure = self._create_metrics_figure()
            # Add kivy widget to the canvas
            self.ids.summary_canvas.clear_widgets()
            self.ids.summary_canvas.add_widget(
                FigureCanvasKivyAgg(self.metrics_figure)
            )

    def changed_show_voltage(self, active_state):
        Logger.debug('Show bus voltage checked!')
        Logger.debug(active_state)
        self._show_voltage_status = active_state

    def clear_metrics_figure(self):
        """ Clears the metrics figure from the UI canvas.
        """
        self.ids.summary_canvas.clear_widgets()

    def save_figure_options_metrics(self):
        """Provides interface to save the metric figure onto the local drive.
        """
        if self.metrics_figure is None:
            self._show_error_popup('No Figure to Save', 
                                   'Please create a plot before saving.')
        else:
            chooser = SaveFigureDialog(
                save=self.save_figure, cancel=self.dismiss_popup
            )
            self._popup = Popup(title="Save figure options", content=chooser)
            self._popup.open()

    def save_figure(self, selection, filename):
        """ Saves the current metric figure into the local drive.

        Parameters
        ----------
        selection : list
            A list containing information of the path where the figure
            will be stored. The fullpath is the first element of this list.
        filename : str
            Filename for the figure to be saved.
        """
        fullpath = selection[0]

        # by default, the figures are currently saved in PNG format
        split = os.path.splitext(filename)
        if split[1].lower() != ".png":
            filename = filename + ".png"

        if os.path.isdir(fullpath):
            fullpath = os.path.join(fullpath, filename)
        else:
            fullpath = os.path.join(os.path.dirname(fullpath), filename)

        Logger.debug("saving figure %s", fullpath)

        # by default, the figures are currently saved with DPI 300
        self.metrics_figure.savefig(fullpath, dpi=300)
        self.dismiss_popup()

    def _show_error_popup(self, title_str, msg):
        """A generic popup dialog box to show errors within the 
           visualization screen.
        
        Parameters
        ----------
        title_str : str
            Title of the popup box.
        msg : str
            Message to be displayed in the popup box.
        """
        content = MessagePopupContent()

        popup = Popup(
            title=title_str, content=content, auto_dismiss=False,
            size_hint=(0.4, 0.4)
        )
        content.ids.msg_label.text = str(msg)
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        popup.open()
        return

    def _check_metrics_list_selection(self):
        """Checks if at least one of the variables is selected from 
           the dropdown menus.
        """
        for _, config_variables in self.selected_metric_items.items():
            if config_variables != []:
                # at least one variable is selected, not empty
                return False
        return True
        
    def drop_config_menu_metrics(self):
        """Displays the dropdown menu in the visualization screen.
        """
        menu_items = []
        for config_id, config_ui_id in self.config_id_to_name.items():
            display_text = config_ui_id
            secondary_detail_text = []
            tertiary_detail_text = []
            final_secondary_text = []
            final_tertiary_text = []

            for i, config in enumerate(self.project.current_checkpoint.configurations()):
                if config_ui_id == f'Configuration {i+1}':
                    for storage in config.storage:
                        if storage is not None:
                            secondary_detail_text.append(
                                f"name: {storage.name}, bus: {storage.bus}")
                            tertiary_detail_text.append(
                                f"kw: {storage.kw_rated}, kwh: {storage.kwh_rated}")
                        else:
                            secondary_detail_text.append('no storage')

            final_secondary_text = "\n".join(secondary_detail_text)
            final_tertiary_text = "\n".join(tertiary_detail_text)

            menu_items.append({
                "viewclass": "ThreeLineListItem",
                "text": display_text,
                "height": dp(90),
                "secondary_text": final_secondary_text,
                "tertiary_text": final_tertiary_text,
                "on_release": lambda x=config_id, y=config_ui_id : self.set_config(x,y)
            })

        self.menu = MDDropdownMenu(
            caller=self.ids.config_list_detail_metrics, 
            items=menu_items, 
            width_mult=10
        )
        self.menu.open()

    def set_config(self, value_id, value_ui_id):
        """Populates the variables list based on the item (configuration)
        selected from the dropdown menu.

        Parameters
        ----------
        value_id : str
            Internal ID of the selected configuration.
        filename : str
            ID displayed in the UI of the selected configuration.
        """
        results_item_data = []

        self.current_configuration = value_ui_id
        
        # read the current selected configuration
        self.ids.config_list_detail_metrics.text = value_ui_id

        # put the 'Result' objects in a dict with configuration ids
        # this will allows the results to be mapped with 
        # corresponding configurations
        simulation_results = {}
        for result in self.project_results.results():
            # configuration directory of the result
            config_dir = os.path.basename(os.path.normpath(result.config_dir))
            simulation_results[config_dir] = result

        # extract the `current_result` based on selection from drop down menu
        current_result = simulation_results[value_id]

        # extract the data
        metrics_headers, metrics_accumulated, metrics_data = current_result.metrics_log()
        
        Logger.debug('------------------------------------------------------------')
        Logger.debug(self.selected_metric_items)
        Logger.debug('------------------------------------------------------------')

        # add the list of metrics in the selected configuration into the RecycleView        
        for item in metrics_headers:
            # do not add 'time' to the variable list
            if item == 'time':
                continue
            else:
                results_item_data +=[{
                    "text": item,
                    "active": item in self.selected_metric_items[self.current_configuration],
                    "owner": self
                }]

                self.ids.metrics_list_recycle.data = results_item_data
                self.ids.metrics_list_recycle.refresh_from_data()
        
        # close the drop-down menu
        self.menu.dismiss()
        
    def on_selection_changed(self, result_list_item, selected):
        """Refreshes 'self.selected_metric_items' with current selection
        """
        # ensure selection is checked in the UI
        for r in self.ids.metrics_list_recycle.data:
            if r["text"] == result_list_item:
                r["active"] = selected

        # refresh `selected_metric_items` with current selection
        for r in self.ids.metrics_list_recycle.data:
            if r["active"]:
                if r["text"] not in self.selected_metric_items[self.current_configuration]:
                    self.selected_metric_items[self.current_configuration].append(r["text"])
            else:
                if r["text"] in self.selected_metric_items[self.current_configuration]:
                    self.selected_metric_items[self.current_configuration].remove(r["text"])
                
    def open_results_detail(self):
        self.manager.current = "results-detail"


class ResultsDetailScreen(SSimBaseScreen):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.list_items = []
        self.selected_list_items_axes_1 = {}
        self.selected_list_items_axes_2 = {}
        self.variable_data = pd.DataFrame()
        self.figure = None       

    def on_enter(self):
        # TO DO: Replace with evaluated configurations
        self.config_id_to_name = {}
        self._reset_selected_list_items()

    def _reset_selected_list_items(self):
        self.selected_list_items_axes_1 = {}
        self.selected_list_items_axes_2 = {}
        ctr = 1

        # extract base directory       
        _current_checkpoint_base_dir = \
            self.project.current_checkpoint.results().base_dir

        # a list that keep track of configurations that have
        # been evaluated
        _evaluated_configs = []       
        for item in os.listdir(_current_checkpoint_base_dir):
            if os.path.exists(_current_checkpoint_base_dir / item / "evaluated"):
                _evaluated_configs.append(item)

        for config in self.project.current_checkpoint.configurations():
            # check if the configuration has been completely evaluated
            # before creating the mapping
            if config.id in _evaluated_configs:
                self.config_id_to_name[config.id] = 'Configuration ' + str(ctr)
                self.selected_list_items_axes_1['Configuration ' + str(ctr)] = []
                self.selected_list_items_axes_2['Configuration ' + str(ctr)] = []
                ctr += 1


    def dismiss_popup(self):
        self._popup.dismiss()

    def _all_pv_power(self, result):
        pv_data = []
        for pv in self.project.pv_names:
            _, pv_power = result.pvsystem_power(pv)
            # The monitor output is negative for power out, but we want positive here
            pv_power = pv_power.set_index("time")
            pv_power *= -1.0
            pv_power.columns = [f"{pv}_{col}" for col in pv_power.columns]
            pv_data.append(pv_power)
        return pd.concat(pv_data, axis=1)

    def _create_figure(self):
        """Creates instance of matplotlib figure based on selections 
        made in the UI.
        
        Returns
        ----------
        matplotlib.Figure:
            Instance of matplotlib figure.
        """
        # keep track of whether items are selected from the second list
        _second_list_selected = any(self.selected_list_items_axes_2.values())
        
        # use the ggplot theme
        plt.style.use('ggplot')

        # create subplots based on whether items are selected from 
        # the second list
        if _second_list_selected:
            fig, ax = plt.subplots(2, 1)
        else:
            fig, ax = plt.subplots(1, 1)
        
        # get the project results
        project_results = self.project.current_checkpoint.results().results()

        for result in project_results:
            # obtain pandas dataframe for storage states
            _, data_storage_state = result.storage_state()
            # obtain pandas dataframe for storage voltage, 'time' column is 
            # dropped to avoid duplication 
            _, data_storage_voltage = result.storage_voltages()
            data_storage_voltage.drop(['time'], axis=1, inplace=True)

            _, all_bus_voltage = result.bus_voltages()
            all_bus_voltage.drop(["time"], axis=1, inplace=True)
            # rename the columns
            all_bus_voltage.columns = [
                col + '_bus_voltage' for col in all_bus_voltage.columns
            ]

            # rename the 'data_storage_voltage' by appending '_voltage' to each header
            new_col_names = [item + '_voltage' for item in data_storage_voltage.columns]
            data_storage_voltage.columns = new_col_names

            all_pv_power = self._all_pv_power(result)

            # combine all data into a single dataframe
            data = pd.concat(
                [data_storage_state, data_storage_voltage, all_bus_voltage],
                axis=1
            )
            data = pd.concat(
                [data.set_index("time"), all_pv_power], axis=1, sort=True
            ).reset_index()
            config_dir = os.path.basename(os.path.normpath(result.config_dir))
            config_key = self.config_id_to_name[config_dir]
            
            # columns to plot
            columns_to_plot = self.selected_list_items_axes_1[config_key]
            
            # select subset of data based on columns_to_plot
            selected_data = data[columns_to_plot]
            x_data = data.loc[:, 'time']
            
            # add the selected columns to plot
            if _second_list_selected:
                for column in selected_data.keys():
                    ax[0].plot(x_data, selected_data[column], label=config_key + '-' + column)
            else:
                for column in selected_data.keys():
                    ax.plot(x_data, selected_data[column], label=config_key + '-' + column)

            if _second_list_selected:
                # columns to plot
                columns_to_plot = self.selected_list_items_axes_2[config_key]
                # select subset of data based on columns_to_plot
                selected_data = data[columns_to_plot]

                # add the selected columns to plot
                for column in selected_data.keys():
                    ax[1].plot(x_data, selected_data[column], label=config_key + '-' + column)

        # update the y-axis labels
        if self.ids.detail_figure_ylabel.text is not None:
            if _second_list_selected:
                ax[0].set_ylabel(self.ids.detail_figure_ylabel.text)
            else:
                ax.set_ylabel(self.ids.detail_figure_ylabel.text)

        if _second_list_selected:
            if self.ids.detail_figure_ylabel2.text is not None:
                ax[1].set_ylabel(self.ids.detail_figure_ylabel2.text)

        if self.ids.detail_figure_title is not None:
            fig.suptitle(self.ids.detail_figure_title.text, fontsize=14)
        else:
            fig.suptitle('Detail Plots')
        
        # add x-labels
        if _second_list_selected:
            ax[0].set_xlabel('time (s)')
            ax[1].set_xlabel('time (s)')
        else:
            ax.set_xlabel('time (s)')

        # add legends
        if _second_list_selected:
            ax[0].legend(loc='best')
            ax[1].legend(loc='best')
        else:
            ax.legend(loc='best')

        return fig

    def update_figure(self):
        """ Places the details figure in the UI canvas.
        """
        # check if at least one variable is selected for plotting
        if self._check_list_selection():
            self._show_error_popup('No Variable(s) Selected!', 
                                   'Please select variable(s) from the \
                                    dropdown menu to update the plot.')
        else:
            self.figure = self._create_figure()
            self.ids.detail_plot_canvas.clear_widgets()
            self.ids.detail_plot_canvas.add_widget(
                FigureCanvasKivyAgg(self.figure)
            )

    def save_figure_options(self):
        """Provides interface to save the metric figure onto the local drive.
        """
        if self.figure is None:
            self.__show_no_figure_popup('No Figure to Plot. \
                                        Please create a plot before saving.')
        else:
            chooser = SaveFigureDialog(
                save=self.save_figure, cancel=self.dismiss_popup
            )

            self._popup = Popup(title="Save figure options", content=chooser)
            self._popup.open()

    def save_figure(self, selection, filename):
        """ Saves the current detail figure into the local drive.

        Parameters
        ----------
        selection : list
            A list containing information of the path where the figure
            will be stored. The fullpath is the first element of this list.
        filename : str
            Filename for the figure to be saved.
        """
        fullpath = selection[0]

        # by default, the figures are currently saved in PNG format
        split = os.path.splitext(filename)
        if split[1].lower() != ".png":
            filename = filename + ".png"

        if os.path.isdir(fullpath):
            fullpath = os.path.join(fullpath, filename)
        else:
            fullpath = os.path.join(os.path.dirname(fullpath), filename)

        Logger.debug("saving figure %s", fullpath)

        # by default, the figures are currently saved with DPI 300
        self.figure.savefig(fullpath, dpi=300)
        self.dismiss_popup()

    def _show_error_popup(self, title_str, msg):
        """A generic popup dialog box to show errors within the 
        visualization screen.
        
        Parameters
        ----------
        title_str : str
            Title of the popup box.
        msg : str
            Message to be displayed in the popup box.
        """
        content = MessagePopupContent()

        popup = Popup(
            title=title_str, content=content, auto_dismiss=False,
            size_hint=(0.4, 0.4)
        )
        content.ids.msg_label.text = str(msg)
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        popup.open()
        return
    
    def _check_list_selection(self):
        """Checks if at least one of the variables is selected from 
        the dropdown menus.
        """
        list_item_axes1_empty = True
        list_item_axes2_empty = True
        for _, config_variables in self.selected_list_items_axes_1.items():
            if config_variables != []:
                # at least one variable is selected, not empty
                list_item_axes1_empty = False
                # return False
        for _, config_variables in self.selected_list_items_axes_2.items():
            if config_variables != []:
                list_item_axes2_empty = False

        if not list_item_axes1_empty or not list_item_axes2_empty:
            return False
        else:
            return True

    def clear_figure(self):
        """ Clears the detail figure from the UI canvas.
        """
        self.ids.detail_plot_canvas.clear_widgets()

    def drop_config_menu(self):
        """Displays the dropdown menu in the visualization screen.
        """
        menu_items = []
        for config_id, config_ui_id in self.config_id_to_name.items():
            display_text = config_ui_id
            secondary_detail_text = []
            tertiary_detail_text = []
            final_secondary_text = []
            final_tertiary_text = []

            for i, config in enumerate(self.project.current_checkpoint.configurations()):
                if config_ui_id == f'Configuration {i+1}':
                    for storage in config.storage:
                        if storage is not None:
                            secondary_detail_text.append(
                                f"name: {storage.name}, bus: {storage.bus}")
                            tertiary_detail_text.append(
                                f"kw: {storage.kw_rated}, kwh: {storage.kwh_rated}")
                        else:
                            secondary_detail_text.append('no storage')

            final_secondary_text = "\n".join(secondary_detail_text)
            final_tertiary_text = "\n".join(tertiary_detail_text)

            menu_items.append({
                "viewclass": "ThreeLineListItem",
                "text": display_text,
                "height": dp(90),
                "secondary_text": final_secondary_text,
                "tertiary_text": final_tertiary_text,
                "on_release": lambda x=config_id, y=config_ui_id : self.set_config(x,y)
            })

        self.menu = MDDropdownMenu(
            caller=self.ids.config_list_detail, 
            items=menu_items, 
            width_mult=10
        )
        self.menu.open()

    def set_config(self, value_id, value_ui_id):
        """Populates the variables list based on the item (configuration)
        selected from the dropdown menu.

        Parameters
        ----------
        value_id : str
            Internal ID of the selected configuration.
        value_ui_id : str
            ID displayed in the UI of the selected configuration.
        """
        results_detail_item_data_1 = []
        results_detail_item_data_2 = []

        self.current_configuration = value_ui_id
               
        # read the current selected configuration
        self.ids.config_list_detail.text = value_ui_id
        
        # put the 'Result' objects in a dict with configuration ids
        # this will allows the results to be mapped with 
        # corresponding configurations
        simulation_results = {}
        for result in self.project.current_checkpoint.results().results():
            # configuration directory of the result
            config_dir = os.path.basename(os.path.normpath(result.config_dir))
            simulation_results[config_dir] = result

        # extract the `current_result` based on selection from drop down menu
        if value_id in simulation_results:
            current_result = simulation_results[value_id]
          
            # extract the data
            storage_state_headers, storage_state_data = current_result.storage_state()
            storage_voltage_headers, storage_voltage_data = current_result.storage_voltages()
            bus_voltage_headers, bus_voltage_data = current_result.bus_voltages()

            
            # remove 'time' from the header list and pandas data frame to prevent
            # duplication
            if storage_voltage_headers is not None: 
                storage_voltage_headers.pop(0)
            storage_voltage_data.drop(['time'], axis=1, inplace=True)

            if bus_voltage_headers is not None:
                bus_voltage_headers.pop(0)
            bus_voltage_data.drop(['time'], axis=1, inplace=True)

            # 'storage_voltage_headers' have no indication that these labels
            # represent voltage, append string '_voltage' to each label
            storage_voltage_headers = [item + '_voltage' for item in storage_voltage_headers]
            bus_voltage_headers = [item + '_bus_voltage' for item in bus_voltage_headers]
            pv_headers = list(self._all_pv_power(current_result).columns)
            self.list_items = (
                storage_state_headers
                + storage_voltage_headers
                + bus_voltage_headers
                + pv_headers
            )
            self.variable_data = pd.concat(
                [storage_state_data, storage_voltage_data, bus_voltage_data],
                axis=1
            )

            self.x_data = list(self.variable_data.loc[:, 'time'])

            for item in self.list_items:
                # do not add 'time' to the variable list
                if item == 'time':
                    continue
                else:
                    results_detail_item_data_1 +=[{
                        "text": item,
                        "active": item in self.selected_list_items_axes_1[self.current_configuration],
                        "owner": self
                    }]

                    results_detail_item_data_2 +=[{
                        "text": item,
                        "active": item in self.selected_list_items_axes_2[self.current_configuration],
                        "owner": self
                    }]

            self.ids.variable_list_detail_axes_1_recycle.data = results_detail_item_data_1
            self.ids.variable_list_detail_axes_1_recycle.refresh_from_data()
            self.ids.variable_list_detail_axes_2_recycle.data = results_detail_item_data_2
            self.ids.variable_list_detail_axes_2_recycle.refresh_from_data()
            
            # close the drop-down menu
            self.menu.dismiss()

        else:

            Logger.debug('This configuration has not been evaluated')

    def on_selection_changed_1(self, result_list_item, selected):
        """Refreshes 'self.selected_list_items_axes_1' with current selection
        """
        # ensure selection is checked in the UI
        for r in self.ids.variable_list_detail_axes_1_recycle.data:
            if r["text"] == result_list_item:
                r["active"] = selected
        
        # refresh 'selected_list_items_axes_1' with current selection
        for r in self.ids.variable_list_detail_axes_1_recycle.data:
            if r["active"]:
                if r["text"] not in self.selected_list_items_axes_1[self.current_configuration]:
                    self.selected_list_items_axes_1[self.current_configuration].append(r["text"])
            else:
                if r["text"] in self.selected_list_items_axes_1[self.current_configuration]:
                    self.selected_list_items_axes_1[self.current_configuration].remove(r["text"])

    def on_selection_changed_2(self, result_list_item, selected):     
        """Refreshes 'self.selected_list_items_axes_2' with current selection
        """
        # ensure selection is checked in the UI
        for r in self.ids.variable_list_detail_axes_2_recycle.data:
            if r["text"] == result_list_item:
                r["active"] = selected
        
        # refresh 'selected_list_items_axes_2' with current selection
        for r in self.ids.variable_list_detail_axes_2_recycle.data:
            if r["active"]:
                if r["text"] not in self.selected_list_items_axes_2[self.current_configuration]:
                    self.selected_list_items_axes_2[self.current_configuration].append(r["text"])
            else:
                if r["text"] in self.selected_list_items_axes_2[self.current_configuration]:
                    self.selected_list_items_axes_2[self.current_configuration].remove(r["text"])       


# NOTE: This class may longer be required
class ListItemWithCheckbox(TwoLineAvatarIconListItem):

    def __init__(self, text, sec_text, tert_text, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = text
        self.secondary_text = sec_text
        self.tertiary_text = tert_text

    def delete_item(self, the_list_item):
        print("Delete icon button was pressed")
        print(the_list_item)
        self.parent.remove_widget(the_list_item)
        
    @property
    def selected(self):
        return self.ids.selected.active


class SelectFileDialog(FloatLayout):
    load = ObjectProperty(None)
    cancel = ObjectProperty(None)


class SelectGridDialog(FloatLayout):
    load = ObjectProperty(None)
    cancel = ObjectProperty(None)


class LoadSSIMTOMLDialog(FloatLayout):
    load = ObjectProperty(None)
    cancel = ObjectProperty(None)


class SaveSSIMTOMLDialog(FloatLayout):
    save = ObjectProperty(None)
    cancel = ObjectProperty(None)

    def manage_filename_field(self):
        sel = self.ids.filechooser.selection[0]
        if os.path.isdir(sel):
            self.ids.filenamefield.text = ""
        else:
            self.ids.filenamefield.text = os.path.basename(sel)


class SaveFigureDialog(FloatLayout):
    save = ObjectProperty(None)
    cancel = ObjectProperty(None)
    
    def manage_filename_field(self):
        sel = self.ids.filechooser.selection[0]
        if os.path.isdir(sel):
            self.ids.filenamefield.text = ""
        else:
            self.ids.filenamefield.text = os.path.basename(sel)


class SSimScreen(SSimBaseScreen):
    grid_path = ObjectProperty(None)

    colors = list(mplcolors.TABLEAU_COLORS.keys())

    cindex = 0
    curr_x_min = 0.0
    curr_x_max = 0.0
    curr_y_min = 0.0
    curr_y_max = 0.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._popup = None

    def on_kv_post(self, base_widget):
        self.refresh_grid_plot()

    def report(self, message):
        Logger.debug("button pressed: %s", message)

    def dismiss_popup(self):
        if self._popup: self._popup.dismiss()
        
    def _show_no_grid_file_popup(dismiss_screen=None, manager=None):
        """Show a popup dialog warning that no grid model file is selected.

        Parameters
        ----------
        dismiss_screen : str, optional

        """
        poppup_content = NoGridFilePopupContent()
        poppup_content.orientation = "vertical"
        popup = Popup(title='No Grid Model File Selected',
                      content=poppup_content,
                      auto_dismiss=False, size_hint=(0.4, 0.4))

        def dismiss(*args):
            popup.dismiss()
            if (dismiss_screen is not None) and (manager is not None):
                manager.current = dismiss_screen

        poppup_content.ids.dismissBtn.bind(on_press=dismiss)
        # open the popup
        popup.open()


    def load_grid(self, path, filename):
        if len(filename) == 0:
            self._show_no_grid_file_popup()
            return

        self.project.set_grid_model(filename[0])
        self.reset_grid_model_label()
        self.refresh_grid_plot()
        self.dismiss_popup()

    def reset_grid_model_label(self):
        self.ids.grid_model_label.text = "Grid Model: "

        if self.project._grid_model_path:
            self.ids.grid_model_label.text += self.project._grid_model_path
        else:
            self.ids.grid_model_label.text += "None"

    def reset_project_name_field(self):
        self.ids.project_name.text = self.project.name

    def load_toml_file(self, path, filename):
        if len(filename) == 0:
            Logger.debug("Cannot load file.  No file selected.")
            return
        
        Logger.debug("loading file %s", filename[0])
        self.project.load_toml_file(filename[0])
        self.set_current_input_file(filename[0])
        self.reset_grid_model_label()
        self.reset_project_name_field()
        self.refresh_grid_plot()
        self.reset_reliability()
        self.dismiss_popup()

    def reset_reliability(self):
        """Notify the reliability form to reload the model parameters."""
        Logger.debug(
            f"Reseting reliability: {self.project.reliability_params}")
        reliability = self.manager.get_screen("reliability-config")
        reliability.load(self.project.reliability_params)

    def set_current_input_file(self, fullpath):
        self.project._input_file_path = fullpath
        app = MDApp.get_running_app()
        app.title = "SSim: " + fullpath

    def save_toml_file(self, selection, filename):
        fullpath = selection[0]

        split = os.path.splitext(filename)
        if split[1].lower() != ".toml":
            filename = filename + ".toml"

        if os.path.isdir(fullpath):
            fullpath = os.path.join(fullpath, filename)
        else:
            fullpath = os.path.join(os.path.dirname(fullpath), filename)

        Logger.debug("saving file %s", fullpath)

        self.set_current_input_file(fullpath)
        toml = self.project.write_toml()

        with open(fullpath, 'w') as f:
            f.write(toml)

        self.dismiss_popup()

    def read_toml(self):
        chooser = LoadSSIMTOMLDialog(
            load=self.load_toml_file, cancel=self.dismiss_popup)

        self._popup = Popup(title="Select SSIM TOML File", content=chooser)
        self._popup.open()

    def write_to_toml(self):
        if not self.project._input_file_path:
            self.write_as_toml()
            return

        fname = os.path.basename(self.project._input_file_path)
        dname = [os.path.dirname(self.project._input_file_path)]

        self.save_toml_file(dname, fname)

    def write_as_toml(self):
        chooser = SaveSSIMTOMLDialog(
            save=self.save_toml_file, cancel=self.dismiss_popup)

        self._popup = Popup(title="select SSIM TOML file", content=chooser)
        self._popup.open()
        
    def on_pre_enter(self):
        self.refresh_grid_plot()

    def select_grid_model(self):
        chooser = SelectGridDialog(
            load=self.load_grid, cancel=self.dismiss_popup)

        self._popup = Popup(title="select grid model", content=chooser)
        self._popup.open()

    def open_der_configuration(self):
        self.manager.current = "der-config"

    def open_load_configuration(self):
        self.manager.current = "load-config"

    def open_metric_configuration(self):
        self.manager.current = "metric-config"

    def open_reliability_configuration(self):
        self.manager.current = "reliability-config"

    def do_run_simulation(self):
        self.manager.current = "run-sim"
        if self.project.grid_model is None:
            _show_no_grid_popup("ssim", self.manager)

    def num_phases(self, line):
        dssdirect.Lines.Name(line)
        return dssdirect.Lines.Phases()

    def get_raw_bus_name(self, bus: str):
        return bus.split(".", 1)[0]

    def bus_coords(self, bus):
        dssdirect.Circuit.SetActiveBus(bus)
        return dssdirect.Bus.X(), dssdirect.Bus.Y()

    def all_bus_coords(self, gm) -> dict:
        if len(gm.bus_names) == 0:
            return None

        seg_busses = {}

        for bus in gm.bus_names:
            bc = self.bus_coords(bus)
            seg_busses[self.get_raw_bus_name(bus)] = bc

        return seg_busses

    def line_bus_coords(self, line):
        bus1, bus2 = self.line_busses(line)
        return [self.bus_coords(bus1), self.bus_coords(bus2)]

    def line_busses(self, line):
        dssdirect.Lines.Name(line)
        return [dssdirect.Lines.Bus1(), dssdirect.Lines.Bus2()]
    
    def changed_show_bus_labels(self, active_state):
        self.refresh_grid_plot()
        
    def changed_show_storage_options(self, active_state):
        if len(self.project.storage_options) > 0:
            self.refresh_grid_plot()

    def changed_show_pv_options(self, actove_state):
        if len(self.project.pvsystems) > 0:
            self.refresh_grid_plot()
        
    def getImage(self, path):
        return OffsetImage(plt.imread(path, format="png"), zoom=.1)

    @staticmethod
    def _pv_path_vertices(xpix, ypix, w, h, xoffset = 0., yoffset = 5.):
        llx = xpix + xoffset - w/2.
        lly = ypix + yoffset

        panellow = 0.35 * h
        tiltoffset = 1./8. * w

        # Start with main rectangle.
        codes = [Path.MOVETO] + [Path.LINETO]*4
        vertices = [
            [llx,   lly+panellow], [llx+w-tiltoffset, lly+panellow],
            [llx+w, lly+h       ], [llx+tiltoffset,   lly+h       ],
            [llx,   lly+panellow]
            ]

        poleleft = llx + 0.35*w
        poleright = poleleft + .15*w
        poleheight = panellow

        # Add a small rectangle looking like the mounting pole on the bottom.
        codes += [Path.MOVETO] + [Path.LINETO]*3
        vertices += [
            [poleleft , lly + poleheight], [poleleft , lly             ],
            [poleright, lly             ], [poleright, lly + poleheight]
            ]

        spacing = (w - tiltoffset) / 4.
        halfpanhght = (h - panellow) / 2.

        # Finish with a drawing of vertical and horizontal lines on the box
        codes += ([Path.MOVETO] + [Path.LINETO]) * 5
        vertices += [
            [llx +   spacing, lly + panellow],
            [llx+ tiltoffset +   spacing, lly+h],
            [llx + 2*spacing, lly + panellow],
            [llx+ tiltoffset + 2*spacing, lly+h],
            [llx + 3*spacing, lly + panellow],
            [llx+ tiltoffset + 3*spacing, lly+h],
            [llx + 4*spacing, lly + panellow],
            [llx+ tiltoffset + 4*spacing, lly+h],
            [llx + tiltoffset/2., lly + panellow + halfpanhght],
            [llx + w - tiltoffset/2., lly + panellow + halfpanhght]
        ]
        return vertices, codes

    def __make_pv_patch(
        self, x, y, w, h, c, ax, xoffset = 0., yoffset = 5., facecolor = None
        ):

        xpix, ypix = ax.transData.transform((x, y)).T

        vertices, codes = self._pv_path_vertices(
            xpix, ypix, w, h, xoffset, yoffset)

        if facecolor is None:
            facecolor = ax.get_facecolor()

        #transform the patch vertices back to data coordinates.
        inv = ax.transData.inverted()
        tverts = inv.transform(vertices)

        ax.add_patch(
            patches.PathPatch(Path(tverts, codes), facecolor=facecolor,
            edgecolor=c)
            )
        
    @staticmethod
    def _battery_path_vertices(xpix, ypix, w, h, xoffset, yoffset,
                               incl_plus_minus=True):
        llx = xpix + xoffset - w/2.
        lly = ypix + yoffset
        
        # Start with main rectangle.
        codes = [Path.MOVETO] + [Path.LINETO]*4
        vertices = [
            [llx,lly], [llx+w, lly], [llx+w, lly+h], [llx, lly+h], [llx, lly]
            ]
       
        # Add a small rectangle looking like the nub on + side of a battery.
        codes += [Path.MOVETO] + [Path.LINETO]*3
        vertices += [
            [llx      ,lly+   h/4.], [llx-w/12., lly+   h/4.],
            [llx-w/12.,lly+3.*h/4.], [llx      , lly+3.*h/4.]
            ]

        # Finish with a drawing of a + and - sign if requested.  Don't use
        # annotations b/c this is simpler and more functional.  It's hard to
        # size an annotation properly.
        if incl_plus_minus:
            codes += ([Path.MOVETO] + [Path.LINETO])*3
            
            vertices += [
                [llx+   w/4.,lly+h/4.], [llx+   w/4., lly+3.*h/4.],
                [llx+   w/8.,lly+h/2.], [llx+3.*w/8., lly+   h/2.],
                [llx+5.*w/8.,lly+h/2.], [llx+7.*w/8., lly+   h/2.],
                ]

        return vertices, codes

    def __make_battery_patch(
        self, x, y, w, h, c, ax, xoffset = 0., yoffset = 5.,
        facecolor = None, incl_plus_minus = True
        ):

        xpix, ypix = ax.transData.transform((x, y)).T

        vertices, codes = self._battery_path_vertices(
            xpix, ypix, w, h, xoffset, yoffset, incl_plus_minus)

        if facecolor is None:
            facecolor = ax.get_facecolor()

        #transform the patch vertices back to data coordinates.
        inv = ax.transData.inverted()
        tverts = inv.transform(vertices)

        ax.add_patch(
            patches.PathPatch(Path(tverts, codes), facecolor=facecolor,
            edgecolor=c)
            )

    def _draw_der(self, ax, storage=True, pv=True):
        der_options = itertools.chain(
            self.project.storage_options if storage else [],
            self.project.pvsystems if pv else []
        )

        # Without getting the limits here, things don't draw right.  IDK why.
        _ = ax.get_ylim()

        w = 12
        h = 6
        o = 2
        yo = 4

        der_colors = {}
        der_busses = defaultdict(list)
        seg_busses = self.all_bus_coords(self.project.grid_model)
        cindex = 0

        for der in der_options:
            der_colors[der] = self.colors[cindex]
            cindex = (cindex + 1) % len(self.colors)
            for bus in der.busses:
                if bus not in seg_busses:
                    continue
                der_busses[bus].append(der)

        for bus, ders in der_busses.items():
            bx, by = seg_busses[bus]
            for i, der in enumerate(ders):
                if isinstance(der, StorageOptions):
                    draw_func = self.__make_battery_patch
                elif isinstance(der, PVOptions):
                    draw_func = self.__make_pv_patch
                else:
                    Logger.warning(
                        f"Unexpected DER type '{type(der)}' "
                        "encountered while drawing map"
                    )
                    continue
                draw_func(bx, by, w, h, der_colors[der], ax, i * o, yo + i * o)

        if len(der_busses.keys()) > 0:
            self.__make_plot_legend(ax, der_colors)
                
    def __draw_fixed_pv_assets(self, ax):
                
        gm = self.project.grid_model
        
        # make a mapping of all busses to receive batteries to the storage
        # options that include them.  Also map colors to storage options.

        # Without getting the limits here, things don't draw right.  IDK why.
        ylim = ax.get_ylim()

        w = 12
        h = 6 
        o = 2
        yo = 4

        self.cindex = 0
                
        seg_busses = self.__get_line_segment_busses(gm)
        
        for pv in self.project.pv_assets:
            color = self.colors[self.cindex]
            self.cindex = (self.cindex + 1) % len(self.colors)
            if pv.bus not in seg_busses: continue            
            bx, by = [seg_busses[pv.bus][0], seg_busses[pv.bus][1]]            
            self.__make_pv_patch(bx, by, w, h, color, ax)

    def __make_plot_legend(self, ax, der_colors):
        custom_lines = []
        names = []
                        
        for der, color in der_colors.items():
            names.append(f"{der.name} ({len(der.busses)})")
            if isinstance(der, PVOptions):
                vertices, codes = self._pv_path_vertices(0, 0, 10, 6, 0, -2.5)
                path = Path(vertices, codes)
                custom_lines.append(
                    Line2D(
                        [0], [0],
                        marker=path,
                        color="w",
                        lw=0,
                        markersize=20,
                        markerfacecolor="w",
                        markeredgecolor=color
                    )
                )
            elif isinstance(der, StorageOptions):
                vertices, codes = self._battery_path_vertices(0, 0, 12, 6, 0, -2.5, True)
                path = Path(vertices, codes)
                custom_lines.append(
                    Line2D(
                        [0], [0],
                        marker=path,
                        color="w",
                        lw=0,
                        markersize=20,
                        markerfacecolor="w",
                        markeredgecolor=color
                    )
                )
            else:
                custom_lines.append(Line2D([0], [0], color=color, lw=4))

        ax.legend(custom_lines, names)

    def __get_line_segments(self, gm):
        lines = gm.line_names
        if len(lines) == 0: return None
        
        return [line for line in lines
            if (0., 0.) not in self.line_bus_coords(line)]
    
    def __get_line_segment_busses(self, gm, seg_lines=None):
        if seg_lines is None:
            seg_lines = self.__get_line_segments(gm)
        
        if len(seg_lines) == 0:
            return self.all_bus_coords()

        seg_busses = {}
        
        for line in seg_lines:
            bus1, bus2 = self.line_busses(line)
            bc1 = self.bus_coords(bus1)
            bc2 = self.bus_coords(bus2)
            seg_busses[self.get_raw_bus_name(bus1)] = bc1
            seg_busses[self.get_raw_bus_name(bus2)] = bc2

        return seg_busses
    
    def compute_plot_limits(self):
        return (
            self.curr_x_min - 0.05 * (self.curr_x_max - self.curr_x_min),
            self.curr_x_max + 0.05 * (self.curr_x_max - self.curr_x_min),
            self.curr_y_min - 0.05 * (self.curr_y_max - self.curr_y_min),
            self.curr_y_max + 0.05 * (self.curr_y_max - self.curr_y_min)
            )

    def set_plot_limits(self, lims = None):
        ax = plt.gca()
        if lims is None:
            lims = self.compute_plot_limits()        
        ax.set_xlim(lims[0], lims[1])
        ax.set_ylim(lims[2], lims[3])

    def draw_plot_using_dss_plot(self):        
        gm = self.project.grid_model
        if gm is None:
            self.ids.grid_diagram.display_plot_error(
                "There is no current grid model."
                )
            return

        plt.clf()

        dss.plot.enable(show=False)
        label_txt = " Labels=Yes" if self.ids.show_bus_labels.active else ""
        dssdirect.Text.Command(f"plot circuit dots=Yes{label_txt}")

        plt.title('')
        plt.xticks([])
        plt.yticks([])
        plt.xlabel('')
        plt.ylabel('')        
        
        fig = plt.gcf()
        ax = plt.gca()
        ax.axis("off")
        
        blocs = self.__get_bus_marker_locations()
        if blocs is None:
            self.ids.grid_diagram.display_plot_error(
                "Bus locations are not known so no meaningful plot can be " +
                "produced."
                )
            return
        
        x, y = blocs
        # Without doing the scatter here, things don't draw right.  IDK why.
        ax.scatter(x, y, marker="None")
        
        self._draw_der(
            ax,
            storage=self.ids.show_storage_options.active,
            pv=self.ids.show_pv_options.active
        )

        fig.tight_layout()

        self.curr_x_min, self.curr_x_max = (min(x), max(x))
        self.curr_y_min, self.curr_y_max = (min(y), max(y))
        self.set_plot_limits()

        ax.callbacks.connect('ylim_changed', self.axis_limit_changed)
        self.ids.grid_diagram.reset_plot()
        
    def axis_limit_changed(self, ax):
        lims = self.compute_plot_limits()
        cxlims = ax.get_xlim()
        cylims = ax.get_ylim()
        
        if cxlims[0] != lims[0] or cxlims[1] != lims[1] or \
           cylims[0] != lims[2] or cylims[1] != lims[3]:
            self.set_plot_limits()
        
    def __get_bus_marker_locations(self):
        gm = self.project.grid_model
        
        if gm is None:
            self.ids.grid_diagram.display_plot_error(
                "There is no current grid model."
                )
            return
        
        lines = gm.line_names
        busses = gm.bus_names
        
        if len(lines) == 0 and len(busses) == 0:
            self.ids.grid_diagram.display_plot_error(
                "There are no lines and no busses in the current grid model."
                )
            return
        
        plotlines = len(lines) > 0
        
        seg_lines = self.__get_line_segments(gm)
        seg_busses = self.__get_line_segment_busses(gm, seg_lines)
        
        if plotlines:            
            line_segments = [self.line_bus_coords(line) for line in seg_lines]
            
            if len(line_segments) == 0:
                self.ids.grid_diagram.display_plot_error(
                    "There are lines but their bus locations are not known " +
                    "so no meaningful plot can be produced."
                    )
                return
                        
            return zip(*[(x, y) for seg in line_segments for x, y in seg])

        else:
            return ([seg_busses[bus][0] for bus in seg_busses], 
                [seg_busses[bus][1] for bus in seg_busses])
    
    def refresh_grid_plot(self):
        self.draw_plot_using_dss_plot()
        # return
    
        # gm = self.project.grid_model
        
        # plt.clf()

        # if gm is None:
        #     self.ids.grid_diagram.display_plot_error(
        #         "There is no current grid model."
        #         )
        #     return

        # lines = gm.line_names
        # busses = gm.bus_names

        # if len(lines) == 0 and len(busses) == 0:
        #     self.ids.grid_diagram.display_plot_error(
        #         "There are no lines and no busses in the current grid model."
        #         )
        #     return

        # # Start by plotting the lines if there are any.  Note that if there are
        # # lines, there must be busses but the opposite may not be true.
        # plotlines = len(lines) > 0
                
        # fig, ax = plt.subplots()
        
        # seg_lines = self.__get_line_segments(gm)

        # if plotlines:
        #     line_segments = [self.line_bus_coords(line) for line in seg_lines]

        #     if len(line_segments) == 0:
        #         self.ids.grid_diagram.display_plot_error(
        #             "There are lines but their bus locations are not known " +
        #             "so no meaningful plot can be produced."
        #             )
        #         return
            
        #     lc = LineCollection(
        #         line_segments, norm=plt.Normalize(1, 3), cmap='tab10'
        #         )

        #     lc.set_capstyle('round')

        #     fig.tight_layout()

        #     ax.add_collection(lc)
        #     ax.axis("off")
            
        # x, y = self.__get_bus_marker_locations()
        # ax.scatter(x, y)
        
        # if self.ids.show_storage_options.active:
        #     self.__draw_storage_options(ax)
        #     self.__make_plot_legend(ax)
            
        # seg_busses = self.__get_line_segment_busses(gm, seg_lines)
        
        # if self.ids.show_bus_labels.active:
        #     for bus in seg_busses:
        #         loc = seg_busses[bus]
        #         ax.annotate(bus, (loc[0], loc[1]))
                
        # self.curr_x_min, self.curr_x_max = (min(xs), max(xs))
        # self.curr_y_min, self.curr_y_max = (min(ys), max(ys))
        # self.set_plot_limits()

        # dg = self.ids.grid_diagram
        # dg.reset_plot()


class ValidationError(Exception):
    """Raised for parameter validation errors."""
    pass


class ReliabilityModelTab(MDGridLayout, MDTabsBase):
    """Base class for tabs used to configure reliability models.

    The property `model_name` should be set to the name the model is
    saved as in the JSON grid configuration file.
    """

    def __init__(self, model_name="unnamed", *args, **kwargs):
        self.model_name = model_name
        super().__init__(*args, **kwargs)

    def validate(self):
        try:
            self.to_dict()
        except ValueError:
            raise ValidationError(
                f"Invalid or missing values in {self.model_name}"
            )
        return True

    def to_dict(self):
        raise NotImplementedError()

    def load(self):
        raise NotImplementedError()


class LineReliabilityParams(ReliabilityModelTab):
    """Parameters for the line reliability model."""

    @property
    def enabled(self):
        """Return True if the line reliability model is enabled."""
        return self.ids.enabled.active

    def validate(self):
        super().validate()
        if not self.enabled:
            return True
        d = self.to_dict()
        if d["min_repair"] <= d["max_repair"]:
            return True
        raise ValidationError(
            f"{self.model_name}:\n\tMinimum repair time must be "
            f"less than or equal to maximum repair time."
        )

    def to_dict(self):
        """Return a dictionary of the model parameters."""
        try:
            return {
                "enabled": self.enabled,
                "mtbf": float(self.ids.line_mtbf.text),
                "min_repair": float(self.ids.line_repair_min.text),
                "max_repair": float(self.ids.line_repair_max.text)
            }
        except ValueError:
            return {"enabled": self.enabled}

    def load(self, params):
        """Load model parameters from `params` into the form.

        Parameters
        ----------
        params : dict
            Dictionary with optional keys 'enabled', 'mtbf', 'min_repair', and
            'max_repair'.
        """
        self.ids.enabled.active = params.get("enabled", False)
        self.ids.line_mtbf.text = str(params.get("mtbf", ""))
        self.ids.line_repair_min.text = str(params.get("min_repair", ""))
        self.ids.line_repair_max.text = str(params.get("max_repair", ""))


class SwitchReliabilityParams(ReliabilityModelTab):
    """Parameters for the switch reliability model."""

    @property
    def enabled(self):
        """Return True if the switch reliability model is enabled."""
        return self.ids.enabled.active

    def validate(self):
        if not super().validate():
            return False
        if not self.enabled:
            return True
        d = self.to_dict()
        # XXX This will work, but we don't provide any useful error
        #     message to the user.
        repair_valid = d["min_repair"] <= d["max_repair"]
        prob_valid = (d["p_open"] + d["p_closed"] + d["p_current"]) == 1.0
        if repair_valid and prob_valid:
            return True
        message = f"{self.model_name}: "
        if not repair_valid:
            message += (
                "\n\tMinimum repair time must be less than or equal "
                "to maximum repair time"
            )
        if not prob_valid:
            message += (
                "\n\tp_open, p_closed, and p_current must sum to 1.0"
            )
        raise ValidationError(message)

    def to_dict(self):
        """Return a dictionary of the model parameters."""
        try:
            return {
                "enabled": self.enabled,
                "mtbf": float(self.ids.switch_mtbf.text),
                "min_repair": float(self.ids.switch_repair_min.text),
                "max_repair": float(self.ids.switch_repair_max.text),
                "p_open": float(self.ids.switch_p_open.text),
                "p_closed": float(self.ids.switch_p_closed.text),
                "p_current": float(self.ids.switch_p_current.text)
            }
        except ValueError:
            return {"enabled": self.enabled}

    def load(self, params):
        self.ids.enabled.active = params.get("enabled", False)
        self.ids.switch_mtbf.text = str(params.get("mtbf", ""))
        self.ids.switch_repair_min.text = str(params.get("min_repair", ""))
        self.ids.switch_repair_max.text = str(params.get("max_repair", ""))
        self.ids.switch_p_open.text = str(params.get("p_open", ""))
        self.ids.switch_p_closed.text = str(params.get("p_closed", ""))
        self.ids.switch_p_current.text = str(params.get("p_current", ""))


class GeneratorReliabilityParams(ReliabilityModelTab):
    """Parameters for the generator reliability model."""

    @property
    def enabled(self):
        """Return True if either the aging or wearout models are enabled."""
        return self.aging_enabled or self.wearout_enabled

    @property
    def aging_enabled(self):
        """Return True if the generator aging model is enabled."""
        return self.ids.aging_active.active

    @property
    def wearout_enabled(self):
        """Return True if the generator wearout model is enabled."""
        return self.ids.wearout_active.active

    def validate(self):
        super().validate()
        # Validate relationships between parameters
        valid = {
            m: d["min_repair"] <= d["max_repair"]
            for m, d in self.to_dict().items()
            if (isinstance(d, dict) and d["enabled"])
        }
        if all(valid.values()):
            return True
        message = f"{self.model_name}: "
        for m, isvalid in valid.items():
            if isvalid:
                continue
            message += (
                f"\n\t{m}: Minimum repair time must be less than or equal "
                "to maximum repair time."
            )
        raise ValidationError(message)

    def to_dict(self):
        """Return a dictionary of the model parameters."""
        model = {"enabled": self.enabled}
        try:
            model["aging"] = {
                "enabled": self.aging_enabled,
                "mtbf": float(self.ids.aging_mtbf.text),
                "min_repair": float(self.ids.aging_repair_min.text),
                "max_repair": float(self.ids.aging_repair_max.text)
            }
        except ValueError:
            model["aging"] = {"enabled": self.aging_enabled}
        try:
            model["operating_wear_out"] = {
                "enabled": self.wearout_enabled,
                "mtbf": float(self.ids.wearout_mtbf.text),
                "min_repair": float(self.ids.wearout_repair_min.text),
                "max_repair": float(self.ids.wearout_repair_max.text)
            }
        except ValueError:
            model["operating_wear_out"] = {"enabled": self.wearout_enabled}
        return model

    def _load_aging(self, aging):
        self.ids.aging_mtbf.text = str(aging.get("mtbf", ""))
        self.ids.aging_repair_min.text = str(aging.get("min_repair", ""))
        self.ids.aging_repair_max.text = str(aging.get("max_repair", ""))
        self.ids.aging_active.active = aging.get("enabled", False)

    def _load_wearout(self, wearout):
        self.ids.wearout_mtbf.text = str(wearout.get("mtbf", ""))
        self.ids.wearout_repair_min.text = str(wearout.get("min_repair", ""))
        self.ids.wearout_repair_max.text = str(wearout.get("max_repair", ""))
        self.ids.wearout_active.active = wearout.get("enabled", False)

    def load(self, params):
        """Load the model params from a dict."""
        if "aging" in params:
            self._load_aging(params["aging"])
        if "operating_wear_out" in params:
            self._load_wearout(params["operating_wear_out"])


class ReliabilityConfigurationScreen(SSimBaseScreen):
    """Screen for configuring the reliability model."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load(self.project.reliability_params)
        self.ids.save.bind(
            on_press=lambda x: self.save()
        )

    def _model_tabs(self):
        return self.ids.reliability_models.get_slides()

    def validate(self):
        """Validate input for all enabled models."""
        errors = []
        error_messages = []
        for tab in self._model_tabs():
            if not tab.enabled:
                continue
            try:
                tab.validate()
            except ValidationError as e:
                errors.append(tab.title)
                error_messages.append(
                    # Work around Kivy bug when displaying tabs
                    # (see kivy issue #3477)
                    str(e).replace("\t", "    ")
                )
        if errors == []:
            return True
        _show_error_popup(
            f"Errors found in tabs: {', '.join(errors)}\n\n"
            + "\n\n".join(error_messages)
        )
        return False

    def load(self, params):
        """Load parameters from `params` into the forms.

        Parameters
        ----------
        params : dict
            Dictionary of reliability model parameters.
        """
        for tab in self._model_tabs():
            if tab.model_name not in params:
                continue
            tab.load(params[tab.model_name])

    def save(self):
        """Add reliability model parameters from to the Project."""
        if not self.validate():
            return
        for tab in self._model_tabs():
            Logger.debug(f"model_name: {tab.model_name}")
            self.project.add_reliability_model(tab.model_name, tab.to_dict())
        self.manager.current = "ssim"


def _show_error_popup(message):
    content = MessagePopupContent()
    content.ids.msg_label.text = message
    popup = Popup(title="Configuration error!", content=content)
    content.ids.dismissBtn.bind(on_press=popup.dismiss)
    popup.open()


def _show_no_grid_popup(dismiss_screen=None, manager=None):
    """Show a popup dialog warning that no grid model is selected.

    If the dismiss screen or manager are null, then no screen is set upon
    dismissal.  Whatever screen was visible when this popup was created will
    become visible again.

    Parameters
    ----------
    dismiss_screen : str, optional
        The name of the screen to return to when the popup is dismissed.
    manager : ScreenManager, optional
        The screen manager that is used to set the dismiss screen.
    """
    poppup_content = NoGridPopupContent()
    poppup_content.orientation = "vertical"
    popup = Popup(title='No Grid Model', content=poppup_content,
                  auto_dismiss=False, size_hint=(0.4, 0.4))

    def dismiss(*args):
        popup.dismiss()
        if (dismiss_screen is not None) and (manager is not None):
            manager.current = dismiss_screen

    poppup_content.ids.dismissBtn.bind(on_press=dismiss)
    # open the popup
    popup.open()


def _make_xy_matlab_plot(
    mpb: MatlabPlotBox, xs: list, ys: list, xlabel: str, ylabel: str,
    title: str
    ):
    
    """A utility method to plot the xs and ys in the given box.  The supplied
    title and axis labels are installed.

    Parameters
    ----------
    mpb: MatlabPlotBox
        The plot box that will house the plot created.
    xs: list
        The list of x values to plot.  Should be a list of floats.
    ys: list
        The list of y values to plot.  Should be a list of floats.
    xlabel: str
        The x axis label to put on the created plot.
    ylabel: str
        The y axis label to put on the created plot.
    title: str
        The string to use as the plot title.
    """
    fig, ax = plt.subplots(1, 1, layout="constrained")
    ax.plot(xs, ys, marker='o')
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    plt.title(title)
    mpb.reset_plot()


def _configure_fonts(exo_regular, exo_bold, exo_italic,
                     opensans_regular, opensans_bold, opensans_italic):
    # Configure the fonts use but the quest style
    LabelBase.register(
        name='Exo 2',
        fn_regular=exo_regular,
        fn_bold=exo_bold,
        fn_italic=exo_italic
    )

    LabelBase.register(
        name='Open Sans',
        fn_regular=opensans_regular,
        fn_bold=opensans_bold,
        fn_italic=opensans_italic
    )


def _paths(package, names):
    basepath = files(package)
    # all names need to be referenced individually so that each file
    # is guaranteed to exist when they are referenced.  As far as I
    # can tell there is no way to just make a directory containing all
    # resources in a package using importlib_resources.
    return list(as_file(basepath.joinpath(name)) for name in names)


def _font_paths():
    return dict(
        zip(_FONT_FILES.keys(),
            _paths("ssim.ui.kivy.fonts", _FONT_FILES.values()))
    )


def _kv_paths():
    return _paths("ssim.ui.kivy", _KV_FILES)


def _image_paths():
    return _paths("ssim.ui.kivy.images", _IMAGE_FILES)


def main():
    """Run the storage-sim kivy application."""
    Logger.setLevel(LOG_LEVELS["debug"])
    with ExitStack() as stack:
        font_paths = {font_name: str(stack.enter_context(font_path))
                      for font_name, font_path in _font_paths().items()}
        kv_paths = [stack.enter_context(kv) for kv in _kv_paths()]
        image_paths = [stack.enter_context(img) for img in _image_paths()]
        _configure_fonts(**font_paths)
        resource_dirs = set(
            resource.parent
            for resource in itertools.chain(kv_paths, image_paths)
        )
        for resource_dir in resource_dirs:
            kivy.resources.resource_add_path(resource_dir)
        SSimApp().run()


if __name__ == '__main__':
    main()
