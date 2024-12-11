.. storage-sim documentation master file, created by
   sphinx-quickstart on Thu Feb 11 10:06:46 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

QuEST-SSim
==========

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   api
   ems
   configuration
   inverter_controls
   metrics
   demo_examples
   changelog

Installation
------------

The SSim package is available on pypi. You can install it via::

  pip install quest-ssim


Quick Start
-----------

A quick start guide describing how to launch, configure, and run the
simulator is available on `OSTI <https://www.osti.gov/servlets/purl/2430055>`_.

Running the simulation
----------------------

You may launch the GUI with the ``ssim`` command, or use HELICS CLI to run the
simulator directly. An example configuration for the HELICS CLI is provided in
``examples/demo_670/federation.json`` (shown below):

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
