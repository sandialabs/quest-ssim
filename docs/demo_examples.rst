Instructions on Running Demo Examples
=====================================

This document provides instructions on how to run the example case studies present in the paper -

    U. Tamrakar, W. Vining, and J. Eddy, "An Open-Source Tool for Energy Storage Sizing and Placement in 
    Electric Grids," in IEEE EESAT 2025. 

This particular document in not a comprehensive documentation of the tool. The documentation of the tool is available under ``docs`` folder in the repository. 

It is assumed the simulator is already installed. For instructions to install the simulator please refer to:

Required Files
--------------
All the files requried to run the examples cases presented in the paper are available under ``examples`` 
folder of the repository. Following are the list of requried files:

**Files common to all the cases in the paper:**

- OpenDSS grid model: ``examples/ieee34demo/ieee34Mod_temp.dss``
- Irradiance profile: ``examples/ieee34demo/5MinuteIrradiance.csv``

**Sub-folders for each case in the paper:**

- Base case simulation files: ``examples/presentation_demo0``
- Configuration 1 simulation files: ``examples/presentation_demo1``
- Configuration 2 simulation files: ``examples/presentation_demo2``
- Configuration 3 simulation files: ``examples/presentation_demo3``

Each of the sub-folders containts two kinds of configuration files that are needed to run the simulations. The first
is a `federate_config` file which is a JSON file used directly by HELICS for configuring each federate (see`<https://docs.helics.org/en/helics3/references/configuration_options_reference.html>`. 
For more information about helics configuration options). The other file is a `grid_config` JSON file specifying 
the configuration of the grid that is being simulated. The instructions for configuring the JSON files for Configuration 1
is described in the following sections followed by instructions to run it from the CLI. The same procedure applies 
for setting up and running the other configurations as well (with changes in parameters as required). Detailed description of the structure of these files are 
available in ()

Setting up `grid_config` JSON file:
-----------------------------------
The setup of the file ``examples/presentation_demo1/grid_confgi1.json`` is described here.
The fields relevant to these example cases are:

- ``"dss_file"`` which specifies the path to the OpenDSS model file
- ``"storage"`` is a list of storage device specifications
- ``busses_to_log`` and ``busses_to_measure`` specifies the metrics
- ``"pvsystem"`` is a list of PV device specifications
- ``"invcontrol"`` is lost of inverter contro models
- ``"reliability"`` provides a JSON object specifying the parameters of the reliability model.

``"dss_file"``:
^^^^^^^^^^^^^^^
This field points to the OpenDSS model of IEEE 34 bus test system. 
Again this file is available under `examples/ieee34demo/ieee34Mod_temp.dss``. ::

    "dss_file": "../ieee34demo/ieee34Mod_temp.dss"

``"busses_to_log"`` and ``"busses_to_measure"``: 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
These fields are used to configure the metrics. In this example, the metrics are being setup to compare the voltage 
along the diffrerent busses in the test system. The ``"busses_to_log"`` specifies which busses are to be logged. 
Similarly, the ``"busses_to_measure"`` describes how the metrics should be setup. ::


    "busses_to_log": ["814", "828", "860", "840"]

    "busses_to_measure": [
        {"name":  "814", "objective":  1.0, "lower_limit":  0.975, "upper_limit": 1.025, "sense": "SeekValue"},
        {"name":  "828", "objective":  1.0, "lower_limit":  0.975, "upper_limit": 1.025, "sense": "SeekValue"},
        {"name":  "860", "objective":  1.0, "lower_limit":  0.975, "upper_limit": 1.025, "sense": "SeekValue"},
        {"name":  "840", "objective":  1.0, "lower_limit":  0.975, "upper_limit": 1.025, "sense": "SeekValue"}
    ]

``"storage"``:
^^^^^^^^^^^^^^^
This field allows the storage assets to be placed and configured along the test system. In Configuration 1, 
the storage asset is assumeted to be placed at Bus814 (Note that: in the actual file, there are fields for 
other storage assests as well but the controller parameters are set to 0.0 essentially disabling them. This 
is done so that the same file can be repurposed for all the cases with simple modifications to the controller
parameters.) Various parameters of the storage asses are defined here 
which are self explanatory based on the field names. Of particular interest is the field ``"controller"``. 
This allows custom storage controllers to be assigned to the storage asset. In this particular case, a ``"droop"`` 
controller is used. This controller is already available in the simulator. The necessary parameters for the 
controller is based as dictionary through the ``"controller_params"`` field. In this case, the active power droop 
coefficient ``"p_droop"`` and the reactive power droop coefficient ``"q_droop"`` are provided:: 

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
This field allows PV systems to be placed and configured along the test system. The snippet below show the 
configuration for PV802 at bus 802. The other PVs are configured in a similar manner. The ``"irradiance_profile"`` 
field points to the file where the irradiance_profile is stoted. ::

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
This field sets up the parameters for inverter controls that can be assigned to storage/PV assets in the system. The field 
``"der_list`` specifies which PV/storage assets the controller is associated with and ``inv_control_mode`` defines the control 
mode. In these set of examples, the ``"voltvar"`` controllers are enabled for PV assets at bus 850 and 860 
so the field ``"der_list`` is set to ``["PVsystem.PV850", "PVsystem.PV860" ]`` and the field ``inv_control_mode`` 
is set to  ``"voltvar"``. The field ``"function_curve_1"`` specifices a XY curve that the controller will folow.
A detailed description of these control modes can be found at (). ::

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
This field sets up the parameters for reliability studies. Default values are used as these are not very 
relevant to the voltage regulation example being presented in the paper.

Setting up `federate_config` JSON file:
---------------------------------------
The setup of the file ``examples/presentation_demo1/federation_confgi1.json`` is described here. As mentioned 
earlier, this is a JSON file used directly by HELICS for configuring each federate in the co-simulation. Only 
a few parameters/fields are relevant to setup and run the examples presented in the paper. The first field is 
the ``"federates"`` field which sets up all the federates within a HELICS co-simulation. The first value for field 
is: ::

    {
      "directory": ".",
      "exec": "helics_broker -f 8",
      "host": "localhost",
      "name": "broker"
    }

This setup the helics_broker and specifices how many federates are setup. In this case this value is set to 8.
This includes 4 federates for the storage simulation (one at each critical bus), 1 for the grid simulation, 
1 for the reliability simulation, 1 for the logger and the final 1 for the metrics federate. Each federate is 
then configured separately. For example, the federate for stoage at bus 814 is setup as follows: ::

    {
      "directory": ".",
      "exec": "storage-federate S814 --hours 24 grid_config1.json ../../ssim/federates/storage.json",
      "host": "localhost",
      "name": "s814"
    }

Here, within the 'exec' field, the name ``S814`` must match the storage name provided in the grid 
configuration files. Similary ``-hours 24`` specifices the simulaton time in hours, this is followed by 
the name of the grod configuration file `` grid_config1.json ``.