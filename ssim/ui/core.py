"""Core classes and functions for the user interface."""


class Project:
    """A set of grid configurations that make up a complete study."""

    def __init__(self, name: str):
        self.name = name
        self._grid_model = None
        self._storage_options = None
        self._metrics = None


class Configuration:
    """A specific grid configuration to be evalueated."""

    def __init__(self, id, grid, storage_devices):
        self.results = None

    def evaluate(self):
        pass

    def is_evaluated(self):
        return self.results is not None


class Results:
    """Results from simulating a specific configuration."""

    def __init__(self):
        pass

