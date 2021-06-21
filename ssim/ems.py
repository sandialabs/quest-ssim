"""Energy Management System."""
import json


class StorageControlMessage:
    """Control messages for storage devices.

    Parameters
    ----------
    action : str
        Control action. Can be 'charge', 'discharge', or 'idle'
    real_power : float
        Real power for charging or discharging. Should be positive for
        both, the direction is determined by `action`. If charging
        `real_power` is the power flowing into the device, if discharging
        it is the power flowing out of the device. [kW]
    reactive_power : float
        Reactive power setting for the device. Sign determines the direction
        of flow. [kVAR]
    """
    def __init__(self, action, real_power, reactive_power):
        if action not in {'charge', 'discharge', 'idle'}:
            raise ValueError(f"Unknown action {action}. Action must be one of "
                             "'charge', 'discharge', or 'idle'.")
        if action == 'idle' and real_power != 0:
            raise ValueError("If action is 'idle' real_power must be 0 (got "
                             f"{real_power}")
        self.action = action
        self.real_power = real_power
        self.reactive_power = reactive_power

    @classmethod
    def from_json(cls, data):
        """Construct a StorageControlMessage from a JSON string."""
        action = json.loads(data)
        return cls(action['action'], action['kW'], action['kVAR'])

    def to_json(self):
        return json.dumps({'action': self.action,
                           'kW': self.real_power,
                           'kVAR': self.reactive_power})


class EMS:
    """Energy Management System.

    Parameters
    ----------
    config : str
        Path to the grid configuration file.
    """
    def __init__(self, config):
        with open(config) as f:
            grid_config = json.load(f)
        self.storage = {
            storage["name"]: {"capacity": storage["kwhrated"],
                              "kw": storage["kwrated"]}
            for storage in grid_config["storage"]
        }
        self.soc = {
            storage["name"]: storage["%stored"] / 100
            for storage in grid_config["storage"]
        }
        self.peak_start = grid_config["ems"]["peak_start"]
        self.peak_end = grid_config["ems"]["peak_end"]
        self._actions = {}
        self.time = 0.0

    def update(self, message):
        """Update the state of the EMS.

        Parameters
        ----------
        message : dict
            Dictionary with information used to update the EMS. This contains,
            for example, the state of charge of a storage device.
        """
        self.soc[message["name"]] = message["soc"]

    def _do_discharge(self):
        for device, soc in self.soc.items():
            if soc > 0:
                self._actions[device] = \
                    StorageControlMessage(
                        "discharge",
                        self.storage[device]["kw"],
                        0.0
                    )
            else:
                self._actions[device] = StorageControlMessage("idle", 0.0, 0.0)

    def _do_charge(self):
        for device, soc in self.soc.items():
            if soc < 1.0:
                self._actions[device] = \
                    StorageControlMessage(
                        "charge",
                        self.storage[device]["kw"],
                        0.0
                    )
            else:
                self._actions[device] = StorageControlMessage("idle", 0.0, 0.0)

    def _on_peak(self, time):
        if self.peak_start < self.peak_end:
            return self.peak_start <= time % 24 <= self.peak_end
        return not(self.peak_end < time % 24 < self.peak_start)

    def step(self, time):
        """Determine what control actions to take next."""
        self.time = time
        if self._on_peak(time / 3600):
            self._do_discharge()
        else:
            self._do_charge()

    def control_actions(self):
        return self._actions.items()

    def next_update(self):
        return self.time + 300
