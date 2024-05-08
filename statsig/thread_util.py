import threading
from typing import Callable, Optional

from .statsig_error_boundary import _StatsigErrorBoundary

THREAD_JOIN_TIMEOUT = 10.0


def spawn_background_thread(name: str,
                            task: Callable[..., None],
                            args: tuple,
                            error_boundary: Optional[_StatsigErrorBoundary] = None):
    try:
        thread = threading.Thread(target=task, args=args, name=f"Statsig::{name}")
        thread.daemon = True
        thread.start()
        return thread

    except Exception as e:
        if error_boundary is not None:
            error_boundary.log_exception("spawn_background_thread", e)
        return None
