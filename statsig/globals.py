import os

from .output_logger import OutputLogger, LogLevel

STATSIG_BATCHING_INTERVAL_SECONDS = 60.0
STATSIG_LOGGING_INTERVAL_SECONDS = 1.0

logger = OutputLogger('statsig.sdk')

os.environ["GRPC_VERBOSITY"] = "NONE"


def set_logger(output_logger):
    global logger
    logger = output_logger


def set_log_level(log_level: LogLevel):
    logger.set_log_level(log_level)
