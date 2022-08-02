"""Storage Sizing and Placement Kivy application"""
from kivy.logger import Logger, LOG_LEVELS
from kivy.app import App
from kivy.uix.screenmanager import Screen

from ssim.ui import Project


class SSimApp(App):

    def __init__(self, *args, **kwargs):
        self.project = Project("unnamed") # TODO name
        super(SSimApp, self).__init__(*args, **kwargs)

    def build(self):
        return SSim()


class SSim(Screen):

    def report(self, message):
        Logger.debug("button pressed: %s", message)


if __name__ == '__main__':
    Logger.setLevel(LOG_LEVELS["debug"])
    SSimApp().run()
