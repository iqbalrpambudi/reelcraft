"""Background threads of the server besides the pipeline worker. See ADR 0003."""

import logging
import threading
from collections.abc import Callable

from reelcraft.services import autopilot, publishing

log = logging.getLogger(__name__)
TICK_SECONDS = 5.0


def upload_all() -> None:
    while publishing.upload():  # drain: posts queued together go out together
        pass


def start() -> threading.Event:
    """Uploads and Autopilot each in their own thread: a slow AI call must not hold back posts."""
    stop = threading.Event()

    def loop(tick: Callable[[], None]) -> None:
        while not stop.is_set():
            try:
                tick()
            except Exception:  # one bad tick must not stop later ones
                log.exception("Scheduler error in %s", tick.__name__)
            stop.wait(TICK_SECONDS)

    for tick in (upload_all, autopilot.tick):
        threading.Thread(target=loop, args=(tick,), name=tick.__name__, daemon=True).start()
    return stop
