"""Storage Sizing and Placement Kivy application"""

from ssim.metrics import ImprovementType, Metric, MetricTimeAccumulator
from kivymd.app import MDApp
from ssim.ui import Project
from kivy.logger import Logger, LOG_LEVELS
from kivy.app import App
from kivy.metrics import dp
from kivymd.uix.list import IRightBodyTouch, OneLineListItem, TwoLineListItem, OneLineAvatarIconListItem
from kivy.uix.popup import Popup
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.dropdown import DropDown
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.properties import ObjectProperty, StringProperty
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.menu import MDDropdownMenu

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


class DERConfigurationScreen(SSimBaseScreen):
    pass

class LoadConfigurationScreen(SSimBaseScreen):
    pass

class NoGridPopupContent(BoxLayout):
    pass

class BusListItemWithCheckbox(OneLineAvatarIconListItem):
    '''Custom list item.'''
    icon = StringProperty("android")

    def __int__(self, bus):
        self.text = bus
        self.bus = bus

class RightCheckbox(IRightBodyTouch, MDCheckbox):
    pass

class MetricConfigurationScreen(SSimBaseScreen):

    _selBusses = []

    def __reset_checked_bus_list(self):
        self._selBusses.clear()
        for wid in self.ids.interlist.children:
            if isinstance(wid, BusListItemWithCheckbox):
                cb = wid.ids.check
                if cb.active:
                    print(wid.text, wid.secondary_text)
                    self._selBusses.append(cb)
                    
    def drop(self):
        self.menu_items = [
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
            caller=self.ids.caller,
            items=self.menu_items,
            width_mult=3
            )
        self.menu.open()

    def set_sense(self, value):
        self.ids.caller.text = value
        self.menu.dismiss()

    def reload_metric_values(self):
        pass

    def store_metrics(self):
        cat = "Voltage"
        limit = float(self.ids.limitText.text)
        obj = float(self.ids.objectiveText.text)
        sense = ImprovementType.parse(self.ids.caller.text)

        for bus in self._selBusses:
            accum = MetricTimeAccumulator(Metric(limit, obj, sense))
            self.project.add_metric(cat, bus, accum)

    def on_item_check_changed(self, ckb, value):
        bus = ckb.listItem.text
        if value:
            self._selBusses.append(bus)
        else:
            self._selBusses.remove(bus)

        self.reload_metric_values()

    def configure_voltage_metrics(self):
        self.load_bussed_into_list()

    def configure_some_other_metrics(self):
        self._selBusses.clear()
        self.ids.interlist.clear_widgets()
        self.ids.metriclist.clear_widgets()
        self.ids.interlabel.text = "Metric Objects"
        print("I'm passing on the other issue...")

    def _return_to_main_screen(self, dt):
        self.manager.current = "ssim"

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
        #busses = self.project.bus_names()
        self.ids.interlist.clear_widgets()
        self.ids.metriclist.clear_widgets()
        self.ids.interlabel.text = "Busses"

        if self.project._grid_model is None:
            self.__show_no_grid_model_popup()
            return

        list = self.ids.interlist
        busses = self.project._grid_model.bus_names
        for x in busses:
            bItem = BusListItemWithCheckbox(text=str(x))
            bItem.ids.check.bind(active=self.on_item_check_changed)
            list.add_widget(bItem)


class LoadConfigurationScreen(SSimBaseScreen):
    pass


class RunSimulationScreen(SSimBaseScreen):
    pass


class SSimScreen(SSimBaseScreen):

    bus_list = ObjectProperty(None)

    def report(self, message):
        Logger.debug("button pressed: %s", message)

    def select_grid_model(self):
        self.project.set_grid_model("examples/ieee13demo/IEEE13Nodeckt.dss")
        Logger.debug("busses: %s", self.project.bus_names)
        self.bus_list.text = "\n".join(self.project.bus_names)

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
