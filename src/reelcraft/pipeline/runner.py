from collections.abc import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.pipeline.context import Cancelled, Listener, StepContext
from reelcraft.pipeline.steps import analyze, edit, ingest, script, tag, voice
from reelcraft.storage.db import session_scope, utcnow
from reelcraft.storage.files import project_dir
from reelcraft.storage.models import Project, StepRun

# Order is the pipeline; later milestones append render, publish
STEPS: dict[str, Callable[[StepContext], None]] = {
    "ingest": ingest.run,
    "analyze": analyze.run,
    "tag": tag.run,
    "script": script.run,
    "voice": voice.run,
    "edit": edit.run,
}


def ensure_runs(session: Session, project_id: str) -> list[StepRun]:
    """One step_runs row per step, in pipeline order."""
    existing = {
        r.step: r for r in session.scalars(select(StepRun).where(StepRun.project_id == project_id))
    }
    for step in STEPS:
        if step not in existing:
            existing[step] = StepRun(project_id=project_id, step=step)
            session.add(existing[step])
    session.flush()
    return [existing[step] for step in STEPS]


def invalidate(session: Session, project_id: str, from_step: str) -> None:
    """Outputs of `from_step` and everything after it are stale: mark them pending."""
    stale = list(STEPS)[list(STEPS).index(from_step) :]
    for run in ensure_runs(session, project_id):
        if run.step in stale and run.status != "running":
            run.status, run.progress, run.message, run.error = "pending", 0, None, None


def plan(session: Session, project_id: str, start: str | None, end: str | None) -> list[str]:
    """Steps to run: from `start` (default: first step not done) through `end` (default: last)."""
    names = list(STEPS)
    for name in (start, end):
        if name and name not in STEPS:
            raise ReelcraftError(f"Step tidak dikenal: {name}. Pilihan: {', '.join(names)}")
    runs = ensure_runs(session, project_id)
    if start is None:
        start = next((r.step for r in runs if r.status != "done"), None)
        if start is None:
            return []
    first, last = names.index(start), names.index(end or names[-1])
    if first > last:
        raise ReelcraftError(f"Step {start} ada setelah {end}")
    return names[first : last + 1]


BUSY = ("reserved", "queued", "running")


def claim(project_id: str, start: str | None, end: str | None, queue: bool = False) -> list[str]:
    """Validate and reserve a run; raises if the project is busy.

    queue=False: the caller executes right away in its own process (CLI).
    queue=True: the server worker picks it up, in FIFO order, even after a restart.
    """
    with session_scope() as s:
        if not s.get(Project, project_id):
            raise NotFound(f"Project {project_id} tidak ditemukan")
        steps = plan(s, project_id, start, end)
        runs = ensure_runs(s, project_id)
        # shortcut: check-then-set in one transaction; two processes starting in the same
        # instant could both pass. Upgrade to a lock row if runs get triggered automatically.
        if any(r.status in BUSY for r in runs):
            raise ReelcraftError("Project ini sedang diproses. Tunggu atau batalkan dulu.")
        if steps:
            invalidate(s, project_id, steps[0])
            now = utcnow()
            for r in runs:
                if r.step in steps:
                    r.status, r.queued_at = ("queued" if queue else "reserved"), now
    return steps


def next_queued() -> tuple[str, list[str]] | None:
    """The project queued longest ago, with its queued steps in pipeline order."""
    with session_scope() as s:
        first = s.scalars(
            select(StepRun).where(StepRun.status == "queued").order_by(StepRun.queued_at).limit(1)
        ).first()
        if not first:
            return None
        queued = set(
            s.scalars(
                select(StepRun.step).where(
                    StepRun.project_id == first.project_id, StepRun.status == "queued"
                )
            )
        )
        return first.project_id, [step for step in STEPS if step in queued]


def execute(project_id: str, steps: list[str], listener: Listener | None = None) -> str:
    """Run claimed steps in order; stops at the first failure. Returns the final status."""
    status = "done"
    for i, step in enumerate(steps):
        with session_scope() as s:
            run = s.get(StepRun, (project_id, step))
            assert run is not None
            run.status, run.progress, run.message, run.error = "running", 0, None, None
            run.cancel_requested, run.started_at, run.finished_at = False, utcnow(), None
        ctx = StepContext(project_id, step, project_dir(project_id), listener)
        error = None
        try:
            STEPS[step](ctx)
        except Cancelled:
            status = "cancelled"
        except KeyboardInterrupt:
            status = "cancelled"
            _finish(project_id, step, status, None)
            _release(project_id, steps[i + 1 :])
            raise
        except Exception as e:
            status, error = "failed", str(e)[:2000] or e.__class__.__name__
        else:
            status = "done"
        _finish(project_id, step, status, error)
        if listener:
            listener(step, 100 if status == "done" else -1, error or status)
        if status != "done":
            _release(project_id, steps[i + 1 :])
            break
    return status


def run(
    project_id: str,
    start: str | None = None,
    end: str | None = None,
    listener: Listener | None = None,
) -> str:
    """Claim and execute in this process (CLI, tests). The web queues `execute` instead."""
    steps = claim(project_id, start, end)
    return execute(project_id, steps, listener) if steps else "done"


def request_cancel(project_id: str) -> bool:
    with session_scope() as s:
        result = s.execute(
            update(StepRun)
            .where(StepRun.project_id == project_id, StepRun.status == "running")
            .values(cancel_requested=True)
        )
        released = _release_in(s, project_id, None)  # waiting steps never start
        return bool(getattr(result, "rowcount", 0)) or released


def recover_interrupted() -> None:
    """At server start. A step left running belongs to a process that died: mark it failed and
    drop what was waiting behind it. Queued runs of other projects survive and resume."""
    # shortcut: also hits a CLI run genuinely in progress while the server starts; store the
    # owning PID on the run if that turns out to matter.
    with session_scope() as s:
        dead = list(s.scalars(select(StepRun.project_id).where(StepRun.status == "running")))
        s.execute(
            update(StepRun)
            .where(StepRun.status == "running")
            .values(status="failed", error="Terhenti karena proses berhenti", finished_at=utcnow())
        )
        s.execute(
            update(StepRun)
            .where(
                (StepRun.status == "reserved")
                | ((StepRun.status == "queued") & StepRun.project_id.in_(dead))
            )
            .values(status="pending")
        )


def _finish(project_id: str, step: str, status: str, error: str | None) -> None:
    with session_scope() as s:
        run = s.get(StepRun, (project_id, step))
        assert run is not None
        run.status, run.error, run.finished_at = status, error, utcnow()
        run.cancel_requested = False
        if status == "done":
            run.progress, run.message = 100, None


def _release(project_id: str, steps: list[str]) -> None:
    with session_scope() as s:
        _release_in(s, project_id, steps)


def _release_in(s: Session, project_id: str, steps: list[str] | None) -> bool:
    query = update(StepRun).where(
        StepRun.project_id == project_id, StepRun.status.in_(("reserved", "queued"))
    )
    if steps is not None:
        query = query.where(StepRun.step.in_(steps))
    return bool(getattr(s.execute(query.values(status="pending")), "rowcount", 0))
