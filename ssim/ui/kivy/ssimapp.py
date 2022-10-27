"""Storage Sizing and Placement Kivy application"""
import os

from kivy.logger import Logger, LOG_LEVELS
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.properties import ObjectProperty
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout

from kivymd.app import MDApp
from kivymd.uix.list import (
    TwoLineAvatarIconListItem,
    ILeftBodyTouch,
    OneLineListItem
)
from kivymd.uix.selectioncontrol import MDCheckbox
from kivy.core.text import LabelBase

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


class StorageConfigurationScreen(SSimBaseScreen):
    """Configure a single energy storage device."""

    def __init__(self, der_screen, *args, **kwargs):
        self._der_screen = der_screen
        # default storage configuration
        self.ess = StorageOptions(
            "unnamed", 3, [], [], []
        )
        super().__init__(*args, **kwargs)
        for bus in self.project.bus_names:
            bus_list_item = BusListItem(bus, self.project.phases(bus))
            self.ids.bus_list.add_widget(bus_list_item)

    def _update_powers(self):
        listed_powers = set(
            float(c.text)
            for c in self.ids.power_list.children
        )
        for power in self.ess.power:
            if power in listed_powers:
                continue
            self.ids.power_list.add_widget(OneLineListItem(text=str(power)))

    def _update_durations(self):
        listed_durations = set(
            float(c.text)
            for c in self.ids.duration_list.children
        )
        for duration in self.ess.duration:
            if duration in listed_durations:
                continue
            self.ids.duration_list.add_widget(OneLineListItem(text=str(duration)))

    def add_power(self, power):
        self.ess.add_power(power)
        self._update_powers()

    def add_duration(self, duration):
        self.ess.add_duration(duration)
        self._update_durations()

    def save(self):
        for bus_item in self.ids.bus_list.children:
            Logger.debug(f"bus_item: {bus_item}")
            Logger.debug(f"bus_item.ids: {bus_item.ids}")

            if bus_item.ids.selected.active:
                self.ess.add_bus(bus_item.text)

        if not self.ess.valid:
            Logger.error("invalid storage configuration")
            Logger.error(f"powers: {self.ess.power}, durations: {self.ess.duration}, busses: {self.ess.busses}")
            return

        self.project.add_storage_option(self.ess)
        self._der_screen.add_ess(self.ess)
        self.ess = StorageOptions("unnamed", 3, [], [], [])
        self.manager.current = "der-config"
        self.manager.remove_widget(self)

    def cancel(self):
        self.manager.current = "der-config"


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
