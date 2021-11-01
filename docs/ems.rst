========================
Energy Management System
========================

The energy management system is implemented as a helics message federate
that communicates with storage controllers, the reliability federate, and
the grid federate.

It receives information about the state of charge of the storage
devices, the status of generators, and the status of loads connected
to the grid and sends messages to each storage controller and to the
gird federate containing set-points for storaged devices and
dispatchable generators.

The EMS als receives reliability events in order to track isolated
sections of the grid (e.g. PV systems, storage devices, and loads that
are disconnected from the grid and therefore should be excluded from
the dispatch decisions) or other failures that should be accounted for
in dispatch decisions.

HELICS Interface
================

The EMS federate provides two endpoints to which other federated can
send messages. Reliability messages are received on the
"ems/reliability" endpoint and status messages for components such as
generators or storage devices are received on the "ems/control"
endpoint. The "ems/control" endpoint is also the source of messages
sent from the EMS federate to dispatch storage and generators, or to
perform other control actions in the grid.

Status messages, sent to the EMS federate, are JSON representations of
dataclasses that inherit from :py:class:`ssim.grid.StatusMessage`. See
:ref:`status_messages` for more information.

Grid Federate Endpoints
-----------------------

The following global endpoints are used by the grid federate for
communication with the EMS federate.

- ``"load.control"`` Single endpoint used to send load status messages to
  the EMS. A separate message is send for each load.
- ``"pvsystem.{name}.control"`` Sends status of a PV system to the EMS
  (one endpoint per PV system).
- ``"generator.{name}.control"`` Sends status of generators to the ems
  (one endpoint per generator).

Storage Controller Endpoints
----------------------------

- ``"storage.{name}.control"`` Sends status of a storage device to the
  EMS and receives control messaged from the EMS.

EMS Interface Overview
----------------------

The diagram below shows an overview of the endpoints described above.

.. digraph:: ems_helics

   graph [rankdir=LR];
   node [style=rounded];

   ems [label="EMS"; shape=record; style=rounded];
   s1 [label="<f0> s1 controller| <control> storage.s1.control | <soc> soc";
       shape=record; style=rounded];
   grid [label="grid federate | <total_load> total power | <pv1> pvsystem.pv1.control | ... | <gen1> generator.gen1.control | ... | <load> load.control | <s1_soc> storage.s1.soc | <other> ...";
         shape=record];
   reliability [label="reliability federate"; shape=record];
   clone [label="cloning filter"; shape=ellipse];

   ems -> s1:control [label="power setpoint"];
   grid:s1_soc -> s1:soc;
   grid:load -> ems [label="load status*"];
   grid:pv1 -> ems [label="pv1 status"];
   grid:gen1 -> ems [label="gen1 status"];
   grid:total_load -> ems;
   s1:control -> ems [label="soc"];
   reliability -> clone [label="failure/restoration events"];
   clone -> {ems grid:other};

.. _status_messages:

Status Messages
===============

The following dataclasses are used to represent status messages sent
from other federates to the EMS.

.. autoclass:: ssim.grid.StorageStatus
   :members:
   :undoc-members:

.. autoclass:: ssim.grid.PVStatus
   :members:
   :undoc-members:

.. autoclass:: ssim.grid.GeneratorStatus
   :members:
   :undoc-members:

.. autoclass:: ssim.grid.LoadStatus
   :members:
   :undoc-members:

Each status message class inherits from

.. autoclass:: ssim.grid.StatusMessage
   :members:
