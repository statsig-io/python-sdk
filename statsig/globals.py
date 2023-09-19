from .output_logger import OutputLogger


logger = OutputLogger('statsig.sdk')


def set_logger(output_logger):
    global logger
    logger = output_logger


def enable_debug_logs():
    global logger
    logger = OutputLogger('statsig.sdk', True)
