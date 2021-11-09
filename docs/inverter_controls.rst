===========================
Inverter Controls Overview
===========================

The inverter controls for PVs and energy storage systems are implemented based
on OpenDSS. The following inverter controls are available:

- Limiting DER power
- Constant power factor
- Constant reactive power
- Volt-Var function
- Volt-Watt function
- Dynamic Reactive Current (DRC) function
- Watt-pf function

These functions can be implemented using the JSON configurations files by
defining appropriate function curves and assoicated parameter settings. The
following sections will describe each of these inverter functions and provide
details about implementing them in this simulator.

Limiting DER power
___________________
This function establishes an upper limit on the real power that the DER
can produce/discharge and charge at its interface with the grid. This function
can be enabled by defining appropriate parmeters while defining the DER units
in the JSON config files. For storage, it is specified by defining the
property ``%kWRated`` which applies to both charging and discharging states.
For PV systems, it is specified through the property ``%Pmpp``. In both cases,
the default value is 100% meaning that the function is disabled.

Constant power factor
_____________________
This function is enabled by setting the property ``pf`` of the DER unit to the
desired value.

Constant reactive power
_______________________
This function is enabled by setting the property ``kvar`` of the DER unit to
the desired value.

To properly setup inverter controls, two sets of properties needs to be defined
for the functions. The first set of properties are common to all the inverter
functions while the second set are properties specific to each inverter
function. These can either be Reactive Power Control, Active Power Limit or
both. These properties can be set while defining the inverter controls through
the JSON configuration files.

Common Parameters for Inverter Functions
_________________________________________
The common parameters that need to be defined for inveter functions are:

- ``der_list``:

- ``inverter_control_mode``:

- ``voltage_curvex_ref``: Base voltage used to normalize (compute per-unit values) of the monitored voltage. The options are listed below:
    - ``rated``: Uses the rated voltage of the controlled DER unit as the base voltage. In other words, 1.0 in the volt-var curve equals rated voltage.
    - ``avg``: Uses an average value calculated using the monitored votlage of previous time steps that are stored in a moving window. The window has length in units of time defined using the parameter ``avgwindowlen``.
    - ``ravg``: Uses the rated voltage of the controlled DER unit as the base voltage. Same as avg, with the exception that the avgerage terminal voltage is divided by the rated voltage.

- ``avgwindowlen``: Sets the length of the averaging window over which the average DER terminal voltage is calculated. Units are indicated by appending s, m, or h to the integer value. Defaults to 0 seconds.

- ``voltageChangeTolerance``: Tolerance in per-unit of the control loop convergence associated to the monitored voltage in per-unit. Defaults to 0.0001 pu.
- ``RateofChangeMode``: Limits the changes of the reactive power and the active power between time steps. Defaults to ``INACTIVE``. The options are as follows:
    - ``INACTIVE``: Indicates no limit on rate of change for either active or reactive power output.
    - ``LPF``: A low-pass filter will be applied to the reactive or active power output as a function of a time constant defined by the parameter ``LPFTau``.
    - ``RISEFALL``: A rise and fall limit in the change of active and/or reactive power expressed in terms of pu power per second, defined in the parameter ``RiseFallLimit``, is applied to the desired reactive power and/or the active power limit.
- ``LPFTau``: Filter time constant of the LPF option of the RateofChangeMode property. The time constant will cause the low-pass filter to achieve 95% of the target value in 3 time constants. Defaults to 0 seconds.
- ``RiseFallLimit``: Limit in power in pu per second used by the ``RISEFALL`` option of the ``RateofChangeMode`` paramter.The base value for this ramp is defined in the ``RefReactivePower`` parameter and/or in ``VoltwattYAxis`` parameter.
- ``monBus``: Name of monitored bus used by the voltage-dependent control modes. Default is bus of the controlled DER unit.
- ``monBusesVbase``: Array list of rated voltages of the buses and their nodes presented in the ``monBus`` parameter. This list may have different line-to-line and/or line-to-ground voltages.
- ``monVoltageCalc``:


Parameters that Control Reactive Power
______________________________________
These parameters control the reactive power of the DER unit being controlled.
These parameters effect the following inverter functions - volt-var, DRC,
watt-var.

- ``RefReactivePower``:
- ``VarChangeTolerance``:
- ``deltaQ_factor``: Sets the maximum change (in per unit) from the prior var output level to the desired var output level during each control iteration. Defaults to -1.0 meaning OpenDSS engine take care of selection of this factor internally.

Parameters that Limit Active Power
__________________________________
These parameters limit the active power of the DER unit being controlled. These
parameters mainly effect the volt-watt function:

- ``ActivePChangeTolerance``:
- ``deltaP_factor``:
- ``VoltwattYAxis``:

Parameters for DRC function
___________________________
These parameters define the operating charactersitics of the DRC inverter
function:

- ``DbvMin``:
- ``DbvMax``:
- ``ArGraLowV``:
- ``ArGraHiV``:
- ``DynReacavgwindowlen``: