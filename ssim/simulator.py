"""Functions for initializing and running the simulation."""
import logging
import time
from multiprocessing import Process

from helics import helicsCreateBroker

from ssim.federates import storage, opendss, logger

_BROKER_NAME = "ssimbroker"


def _helics_broker():
    """Start the helics broker"""
    logging.basicConfig(format="[broker] %(levelname)s - %(message)s",
                        level=logging.DEBUG)
    logging.debug(f"starting broker {_BROKER_NAME}")
    broker = helicsCreateBroker("zmq", "", f"-f3 --name={_BROKER_NAME}")
    logging.debug(f"created broker: {broker}")
    logging.debug(f"broker connected: {broker.is_connected()}")
    while broker.is_connected():
        # busy wait until the broker exits.
        time.sleep(1)


def run_simulation(opendss_file, storage_devices, hours,
                   loglevel=logging.WARN):
    """Simulate the performance of the grid with attached storage.

    Parameters
    ----------
    opendss_file : PathLike
        Grid model file.
    storage_devices : dict
        Dictionary keys are storage names, values are dictionaries with
        keys 'kwhrated', 'kwrated', and 'bus' which specify the kWh rating,
        the maximum kW rating, and the bus where the device is connected
        respectively.
    hours : float
        Number of hours to simulate.
    """
    broker_process = Process(target=_helics_broker, name="broker")
    grid_process = Process(
        target=opendss.run_opendss_federate,
        args=(opendss_file,
              {storage_name:
                  {'bus': specs['bus'],
                   'params': {param: value
                              for param, value in specs.items()
                              if param != 'bus'}}
               for storage_name, specs in storage_devices.items()},
              hours,
              loglevel),
        name="grid_federate"
    )
    storage_process = Process(
        target=storage.run_storage_federate,
        args=(storage_devices,
              hours,
              loglevel),
        name="storage_federate"
    )
    power_logger = Process(
        target=logger.run_logger,
        args=(loglevel,
              {specs['bus'] for specs in storage_devices.values()},
              set(storage_devices.keys()),
              hours,
              True),
        name="logger_federate"
    )
    logging.info("starting broker")
    broker_process.start()
    logging.info("starting federates")
    power_logger.start()
    grid_process.start()
    storage_process.start()

    logging.info("running...")
    power_logger.join()
    broker_process.join()
    grid_process.join()
    storage_process.join()
    logging.info("done.")
