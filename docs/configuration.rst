.. _configuration:

========================
Simulation Configuration
========================

Two kinds of configuration files are needed to run the simulation. The firs
is a set of :ref:`federate_config` files which are JSON files used directly
by helics for configuring each federate (see
`<https://docs.helics.org/en/helics3/references/configuration_options_reference.html>`_
for more information about helics configuration options). The other file is
a JSON file specifying the configuration of the grid that is being simulated.
This is described below in :ref:`grid_config`.

.. _grid_config:

Grid Configuration
==================

The configuration of the grid is specified in a JSON file that is passed to
each federate (although not every federate uses every field in the JSON file).
The main fields are

- ``"dss_file"`` which specifies the path to the OpenDSS model file
- ``"storage"`` is a list of storage device specifications (see
  :ref:`storage_config`).
- ``"reliability"`` provides a JSON object specifying the parameters of the
  reliability model.

An example configuration file is shown in :ref:`grid_example`

.. _storage_config:

Storage Device Configuration
----------------------------

These keys are required:

- ``"name"`` is a unique identifier for the device (among all storage devices)
- ``"bus"`` is the OpenDSS bus where the device is connected
- ``"kwrated"`` maximum power output of the device
- ``"kwhrated"`` capacity of the device
- ``"controller"`` is the controller (value can be ``"droop"`` or ``"cycle"``.

If the controller is ``"droop"`` then ``"controller_params"`` is required with
a JSON object as its value containing the keys ``"p_droop"`` and ``"q_droop"``.

Any other keys can be added with names that are valid OpenDSS storage object
parameters (for example ``"%stored"``).

.. _grid_example:

Example Grid Configuration File
-------------------------------

.. literalinclude:: ../examples/grid.json

.. _federate_config:

Federate Configuration
======================

Each federate is initialized from a JSON configuration file. With the exception
of the logger federate, each of federate must have its publications,
subscriptions and endpoints specified in the config file. For storage devices
the configuration looks like this:

.. literalinclude:: ../examples/s1.json

For the grid federate (with two connected storage devices as shown in
:ref:`grid_example`) the federate configuration looks like this:

.. literalinclude:: ../examples/grid-federate.json
