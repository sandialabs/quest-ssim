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
- ``voltage_curvex_ref``:
- ``avgwindowlen``:
- ``voltageChangeTolerance``:
- ``RateofChangeMode``:
- ``RiseFallLimit``:
- ``LPFTau``:
- ``monBus``:
- ``monBusesVbase``:
- ``monVoltageCalc``:


Parameters that Control Reactive Power
______________________________________
These parameters control the reactive power of the DER unit being controlled.
These parameters effect the following inverter functions - volt-var, DRC,
watt-var.

- ``RefReactivePower``:
- ``VarChangeTolerance``:
- ``deltaQ_factor``:

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