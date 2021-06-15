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
