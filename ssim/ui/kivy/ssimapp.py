"""Storage Sizing and Placement Kivy application"""
import itertools
import math
import os
import re
import sys
from contextlib import ExitStack
from math import cos, hypot
from threading import Thread
from typing import List

import kivy
import numpy as np
import matplotlib as mpl
mpl.use('module://kivy.garden.matplotlib.backend_kivy')
from matplotlib.path import Path
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import matplotlib.patches as patches
import matplotlib.colors as mplcolors

from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import dss.plot
import opendssdirect as dssdirect
import pandas as pd
from importlib_resources import files, as_file
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.logger import Logger, LOG_LEVELS
from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.textinput import TextInput
from kivy.core.window import Window
from kivymd.app import MDApp
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.list import IRightBodyTouch, OneLineAvatarIconListItem
from kivymd.uix.list import (
    TwoLineAvatarIconListItem,
    TwoLineIconListItem,
    ILeftBodyTouch,
    OneLineRightIconListItem,
    MDList
)
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.tab import MDTabsBase
from kivymd.uix.textfield import MDTextField
from matplotlib.collections import LineCollection
from ssim.metrics import ImprovementType, Metric, MetricTimeAccumulator
import ssim.ui
from ssim.ui import (
    Configuration,
    Project,
    StorageControl,
    StorageOptions,
    ProjectResults,
    is_valid_opendss_name
)

import kivy.garden
import inspect
kivy.garden.garden_system_dir = os.path.join(
    os.path.dirname(inspect.getfile(ssim.ui)), "libs/garden"
)
from kivy.garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg, NavigationToolbar2Kivy

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
    """A utility method to parse a string into a floating point value or
     leave it as is if the cast fails.

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


class SSimApp(MDApp):

    def __init__(self, *args, **kwargs):
        self.project = Project("unnamed")
        super().__init__(*args, **kwargs)

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
        self.project_results = ProjectResults(self.project)
        self.configurations: List[Configuration] = []
        self.configurations_to_eval: List[Configuration] = []
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


class BusListItem(TwoLineIconListItem):

    def __init__(self, busname, busphases, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.text = busname
        self.secondary_text = str(busphases)

    def mark(self, check, the_list_item):
        """mark the task as complete or incomplete"""
        if check.active:
            self.parent.parent.parent.add_bus(the_list_item)
        else:
            self.parent.parent.parent.remove_bus(the_list_item)

    @property
    def active(self):
        return self.ids.selected.active


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


class StorageControlModelTab(FloatLayout, MDTabsBase):
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


class StorageConfigurationScreen(SSimBaseScreen):
    """Configure a single energy storage device."""

    def __init__(self, der_screen, ess: StorageOptions, *args, **kwargs):
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

    def initialize_widgets(self):
        if self.options is None: return

        for power in self.options.power:
            self.ids.power_list.add_item(power)

        for duration in self.options.duration:
            self.ids.duration_list.add_item(duration)

        self.ids.device_name.text = self.options.name

        for bus_list_item in self.ids.bus_list.children:
            if bus_list_item.text in self.options.busses:
                bus_list_item.ids.selected.active = True

        self.ids.required.active = self.options.required

        Clock.schedule_once(lambda dt: self._refocus_field(self.ids.device_name), 0.05)

    def on_kv_post(self, base_widget):
        self.ids.bus_list.clear_widgets()
        for bus in self.project.bus_names:
            bus_list_item = BusListItem(bus, self.project.phases(bus))
            self.ids.bus_list.add_widget(bus_list_item)

    def _check_name(self, textfield):
        if not textfield.text_valid():
            textfield.helper_text = "invalid name"
            textfield.error = True
            return False
        existing_names = {name.lower() for name in self.project.storage_names}
        if textfield.text.lower() in existing_names:
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
            Clock.schedule_once(lambda dt: self._refocus_field(textfield), 0.05)
        else:
            textfield.set_error_message()

    def _refocus_field(self, field):
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

    def _add_device_duration(self, textfield):
        self._add_option(self.ids.duration_list, textfield)

    def _add_device_power(self, textfield):
        self._add_option(self.ids.power_list, textfield)

    @property
    def _ess_powers(self):
        return list(self.ids.power_list.options)

    @property
    def _ess_durations(self):
        return list(self.ids.duration_list.options)

    @property
    def _selected_busses(self):
        return list(
            bus_item.text
            for bus_item in self.ids.bus_list.children
            if bus_item.active
        )

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

        if self.show_error(self.options.validate_name()): return
        if self.show_error(self.options.validate_soc_values()): return
        if self.show_error(self.options.validate_power_values()):  return
        if self.show_error(self.options.validate_duration_values()): return
        if self.show_error(self.options.validate_busses()): return
        if self.show_error(self.options.validate_controls()): return

        # self._der_screen.add_ess(self.options)
        self.manager.current = "der-config"
        self.manager.remove_widget(self)

    def cancel(self):
        # if self._editing is not None:
        # Restore the original device
        #    self._der_screen.add_ess(self._editing)
        self.manager.current = "der-config"
        self.manager.remove_widget(self)

    def on_enter(self, *args):
        return super().on_enter(*args)


class XYGridView(RecycleView):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type("on_item_deleted")
        self.register_event_type("on_value_changed")

    def delete_item(self, index: int):
        self.data.pop(index)
        Clock.schedule_once(lambda dt: self.__raise_deleted_item(), 0.05)

    def x_value_changed(self, index: int, value):
        self.__on_value_changed(index, "x", value)

    def y_value_changed(self, index: int, value):
        self.__on_value_changed(index, "y", value)

    def __on_value_changed(self, index: int, key: str, value):
        self.data[index][key] = parse_float_or_str(value)
        Clock.schedule_once(lambda dt: self.__raise_value_changed(), 0.05)

    def __raise_value_changed(self):
        self.dispatch("on_value_changed")

    def on_value_changed(self):
        pass

    def on_item_deleted(self):
        pass

    def __raise_deleted_item(self):
        """Dispatches the on_item_deleted method to anything bound to it.
        """
        self.dispatch("on_item_deleted")

    def extract_data_lists(self, sorted: bool = True) -> (list, list):
        """Reads all values out of the "x" and "y" columns of this control and returns them as
            pair of lists that may be sorted if requested.

        Parameters
        ----------
        sorted : bool
            True if this method should try and c0-sort the extracted x and y lists before
            returning them and false otherwise.

        Returns
        -------
        tuple:
            A pair of lists containing the x and y values in this grid.  The lists will be
            co-sorted using the x list as an index if requested and they can be sorted.
        """
        xvs = self.extract_x_vals()
        yvs = self.extract_y_vals()
        if not sorted: return (xvs, yvs)
        return try_co_sort(xvs, yvs)

    def extract_x_vals(self) -> list:
        """Reads all values out of the "x" column of this control and returns them as a list.

        Returns
        -------
        list:
            A list containing all values in the "x" column of this control.  The values in
            the list will be of type float if they can be cast as such.  Otherwise, raw text
            representations will be put in the list in locations where the cast fails.
        """
        return [child.x_value for child in self.children[0].children]

    def extract_y_vals(self) -> list:
        """Reads all values out of the "y" column of this control and returns them as a list.

        Returns
        -------
        list:
            A list containing all values in the "y" column of this control.  The values in
            the list will be of type float if they can be cast as such.  Otherwise, raw text
            representations will be put in the list in locations where the cast fails.
        """
        return [child.y_value for child in self.children[0].children]


class XYGridViewItem(RecycleDataViewBehavior, BoxLayout):
    index: int = -1

    last_text: str = ""

    @property
    def x_value(self):
        """Returns the current contents of the x value field of this row.

        Returns
        -------
        float or str:
            If the current content of the x value field of this row can be cast to
            a float, then the float is returned.  Otherwise, the raw string contents
            of the field are returned.
        """
        return parse_float_or_str(self.ids.x_field.text)

    @property
    def y_value(self):
        """Returns the current contents of the y value field of this row.

        Returns
        -------
        float or str:
            If the current content of the y value field of this row can be cast to
            a float, then the float is returned.  Otherwise, the raw string contents
            of the field are returned.
        """
        return parse_float_or_str(self.ids.y_field.text)

    def refresh_view_attrs(self, rv, index, data):
        """A method of the RecycleView called automatically to refresh the content of the view.

        Parameters
        ----------
        rv : RecycleView
            The RecycleView that owns this row and wants it refreshed (not used in this function).
        index: int
            The index of this row.
        data: dict
            The dictionary of data that constitutes this row.  Should have keys for 'x' and 'y'.
        """
        self.index = index
        self.ids.x_field.text = str(data['x'])
        self.ids.y_field.text = str(data['y'])

    def on_delete_button(self):
        """A callback function for the button that deletes the data item represented by
        this row from the data list"""
        self.parent.parent.delete_item(self.index)

    def on_x_value_changed(self, instance, text):
        """A callback method used when the value in the x field of an XY grid changes.

        This method notifies the grandparent, which is an XYGridView, of the change.

        Parameters
        ----------
        instance
            The x text field whose value has changed.
        text
            The new x value as a string.
        """
        if self.parent:
            self.parent.parent.x_value_changed(self.index, self.x_value)

    def on_x_focus_changed(self, instance, value):
        """A callback method used when the focus on the x field of an XY grid changes.

        This method checks to see if this is a focus event or an unfocus event.
        If focus, it stores the current value in the field for comparison later.
        If unfocus and the value has not changed, nothing is done.  If the value has changed,
        then the self.on_x_value_changed method is invoked.

        Parameters
        ----------
        instance
            The x text field whose value has changed.
        value
            True if this is a focus event and false if it is unfocus.
        """
        if value:
            self.last_text = instance.text
        elif value != instance.text:
            self.on_x_value_changed(instance, instance.text)

    def on_y_value_changed(self, instance, text):
        """A callback method used when the value in the y field of an XY grid is validated.

        This method notifies the grandparent, which is an XYGridView, of the change.

        Parameters
        ----------
        instance
            The y text field whose value has changed.
        text
            The new y value as a string.
        """
        if self.parent:
            self.parent.parent.y_value_changed(self.index, self.y_value)

    def on_y_focus_changed(self, instance, value):
        """A callback method used when the focus on the y field of an XY grid changes.

        This method checks to see if this is a focus event or an unfocus event.
        If focus, it stores the current value in the field for comparison later.
        If unfocus and the value has not changed, nothing is done.  If the value has changed,
        then the self.on_y_value_changed method is invoked.

        Parameters
        ----------
        instance
            The y text field whose value has changed.
        value
            True if this is a focus event and false if it is unfocus.
        """
        if value:
            self.last_text = instance.text
        elif value != instance.text:
            self.on_y_value_changed(instance, instance.text)


class XYItemTextField(TextInput):
    """A class to serve as a text field used in an XY grid.

    This class can be either an x or a y value field and enforces the
    requirement that the contents be a floating point number by indicating
    if it is not.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.def_back_color = self.background_color
        self.bind(text=self.set_error_message)
        self.hint_text = "Enter a number."

    def set_error_message(self, instance, text):
        """A function to set this text field to an error state.

        This method checks to see if the contents of this text field are
        a floating point number and does nothing if so.  If not, then this
        sets the background color to "red".

        Parameters
        ----------
        instance:
            The text field that initiated this call.
        text:
            The current text content of the text field as of this call.
        """
        v = parse_float(text) is not None
        self.background_color = "red" if not v else self.def_back_color


class VoltVarTabContent(BoxLayout):
    """The class that stores the content for the Volt-Var tab in the storage
     option control tabs."""

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

    def rebuild_plot(self):
        """A function to reset the plot of the volt var data.

        This method extracts the volt var data out of the UI grid and then, if
        the data exists, plots it in the associated plot.
        """
        xs, ys = self.ids.grid.extract_data_lists()

        if len(xs) == 0:
            self.ids.plot_box.display_plot_error("No Data")

        else:
            _make_xy_matlab_plot(
                self.ids.plot_box, xs, ys, 'Voltage (p.u.)',
                'Reactive Power (p.u.)', 'Volt-Var Control Parameters'
                )


class VoltWattTabContent(BoxLayout):
    """The class that stores the content for the Volt-Watt tab in the storage
     option control tabs"""

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

    def rebuild_plot(self):
        """A function to reset the plot of the volt watt data.

        This method extracts the volt watt data out of the UI grid and then, if
        the data exists, plots it in the associated plot.
        """
        xs, ys = self.ids.grid.extract_data_lists()

        if len(xs) == 0:
            self.ids.plot_box.display_plot_error("No Data")

        else:
            _make_xy_matlab_plot(
                self.ids.plot_box, xs, ys, 'Voltage (p.u.)',
                'Watts (p.u.)', 'Volt-Watt Control Parameters'
            )


class VarWattTabContent(BoxLayout):
    """The class that stores the content for the Var-Watt tab in the storage
     option control tabs"""

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

    def rebuild_plot(self):
        """A function to reset the plot of the var watt data.

        This method extracts the var watt data out of the UI grid and then, if
        the data exists, plots it in the associated plot.
        """
        xs, ys = self.ids.grid.extract_data_lists()

        if len(xs) == 0:
            self.ids.plot_box.display_plot_error("No Data")

        else:
            _make_xy_matlab_plot(
                self.ids.plot_box, xs, ys, 'Reactive Power (p.u.)',
                'Watts (p.u.)', 'Var-Watt Control Parameters'
            )


class VoltVarVoltWattTabContent(BoxLayout):
    """The class that stores the content for the Volt-Var & Volt-Watt tab in the storage
     option control tabs"""

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


class StorageControlConfigurationScreen(SSimBaseScreen):
    """Configure the control strategy of a single energy storage device."""

    def __init__(self, der_screen, project, options, *args, **kwargs):
        super().__init__(project, *args, **kwargs)
        self._der_screen = der_screen
        self._options = options

        self.ids.min_soc.text = str(self._options.min_soc * 100.0)
        self.ids.max_soc.text = str(self._options.max_soc * 100.0)
        self.ids.init_soc.text = str(self._options.initial_soc * 100.0)

        Clock.schedule_once(lambda dt: self.__set_focus_clear_sel(self.ids.max_soc), 0.05)
        Clock.schedule_once(lambda dt: self.__set_focus_clear_sel(self.ids.min_soc), 0.05)
        Clock.schedule_once(lambda dt: self.__set_focus_clear_sel(self.ids.init_soc), 0.05)

        self.load_all_control_data()

        self._mode_dict = {
            "droop": "Droop", "voltvar": "Volt-Var", "voltwatt": "Volt-Watt",
            "varwatt": "Var-Watt", "vv_vw": "Volt-Var & Volt-Watt",
            "constantpf": "Constant Power Factor"
        }
        
        self._set_mode_dict = {
            "droop": self.set_droop_mode, "voltvar": self.set_volt_var_mode,
            "voltwatt": self.set_volt_watt_mode, "varwatt": self.set_var_watt_mode,
            "vv_vw": self.set_volt_var_and_volt_watt_mode,
            "constantpf": self.set_const_power_factor_mode
        }

        if self._options is not None:
            self.dispatch_set_mode(self._options.control.mode)

    def load_all_control_data(self):
        """Verifies the existence of all control mode parameters and then sets
        the contents of the controls used to display and modify them.

        This uses the individual "set...data" methods for each control mode. 
        See those methods for more details of each.
        """
        self.set_droop_data()
        self.set_volt_var_data()
        self.set_volt_watt_data()
        self.set_var_watt_data()
        self.set_volt_var_and_volt_watt_data()
        self.set_const_power_factor_data()

    @staticmethod
    def __set_focus_clear_sel(widget, value=True):
        """Sets the focus of the supplied widget to the supplied value and
        schedules a call to widget.cancel_selection().
        
        Parameters
        ----------
        widget:
            The widget whose focus is to be set to the supplied value and on
            whom selection is to be canceled.
        value:
            True if the widget is to receive focus and false otherwise.
        """
        widget.focus = value
        Clock.schedule_once(lambda dt: widget.cancel_selection(), 0.05)

    def set_mode_label_text(self):
        """ Adds the current device name to the label that informs a user to
        select a current control model.
        """
        txt = f"Select a control mode for this storage asset: [b]{self.device_name}[/b]"
        if self._options.control.mode:
            pName = self._mode_dict[self._options.control.mode]
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

    def on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        """A callback function used by the control mode tab to notify of tab
        changes

        This extracts and stores any data that was input on the previous tab
        and then ensures that the new tab is in the correct state.

        Parameters
        ----------
        instance_tabs:
            The tab control that issued this call.
        instance_tab:
            The newly selected tab in the calling tab control.
        instance_tab_label:
            The label object of the newly selected tab.
        tab_text:
            The text or name icon of the newly selected tab.
        """
        self.read_all_data()
        self.dispatch_set_mode(self.__find_inv_mode__(tab_text))
        self.set_mode_label_text()

    def __find_inv_mode__(self, txt: str) -> str:
        for k,v in self._mode_dict.items():
            if v == txt: return k
        return None

    def set_droop_mode(self):
        """Changes the current contorl mode for the current storage option to
        droop.

        This ensures control parameters for the droop mode, registers the
        fields for data extraction, and sets focus on the two fields to put
        them into editing mode.
        """
        self.set_mode("droop", self.ids.droop_tab)
        self.set_droop_data()

    def set_droop_data(self):
        """Verifies the existence of droop parameters and then sets the
        contents of the controls used to display and modify them.
        """
        pval, qval = self.verify_droop_params()
        pfield = self.ids.droop_tab_content.ids.p_value
        qfield = self.ids.droop_tab_content.ids.q_value

        pfield.text = str(pval)
        qfield.text = str(qval)

        Clock.schedule_once(lambda dt: self.__set_focus_clear_sel(pfield), 0.05)
        Clock.schedule_once(lambda dt: self.__set_focus_clear_sel(qfield), 0.05)

    def verify_droop_params(self) -> (float, float):
        """ Checks to see if there is a recorded set of droop parameters in the
        current control parameters list and installs them as default values if
        they are missing.

        Returns
        -------
        tuple:
            The result of verifying the P and Q droop parameters.
        """
        return (
            self.__verify_control_param("droop", "p_droop"),
            self.__verify_control_param("droop", "q_droop")
        )

    def set_volt_var_mode(self):
        """Changes the current contorl mode for the current storage option to
        volt-var.

        This ensures control parameters for the volt-var mode and loads the
        volt-var data into the xy grid.
        """
        self.set_mode("voltvar", self.ids.vv_tab)
        self.set_volt_var_data()

    def set_volt_var_data(self):
        """Verifies the existence of Volt-Var parameters and then sets the
        contents of the controls used to display and modify them.
        """
        vvs, var = self.verify_volt_var_params()
        self.__set_xy_grid_data(self.ids.vv_tab_content.ids.grid, vvs, var)
        self.ids.vv_tab_content.rebuild_plot()

    def verify_volt_var_params(self) -> (list, list):
        """ Checks to see if there is a recorded set of Volt-Var parameters in
        the current control parameters list and installs them as default values
        if they are missing.

        Default volts are [0.5, 0.95, 1.0, 1.05, 1.5] and default VARs are
        [1.0, 1.0, 0.0, -1.0, -1.0].

        Returns
        -------
        tuple:
            The result of verifying the volt and var lists in the control
            parameters. The first member of the tuple will be the volts list
            and the second is the list of var values.
        """
        return (
            self.__verify_control_param("voltvar", "volts"),
            self.__verify_control_param("voltvar", "vars")
        )

    def set_volt_watt_mode(self):
        """Changes the current contorl mode for the current storage option to
        volt-watt.

        This ensures control parameters for the volt-var mode and loads the
        volt-watt data into the xy grid.
        """
        self.set_mode("voltwatt", self.ids.vw_tab)
        self.set_volt_watt_data()

    def set_volt_watt_data(self):
        """Verifies the existence of Volt-Watt parameters and then sets the
        contents of the controls used to display and modify them.
        """
        vvs, wvs = self.verify_volt_watt_params()
        self.__set_xy_grid_data(self.ids.vw_tab_content.ids.grid, vvs, wvs)
        self.ids.vw_tab_content.rebuild_plot()

    def verify_volt_watt_params(self) -> (list, list):
        """ Checks to see if there is a recorded set of Volt-Watt parameters in
        the current control parameters list and installs them as default values
        if they are missing.

        Returns
        -------
        tuple:
            The result of verifying the volt and watt lists in the control
            parameters. The first member of the tuple will be the volts list
            and the second is the list of watt values.
        """
        return (
            self.__verify_control_param("voltwatt", "volts"),
            self.__verify_control_param("voltwatt", "watts")
        )

    def set_var_watt_mode(self):
        """Changes the current contorl mode for the current storage option to
        var-watt.

        This ensures control parameters for the volt-var mode and loads the
        var-watt data into the xy grid.
        """
        self.set_mode("varwatt", self.ids.var_watt_tab)
        self.set_var_watt_data()

    def set_var_watt_data(self):
        """Verifies the existence of Var-Watt parameters and then sets the
        contents of the controls used to display and modify them.
        """
        vvs, wvs = self.verify_var_watt_params()
        self.__set_xy_grid_data(self.ids.var_watt_tab_content.ids.grid, vvs, wvs)
        self.ids.var_watt_tab_content.rebuild_plot()

    def verify_var_watt_params(self) -> (list, list):
        """ Checks to see if there is a recorded set of Var-Watt parameters in
        the current control parameters list and installs them as default values
        if they are missing.

        Returns
        -------
        tuple:
            The result of verifying the VAR and Watt lists in the control
            parameters. The first member of the tuple will be the VARs list
            and the second is the list of Watt values.
        """
        return (
            self.__verify_control_param("varwatt", "vars"),
            self.__verify_control_param("varwatt", "watts")
        )

    def set_volt_var_and_volt_watt_mode(self):
        """Changes the current contorl mode for the current storage option to
        volt-var & var-watt.

        This ensures control parameters for the volt-var mode and loads the
        volt-var & var-watt data into the xy grid.
        """
        self.set_mode("vv_vw", self.ids.vv_vw_tab)
        self.set_volt_var_and_volt_watt_data()

    def set_volt_var_and_volt_watt_data(self):
        """Verifies the existence of Volt-Var & Volt-Watt parameters and then
        sets the contents of the controls used to display and modify them.
        """
        vvvs, vars, vwvs, watts = self.verify_volt_var_and_volt_watt_params()
        self.__set_xy_grid_data(self.ids.vv_vw_tab_content.ids.vv_grid, vvvs, vars)
        self.__set_xy_grid_data(self.ids.vv_vw_tab_content.ids.vw_grid, vwvs, watts)
        self.ids.vv_vw_tab_content.rebuild_plot()

    def verify_volt_var_and_volt_watt_params(self) -> (list, list, list, list):
        """ Checks to see if there is a recorded set of Volt-Var and Volt_Watt
        parameters in the current control parameters list and installs them as
        default values if they are missing.

        Returns
        -------
        tuple:
            The result of verifying the Volt-Var and Volt-Watt lists in the
            control parameters. The first member of the tuple will be the
            Volt-Var Volts.  The second is the list of Volt-Var Var values. 
            The third is the list of Volt-Watt Volt values and finally, the
            fourth is the list of Watt Values of the Volt-Watt mode.
        """
        return (
            self.__verify_control_param("vv_vw", "vv_volts"),
            self.__verify_control_param("vv_vw", "vv_vars"),
            self.__verify_control_param("vv_vw", "vw_volts"),
            self.__verify_control_param("vv_vw", "vw_watts")
        )

    def set_const_power_factor_mode(self):
        """Changes the current contorl mode for the current storage option to
        const PF.

        This ensures control parameters for the const PF mode, registers the
        fields for data extraction, and sets focus on the two fields to put
        them into editing mode.
        """
        self.set_mode("constantpf", self.ids.const_pf_tab)
        self.set_const_power_factor_data()

    def set_const_power_factor_data(self):
        """Verifies the existence of the Constant Power Factor parameters and
        then sets the contents of the controls used to display and modify them.
        """
        cpf = self.verify_const_pf_params()
        pffield = self.ids.const_pf_tab_content.ids.pf_value
        pffield.text = str(cpf)
        Clock.schedule_once(lambda dt: self.__set_focus_clear_sel(pffield), 0.05)

    def verify_const_pf_params(self) -> float:
        """ Checks to see if there is a recorded constant power factor
        parameter in the current control parameters list and installs it as the
        default value if it is missing.

        Returns
        -------
        float:
            The result of verifying the constant PF value parameter.
        """
        return self.__verify_control_param("constantpf", "pf_val")

    def __verify_control_param(self, mode: str, label: str):
        """Verifies that there is a data value in the control parameters for
        the current storage element and puts the default value in if not.

        Parameters
        ----------
        mode : str
            The control mode for which to store the default value for label
        label : str
            The key to check for in the current storage control parameters.

        Return
        ------
        parameters:
            The current parameters of the supplied mode.  The data type will
            depend on which control mode is supplied.
        """
        defaults = StorageControl.default_params(mode)

        if mode not in self._options.control.params:
            self._options.control.params[mode] = {}

        if label not in self._options.control.params[mode]:
            self._options.control.params[mode][label] = defaults[label]

        return self._options.control.params[mode][label]

    def __set_xy_grid_data(self, grid: XYGridView, xdat: list, ydat: list) -> list:
        """Converts the supplied lists into a dictionary appropriately keyed to
        be assigned as the data for the supplied grid and assignes it.

        This performs a try-co-sort of the lists prior to assignment to the
        grid data.

        Parameters
        ----------
        grid : XYGridView
            The grid to assign data to.
        xdat : list
            The list of x values to assign to the x column of the grid.
        ydat : list
            The list of y values to assign to the y column of the grid.

        Return
        ------
        list:
            The list of dictionaries that was craeted from the xdat and ydat.
            See the make_xy_grid_data function documentation for more details
            on the format of the returned list.
        """
        xs, ys = try_co_sort(xdat, ydat)
        grid.data = make_xy_grid_data(xs, ys)
        return grid.data

    def dispatch_set_mode(self, mode):
        if mode in self._set_mode_dict:
            self._set_mode_dict[mode]()
        else:
            self.set_droop_mode()

    def set_mode(self, name: str, tab) -> bool:
        """Changes the current contorl mode for the current storage option to
        the supplied one and sets the current tab.

        If the current control mode is the supplied one, then the only thing
        this does is set the supplied tab if it is not correct.

        Parameters
        ----------
        name : str
            The name of the control mode to make current.
        tab
            The tab page to make visible.

        Returns
        -------
        bool:
            True if this method goes so far as to actually change the mode
            and False if the the mode is already the requested one. 
            Regardless, this method will set the current tab if needed.
        """
        if self.ids.control_tabs.get_current_tab() is not tab:
            self.ids.control_tabs.switch_tab(tab.tab_label_text)

        if self._options.control.mode == name: return False
        self._options.control.mode = name
        # self._options.control.params.clear()
        return True

    def save(self):
        self.cancel()

    def read_all_data(self):
        """Reads all entered data out of the controls for all control modes.

        This uses the individual "read...data" methods for each mode.  See them
        for more information about each.
        """
        self._options.min_soc = self.ids.min_soc.fraction()
        self._options.max_soc = self.ids.max_soc.fraction()
        self._options.initial_soc = self.ids.init_soc.fraction()
        self.read_droop_data()
        self.read_const_pf_data()
        self.read_voltvar_data()
        self.read_voltwatt_data()
        self.read_varwatt_data()
        self.read_voltvar_and_voltwatt_data()

    def read_droop_data(self):
        """Reads and stores the entered data out of the controls for droop mode.

        The data is stored in the options control parameters.
        """
        droop_map = self._options.control.params["droop"]
        droop_map["p_droop"] = parse_float(self.ids.droop_tab_content.ids.p_value.text)
        droop_map["q_droop"] = parse_float(self.ids.droop_tab_content.ids.q_value.text)

    def read_const_pf_data(self):
        """Reads and stores the entered data out of the controls for constant
        power factor mode.

        The data is stored in the options control parameters.
        """
        constpf_map = self._options.control.params["constantpf"]
        constpf_map["pf_val"] = parse_float(self.ids.const_pf_tab_content.ids.pf_value.text)

    def read_voltvar_data(self):
        """Reads and stores the entered data out of the controls for Volt-Var
        mode.

        The data is stored in the options control parameters.
        """
        self._extract_and_store_data_lists(
            self.ids.vv_tab_content.ids.grid, "voltvar", "volts", "vars"
        )

    def read_voltwatt_data(self):
        """Reads and stores the entered data out of the controls for Volt-Watt
        mode.

        The data is stored in the options control parameters.
        """
        self._extract_and_store_data_lists(
            self.ids.vw_tab_content.ids.grid, "voltwatt", "volts", "watts"
        )

    def read_varwatt_data(self):
        """Reads and stores the entered data out of the controls for Var-Watt
        mode.

        The data is stored in the options control parameters.
        """
        self._extract_and_store_data_lists(
            self.ids.var_watt_tab_content.ids.grid, "varwatt", "vars", "watts"
        )

    def read_voltvar_and_voltwatt_data(self):
        """Reads and stores the entered data out of the controls for Volt-Var &
        Volt-Watt mode.

        The data is stored in the options control parameters.
        """
        self._extract_and_store_data_lists(
            self.ids.vv_vw_tab_content.ids.vv_grid,
           "vv_vw", "vv_volts", "vv_vars"
        )

        self._extract_and_store_data_lists(
            self.ids.vv_vw_tab_content.ids.vw_grid,
           "vv_vw", "vw_volts", "vw_watts"
        )

    def cancel(self):
        """Returns to the "configure-storage" form.

        This does not do anything with data.  It does not save any input data
        nor does it roll back any previously saved data.

        This is called when the user presses the "back" button.
        """
        self.read_all_data()
        self.manager.current = "configure-storage"
        self.manager.remove_widget(self)

    def _extract_and_store_data_lists(self, xyc: XYGridView, mode: str, l1name: str, l2name: str):
        """Reads the x and y data from the supplied grid and stores them in the
        control parameters using the supplied list keys.

        Parameters
        ----------
        l1name : str
            The key by which to store the "x" values read out of the grid into
            the control parameters
        l2name : str
            The key by which to store the "y" values read out of the grid into
            the control parameters
        """
        xl, yl = xyc.extract_data_lists()
        param_map = self._options.control.params[mode]
        param_map[l1name] = xl
        param_map[l2name] = yl


class PVConfigurationScreen(SSimBaseScreen):
    """Configure a single PV system."""

    def __init__(self, *args, **kwargs):
        self.pvsystem = None
        super().__init__(*args, **kwargs)

    def save(self):
        # TODO add the new storage device to the project
        self.manager.current = "der-config"

    def cancel(self):
        self.manager.current = "der-config"


class DERConfigurationScreen(SSimBaseScreen):
    """Configure energy storage devices and PV generators."""

    def __init__(self, *args, **kwargs):
        # comes first so the manager is initialized
        super().__init__(*args, **kwargs)
        self.ids.delete_storage.bind(
            on_release=self.delete_ess
        )

    def load_project_data(self):
        self.ids.ess_list.clear_widgets()
        for so in self.project.storage_devices:
            self.ids.ess_list.add_widget(
                StorageListItem(so, self)
            )

        for pv in self.project.pvsystems:
            self.ids.pv_list.add_widget(
                PVListItem(pv)
            )

    def new_storage(self):
        ess = StorageOptions("NewBESS", 3, [], [], [])

        self.add_ess(ess)

        self.manager.add_widget(
            StorageConfigurationScreen(
                self, ess, name="configure-storage")
        )

        self.manager.current = "configure-storage"

    def add_ess(self, ess):
        self.project.add_storage_option(ess)
        self.ids.ess_list.add_widget(
            StorageListItem(ess, self)
        )

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
        # self.project.remove_storage_option(ess)
        # self.ids.ess_list.remove_widget(ess_list_item)
        self.manager.add_widget(
            StorageConfigurationScreen(self, ess, name="configure-storage"))
        self.manager.current = "configure-storage"


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
        self.secondary_text = str(pv.bus)
        self._der_screen = der_screen


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


class NoFigurePopupContent(BoxLayout):
    pass


class MissingMetricValuesPopupContent(BoxLayout):
    pass


class MessagePopupContent(BoxLayout):
    pass


class BusListItemWithCheckbox(OneLineAvatarIconListItem):
    '''Custom list item.'''
    icon = StringProperty("android")

    def __int__(self, bus):
        self.text = bus
        self.bus = bus


class MetricListItem(TwoLineAvatarIconListItem):
    pass


class RightCheckbox(IRightBodyTouch, MDCheckbox):
    pass


class LeftCheckbox(ILeftBodyTouch, MDCheckbox):
    pass


class MetricConfigurationScreen(SSimBaseScreen):
    _selBusses = []
    _currentMetricCategory = "None"
    _metricIcons = {"Bus Voltage": "lightning-bolt-circle", "Unassigned": "chart-line"}

    _def_btn_color = '#005376'

    def on_kv_post(self, base_widget):
        """Implemented to manage the states of the upper limit, lower limit,
        and objective fields.

        This schedules calls to "_refocus_field" on each text box.  See that
        method for details.

        Parameters
        ----------
        base_widget:
           The base-most widget whose instantiation triggered the kv rules.
        """
        Clock.schedule_once(lambda dt: self._refocus_field(self.ids.upperLimitText), 0.05)
        Clock.schedule_once(lambda dt: self._refocus_field(self.ids.lowerLimitText), 0.05)
        Clock.schedule_once(lambda dt: self._refocus_field(self.ids.objectiveText), 0.05)

    def _refocus_field(self, field):
        """Sets the focus of the supplied field.

        For some field types, this has the effect of putting it into an
        editable state which can change its appearance even if it is
        subsequently un-focused.
        """
        field.focus = True

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
            Clock.schedule_once(lambda dt: self._refocus_field(self.ids.lowerLimitText), 0.05)

        if common_upper_limit is None:
            self.ids.upperLimitText.set_varied_mode() if is_varied else \
                self.ids.upperLimitText.set_not_set_mode()
        else:
            self.ids.upperLimitText.text = str(common_upper_limit)
            Clock.schedule_once(lambda dt: self._refocus_field(self.ids.upperLimitText), 0.05)

        if common_obj is None:
            self.ids.objectiveText.set_varied_mode() if is_varied else \
                self.ids.objectiveText.set_not_set_mode()
        else:
            self.ids.objectiveText.text = str(common_obj)
            Clock.schedule_once(lambda dt: self._refocus_field(self.ids.objectiveText), 0.05)

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

        err = Metric.validate_metric_values(lower_limit, upper_limit, obj, sense, False)

        if err:
            self.__show_invalid_metric_value_popup(err)
            return

        for bus in self._selBusses:
            accum = MetricTimeAccumulator(Metric(lower_limit, upper_limit, obj, sense))
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
        numCldrn = len(self.ids.interlist.children) == 0
        self.ids.btnSelectAll.disabled = numCldrn
        self.ids.btnDeselectAll.disabled = numCldrn

    def deselect_all_metric_objects(self):
        """Deselects all the items in the middle list on this form by setting
        the check box active values to False.
        """
        for wid in self.ids.interlist.children:
            if isinstance(wid, BusListItemWithCheckbox):
                wid.ids.check.active = False

    def select_all_metric_objects(self):
        """Selects all the items in the middle list on this form.

        This clears the currently selected busses and then appends each
        back into the list of selected busses as the checks are set.
        """
        self._selBusses.clear()
        for wid in self.ids.interlist.children:
            if isinstance(wid, BusListItemWithCheckbox):
                wid.ids.check.active = True
                self._selBusses.append(wid.text)

    def reload_metric_list(self):
        """Reloads the list of all defined metrics.

        This method creates a list item for all metrics previously defined for
        the current category.
        """
        self.ids.metriclist.clear_widgets()
        self.reset_metric_list_label()
        manager = self.project.get_manager(self._currentMetricCategory)

        if manager is None: return

        list = self.ids.metriclist
        list.active = False
        for key, m in manager.all_metrics.items():
            txt = self._currentMetricCategory + " Metric for " + key
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

    def on_item_check_changed(self, ckb, value):
        """A callback function for the list items to use when their check state
        changes.

        This method looks at teh current check state (value) and either adds
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
        bus = ckb.listItem.text
        if value:
            self._selBusses.append(bus)
        else:
            self._selBusses.remove(bus)

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
        self.ids.interlist.clear_widgets()
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

    def load_busses_into_list(self):
        """Purposes the middle list in the form for busses and loads it with
        newly created BusListItemWithCheckbox instances for each bus in the
        grid model.

        This method clears any current selected busses, clears any contents of
        the center list, and then reloads the list.  If there is no currently
        selected grid model, then __show_no_grid_model_popup is called and the
        method is aborted.
        """
        self._selBusses.clear()
        list = self.ids.interlist
        list.clear_widgets()
        list.text = "Busses"

        if self.project._grid_model is None:
            self.__show_no_grid_model_popup()
            return

        busses = self.project._grid_model.bus_names
        list.active = False
        for x in busses:
            bItem = BusListItemWithCheckbox(text=str(x))
            bItem.ids.check.bind(active=self.on_item_check_changed)
            list.add_widget(bItem)

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
        self.configurations: List[Configuration] = []
        self.storage_options: List[StorageOptions] = []
        self._run_thread = None
        self._canceled = False

    def on_enter(self):
        # populate configurations list
        self.populate_configurations()
        # update the configurations that are currently selected for 
        # evaluation
        self._update_configurations_to_eval()
        # enable/disable selection buttons
        self.manage_selection_buttons_enabled_state()
        # enable/disable run button
        self.manage_run_button_enabled_state()

    def populate_configurations(self):
        """Populates the configurations list. Also creates mappings between
           internal configurations IDs and once that are displayed in the UI.
        """
        configs = []
        self.ids.config_list.clear_widgets()
        self.ids.config_list.active = False
        for i, config in enumerate(self.project.configurations()):
            configs.append(config)
            # establish the mappings between config id and config UI_ids
            self.config_id_to_name[config.id] = f'Configuration {i+1}'
            # populate the UI with the configuration
            self._add_config_to_ui(config)

        self.configurations = configs

    def _add_config_to_ui(self, config):
        """Populates the UI with details on the Configuration `config`.

        Parameter
        ---------
        config: Configuration
            The configuration to be added to the UI.
        """
        secondary_detail_text = []
        tertiary_detail_text = []
        final_secondary_text = []
        final_tertiary_text = []

        for storage in config.storage:
            if storage is not None:
                secondary_detail_text.append(f"name: {storage.name}, bus: {storage.bus}")
                tertiary_detail_text.append(f"kw: {storage.kw_rated}, kwh: {storage.kwh_rated}")
            else:
                secondary_detail_text.append('no storage')
        final_secondary_text = "\n".join(secondary_detail_text)
        final_tertiary_text = "\n".join(tertiary_detail_text)

        config_item = ListItemWithCheckbox(text=self.config_id_to_name[config.id], 
                                           sec_text=final_secondary_text, 
                                           tert_text=final_tertiary_text)
        config_item.ids.selected.bind(active=self.on_item_check_changed)
        config_item.ids.delete_config.bind(on_release=self.on_delete_config)
        self.ids.config_list.add_widget(config_item)

        # update the items that are currently selected
        if config.id in self.selected_configurations.keys():
            config_item.ids.selected.active = True
        else:
            config_item.ids.selected.active = False

    def _update_configurations_to_eval(self):
        """Updates the list (`self.configurations_to_eval`) that keeps 
        track of current selection in the UI for configurations to 
        be evaluated.
        """
        no_of_configurations = len(self.configurations)
        ctr = no_of_configurations - 1
        self.configurations_to_eval = []
        for wid in self.ids.config_list.children:
            if wid.selected:
                self.configurations_to_eval.append(self.configurations[ctr])
            ctr = ctr - 1
        # run all the configurations
        Logger.debug("===================================")
        Logger.debug('Selected Configurations:')
        Logger.debug(self.selected_configurations)
        Logger.debug("===================================")

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
    
    def on_item_check_changed(self, ckb, value):
        """A callback function for the config list items to use when their
        check state changes.

        This method looks at the current check state (value) and either 
        adds configuration UI id into the dict of currently selected 
        configurations (`self.selected_configurations`) if value is true 
        and removes it if value is false.

        Parameters
        ----------
        ckb:
            The check box whose check state has changed.
        value:
            The current check state of the check box 
            (true = checked, false = unchecked).
        """
        config_key = self._get_config_key(self.config_id_to_name,
                                          ckb.listItem.text)

        if value:
            self.selected_configurations[config_key] = ckb.listItem.text
        else:
            del self.selected_configurations[config_key]

        # update the configurations that are currently selected for 
        # evaluation
        self._update_configurations_to_eval()
        # enable/disable run button
        self.manage_run_button_enabled_state()

    def on_delete_config(self, value):
        Logger.debug("???????")
        Logger.debug(value)
        Logger.debug("Delete pressed")

    def manage_run_button_enabled_state(self):
        numCldrn = len(self.configurations_to_eval) == 0
        self.ids.run_configuration_btn.disabled = numCldrn

    def manage_selection_buttons_enabled_state(self):
        """Enables or disables the buttons for select all and deselect all 
        based on whether or not there are any entries in the configuration 
        list.

        If there are items in the list, the buttons are enabled.  
        If there are no items in the list, the buttons are disabled.
        """
        numCldrn = len(self.ids.config_list.children) == 0
        self.ids.btnSelectAll.disabled = numCldrn
        self.ids.btnDeselectAll.disabled = numCldrn

    def deselect_all_configurations(self):
        """Deselects all the items in the configuration list."""
        for wid in self.ids.config_list.children:
            if isinstance(wid, ListItemWithCheckbox):
                wid.ids.selected.active = False
        # update the configurations to be evaluated list
        self._update_configurations_to_eval()

    def select_all_configurations(self):
        """Selects all the items in configuration list.
        """
        self.configurations_to_eval.clear()
        for wid in self.ids.config_list.children:
            if isinstance(wid, ListItemWithCheckbox):
                wid.ids.selected.active = True
        # update the configurations that are currently selected for 
        # evaluation
        self._update_configurations_to_eval()
        
    def _evaluate(self):
        """Initiates evaluation of configurations that are currelty selected.
        """
        # step 1: get an update on the current selection
        self._update_configurations_to_eval()

        # step 2: evaluate the selected configurations
        for config in self.configurations_to_eval:
            if self._canceled:
                Logger.debug("evaluation canceled")
                break
            Logger.debug("Currently Running configuration:")
            Logger.debug(self.config_id_to_name[config.id])
            Logger.debug("==========================================")
            config.evaluate(basepath=self.project.base_dir)
            config.wait()
            self._progress_popup.content.increment()
        Logger.debug("clearing progress popup")
        self._canceled = False
        self._progress_popup.dismiss()

    def run_configurations(self):
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
        self.project_results = ProjectResults(self.project)
        # keeps track of metrics that have been selected for plotting
        self.selected_metric_items = {}
        # stores the current configuration selected from the dropdown menu
        self.current_configuration = None
        self.metrics_figure = None

    def on_enter(self):
        # TO DO: Replace with evaluated configurations
        ctr = 1
        for config in self.project.configurations():
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
        metrics_fig = plt.figure()
        plt.clf()
        ctr = 1
        for result in self.project_results.results():
            config_dir = os.path.basename(os.path.normpath(result.config_dir))

            # obtain accumulated metric values and times-series 
            # data in a pandas dataframe for metrics
            _, accumulated_metric, data_metrics = result.metrics_log()
            config_key = self.config_id_to_name[config_dir]

            # columns to plot
            columns_to_plot = self.selected_metric_items[config_key]

            # select the susbset of data based on 'columns_to_plot'
            selected_data = data_metrics[columns_to_plot]
            x_data = data_metrics.loc[:, 'time']

            # add the selected columns to the plot
            for column in selected_data.keys():
                plt.plot(x_data, selected_data[column], 
                         label=config_key + '-' + column + ' :' + str(accumulated_metric))

            ctr += 1
        
        # x-axis label will always be time and seconds by default
        plt.xlabel('time [s]')
        # update y-axis label based on user input
        if self.ids.detail_figure_ylabel.text is not None:
            plt.ylabel(self.ids.detail_figure_ylabel.text)
        plt.legend()
        # update the title based on user input
        if self.ids.detail_figure_title.text is not None:
            plt.title(self.ids.detail_figure_title.text)
        else:
            plt.title('Metrics Plots')

        return metrics_fig

    def update_metrics_figure(self):
        """ Places the metrics figure in the UI canvas.
        """
        # check if atleast one variable is selected for plotting
        if self._check_metrics_list_selection():
            self._show_error_popup('No Metrics(s) Selected!', 
                                   'Please select metrics(s) from the \
                                    dropdown menu to update the plot.')
        else:
            self.metrics_figure = self._create_metrics_figure()
            # Add kivy widget to the canvas
            self.ids.summary_canvas.clear_widgets()
            self.ids.summary_canvas.add_widget(
                FigureCanvasKivyAgg(self.metrics_figure)
            )

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
           visualiation screen.
        
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

            for i, config in enumerate(self.project.configurations()):
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
        self.current_configuration = value_ui_id
        
        # read the current selected configuration
        self.ids.config_list_detail_metrics.text = value_ui_id

        # put the 'Result' objects in a dict with configuration ids
        # this will allows the results to be mapped with 
        # corresponding configurations
        simulation_results = {}
        for result in self.project_results.results():
            # configuraiton directory of the result
            config_dir = os.path.basename(os.path.normpath(result.config_dir))
            simulation_results[config_dir] = result

        # extract the `current_result` based on selection from drop down menu
        current_result = simulation_results[value_id]

        # extract the data
        metrics_headers, metrics_accumulated, metrics_data = current_result.metrics_log()
        
        # add the list of metrics in the selected configuration into the MDList
        # clear the variable list
        self.ids.metrics_list.clear_widgets()
    
        for item in metrics_headers:
            # do not add 'time' to the variable list
            if item == 'time':
                continue
            else:
                metrics_item = ResultsMetricsListItemWithCheckbox(variable_name=str(item))
                metrics_item.ids.metrics_selected.bind(active=self.on_item_check_changed)
                self.ids.metrics_list.add_widget(metrics_item)

                # Check if the variable in already selected.
                if item in self.selected_metric_items[self.current_configuration]:
                    metrics_item.ids.metrics_selected.active = True
                else:
                    metrics_item.ids.metrics_selected.active = False     

        # close the drop-down menu
        self.menu.dismiss()

    def on_item_check_changed(self, ckb, value):
        """A callback function for the list items to use when their check 
        state changes.

        This method looks at the current check state (value) and either adds 
        the currently selected variable into `self.selected_metric_items` 
        if value is true and removes it if value is false.

        Parameters
        ----------
        ckb:
            The check box whose check state has changed.
        value:
            The current check state of the check box (true = checked, false = unchecked).
        """
        if value:
            if str(ckb.listItem.text) not in self.selected_metric_items[str(self.current_configuration)]:
                self.selected_metric_items[str(self.current_configuration)].append(str(ckb.listItem.text))
        else:
            self.selected_metric_items[str(self.current_configuration)].remove(str(ckb.listItem.text))
        
    def open_results_detail(self):
        self.manager.current = "results-detail"


class ResultsDetailScreen(SSimBaseScreen):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_configuration = None
        self.list_items = []
        self.selected_list_items = {}
        self.variable_data = pd.DataFrame()
        self.figure = None

    def on_enter(self):
        # TO DO: Replace with evaluated configurations
        ctr = 1
        for config in self.project.configurations():
            self.config_id_to_name[config.id] = 'Configuration ' + str(ctr)
            self.selected_list_items['Configuration ' + str(ctr)] = []
            ctr += 1

    def dismiss_popup(self):
        self._popup.dismiss()

    def _create_figure(self):
        """Creates instance of matplotlib figure based on selections 
        made in the UI.
        
        Returns
        ----------
        matplotlib.Figure:
            Instance of matplotlib figure.
        """
        fig = plt.figure()
        plt.clf()
        project_results = self.project_results.results()
        ctr = 1
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

            # combine all data into a single dataframe
            data = pd.concat(
                [data_storage_state, data_storage_voltage, all_bus_voltage],
                axis=1
            )
            config_dir = os.path.basename(os.path.normpath(result.config_dir))
            config_key = self.config_id_to_name[config_dir]
            
            # columns to plot
            columns_to_plot = self.selected_list_items[config_key]

            # select subset of data based on columns_to_plot
            selected_data = data[columns_to_plot]
            x_data = data.loc[:, 'time']
            
            # add the selected columns to plot
            for column in selected_data.keys():
                plt.plot(x_data, selected_data[column], label=config_key + '-' + column)
            ctr += 1

        plt.xlabel('time')

        # update the y-axis labels
        if self.ids.detail_figure_ylabel.text is not None:
            plt.ylabel(self.ids.detail_figure_ylabel.text)
        plt.legend()
        if self.ids.detail_figure_title is not None:
            plt.title(self.ids.detail_figure_title.text)
        else:
            plt.title('Detail Plots')

        return fig

    def update_figure(self):
        """ Places the details figure in the UI canvas.
        """
        # check if atleast one variable is selected for plotting
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
        visualiation screen.
        
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
        for _, config_variables in self.selected_list_items.items():
            if config_variables != []:
                # at least one variable is selected, not empty
                return False
        return True

    def clear_figure(self):
        """ Clears the detail figure from the UI canvas.
        """
        self.ids.detail_plot_canvas.clear_widgets()

    # def drop_config_menu(self):
    #     """Displays the dropdown menu in the visualization screen.
    #     """
    #     menu_items = []
    #     for config_id, config_ui_id in self.config_id_to_name.items():
    #         display_text = config_ui_id
    #         menu_items.append({
    #             "viewclass": "OneLineListItem",
    #             "text": display_text,
    #             "on_release": lambda x=config_id, y=config_ui_id : self.set_config(x, y)
    #         })

    #     self.menu = MDDropdownMenu(
    #         caller=self.ids.config_list_detail, items=menu_items, width_mult=5
    #     )
    #     self.menu.open()

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

            for i, config in enumerate(self.project.configurations()):
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
        filename : str
            ID displayed in the UI of the selected configuration.
        """
        self.current_configuration = value_ui_id
               
        # read the current selected configuration
        self.ids.config_list_detail.text = value_ui_id
        
        # put the 'Result' objects in a dict with configuration ids
        # this will allows the results to be mapped with 
        # corresponding configurations
        simulation_results = {}
        for result in self.project_results.results():
            # configuraiton directory of the result
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

            self.list_items = (
                storage_state_headers
                + storage_voltage_headers
                + bus_voltage_headers
            )
            self.variable_data = pd.concat(
                [storage_state_data, storage_voltage_data, bus_voltage_data],
                axis=1
            )

            self.x_data = list(self.variable_data.loc[:, 'time'])

            self.ids.variable_list_detail.clear_widgets()
            # add the list of variables in the selected configuration
            # into the MDList

            for item in self.list_items:
                # do not add 'time' to the variable list
                if item == 'time':
                    continue
                else:
                    list_item = ResultsVariableListItemWithCheckbox(variable_name=str(item))
                    list_item.ids.selected.bind(active=self.on_item_check_changed)
                    self.ids.variable_list_detail.add_widget(list_item)
                
                    if item in self.selected_list_items[self.current_configuration]:
                        list_item.ids.selected.active = True
                    else:
                        list_item.ids.selected.active = False

            # close the drop-down menu
            self.menu.dismiss()

        else:

            Logger.debug('This configuration has not been evaluated')

    def on_item_check_changed(self, ckb, value):
        """A callback function for the list items to use when their check 
        state changes.

        This method looks at the current check state (value) and either adds 
        the currently selected variable into `self.selected_list_items` 
        if value is true and removes it if value is false.

        Parameters
        ----------
        ckb:
            The check box whose check state has changed.
        value:
            The current check state of the check box (true = checked, false = unchecked).
        """
        if value:
            if str(ckb.listItem.text) not in self.selected_list_items[str(self.current_configuration)]:
                self.selected_list_items[str(self.current_configuration)].append(str(ckb.listItem.text))
        else:
            self.selected_list_items[str(self.current_configuration)].remove(str(ckb.listItem.text))


class ListItemWithCheckbox(TwoLineAvatarIconListItem):

    def __init__(self, text, sec_text, tert_text, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = text
        self.secondary_text = sec_text
        self.tertiary_text = tert_text

    def delete_item(self, the_list_item):
        print("Delete icon was button was pressed")
        print(the_list_item)
        self.parent.remove_widget(the_list_item)
        
    @property
    def selected(self):
        return self.ids.selected.active


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
    
    def on_kv_post(self, base_widget):
        self.refresh_grid_plot()

    def report(self, message):
        Logger.debug("button pressed: %s", message)

    def dismiss_popup(self):
        self._popup.dismiss()

    def load_grid(self, path, filename):
        Logger.debug("loading file %s", filename[0])
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

        self._popup = Popup(title="select SSIM TOML file", content=chooser)
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
        
    def getImage(self, path):
        return OffsetImage(plt.imread(path, format="png"), zoom=.1)
    
    def __make_pv_patch(
        self, x, y, w, h, c, ax, xoffset = 0., yoffset = 5., facecolor = None
        ):
        
        xpix, ypix = ax.transData.transform((x, y)).T

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
            [llx +   spacing, lly + panellow], [llx+ tiltoffset +   spacing, lly+h],
            [llx + 2*spacing, lly + panellow], [llx+ tiltoffset + 2*spacing, lly+h],
            [llx + 3*spacing, lly + panellow], [llx+ tiltoffset + 3*spacing, lly+h],
            [llx + 4*spacing, lly + panellow], [llx+ tiltoffset + 4*spacing, lly+h],
            [llx + tiltoffset/2., lly + panellow + halfpanhght],
            [llx + w - tiltoffset/2., lly + panellow + halfpanhght]
            ]

        if facecolor is None:
            facecolor = ax.get_facecolor()

        #transform the patch vertices back to data coordinates.
        inv = ax.transData.inverted()
        tverts = inv.transform(vertices)

        ax.add_patch(
            patches.PathPatch(Path(tverts, codes), facecolor=facecolor,
            edgecolor=c)
            )
        
    def __make_battery_patch(
        self, x, y, w, h, c, ax, xoffset = 0., yoffset = 5.,
        facecolor = None, incl_plus_minus = True
        ):
        
        xpix, ypix = ax.transData.transform((x, y)).T

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

        if facecolor is None:
            facecolor = ax.get_facecolor()

        #transform the patch vertices back to data coordinates.
        inv = ax.transData.inverted()
        tverts = inv.transform(vertices)

        ax.add_patch(
            patches.PathPatch(Path(tverts, codes), facecolor=facecolor,
            edgecolor=c)
            )
        
    def __draw_storage_options(self, ax):
                
        gm = self.project.grid_model
        
        # make a mapping of all busses to receive batteries to the storage
        # options that include them.  Also map colors to storage options.

        # Without getting the limits here, things don't draw right.  IDK why.
        ylim = ax.get_ylim()

        w = 12
        h = 6 
        o = 2
        yo = 4

        so_colors = {}
        bat_busses = {}
        self.cindex = 0
                
        seg_busses = self.__get_line_segment_busses(gm)
        
        for so in self.project.storage_options:
            so_colors[so] = self.colors[self.cindex]
            self.cindex = (self.cindex + 1) % len(self.colors)
            for b in so.busses:
                if b not in seg_busses: continue
                if b not in bat_busses:
                    bat_busses[b] = [so]
                else:
                    bat_busses[b] += [so]

        # we know where to draw each battery and what color to make them.
        for b, sos in bat_busses.items():
            bx, by = [seg_busses[b][0], seg_busses[b][1]]
            
            # for i in range(len(sos)): self.__make_pv_patch(
            #     bx, by, w, 8, so_colors[sos[i]], ax, i * o, yo + i * o                
            #     )
                
            for i in range(len(sos)): self.__make_battery_patch(
                bx, by, w, h, so_colors[sos[i]], ax, i * o, yo + i * o                
                )
                
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

    def __make_plot_legend(self, ax):

        if len(self.project.storage_options) == 0:
            return    

        # The legend will show the storage options defined and have an
        # indicator of their color.
        self.cindex = 0
        custom_lines = []
        names = []
                        
        for so in self.project.storage_options:
            c = self.colors[self.cindex]
            self.cindex = (self.cindex + 1) % len(self.colors)
            names += [so.name + f" ({len(so.busses)})"]
            custom_lines += [Line2D([0], [0], color=c, lw=4)]
            
        ax.legend(custom_lines, names)

    def __get_line_segments(self, gm):
        lines = gm.line_names
        if len(lines) == 0: return None
        
        return [line for line in gm.line_names
            if (0., 0.) not in self.line_bus_coords(line)]
    
    def __get_line_segment_busses(self, gm, seg_lines=None):
        if seg_lines is None:
            seg_lines = self.__get_line_segments(gm)
        
        seg_busses = {}
        
        if len(seg_lines) == 0:
            busses = gm.bus_names
            if len(busses) == 0:
                return None
            
            for bus in busses:
                bc = self.bus_coords(bus)
                seg_busses[self.get_raw_bus_name(bus)] = bc
        else:            
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
        dssdirect.Text.Command(f"redirect {gm._model_file}")
        #dssdirect.Solution.Solve()
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
        
        if self.ids.show_storage_options.active:
            self.__draw_storage_options(ax)
            self.__make_plot_legend(ax)
                   
        #if self.ids.show_pv_assets.active:
        self.__draw_fixed_pv_assets(ax)
            
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
            Distionary with optional keys 'enabled', 'mtbf', 'min_repair', and
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
        """Return True if the switch reliability mdoel is enabled."""
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
    popup = Popup(
        title="Configuration error!",
        content=content
    )
    content.ids.dismissBtn.bind(on_press=popup.dismiss)
    popup.open()


def _show_no_grid_popup(dismiss_screen=None, manager=None):
    """Show a popup dialog warning that no grid model is selected.

    Parameters
    ----------
    dismiss_screen : str, optional

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
    
    """A utility method to plot the xs and ys in the given box.  The supplied title
    and axis labels are installed.

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
