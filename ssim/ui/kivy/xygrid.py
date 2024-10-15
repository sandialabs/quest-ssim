"""XY-Grid widgets and supporting functions."""
import matplotlib.pyplot as plt
from kivy.clock import Clock
from kivy.logger import Logger
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.textinput import TextInput

from ssim.ui.kivy.util import MatlabPlotBox


class XYGridView(RecycleView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type("on_item_deleted")
        self.register_event_type("on_value_changed")

    def delete_item(self, index: int):
        self.data.pop(index)
        Clock.schedule_once(lambda dt: self.__raise_deleted_item(), 0.05)

    def x_value_changed(self, index: int, value):
        self.__on_value_changed(index, "x", value)

    def y_value_changed(self, index: int, value):
        self.__on_value_changed(index, "y", value)

    def __on_value_changed(self, index: int, key: str, value):
        self.data[index][key] = parse_float_or_str(value)
        Clock.schedule_once(lambda dt: self.__raise_value_changed(), 0.05)

    def __raise_value_changed(self):
        self.dispatch("on_value_changed")

    def on_value_changed(self):
        pass

    def on_item_deleted(self):
        pass

    def set_data(self, xdat, ydat):
        """Set the data in the grid."""
        Logger.debug("-> XYGridView.set_data()")
        xs, ys = try_co_sort(xdat, ydat)
        Logger.debug(f"   xs = {xs}")
        Logger.debug(f"   ys = {ys}")
        self.data = make_xy_grid_data(xs, ys)
        Clock.schedule_once(lambda dt: self.__raise_value_changed(), 0.05)
        Logger.debug(f"   self.data = {self.data}")
        Logger.debug("<- XYGridView.set_data()")

    def __raise_deleted_item(self):
        """Dispatches the on_item_deleted method to anything bound to it."""
        self.dispatch("on_item_deleted")

    def extract_data_lists(self, sorted: bool = True) -> (list, list):
        """Reads all values out of the "x" and "y" columns of this control and
           as returns them pair of lists that may be sorted if requested.

        Parameters
        ----------
        sorted : bool
            True if this method should try and c0-sort the extracted x and y
             lists beforereturning them and false otherwise.

        Returns
        -------
        tuple:
            A pair of lists containing the x and y values in this grid.  The
            lists will be co-sorted using the x list as an index if requested
            and they can be sorted.
        """
        xvs = self.extract_x_vals()
        yvs = self.extract_y_vals()
        if not sorted:
            return (xvs, yvs)
        return try_co_sort(xvs, yvs)

    def extract_x_vals(self) -> list:
        """Reads all values out of the "x" column of this control and returns them as a list.

        Returns
        -------
        list:
            A list containing all values in the "x" column of this control.  The
            values in the list will be of type float if they can be cast as
            such.  Otherwise, raw text representations will be put in the list
            in locations where the cast fails.
        """
        return [child.x_value for child in self.children[0].children]

    def extract_y_vals(self) -> list:
        """Reads all values out of the "y" column of this control and returns them as a list.

        Returns
        -------
        list:
            A list containing all values in the "y" column of this control.
            The values in the list will be of type float if they can be cast as
            such.  Otherwise, raw text representations will be put in the list
            in locations where the cast fails.
        """
        return [child.y_value for child in self.children[0].children]


class XYGridViewItem(RecycleDataViewBehavior, BoxLayout):
    index: int = -1

    last_text: str = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def x_value(self):
        """Returns the current contents of the x value field of this row.

        Returns
        -------
        float or str:
            If the current content of the x value field of this row can be cast
            to a float, then the float is returned.  Otherwise, the raw string
            contents of the field are returned.
        """
        return parse_float_or_str(self.ids.x_field.text)

    @property
    def y_value(self):
        """Returns the current contents of the y value field of this row.

        Returns
        -------
        float or str:
            If the current content of the y value field of this row can be cast
            to a float, then the float is returned.  Otherwise, the raw string
            contents of the field are returned.
        """
        return parse_float_or_str(self.ids.y_field.text)

    def refresh_view_attrs(self, rv, index, data):
        """A method of the RecycleView called automatically to refresh the content of the view.

        Parameters
        ----------
        rv : RecycleView
            The RecycleView that owns this row and wants it refreshed (not used
            in this function).
        index: int
            The index of this row.
        data: dict
            The dictionary of data that constitutes this row.  Should have keys
            for 'x' and 'y'.
        """
        self.index = index
        self.ids.x_field.text = str(data["x"])
        self.ids.y_field.text = str(data["y"])

    def on_delete_button(self):
        """A callback function for the button that deletes the data item
        represented by this row from the data list"""
        self.parent.parent.delete_item(self.index)

    def on_x_value_changed(self, instance, text):
        """A callback method used when the value in the x field of an XY grid changes.

        This method notifies the grandparent, which is an XYGridView, of the
        change.

        Parameters
        ----------
        instance
            The x text field whose value has changed.
        text
            The new x value as a string.
        """
        if self.parent:
            self.parent.parent.x_value_changed(self.index, self.x_value)

    def on_x_focus_changed(self, instance, value):
        """A callback method used when the focus on the x field of an XY grid
            changes.

        This method checks to see if this is a focus event or an unfocus event.
        If focus, it stores the current value in the field for comparison later.
        If unfocus and the value has not changed, nothing is done.  If the value
        has changed, then the self.on_x_value_changed method is invoked.

        Parameters
        ----------
        instance
            The x text field whose value has changed.
        value
            True if this is a focus event and false if it is unfocus.
        """
        if value:
            self.last_text = instance.text
        elif value != instance.text:
            self.on_x_value_changed(instance, instance.text)

    def on_y_value_changed(self, instance, text):
        """A callback method used when the value in the y field of an XY grid is validated.

        This method notifies the grandparent, which is an XYGridView, of the change.

        Parameters
        ----------
        instance
            The y text field whose value has changed.
        text
            The new y value as a string.
        """
        if self.parent:
            self.parent.parent.y_value_changed(self.index, self.y_value)

    def on_y_focus_changed(self, instance, value):
        """A callback method used when the focus on the y field of an XY grid
            changes.

        This method checks to see if this is a focus event or an unfocus event.
        If focus, it stores the current value in the field for comparison later.
        If unfocus and the value has not changed, nothing is done.  If the value
        has changed, then the self.on_y_value_changed method is invoked.

        Parameters
        ----------
        instance
            The y text field whose value has changed.
        value
            True if this is a focus event and false if it is unfocus.
        """
        if value:
            self.last_text = instance.text
        elif value != instance.text:
            self.on_y_value_changed(instance, instance.text)


class XYItemTextField(TextInput):
    """A class to serve as a text field used in an XY grid.

    This class can be either an x or a y value field and enforces the
    requirement that the contents be a floating point number by indicating
    if it is not.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.def_back_color = self.background_color
        self.bind(text=self.set_error_message)
        self.hint_text = "Enter a number."

    def set_error_message(self, instance, text):
        """A function to set this text field to an error state.

        This method checks to see if the contents of this text field are
        a floating point number and does nothing if so.  If not, then this
        sets the background color to "red".

        Parameters
        ----------
        instance:
            The text field that initiated this call.
        text:
            The current text content of the text field as of this call.
        """
        v = parse_float(text) is not None
        self.background_color = "red" if not v else self.def_back_color


def make_xy_grid_data(xs: list, ys: list) -> list:
    """A utility method to create a list of dictionaries suitable for use by an
    XYGrid.

    Parameters
    ----------
    xs : list
        The x value list to be the x values in the resulting dictionary.
    ys : list
        The y value list to be the y values in the resulting dictionary.

    Returns
    -------
    list:
        A list of dictionaries of the form
        [{x: x1, y: y1}, {x: x2, y: y2}, ..., {x: xn, y: yn}] which is what's
        required by an XY grid.
    """
    return [{"x": xs[i], "y": ys[i]} for i in range(len(xs))]


def parse_float(strval) -> float:
    """A utility method to parse a string into a floating point value.

    This differs from a raw cast (float(strval)) in that it swallows
    exceptions.

    Parameters
    ----------
    strval
        The string to try and parse into a floating point number.

    Returns
    -------
    float:
        The value that resulted from parsing the supplied string to a float
        or None if the cast attempt caused an exception.
    """
    try:
        return float(strval)
    except ValueError:
        return None


def parse_float_or_str(strval):
    """A utility method to parse a string into a floating point value or leave
     it as is if the cast fails.

    This used parse_float and if that fails, this returns the supplied input
    string.

    Parameters
    ----------
    strval : Optional[str]
        The string to try and parse into a floating point number, or None.

    Returns
    -------
    float or str or None:
        This returns None if the supplied input string is None.  Otherwise, it
        tries to cast the input string to a float.   If that succeeds, then the
        float is returned.  If it doesn't, then the supplied string is returned
        unaltered.
    """
    if strval is None:
        return None
    flt = parse_float(strval)
    if flt is None:
        return strval
    return flt


def try_co_sort(xl: list, yl: list) -> (list, list):
    """Attempts to co-sort the supplied lists using the x-list as the sort index

    Parameters
    ----------
    xl : list
        The list of "x" values in this grid view to be sorted and treated as
        the index.
    yl: list
        The list of "y" values in this grid view to be sorted in accordance
        with the x-list.

    Returns
    -------
    tuple:
        If the two lists can be co-sorted, then the co-sorted versions of them
        will be returned.  If they cannot b/c an exception occurs, then they
        are returned unmodified.
    """
    if len(xl) < 2:
        return (xl, yl)

    try:
        return (list(t) for t in zip(*sorted(zip(xl, yl))))
    except:
        return (xl, yl)


def make_xy_matlab_plot(
    mpb: MatlabPlotBox, xs: list, ys: list, xlabel: str, ylabel: str, title: str
):
    """A utility method to plot the xs and ys in the given box.  The supplied
    title and axis labels are installed.

    Parameters
    ----------
    mpb: MatlabPlotBox
        The plot box that will house the plot created.
    xs: list
        The list of x values to plot.  Should be a list of floats.
    ys: list
        The list of y values to plot.  Should be a list of floats.
    xlabel: str
        The x axis label to put on the created plot.
    ylabel: str
        The y axis label to put on the created plot.
    title: str
        The string to use as the plot title.
    """
    fig, ax = plt.subplots(1, 1, layout="constrained")
    ax.plot(xs, ys, marker="o")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    plt.title(title)
    mpb.reset_plot()
