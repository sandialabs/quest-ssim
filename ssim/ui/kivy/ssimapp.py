"""Storage Sizing and Placement Kivy application"""

from ast import Return
from ssim.metrics import ImprovementType, Metric, MetricTimeAccumulator
from kivymd.app import MDApp
from ssim.ui import Project
from kivy.logger import Logger, LOG_LEVELS
from kivymd.uix.list import IRightBodyTouch, ILeftBodyTouch, TwoLineAvatarIconListItem, OneLineAvatarIconListItem
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
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

class MissingMetricValuesPopupContent(BoxLayout):
    pass

class InvalidMetricValuesPopupContent(BoxLayout):
    pass

class BusListItemWithCheckbox(OneLineAvatarIconListItem):
    '''Custom list item.'''
    icon = StringProperty("android")

    def __int__(self, bus):
        self.text = bus
        self.bus = bus
        
class MetricListItem(TwoLineAvatarIconListItem):
    pass

class RightCheckbox(IRightBodyTouch, MDCheckbox):
    pass

class LeftCheckbox(ILeftBodyTouch, MDCheckbox):
    pass

class MetricConfigurationScreen(SSimBaseScreen):

    _selBusses = []
    _currentMetricCategory = "None"
    _metricIcons = {"Voltage": "lightning-bolt-circle", "Unassigned": "chart-line"}

    def __reset_checked_bus_list(self):
        self._selBusses.clear()
        for wid in self.ids.interlist.children:
            if isinstance(wid, BusListItemWithCheckbox):
                cb = wid.ids.check
                if cb.active:
                    print(wid.text, wid.secondary_text)
                    self._selBusses.append(cb)
                    
    def drop(self):
        menu_items = [
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
            caller=self.ids.caller, items=menu_items, width_mult=3
            )
        self.menu.open()

    def set_sense(self, value):
        self.ids.caller.text = value
        self.menu.dismiss()

    def manage_store_button_enabled_state(self):
        self.ids.btnStore.disabled = len(self._selBusses) == 0

    def reload_metric_values(self):
        metrics = []
        common_limit = None
        common_obj = None
        common_sense = None

        ''' Gather up the list of all metrics relevant to the selection'''
        for b in self._selBusses:
            m = self.project.get_metric(self._currentMetricCategory, b)
            if m is None:
                common_limit = None
                common_obj = None
                common_sense = None
                metrics.clear()
                break
            else:
                metrics.append(m)
    
        for m in metrics:
            if common_limit is None:
                common_limit = m.metric.limit
                common_obj = m.metric.objective
                common_sense = m.metric.improvement_type
            else:
                if common_limit != m.metric.limit:
                    common_limit = None
                    break                
                if common_obj != m.metric.objective:
                    common_obj = None
                    break
                if common_sense != m.metric.improvement_type:
                    common_sense = None
                    break

        if common_limit is None:
            self.ids.limitText.text = "None or Varied"
        else:
            self.ids.limitText.text = str(common_limit)

        if common_obj is None:
            self.ids.objectiveText.text = "None or Varied"
        else:
            self.ids.objectiveText.text = str(common_obj)
            
        if common_sense is None:
            self.ids.caller.text = "None or Varied"
        else:
            self.ids.caller.text = str(common_sense.name)

    @staticmethod
    def __parse_float(strval):
        try:
            return float(strval)
        except ValueError:
            return None

    def store_metrics(self):
        limit = MetricConfigurationScreen.__parse_float(self.ids.limitText.text)
        obj = MetricConfigurationScreen.__parse_float(self.ids.objectiveText.text)
        sense = ImprovementType.parse(self.ids.caller.text)

        err = Metric.validate_metric_values(limit, obj, sense, False)

        if err is not None:
            self.__show_invalid_metric_value_popup(err)
            return

        if limit is None or obj is None or sense is None:
            self.__show_missing_metric_value_popup()
        else:
            for bus in self._selBusses:
                accum = MetricTimeAccumulator(Metric(limit, obj, sense))
                self.project.add_metric(self._currentMetricCategory, bus, accum)

        self.reload_metric_list()

    def reset_metric_list_label(self):
        """Resets the label atop the list of all defined metrics to include, or not, the current metric category.
        """
        if self._currentMetricCategory is None:
            self.ids.currMetriclabel.text = "Defined Metrics"
        
        elif self._currentMetricCategory == "None":
            self.ids.currMetriclabel.text = "Defined Metrics"

        else:
            self.ids.currMetriclabel.text = \
                "Defined \"" + self._currentMetricCategory + "\" Metrics"

    def reload_metric_list(self):
        """Reloads the list of all defined metrics.

        This method creates a list item for all metrics previously defined for the
        current category.
        """
        self.ids.metriclist.clear_widgets()
        self.reset_metric_list_label()
        manager = self.project.get_manager(self._currentMetricCategory)

        if manager is None: return

        list = self.ids.metriclist
        for mgrKey in manager.all_metrics:
            m = manager.all_metrics.get(mgrKey)
            txt = self._currentMetricCategory + " Metric for " + mgrKey
            deets = "Limit=" + str(m.metric.limit) + ", " + \
                "Objective=" + str(m.metric.objective) + ", " + \
                "Sense=" + m.metric.improvement_type.name
            bItem = MetricListItem(text=txt, secondary_text=deets)
            bItem.bus = mgrKey
            bItem.ids.left_icon.icon = self._metricIcons[self._currentMetricCategory]
            bItem.ids.trash_can.bind(on_release=self.on_delete_metric)
            list.add_widget(bItem)

    def on_delete_metric(self, data):
        bus = data.listItem.bus
        self.project.remove_metric(self._currentMetricCategory, bus)
        self.reload_metric_list()
        self.reload_metric_values()

    def on_item_check_changed(self, ckb, value):
        bus = ckb.listItem.text
        if value:
            self._selBusses.append(bus)
        else:
            self._selBusses.remove(bus)

        self.reload_metric_values()
        self.manage_store_button_enabled_state()

    def configure_voltage_metrics(self):
        self._currentMetricCategory = "Voltage"
        self.load_bussed_into_list()
        self.reload_metric_list()
        self.reload_metric_values()

    def configure_some_other_metrics(self):
        self._currentMetricCategory = "Unassigned"
        self._selBusses.clear()
        self.ids.interlist.clear_widgets()
        self.ids.interlabel.text = "Metric Objects"
        self.reload_metric_list()
        self.reload_metric_values()
        print("I'm passing on the other issue...")

    def _return_to_main_screen(self, dt):
        self.manager.current = "ssim"
        
    def __show_missing_metric_value_popup(self):
        content = MissingMetricValuesPopupContent()

        popup = Popup(
            title='Missing Metric Values', content=content, auto_dismiss=False,
            size_hint=(0.4, 0.4)
            )
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        popup.open()
        return
    
    def __show_invalid_metric_value_popup(self, msg):
        content = InvalidMetricValuesPopupContent()

        popup = Popup(
            title='Invalid Metric Values', content=content, auto_dismiss=False,
            size_hint=(0.4, 0.4)
            )
        content.ids.msg_label.text = str(msg)
        content.ids.dismissBtn.bind(on_press=popup.dismiss)
        popup.open()
        return

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
