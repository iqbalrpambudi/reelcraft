"""The server's second background thread: uploads queued posts. See ADR 0003."""

import logging
import threading

from reelcraft.services import publishing

log = logging.getLogger(__name__)
TICK_SECONDS = 5.0


def tick() -> None:
    while publishing.upload():  # drain: posts queued together go out together
        pass


def start() -> threading.Event:
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            try:
                tick()
            except Exception:  # one bad tick must not stop later ones
                log.exception("Scheduler error")
            stop.wait(TICK_SECONDS)

    threading.Thread(target=loop, name="scheduler", daemon=True).start()
    return stop
