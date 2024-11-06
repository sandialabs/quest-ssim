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

To run the simulator it needs to be installed. Run this from the root
directory of the repository::

  pip install -e .

This will install the stand-alone programs that are repsonsible for running
each federate. To run a simulation use the `helics_cli`. For example, from the
``examples`` directory::

  helics run --path=federation.json

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

Metrics API
-----------

ssim.metrics
^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ssim.metrics
   :members:
   :show-inheritance:


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
   
ssim.federates.metrics
^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: ssim.federates.metrics
   :members:
   :show-inheritance:
