.. storage-sim documentation master file, created by
   sphinx-quickstart on Thu Feb 11 10:06:46 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to storage-sim's documentation!
=======================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   api
   ems
   configuration
   metrics

Running the simulation
----------------------
Use Helics CLI to run the simulator. HELICS CLI can be installed with::

  pip install git+git://github.com/GMLC-TDC/helics-cli.git@main

An example configuration is provided in ``examples/federation.json`` (shown
below):

.. literalinclude:: ../examples/demo_670/federation.json

Running this with::

 helics run --path examples/demo_670/federation.json

will start the grid federate, two storage controllers, the reliability
federate, and the logger federate. When the simulation finishes a variety of
matplotlib figures will be displayed.

For more information on configuring each federate see :ref:`configuration`.

Each federate has its own ``console_scripts`` entry point, which take several
command line arguments specifying how long to run for and the paths to the
configuration files. These entry points are:

- ``storage-federate``
- ``grid-federate``
- ``reliability-federate``
- ``logger-federate``

For an overview of the options you can pass to each entry point use ``--help``.
For example::

 storage-federate --help

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
