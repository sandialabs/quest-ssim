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

.. literalinclude:: ../examples/demo_670/grid.json

.. _federate_config:

Federate Configuration
======================

Federates are configured using JSON configuration files that are distributed
with the SSim application. These files are found in the
:py:mod:`ssim.federates` subpackage. The grid federate configuration, for
example, is found in ``ssim/federates/grid.json``

.. literalinclude:: ../ssim/federates/grid.json

You should not need to change these configurations. Customizable parameters are
exposed by the command line arguments of the federate programs and additional
customization is performed automatically based on the details of the simulation.