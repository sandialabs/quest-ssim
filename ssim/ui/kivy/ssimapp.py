"""Storage Sizing and Placement Kivy application"""
from kivy.logger import Logger, LOG_LEVELS
from kivy.app import App
from kivymd.app import MDApp
from kivymd.uix.list import OneLineListItem, TwoLineListItem
from kivy.uix.popup import Popup
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.properties import ObjectProperty

from ssim.ui import Project


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

class MetricConfigurationScreen(SSimBaseScreen):

    def configure_voltage_metrics(self):
        self.load_bussed_into_list()
        print("I'm passing on the voltage issue...")

    def configure_some_other_metrics(self):
        self.ids.interlist.clear_widgets()
        self.ids.metriclist.clear_widgets()
        self.ids.interlabel.text = "Metric Objects"
        print("I'm passing on the other issue...")

    def load_bussed_into_list(self):
        #busses = self.project.bus_names()
        self.ids.interlist.clear_widgets()
        self.ids.metriclist.clear_widgets()
        self.ids.interlabel.text = "Busses"

        if self.project._grid_model is None:
            content = NoGridPopupContent()
            content.orientation="vertical"
            #box = BoxLayout(orientation="vertical")
            #box.add_widget(Label(
            #    text='',
            #    text_size=self.size
            #    ))
            #disbut = Button(text='Dismiss')
            #box.add_widget(disbut)

            popup = Popup(
                title='No Grid Model', content=content, auto_dismiss=False,
                size_hint=(0.4, 0.4)
                )
            content.ids.dismissBtn.bind(on_press=popup.dismiss)
            #disbut.bind(on_press=popup.dismiss)

            # open the popup
            popup.open()
            return

        list = self.ids.interlist
        busses = self.project._grid_model.bus_names
        for x in busses:
            item = OneLineListItem(text=str(x))
            list.add_widget(item)


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
