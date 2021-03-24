Public API Overview
===================

The initial target for this project is as a component of the QuESt
tool. This will shape the public API we develop for configuring,
running, and collecting the results from simulations. QuESt is a
component-based tool for evaluating energy storage technologies. This
gives us a fair amount of flexibility for developing the storage simulator
API since when it is integrated into QuESt it will require a wrapper that
loads user data and presents the simulation results. As a minimum we should
expose three core features: simulation configuration, reporting the progress
of the simulation, and reporting the simulation results.

Configuring a Simulation
------------------------

To configure a simulation we need the following information:

- a grid model
- a storage device (or set of storage devices)
- a location where the device is connected to the grid
- a set of load profiles, or load models
- a set of generation profiles or models for renewables connected to the grid



Running a Simulation
----------------------

To run the simulation we need to know the following:

- how long to run (stopping criteria)

If possible, we should also provide and API that supports querying the
simulation progress. At the very least this could just be the something that
returns the simulation clock to indicate that progress is being made.

.. automodule:: ssim.simulator
   :members:

Reporting Results
-----------------

Once a simulation has finished we need to collect the statistics recorded
while it was running. The simplest way to report results is via a results
object. QuESt can be responsible for analysis and presentation of the data.

Device API
----------

ssim.storage
^^^^^^^^^^^^

.. automodule:: ssim.storage
   :members:

OpenDSS API
-----------

These modules provide an API for interacting with devices in an OpenDSS
model.

ssim.opendss
^^^^^^^^^^^^

.. automodule:: ssim.opendss
   :members:
   :show-inheritance:

ssim.dssutil
^^^^^^^^^^^^

.. automodule:: ssim.dssutil
   :members:

Federates
---------

ssim.federates.opendss
^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ssim.federates.opendss
   :members:
   :show-inheritance:

ssim.federates.storage
^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ssim.federates.storage
   :members:
   :show-inheritance:

ssim.federates.logger
^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ssim.federates.logger
   :members:
   :show-inheritance:
