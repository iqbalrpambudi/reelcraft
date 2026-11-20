import logging
import threading

from reelcraft.pipeline import runner

log = logging.getLogger(__name__)
IDLE_SECONDS = 1.0


def run_next() -> bool:
    """Execute the oldest queued run, if any. Returns whether there was one."""
    job = runner.next_queued()
    if not job:
        return False
    project_id, steps = job
    runner.execute(project_id, steps)
    return True


def start() -> threading.Event:
    """One background thread draining the queue, one run at a time. Set the event to stop it."""
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            try:
                if not run_next():
                    stop.wait(IDLE_SECONDS)
            except Exception:  # a broken run must not kill the worker
                log.exception("Pipeline worker error")
                stop.wait(IDLE_SECONDS)

    threading.Thread(target=loop, name="pipeline-worker", daemon=True).start()
    return stop
