from .statsig_options import StatsigOptions
from .statsig_telemetry_logger import StatsigTelemetryLogger

STATSIG_BATCHING_INTERVAL_SECONDS = 60.0
STATSIG_LOGGING_INTERVAL_SECONDS = 1.0

logger = StatsigTelemetryLogger()

def init_logger(options: StatsigOptions):
    if options.custom_logger is not None:
        logger.set_logger(options.custom_logger)
    elif options.output_logger_level is not None:
        logger.set_log_level(options.output_logger_level)
    if options.observability_client is not None:
        logger.set_ob_client(options.observability_client)
    if options.sdk_error_callback is not None:
        logger.set_sdk_error_callback(options.sdk_error_callback)
    logger.init()
