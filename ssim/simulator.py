"""Functions for initializing and running the simulation."""
import logging
import time
from multiprocessing import Process

from helics import helicsCreateBroker

from ssim.federates import storage, opendss


_BROKER_NAME = "ssimbroker"


def _helics_broker():
    """Start the helics broker"""
    logging.basicConfig(format="[broker] %(levelname)s - %(message)s",
                        level=logging.DEBUG)
    logging.debug(f"starting broker {_BROKER_NAME}")
    broker = helicsCreateBroker("zmq", "", f"-f2 --name={_BROKER_NAME}")
    logging.debug(f"created broker: {broker}")
    logging.debug(f"broker connected: {broker.is_connected()}")
    while broker.is_connected():
        # busy wait until the broker exits.
        time.sleep(1)


def run_simulation(opendss_file, storage_name, storage_bus,
                   storage_kw_rated, storage_kwh_rated):
    """Simulate the performance of the grid with attached storage.

    Parameters
    ----------
    opendss_file : PathLike
        Grid model file.
    storage_name : str
        Name of the attached storage device.
    storage_bus : str
        Bus where the storage device is connected.
    storage_kw_rated : float
        rated maximum power output from the storage device. [kW]
    storage_kwh_rated : float
        rated capacity of the storage device. [kWh]
    """
    broker_process = Process(target=_helics_broker, name="broker")
    grid_process = Process(
        target=opendss.run_opendss_federate,
        args=(opendss_file, storage_name, storage_bus,
              {'kwrated': storage_kw_rated, 'kwhrated': storage_kwh_rated},
              logging.DEBUG),
        name="grid_federate"
    )
    storage_process = Process(
        target=storage.run_storage_federate,
        args=(storage_name, storage_kwh_rated, storage_kw_rated),
        name="storage_federate"
    )
    logging.info("starting broker")
    broker_process.start()
    logging.info("starting federates")
    grid_process.start()
    storage_process.start()

    logging.info("running...")
    broker_process.join()
    grid_process.join()
    storage_process.join()
    logging.info("done.")
