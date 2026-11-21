from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from reelcraft.pipeline import runner
from reelcraft.storage.models import Job, Project, StepRun


class ActiveStep(BaseModel):
    project_id: str
    project_name: str
    step: str
    status: str  # running, queued, reserved
    progress: int
    message: str | None


class JobOut(BaseModel):
    id: str
    project_id: str
    project_name: str
    steps: list[str]
    status: str
    step: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None


def queue(session: Session) -> list[ActiveStep]:
    """Every step running or waiting, across projects: running first, then in queue order."""
    rows = session.execute(
        select(StepRun, Project.name)
        .join(Project, Project.id == StepRun.project_id)
        .where(StepRun.status.in_(runner.BUSY))
    ).all()
    order = list(runner.STEPS)

    def key(row: tuple[StepRun, str]) -> tuple[bool, float, int]:
        run = row[0]
        waited = run.queued_at.timestamp() if run.queued_at else 0.0
        return run.status != "running", waited, order.index(run.step)

    rows = sorted(rows, key=key)
    return [
        ActiveStep(
            project_id=run.project_id,
            project_name=name,
            step=run.step,
            status=run.status,
            progress=run.progress,
            message=run.message,
        )
        for run, name in rows
    ]


def history(session: Session, limit: int = 50) -> list[JobOut]:
    rows = session.execute(
        select(Job, Project.name)
        .join(Project, Project.id == Job.project_id)
        .order_by(Job.started_at.desc())
        .limit(limit)
    ).all()
    return [
        JobOut(
            id=job.id,
            project_id=job.project_id,
            project_name=name,
            steps=job.steps,
            status=job.status,
            step=job.step,
            error=job.error,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        for job, name in rows
    ]
