"""Storage Sizing and Placement Kivy application"""
import os
import re


from ssim.metrics import ImprovementType, Metric, MetricTimeAccumulator
from kivymd.app import MDApp
from ssim.ui import Project, StorageOptions, is_valid_opendss_name
from kivy.logger import Logger, LOG_LEVELS
from kivy.uix.floatlayout import FloatLayout
from kivymd.uix.list import IRightBodyTouch, ILeftBodyTouch, TwoLineAvatarIconListItem, OneLineAvatarIconListItem
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.core.text import LabelBase
from kivy.clock import Clock
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.button import MDFlatButton ,MDRectangleFlatIconButton
from kivymd.uix.list import OneLineListItem

from kivymd.app import MDApp
from kivymd.uix.list import (
    TwoLineAvatarIconListItem,
    TwoLineIconListItem,
    ILeftBodyTouch,
    OneLineRightIconListItem,
    MDList
)
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.textfield import MDTextField
from kivy.properties import ObjectProperty, StringProperty
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.menu import MDDropdownMenu
import tomli

class SSimApp(MDApp):

    def __init__(self, *args, **kwargs):
        self.project = Project("unnamed")
        super().__init__(*args, **kwargs)

    def build(self):

        screen_manager = ScreenManager()
        screen_manager.add_widget(SSimScreen(self.project, name="ssim"))
        screen_manager.add_widget(
            DERConfigurationScreen(self.project, name="der-config"))
        screen_manager.add_widget(
            LoadConfigurationScreen(self.project, name="load-config"))
        screen_manager.add_widget(
            MetricConfigurationScreen(self.project, name="metric-config"))
        screen_manager.add_widget(
            RunSimulationScreen(self.project, name="run-sim"))
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
        super().__init__(*args, **kwargs)


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
    SIMPLE_FLOAT = re.compile(r"(\+|-)?\d+(\.\d*)?$")

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


class TextFieldPositiveFloat(MDTextField):
    POSITIVE_FLOAT = re.compile(r"\d+(\.\d*)?$")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper_text_mode = "on_focus"
        self.helper_text = "Input value and press enter"

    def text_valid(self):
        return TextFieldPositiveFloat.POSITIVE_FLOAT.match(self.text) is not None

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


class TextFieldPositivePercentage(MDTextField):
    POSITIVE_FLOAT = re.compile(r"\d+(\.\d*)?$")

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

    def __init__(self, der_screen, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        self.options = None

    def on_kv_post(self, base_widget):
        self.ids.bus_list.clear_widgets()
        for bus in self.project.bus_names:
            bus_list_item = BusListItem(bus, self.project.phases(bus))
            self.ids.bus_list.add_widget(bus_list_item)

    def _check_name(self):
        textfield = self.ids.device_name
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

    def _refocus_field(self, textfield):
        textfield.focus = True

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
        self.options = StorageOptions(
            self.ids.device_name.text,
            3,
            self._ess_powers,
            self._ess_durations,
            self._selected_busses,
            required=self.ids.required.active
        )

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
            return

        mytoml = self.options.write_toml()

        self._der_screen.add_ess(self.options)
        self.manager.current = "der-config"
        self.manager.remove_widget(self)

    def cancel(self):
        self.manager.current = "der-config"
        self.manager.remove_widget(self)

    def on_enter(self, *args):
        return super().on_enter(*args)


class StorageControlConfigurationScreen(SSimBaseScreen):
    """Configure the control strategy of a single energy storage device."""
    def __init__(self, der_screen, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._der_screen = der_screen
        self._options = args[0]

        self.ids.min_soc.text = str(self._options.min_soc*100.0)
        self.ids.max_soc.text = str(self._options.max_soc*100.0)
        self.ids.init_soc.text = str(self._options.initial_soc*100.0)

        self._param_field_map = {}

        Clock.schedule_once(lambda dt: self.__set_focus_clear_sel(self.ids.max_soc), 0.05)
        Clock.schedule_once(lambda dt: self.__set_focus_clear_sel(self.ids.min_soc), 0.05)
        Clock.schedule_once(lambda dt: self.__set_focus_clear_sel(self.ids.init_soc), 0.05)

        self.def_btn_color = '#005376'

        if not self._options is None:
            if self._options.control.mode == "droop":
                self.set_droop_mode()
            elif self._options.control.mode == "voltvar":
                self.set_volt_var_mode()
            elif self._options.control.mode == "voltwatt":
                self.set_volt_watt_mode()
            elif self._options.control.mode == "varwatt":
                self.set_var_watt_mode()
            elif self._options.control.mode == "vv_vw":
                self.set_volt_var_and_volt_watt_mode()
            elif self._options.control.mode == "constantpf":
                self.set_const_power_factor_mode()
            else:
                self.set_droop_mode()
    @staticmethod
    def __set_focus_clear_sel(widget, value = True):
        widget.focus = value
        Clock.schedule_once(lambda dt: widget.cancel_selection(), 0.05)

    def set_mode_label_text(self):
        self.ids.mode_label.text = "Select a control mode for this storage asset: [b]" +\
            self.device_name + "[/b]"

    @property
    def device_name(self):
        return "" if self._options is None else self._options.name

    def set_droop_mode(self):
        if self.set_mode("droop", self.ids.droop_mode):
            self._options.control.params["p_droop"] = 500
            self._options.control.params["q_droop"] = -300

        pfield = TextFieldFloat(
            hint_text="P Droop", text=str(self._options.control.params["p_droop"])
            )
        qfield = TextFieldFloat(
            hint_text="Q Droop", text=str(self._options.control.params["q_droop"])
            )
        self.ids.param_box.add_widget(pfield)
        self.ids.param_box.add_widget(qfield)
        self.ids.param_box.add_widget(BoxLayout(size_hint=(1.0, 0.8)))

        self._param_field_map.clear()
        self._param_field_map["p_droop"] = pfield
        self._param_field_map["q_droop"] = qfield

        Clock.schedule_once(lambda dt: self.__set_focus_clear_sel(pfield), 0.05)
        Clock.schedule_once(lambda dt: self.__set_focus_clear_sel(qfield), 0.05)

    def set_volt_var_mode(self):
        self.set_mode("voltvar", self.ids.vv_mode)

    def set_volt_watt_mode(self):
        self.set_mode("voltwatt", self.ids.vw_mode)

    def set_var_watt_mode(self):
        self.set_mode("varwatt", self.ids.var_watt_mode)

    def set_volt_var_and_volt_watt_mode(self):
        self.set_mode("vv_vw", self.ids.vv_vw_mode)

    def set_const_power_factor_mode(self):
        self.set_mode("constantpf", self.ids.const_pf_mode)

    def set_mode(self, name, button) -> bool:
        self.manage_button_selection_states(button)
        if self._options.control.mode == name: return False
        self._options.control.mode = name
        self._options.control.params.clear()
        self.ids.param_box.clear_widgets()
        return True

    def manage_button_selection_states(self, selbutton):
        self.ids.droop_mode.md_bg_color = "red" if selbutton is self.ids.droop_mode else self.def_btn_color
        self.ids.vv_mode.md_bg_color = "red" if selbutton is self.ids.vv_mode else self.def_btn_color
        self.ids.vw_mode.md_bg_color = "red" if selbutton is self.ids.vw_mode else self.def_btn_color
        self.ids.var_watt_mode.md_bg_color = "red" if selbutton is self.ids.var_watt_mode else self.def_btn_color
        self.ids.vv_vw_mode.md_bg_color = "red" if selbutton is self.ids.vv_vw_mode else self.def_btn_color
        self.ids.const_pf_mode.md_bg_color = "red" if selbutton is self.ids.const_pf_mode else self.def_btn_color

    def save(self):
        self._options.min_soc = self.ids.min_soc.fraction()
        self._options.max_soc = self.ids.max_soc.fraction()
        self._options.initial_soc = self.ids.init_soc.fraction()

        self._options.control.params.clear()

        for key in self._param_field_map:
            self._options.control.params[key] = float(self._param_field_map[key].text)

        self.manager.current = "configure-storage"

    def cancel(self):
        self.manager.current = "configure-storage"
        self.manager.remove_widget(self)


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

    def new_storage(self):
        self.manager.add_widget(
            StorageConfigurationScreen(
                self, self.project, name="configure-storage")
        )

        self.manager.current = "configure-storage"

    def add_ess(self, ess):
        self.project.add_storage_option(ess)
        self.ids.ess_list.add_widget(
            StorageListItem(ess)
        )

    def on_pre_enter(self, *args):
        if self.project.grid_model is None:
            _show_no_grid_popup("ssim", self.manager)
        return super().on_pre_enter(*args)


class StorageListItem(TwoLineIconListItem):
    def __init__(self, ess, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = ess.name
        self.secondary_text = str(ess.power)


class LoadConfigurationScreen(SSimBaseScreen):
    pass


class NoGridPopupContent(BoxLayout):
    pass

class NoGridPopupContent(BoxLayout):
    pass

class MissingMetricValuesPopupContent(BoxLayout):
    pass

class InvalidMetricValuesPopupContent(BoxLayout):
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
    _metricIcons = {"Voltage": "lightning-bolt-circle", "Unassigned": "chart-line"}

    def __reset_checked_bus_list(self):
        self._selBusses.clear()
        for wid in self.ids.interlist.children:
            if isinstance(wid, BusListItemWithCheckbox):
                cb = wid.ids.check
                if cb.active:
                    print(wid.text, wid.secondary_text)
                    self._selBusses.append(cb)

    def drop_sense_menu(self):
        menu_items = [
            {
                "viewclass": "OneLineListItem",
                "text": "Minimize",
                "on_release": lambda x="Minimize" : self.set_sense(x)
            },
            {
                "viewclass": "OneLineListItem",
                "text": "Maximize",
                "on_release": lambda x="Maximize" : self.set_sense(x)
            },
            {
                "viewclass": "OneLineListItem",
                "text": "Seek Value",
                "on_release": lambda x="Seek Value" : self.set_sense(x)
            }
        ]

        self.menu = MDDropdownMenu(
            caller=self.ids.caller, items=menu_items, width_mult=3
            )
        self.menu.open()

    def set_sense(self, value):
        self.ids.caller.text = value
        self.menu.dismiss()

    def manage_store_button_enabled_state(self):
        self.ids.btnStore.disabled = len(self._selBusses) == 0

    def reload_metric_values(self):
        metrics = []
        common_limit = None
        common_obj = None
        common_sense = None

        self.ids.metricValueBox.disabled = len(self._selBusses) == 0

        ''' Gather up the list of all metrics relevant to the selection'''
        for b in self._selBusses:
            m = self.project.get_metric(self._currentMetricCategory, b)
            if m is None:
                common_limit = None
                common_obj = None
                common_sense = None
                metrics.clear()
                break
            else:
                metrics.append(m)

        for m in metrics:
            if common_limit is None:
                common_limit = m.metric.limit
                common_obj = m.metric.objective
                common_sense = m.metric.improvement_type
            else:
                if common_limit != m.metric.limit:
                    common_limit = None
                    break
                if common_obj != m.metric.objective:
                    common_obj = None
                    break
                if common_sense != m.metric.improvement_type:
                    common_sense = None
                    break

        if common_limit is None:
            self.ids.limitText.text = "None or Varied"
        else:
            self.ids.limitText.text = str(common_limit)

        if common_obj is None:
            self.ids.objectiveText.text = "None or Varied"
        else:
            self.ids.objectiveText.text = str(common_obj)

        if common_sense is None:
            self.ids.caller.text = "None or Varied"
        else:
            self.ids.caller.text = str(common_sense.name)

    @staticmethod
    def __parse_float(strval):
        try:
            return float(strval)
        except ValueError:
            return None

    def store_metrics(self):
        limit = MetricConfigurationScreen.__parse_float(self.ids.limitText.text)
        obj = MetricConfigurationScreen.__parse_float(self.ids.objectiveText.text)
        sense = ImprovementType.parse(self.ids.caller.text)

        err = Metric.validate_metric_values(limit, obj, sense, False)

        if err is not None:
            self.__show_invalid_metric_value_popup(err)
            return

        if limit is None or obj is None or sense is None:
            self.__show_missing_metric_value_popup()
        else:
            for bus in self._selBusses:
                accum = MetricTimeAccumulator(Metric(limit, obj, sense))
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
        numCldrn = len(self.ids.interlist.children) == 0
        self.ids.btnSelectAll.disabled = numCldrn
        self.ids.btnDeselectAll.disabled = numCldrn


    def deselect_all_metric_objects(self):
        for wid in self.ids.interlist.children:
            if isinstance(wid, BusListItemWithCheckbox):
                wid.ids.check.active = False

    def select_all_metric_objects(self):
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
            deets = "Limit=" + str(m.metric.limit) + ", " + \
                "Objective=" + str(m.metric.objective) + ", " + \
                "Sense=" + m.metric.improvement_type.name
            bItem = MetricListItem(text=txt, secondary_text=deets)
            bItem.bus = key
            bItem.ids.left_icon.icon = self._metricIcons[self._currentMetricCategory]
            bItem.ids.trash_can.bind(on_release=self.on_delete_metric)
            list.add_widget(bItem)

        list.active = True

    def on_delete_metric(self, data):
        bus = data.listItem.bus
        self.project.remove_metric(self._currentMetricCategory, bus)
        self.reload_metric_list()
        self.reload_metric_values()

    def on_item_check_changed(self, ckb, value):
        bus = ckb.listItem.text
        if value:
            self._selBusses.append(bus)
        else:
            self._selBusses.remove(bus)

        self.reload_metric_values()
        self.manage_store_button_enabled_state()

    def configure_voltage_metrics(self):
        self._currentMetricCategory = "Voltage"
        self.load_bussed_into_list()
        self.reload_metric_list()
        self.reload_metric_values()
        self.manage_selection_buttons_enabled_state()

    def configure_some_other_metrics(self):
        self._currentMetricCategory = "Unassigned"
        self._selBusses.clear()
        self.ids.interlist.clear_widgets()
        self.ids.interlabel.text = "Metric Objects"
        self.reload_metric_list()
        self.reload_metric_values()
        self.manage_selection_buttons_enabled_state()
        print("I'm passing on the other issue...")

    def _return_to_main_screen(self, dt):
        self.manager.current = "ssim"

    def __show_missing_metric_value_popup(self):
        content = MissingMetricValuesPopupContent()

        popup = Popup(
            title='Missing Metric Values', content=content, auto_dismiss=False,
            size_hint=(0.4, 0.4)
            )
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        popup.open()
        return

    def __show_invalid_metric_value_popup(self, msg):
        content = InvalidMetricValuesPopupContent()

        popup = Popup(
            title='Invalid Metric Values', content=content, auto_dismiss=False,
            size_hint=(0.4, 0.4)
            )
        content.ids.msg_label.text = str(msg)
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        popup.open()
        return

    def __show_no_grid_model_popup(self):
        content = NoGridPopupContent()

        popup = Popup(
            title='No Grid Model', content=content, auto_dismiss=False,
            size_hint=(0.4, 0.4)
            )
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        content.ids.mainScreenBtn.bind(on_press=popup.dismiss)
        content.ids.mainScreenBtn.bind(on_press=self._return_to_main_screen)
        popup.open()
        return

    def load_bussed_into_list(self):
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

class RunSimulationScreen(SSimBaseScreen):

    def on_enter(self):
        self.populate_confgurations()
        for i in range(20):
            # self.ids.config_list.add_widget(
            #     TwoLineIconListItem(text=f"Single-line item {i}",
            #                         secondary_text="Details")
            # )
            self.ids.config_list.add_widget(
                ListItemWithCheckbox(pk="pk",
                                     text=f"Single-line item {i}",
                                     secondary_text="Details")
            )

    def populate_confgurations(self):
        # item_list = self.ids.interlist
        # TODO: Need to populate the MDlist dynamically
        configs = self.project.configurations


class ListItemWithCheckbox(TwoLineAvatarIconListItem):

    def __init__(self, pk=None, **kwargs):
        super().__init__(**kwargs)
        self.pk = pk

    def delete_item(self, the_list_item):
        self.parent.remove_widget(the_list_item)


class LeftCheckbox(ILeftBodyTouch, MDCheckbox):
    '''Custom left container'''
    pass


class SelectGridDialog(FloatLayout):
    load = ObjectProperty(None)
    cancel = ObjectProperty(None)


class SSimScreen(SSimBaseScreen):

    grid_path = ObjectProperty(None)
    bus_list = ObjectProperty(None)

    def report(self, message):
        Logger.debug("button pressed: %s", message)

    def dismiss_popup(self):
        self._popup.dismiss()

    def load_grid(self, path, filename):
        Logger.debug("loading file %s", filename[0])
        self.project.set_grid_model(filename[0])
        self.bus_list.text = '\n'.join(self.project.bus_names)
        self.dismiss_popup()

    def write_toml(self):
        toml = self.project.write_toml()
        with open('c:/temp/written.toml', 'w') as f:
            f.write(toml)

        self.project.clear_metrics()
        tdat = tomli.loads(toml)
        self.project.read_toml(tdat)

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

    def do_run_simulation(self):
        self.manager.current = "run-sim"
        if self.project.grid_model is None:
            _show_no_grid_popup("ssim", self.manager)
            return


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


if __name__ == '__main__':
    LabelBase.register(
        name='Exo 2',
        fn_regular=os.path.join('resources', 'fonts',
                                'Exo_2', 'Exo2-Regular.ttf'),
        fn_bold=os.path.join('resources', 'fonts',
                             'Exo_2', 'Exo2-Bold.ttf'),
        fn_italic=os.path.join('resources', 'fonts',
                               'Exo_2', 'Exo2-Italic.ttf'))

    LabelBase.register(
        name='Open Sans',
        fn_regular=os.path.join('resources', 'fonts',
                                'Open_Sans', 'OpenSans-Regular.ttf'),
        fn_bold=os.path.join('resources', 'fonts',
                             'Open_Sans', 'OpenSans-Bold.ttf'),
        fn_italic=os.path.join('resources', 'fonts',
                               'Open_Sans', 'OpenSans-Italic.ttf'))

    Logger.setLevel(LOG_LEVELS["debug"])
    SSimApp().run()
