from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from reelcraft.storage.db import session_scope
from reelcraft.storage.models import StepRun

Listener = Callable[[str, int, str], None]  # step, percent, message


class Cancelled(Exception):
    pass


@dataclass
class StepContext:
    project_id: str
    step: str
    dir: Path
    listener: Listener | None = field(default=None, repr=False)

    def progress(self, percent: int, message: str) -> None:
        """Persist progress and stop here if a cancel was requested (from CLI, web, or API)."""
        percent = max(0, min(percent, 99))
        with session_scope() as s:
            run = s.get(StepRun, (self.project_id, self.step))
            assert run is not None
            run.progress, run.message = percent, message
            cancel = run.cancel_requested
        if self.listener:
            self.listener(self.step, percent, message)
        if cancel:
            raise Cancelled
