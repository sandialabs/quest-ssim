"""Storage Sizing and Placement Kivy application"""
from kivy.logger import Logger, LOG_LEVELS
from kivy.app import App
from kivy.uix.screenmanager import Screen, ScreenManager

from ssim.ui import Project


class SSimApp(App):

    def __init__(self, *args, **kwargs):
        self.project = Project("unnamed") # TODO name
        super().__init__(*args, **kwargs)

    def build(self):

        screen_manager = ScreenManager()
        screen_manager.add_widget(SSimScreen(self.project, name="ssim"))
        screen_manager.add_widget(DERConfigurationScreen(self.project, name="der-config"))
        screen_manager.add_widget(LoadConfigurationScreen(self.project, name="load-config"))
        screen_manager.add_widget(MetricConfigurationScreen(self.project, name="metric-config"))
        screen_manager.add_widget(RunSimulationScreen(self.project, name="run-sim"))
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


class MetricConfigurationScreen(SSimBaseScreen):
    pass


class LoadConfigurationScreen(SSimBaseScreen):
    pass


class RunSimulationScreen(SSimBaseScreen):
    pass


class SSimScreen(SSimBaseScreen):

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
