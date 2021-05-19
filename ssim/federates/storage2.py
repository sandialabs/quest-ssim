import argparse

from helics import helicsCreateValueFederateFromConfig, helics_time_maxtime, \
    HelicsLogLevel


def _controller(federate, hours):
    last_voltage = 0.0
    federate.log_message(f"storage starting ({hours})", HelicsLogLevel.TRACE)
    time = federate.request_time(0)
    while time < (hours * 3600):
        federate.log_message(f"granted time: {time}", HelicsLogLevel.TRACE)
        voltage = federate.subscriptions[
            f"grid/storage.{federate.name}.voltage"
        ].double
        soc = federate.subscriptions[
            f"grid/storage.{federate.name}.soc"
        ].double
        federate.log_message(f"voltage: {voltage}", HelicsLogLevel.TRACE)
        federate.log_message(f"soc: {soc}", HelicsLogLevel.TRACE)
        if abs(last_voltage - voltage) > 1.0e-3:
            federate.publications[f"{federate.name}/power"].publish(
                complex((1.0 - voltage) * 5000, voltage * -500)
            )
            last_voltage = voltage
        time = federate.request_time(helics_time_maxtime)


def _start_controller(config_path, hours):
    federate = helicsCreateValueFederateFromConfig(config_path)
    federate.enter_executing_mode()
    for pub in federate.publications:
        federate.log_message(f"publication: {pub}", HelicsLogLevel.INTERFACES)
    for sub in federate.subscriptions:
        federate.log_message(f"subscription: {sub}", HelicsLogLevel.INTERFACES)
    _controller(federate, hours)
    federate.finalize()


def run():
    parser = argparse.ArgumentParser(
        description="HELICS federate for a storage controller."
    )
    parser.add_argument(
        "federate_config",
        type=str,
        help="path to federate config file"
    )
    parser.add_argument(
        "--hours",
        dest='hours',
        type=float,
        default=helics_time_maxtime
    )
    args = parser.parse_args()
    _start_controller(args.federate_config, args.hours)
