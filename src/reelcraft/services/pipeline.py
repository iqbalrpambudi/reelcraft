from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from reelcraft.core.errors import NotFound
from reelcraft.pipeline import runner
from reelcraft.storage.models import Project


class StepRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: str
    status: str
    progress: int
    message: str | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


def status(session: Session, project_id: str) -> list[StepRunOut]:
    """Every pipeline step of the project, in order."""
    if not session.get(Project, project_id):
        raise NotFound(f"Project {project_id} tidak ditemukan")
    return [StepRunOut.model_validate(r) for r in runner.ensure_runs(session, project_id)]
