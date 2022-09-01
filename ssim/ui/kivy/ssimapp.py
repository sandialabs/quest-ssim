"""Storage Sizing and Placement Kivy application"""
import functools

from kivy.logger import Logger, LOG_LEVELS
from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.properties import ObjectProperty
from kivy.uix.popup import Popup

from kivymd.app import MDApp
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.list import ILeftBodyTouch, TwoLineIconListItem
from kivymd.uix.selectioncontrol import MDCheckbox

from ssim.ui import Project, StorageOptions


class SSimApp(MDApp):

    def __init__(self, *args, **kwargs):
        self.project = Project("unnamed") # TODO name
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
        '''mark the task as complete or incomplete'''
        if check.active == True:
            self.parent.parent.parent.add_bus(the_list_item)
        else:
            self.parent.parent.parent.remove_bus(the_list_item)


class StorageConfigurationScreen(SSimBaseScreen):
    """Configure a single energy storage device."""

    def __init__(self, der_screen, *args, **kwargs):
        self._der_screen = der_screen
        # default storage configuration
        self.ess = StorageOptions(
            "unnamed", 3, [50.0], [4.0], []
        )
        super().__init__(*args, **kwargs)
        for bus in self.project.bus_names:
            bus_list_item = BusListItem(bus, self.project.phases(bus))
            self.ids.bus_list.add_widget(bus_list_item)

    def save(self):
        for bus_item in self.ids.bus_list.children:
            Logger.debug(f"bus_item: {bus_item}")
            Logger.debug(f"bus_item.ids: {bus_item.ids}")

            if bus_item.ids.selected.active:
                self.ess.busses.append(bus_item.text)
        self.project.add_storage_option(self.ess)
        self._der_screen.add_ess(self.ess)
        self.ess = StorageOptions("unnamed", 3, [50.0], [4.0], [])
        self.manager.current = "der-config"

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


class MetricConfigurationScreen(SSimBaseScreen):
    pass


class LoadConfigurationScreen(SSimBaseScreen):
    pass


class RunSimulationScreen(SSimBaseScreen):
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


if __name__ == '__main__':
    Logger.setLevel(LOG_LEVELS["debug"])
    SSimApp().run()
