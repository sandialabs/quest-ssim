"""Utilities for the ssim UI."""
import matplotlib.pyplot as plt
from kivy.garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.label import MDLabel


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
