========================
Energy Management System
========================

The energy management system is implemented as a helics message federate
that communicates with storage controllers, the reliability federate, and
the grid federate.

It receives information about the state of charge of the storage devices, and
sends messages to each storage controller instructing it to charge, discharge,
or idle at a particular rate.

The EMS is also tracks reliability events in order to account for isolated
sections of the grid (e.g. PV systems, storage devices, and loads
that are disconnected from the grid and therefore should be excluded from the
dispatch decisions).

EMS API
=======

The EMS needs information about dispatchable generators and loads (storage)
as well as forecasts for the load and for DER generation.

Load Forecasts
--------------

We need forecasts at different time-scales. We should plan to support
forecasts ranging from five minutes to a month ahead. As a starting point,
however, 48-hours ahead should be sufficient. (Prescient uses this time scale
to calculate hourly unit-commitment over a 24 hour period, producing a new
unit commitment plan evey 24 hours with an overlapping 48-hour forecast.)

DER Forecasts
-------------

It seems like a reasonable approach to include DER forecasts separately from
load forecasts. Ideally we should have one forecast for each DER connected
to the grid. Need same time-scales as the load forecasts, but might need some
smaller time-scales as well to support minute-by-minute dispatch decisions.

For solar we can use ``pvlib.forecast``. This module provides APIs for
accessing forecast data from various models.

Storage Specs
-------------

Need to know the storage capacity, charge/discharge limits, current state of
charge, minimum/maximum state of charge (could these change?), idling losses.

HELICS Interface
================

The interface between the EMS and the other simulation federates received
information about the current state of charge of the storage devices, the
current state of the grid (whether any components are not functioning or
are isolated), and any active threats (either before the thread occurs, or
during the threat itself). The federate sends dispatch messages to the storage
controllers.

.. We may want to do more than this in the future, but for now this is a
   good starting point. Only control storage devices, and leave the rest
   for future work. In addition to only implementing control over storage
   devices, the handling of "threat" events described above is for planning
   more than immediate implementation (since the "threat federate" does not
   exist yet).

The interface described above will necessitate an endpoint for sending
control messages to storage controllers (along with an endpoint for receiving
control messages at each controller. Additionally it will need an endpoint
for receiving reliability messages.

There are a couple options for the interface that receives the state of charge
of the storage devices. The easiest approach is to just subscribe to the value
published by the grid federate ("grid/storage.<name>.soc"), but that implies
the the EMS is directly sensing the state of charge from the storage devices.
A more realistic approach is to send the state of charge in a message from
the controller federate for each device.

.. digraph:: ems_helics

   graph [rankdir=LR];
   node [style=rounded];

   ems [label="EMS"; shape=record; style=rounded];
   s1 [label="<f0> s1 controller| <control> control endpoint| <soc> soc";
       shape=record; style=rounded];
   grid [label="grid federate | <load> total power | <s1_soc> storage.s1.soc | <other> ...";
         shape=record];
   reliability [label="reliability federate"; shape=record];
   clone [label="cloning filter"; shape=ellipse];

   ems -> s1:control [label="(dis)charging power"];
   grid:s1_soc -> s1:soc;
   grid:load -> ems;
   s1:control -> ems [label="soc"];
   reliability -> clone [label="failure/restoration events"];
   clone -> {ems grid:other};

Time
====

There are a few options for how the federate manages time. I believe it is not
very realistic for it to operate at every time granted to the grid federate.
There will be some fixed interval at which devices are dispatched which will
vary depending on the dispatch model/tool that is being used (for example,
Prescient uses 5-minutes for economic dispatch and 24-hours for unit
commitment).