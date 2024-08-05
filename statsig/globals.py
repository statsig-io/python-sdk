from .output_logger import OutputLogger

STATSIG_BATCHING_INTERVAL_SECONDS = 60.0
STATSIG_LOGGING_INTERVAL_SECONDS = 5.0


logger = OutputLogger('statsig.sdk')


def set_logger(output_logger):
    global logger
    logger = output_logger


def enable_debug_logs():
    global logger
    logger = OutputLogger('statsig.sdk', True)
