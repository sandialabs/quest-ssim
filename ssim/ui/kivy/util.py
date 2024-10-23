"""Utilities for the ssim UI."""
import inspect
import os

import matplotlib.pyplot as plt

import ssim.ui

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivymd.uix.label import MDLabel  # noqa: E402

import kivy.garden
kivy.garden.garden_system_dir = os.path.join(
    os.path.dirname(inspect.getfile(ssim.ui)), "libs/garden"
)
from kivy.garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg  # noqa: E402


class MatlabPlotBox(BoxLayout):
    def reset_plot(self):
        """Clears the current diagram widget and draws a new one using the
        current figure (plt.gcf())"""
        self.clear_widgets()
        fig = plt.gcf()
        canvas = FigureCanvasKivyAgg(fig)
        self.add_widget(canvas)

    def display_plot_error(self, msg):
        """Puts a label with a supplied message in place of the diagram when
        there is a reason a diagram can't be displayed.

        Parameters
        ----------
        msg : str
            The message to show in place of the diagram when one can't be
            displayed.
        """
        self.clear_widgets()
        self.add_widget(MDLabel(text=msg))


def focus_defocus(widget, dt=0.05):
    """Focus and defocus a widget after a delay.

    This is used to work around the quirks of the TextField widgets that cause
    them to display overlapping text when initialized directly instead of by
    user input.

    """
    def fd(t):
        widget.focus = True
        Clock.schedule_once(lambda _: widget.cancel_selection(), t)
    Clock.schedule_once(fd, dt)
