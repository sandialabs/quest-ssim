"""Storage Sizing and Placement Kivy application"""

from kivy.app import App
from kivy.uix.widget import Widget

from ssim.ui import Project

class SSimApp(App):

    def __init__(self, *args, **kwargs):
        self.project = Project("unnamed") # TODO name
        super().__init__(*args, **kwargs)

    def build(self):
        return SSim()


class SSim(Widget):
    pass

if __name__ == '__main__':
    SSimApp().run()
