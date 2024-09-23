Instructions on Running Demo Examples
=====================================

This document provides instructions on how to run the example case studies present in the paper -

    U. Tamrakar, W. Vining, and J. Eddy, "An Open-Source Tool for Energy Storage Sizing and Placement in 
    Electric Grids," in IEEE EESAT 2025. 

The comprehensive documentation of the tool is available under ``docs`` folder in the repository.

It is assumed the simulator is already installed. For instructions to install the simulator please refer to:

Required Files
--------------
All the requried files to run the examples cases presented in the paper are available under ``examples`` 
folder of the repository. Following are the list of requried files:

**Files common to all the cases in the paper:**

- OpenDSS grid model: ``examples/ieee34demo/ieee34Mod_temp.dss``
- Irradiance profile: ``examples/ieee34demo/5MinuteIrradiance.csv``

**Sub-folders for each case in the paper:**

- Base case simulation files: ``examples/presentation_demo0``
- Configuration 1 simulation files: ``examples/presentation_demo1``
- Configuration 2 simulation files: ``examples/presentation_demo2``
- Configuration 3 simulation files: ``examples/presentation_demo3``

Each of the sub-folders containts two kinds of configuration files are needed to run the simulation. The first
is a `federate_config` files which is a JSON file used directly by HELICS for configuring each federate (see`<https://docs.helics.org/en/helics3/references/configuration_options_reference.html>`_
for more information about helics configuration options). The other file is a `grid_config` JSON file specifying 
the configuration of the grid that is being simulated. The instructions for configuring the JSON files for Configuration 1
is described in the following sections followed by instructions to run it from the CLI. The same procedure applies 
for setting up and running the other configurations. Detailed description of the structure of these files are 
available in

Setting up `grid_config` JSON file:
-----------------------------------
The fields relevant to this example cases are:

- ``"dss_file"`` which specifies the path to the OpenDSS model file
- ``"storage"`` is a list of storage device specifications
- ``busses_to_log`` and ``busses_to_measure`` specifies the metrics
- ``"pvsystem"`` is a list of PV device specifications
- ``"invcontrol"`` is lost of inverter contro models
- ``"reliability"`` provides a JSON object specifying the parameters of the reliability model.

``"dss_file"``:
^^^^^^^^^^^^^^^
This field points to the OpenDSS model of IEEE 34 bus test system: ::

    "dss_file": "../ieee34demo/ieee34Mod_temp.dss"

``"busses_to_log"`` and ``"busses_to_measure"``: 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
These fields are used to configure the metrics ::


    "busses_to_log": ["814", "828", "860", "840"]

    "busses_to_measure": [
        {"name":  "814", "objective":  1.0, "lower_limit":  0.975, "upper_limit": 1.025, "sense": "SeekValue"},
        {"name":  "828", "objective":  1.0, "lower_limit":  0.975, "upper_limit": 1.025, "sense": "SeekValue"},
        {"name":  "860", "objective":  1.0, "lower_limit":  0.975, "upper_limit": 1.025, "sense": "SeekValue"},
        {"name":  "840", "objective":  1.0, "lower_limit":  0.975, "upper_limit": 1.025, "sense": "SeekValue"}
    ]

``"storage"``:
^^^^^^^^^^^^^^^
Setting up :: 

    "storage": [
        {
            "name": "S814",
            "bus": "814",
            "phases": 3,
            "kwrated": 1000,
            "kva": 1100,
            "kwhrated": 3000,
            "%stored": 50,
            "kV": 24.9,
            "controller": "droop",
            "controller_params": {
                "p_droop": 10000,
                "q_droop": 15000
            }
        }
    ]

``"pvsystem"``:
^^^^^^^^^^^^^^^
Setting up ::

    "pvsystem": [
        {
            "name": "PV802",
            "bus": "802",
            "phases": 3,
            "pmpp": 500,
            "kva_rated": 550,
            "kV": 24.9,
            "irradiance_profile": "../ieee34demo/5MinuteIrradiance.csv",
            "inverter_efficiency": {"x":  [10, 50, 90, 100],
                                    "y":  [0.90, 0.94, 0.98, 0.99]},
            "pt_curve": {"x": [0, 25, 75, 100], "y":  [1.2, 1.0, 0.8, 0.6]}
        }
    ]

``"invcontrol"``:
^^^^^^^^^^^^^^^^^
Setting up ::

    "invcontrol": [
            {
                "name": "InvCtrl1",
                "der_list": ["PVsystem.PV850", "PVsystem.PV860" ],
                "inv_control_mode": "voltvar",
                "function_curve_1": {"x":  [0.5, 0.95, 1.0, 1.05, 1.5],
                                     "y":  [1.0, 1.0, 0.0, -1.0, -1.0]}
            }
        ]

``"reliability"``:
^^^^^^^^^^^^^^^^^

Setting up `federate_config` JSON file:
-----------------------------------