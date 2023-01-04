"""Storage Sizing and Placement Kivy application"""
import os
import re

from kivy.logger import Logger, LOG_LEVELS
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.core.text import LabelBase

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

from ssim.ui import Project, StorageOptions


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


class TextFieldPositiveFloat(MDTextField):
    POSITIVE_FLOAT = re.compile(r"\d+(\.\d*)?$")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper_text_mode = "on_focus"
        self.helper_text = "Press enter"

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
            self.helper_text = "Press enter"


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
        return (
            len(self.text) > 0
            and '\t' not in self.text
            and ' ' not in self.text
            and '.' not in self.text
            and '=' not in self.text
        )

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
            on_text_validate=self._assign_name,
        )

    def _assign_name(self, textfield):
        if textfield.text_valid():
            self._ess_name = textfield.text

    def _add_option(self, optionlist, textfield):
        if textfield.text_valid():
            duration = float(textfield.text)
            optionlist.add_item(duration)
        else:
            textfield.set_error_message()

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

    def save(self):
        if not self.ids.device_name.text_valid():
            return

        ess = StorageOptions(
            self.ids.device_name.text,
            3,
            self._ess_powers,
            self._ess_durations,
            self._selected_busses
        )

        if not ess.valid:
            Logger.error("invalid storage configuration")
            Logger.error(
                f"powers: {ess.power}, "
                f"durations: {ess.duration}, "
                f"busses: {ess.busses}"
            )
            return

        self._der_screen.add_ess(ess)
        self.manager.current = "der-config"
        self.manager.remove_widget(self)

    def cancel(self):
        self.manager.current = "der-config"

    def on_enter(self, *args):
        self.ids.bus_list.clear_widgets()
        for bus in self.project.bus_names:
            bus_list_item = BusListItem(bus, self.project.phases(bus))
            self.ids.bus_list.add_widget(bus_list_item)
        return super().on_enter(*args)


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


class StorageListItem(TwoLineIconListItem):
    def __init__(self, ess, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = ess.name
        self.secondary_text = str(ess.power)


class LoadConfigurationScreen(SSimBaseScreen):
    pass


class NoGridPopupContent(BoxLayout):
    pass


class MetricConfigurationScreen(SSimBaseScreen):
    pass


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
        if self.project._grid_model is None:
            poppup_content = NoGridPopupContent()
            poppup_content.orientation = "vertical"
            popup = Popup(title='No Grid Model', content=poppup_content,
                          auto_dismiss=False, size_hint=(0.4, 0.4))
            poppup_content.ids.dismissBtn.bind(on_press=popup.dismiss)
            # open the popup
            popup.open()
            return


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
