"""Storage Sizing and Placement Kivy application"""
from kivy.logger import Logger, LOG_LEVELS
from kivy.app import App
from kivy.uix.screenmanager import Screen, ScreenManager

from ssim.ui import Project


class SSimApp(App):

    def __init__(self, *args, **kwargs):
        self.project = Project("unnamed") # TODO name
        super(SSimApp, self).__init__(*args, **kwargs)

    def build(self):

        screen_manager = ScreenManager()
        screen_manager.add_widget(SSimScreen(name="ssim"))
        screen_manager.add_widget(DERConfigurationScreen(name="der-config"))
        screen_manager.add_widget(LoadConfigurationScreen(name="load-config"))
        screen_manager.add_widget(MetricConfigurationScreen(name="metric-config"))
        screen_manager.add_widget(RunSimulationScreen(name="run-sim"))
        screen_manager.current = "ssim"

        return screen_manager


class DERConfigurationScreen(Screen):
    pass


class LoadConfigurationScreen(Screen):
    pass


class MetricConfigurationScreen(Screen):
    pass


class LoadConfigurationScreen(Screen):
    pass


class RunSimulationScreen(Screen):
    pass


class SSimScreen(Screen):

    def report(self, message):
        Logger.debug("button pressed: %s", message)

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
