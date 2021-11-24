===========================
Inverter Controls Overview
===========================

The inverter controls for Distributed Energy Resources (DERs) like PVs and
energy storage systems are implemented based on OpenDSS. The following inverter
controls are available:

- Limiting DER power output
- Constant power factor
- Constant reactive power
- Volt-Var function
- Volt-Watt function
- Watt-pf function
- Combined Volt-Var and Volt-Watt Function

These functions can be implemented using the JSON configurations files by
defining appropriate function curves and associated parameter settings. An
example configuration is provided in ``examples/demo_inv/controls/
federation.json``. The following following sections will describe each of these
inverter functions and provide details about implementing them in this
simulator.

Inverter controls implemented using DER parameters
__________________________________________________
The functions *Limiting DER power output*, *Constant power factor*, and
*Constant reactive power* can be setup by defining associated parameters of
the DER units while defining the DER units in the JSON configuration files.

Limiting DER power output
~~~~~~~~~~~~~~~~~~~~~~~~~
This function establishes an upper limit on the active power that the DER
can produce/discharge and charge at its interface with the grid. This function
can be enabled by defining appropriate parameters while defining the DER unit(s)
in the JSON configuration file (``grid.json``). For storage, it is specified by
defining the property ``%kWRated`` which applies to both charging and
discharging states. For PV systems, it is specified through the property
``%Pmpp``. In both cases, the default value is 100% meaning that the function
is disabled. In the example shown below the upper limit on the active power of
the storage unit ``S1`` is set to 75%.  ::

    "storage": [
        {
            "name": "S1",
            "bus": "671",
            "phases": 3,
            "kwrated": 500,
            "kwhrated": 5000,
            "%stored": 50,
            "kW": 400,
            "%kWRated": 75,
            "kV": 4.16,
            "controller": "external",
            "controller_params": {
                "p_droop": 0,
                "q_droop": 0
            }
        }
    ]


Constant power factor
~~~~~~~~~~~~~~~~~~~~~
This function is enabled by setting the property ``pf`` of the DER unit to the
desired value while defining the DER unit(s) in the JSON configuration file. The
default value if 1.0 for unity power factor operation. A positive power factor
means that the DER unit injects reactive power at its interface with the grid.
a negative power factor, on the other hand, will absorb reactive power.
In the example shown below the ``pf`` property of the storage unit ``S1`` is
set to a constant value of 0.8: ::

    "storage": [
        {
            "name": "S1",
            "bus": "671",
            "phases": 3,
            "kwrated": 500,
            "kwhrated": 5000,
            "%stored": 50,
            "kW": 400,
            "pf": 0.8,
            "kV": 4.16,
            "controller": "external",
            "controller_params": {
                "p_droop": 0,
                "q_droop": 0
            }
        }
    ]

Constant reactive power
~~~~~~~~~~~~~~~~~~~~~~~
This function is enabled by setting the property ``kvar`` of the DER unit to
the desired value while defining the DER unit(s) in the JSON configuration file.

Inverter controls implemented using defining a inverter controller
___________________________________________________________________
To properly setup the remaining inverter controls, two sets of properties need
to be defined. The first set of properties are common to all the inverter
functions while the second set is specific to each inverter
function. These can either be Reactive Power Control, Active Power Limit or
both. These properties can be set while defining the inverter controls through
the JSON configuration files.

Common Parameters for Inverter Functions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The common parameters that need to be defined for all inverter functions are:

#. ``der_list``: List of DER units to be controlled by the defined inverter controller.If this parameter is not specified, all the DER units in the model will be controlled by the defined inverter controller. ::

    "der_list": ["PVsystem.PV1", "PVsystem.PV2", "Storage.S1"]

#. ``inverter_control_mode``: Name of inverter control function to be enabled. The valid values for the available functions are: *voltvar*, *voltwatt*, *wattpf*, *wattvar*, *vv_vw* : ::

   "inverter_control_mode": "vv_vw"

#. ``voltage_curvex_ref``: Required for ``VOLTVAR`` and ``VOLTWATT`` modes. Base voltage used to normalize (compute per-unit values) of the monitored voltage. The options are listed below:

   #. ``rated``: Uses the rated voltage of the controlled DER unit as the base voltage. In other words, 1.0 in the volt-var curve equals rated voltage.
   #. ``avg``: Uses an average value calculated using the monitored votlage of previous time steps that are stored in a moving window. The window has length in units of time defined using the parameter ``avgwindowlen``.
   #. ``ravg``: Uses the rated voltage of the controlled DER unit as the base voltage. Same as avg, with the exception that the avgerage terminal voltage is divided by the rated voltage.

#. ``avgwindowlen``: Required for ``VOLTVAR`` and ``VOLTWATT`` modes. Sets the length of the averaging window over which the average DER terminal voltage is calculated. Units are indicated by appending s, m, or h to the integer value. Defaults to 0 seconds.

#. ``voltageChangeTolerance``: Tolerance in per-unit of the control loop convergence associated to the monitored voltage in per-unit. The inverter control loop converges if the terminal voltage of the DER unit between two consecutive iterations is less than this value. Defaults to 0.0001 pu.

#. ``RateofChangeMode``: Required for ``VOLTVAR`` and ``VOLTWATT`` modes. Limits the changes of the reactive power and the active power between time steps. Defaults to ``INACTIVE``. The options are as follows:

   #. ``INACTIVE``: Indicates no limit on rate of change for either active or reactive power output.
   #. ``LPF``: A low-pass filter will be applied to the reactive or active power output as a function of a time constant defined by the parameter ``LPFTau``.
   #. ``RISEFALL``: A rise and fall limit in the change of active and/or reactive power expressed in terms of pu power per second, defined in the parameter ``RiseFallLimit``, is applied to the desired reactive power and/or the active power limit.

#. ``LPFTau``: Filter time constant of the LPF option of the RateofChangeMode property. The time constant will cause the low-pass filter to achieve 95% of the target value in 3 time constants. Defaults to 0 seconds.

#. ``RiseFallLimit``: Limit in power in pu per second used by the ``RISEFALL`` option of the ``RateofChangeMode`` paramter.The base value for this ramp is defined in the ``RefReactivePower`` parameter and/or in ``VoltwattYAxis`` parameter.

#. ``monBus``: Name of monitored bus used by the voltage-dependent control modes. Default is bus of the controlled DER unit.

#. ``monBusesVbase``: Array list of rated voltages of the buses and their nodes presented in the ``monBus`` parameter. This list may have different line-to-line and/or line-to-ground voltages.

#. ``monVoltageCalc``: .

Parameters that Control Reactive Power
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
These parameters control the reactive power of the DER unit being controlled.
These parameters effect the following inverter functions - volt-var, DRC,
watt-var.

#. ``RefReactivePower``: Required for ``VOLTVAR`` and ``WATVAR`` mode. Defines the base reactive power according to one of the following options:

   #. ``VARAVAL``: The base values are equal to the available reactive power.
   #. ``VARMAX``: The base values are equal to the value defined in the ``kvarMax`` and ``kvarMaxAbs`` properties of the DER units. These properties need to be defined when adding the DER units through the JSON configuration files.


#. ``VarChangeTolerance``: Required for ``VOLTVAR`` mode. Tolerance in per-unit of the control loop convergence associated with the reactive power. Defaults to 0.025 per unit of the base provided or absorbed reactive power described in the ``RefReactivePower`` property. The inverter control loop converges if the reactive power of the DER unit between two consecutive iterations is less than this value.

#. ``deltaQ_factor``:  Required for ``VOLTVAR`` mode. The y-axis corresponds to the value in pu of the kVA property of the PVSystem.Sets the maximum change (in per unit) from the prior var output level to the desired var output level during each control iteration. Defaults to -1.0 meaning OpenDSS engine take care of selection of this factor internally.

Parameters that Limit Active Power
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
These parameters limit the active power of the DER unit being controlled. These
parameters mainly effect the volt-watt function:

#. ``ActivePChangeTolerance``: Required for ``VOLTWATT`` mode. Tolerance in per-unit of the control loop convergence associated with the active power. The inverter control loop converges if the active power of the DER unit between two consecutive iterations is less than this value. Defaults to 0.01.

#. ``deltaP_factor``: Required for ``VOLTWATT`` mode.  Sets the maximum change (in unit of the y-axis) from the prior active power output level to the desired active power output level during each control iteration. Defaults to -1.0 meaning OpenDSS engine take care of selection of this factor internally. Possible range of values is between 0.05 and 1.0.

#. ``VoltwattYAxis``: Required for ``VOLTWATT`` mode. Specifies the units for the y-axis of the volt-watt curve. The following options are allowed (Defaults to PMPPU), TO DO: for Storage?:

   #. ``PMPPPU``: TThe y-axis corresponds to the value in pu of Pmpp property of the PVSystem.
   #. ``PAVAILABLEPU``: The y-axis corresponds to the value in pu of the available active power of the PVSystem.
   #. ``PCTPMPPPU``: The y-axis corresponds to the value in pu of the power Pmpp multiplied by 1/100 of the %Pmpp property of the PVSystem.
   #. ``KVARATINGPU``:  The y-axis corresponds to the value in pu of the kVA property of the PVSystem.
