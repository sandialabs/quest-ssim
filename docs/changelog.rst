----------
Change Log
----------

.. _changelog-100beta4:

1.0.0.beta4
-----------

December 12, 2024

* Enhancements to configuration filtering.
* Replaced results lists with ``RecycleView`` to improve UI performance.
* Lowered default log levels of federates.
* Enable configuration of simulation duration from the UI.
* Pin the required version of OpenDSSDirect to less than 0.9.0. OpenDSSDirect
  made a number of breaking changes with version 0.9, and we are not ready to
  upgrade at this time.
* Add the ability to configure PV systems to be included in the set of
  configurations that will be evaluated.
* Major refactoring of inverter and storage control configuration classes and
  screens to support the addition of PV systems.
* Fix the number of phases that PV and Storage elements added via the UI are
  connected to.
* Added capability to load a file directly into the UI without requiring the use
  of the file chooser dialogue.
* Added the ability to configure the base directory where all files will be
  written via the TOML project file.
* Added :ref:`instructions for running the examples <demo-examples>`
  to the documentation.

.. _changelog-100beta3:

1.0.0.beta3
-----------

February 14, 2024

* Bump to the latest version of HELICS (3.3); work around problems with HELICS
  versions above 3.1.2.post8 that resulted in a live lock in the co-simulation.
* API documentation improvements.
* Cleaned up the examples.
* Add filtering capability to the configuration list.
* Replace the configuration list with a ``RecycleView`` to improve UI
  performance.
* Renamed the package from ``storage-sim`` to ``quest-ssim``.

.. _changelog-100beta2:

1.0.0.beta2
-----------

November 7, 2023

* Bug fixes for metric normalization & serialization.
* Remember selections in UI menus.
* Fix inverter kVA rating in grid simulation.
* Draw storage symbols on grid map to indicate where storage devices may be
  placed.
* Create checkpoints of the project to enable users to revisit previous
  configurations after making changes to either the grid model or the storage
  options.
* Added filtering capabilities for the bus list.
* Replaced the bus list with a ``RecycleView`` to improve UI performance.

.. _changelog-100beta1:

1.0.0.beta1
-----------

June 14, 2023

* Core co-simulation functionality.
* Configure simulations via JSON files and launch via the HELICS CLI.
* Records performance metrics and measurements from the grid simulation &
  storage elements.
* Basic graphical user interface for configuring and launching the simulation.
