import shutil
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from reelcraft.ai.scripting import TEMPLATES
from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.pipeline import runner
from reelcraft.storage.files import project_dir
from reelcraft.storage.models import Project

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ProjectCreate(BaseModel):
    name: Name


class ProjectUpdate(BaseModel):
    """Only the fields sent change; null clears topic or instructions."""

    name: Name | None = None
    topic: str | None = None
    template: str | None = None
    instructions: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    topic: str | None
    template: str
    instructions: str | None
    created_at: datetime
    updated_at: datetime


def _get(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise NotFound(f"Project {project_id} tidak ditemukan")
    return project


def create(session: Session, data: ProjectCreate) -> ProjectOut:
    project = Project(name=data.name)
    session.add(project)
    session.flush()  # fills id and timestamps
    return ProjectOut.model_validate(project)


def list_all(session: Session) -> list[ProjectOut]:
    rows = session.scalars(select(Project).order_by(Project.created_at.desc()))
    return [ProjectOut.model_validate(p) for p in rows]


def get(session: Session, project_id: str) -> ProjectOut:
    return ProjectOut.model_validate(_get(session, project_id))


def update(session: Session, project_id: str, data: ProjectUpdate) -> ProjectOut:
    project = _get(session, project_id)
    fields = data.model_dump(exclude_unset=True)
    for required in ("name", "template"):
        if fields.get(required, "") is None:
            del fields[required]
    if fields.get("template", "fakta") not in TEMPLATES:
        raise ReelcraftError(f"Template tidak dikenal. Pilihan: {', '.join(TEMPLATES)}")
    for key in ("topic", "instructions"):
        if key in fields:
            fields[key] = (fields[key] or "").strip() or None
    brief = {"topic", "template", "instructions"}
    if any(getattr(project, k) != v for k, v in fields.items() if k in brief):
        runner.invalidate(session, project_id, "script")  # the old script no longer fits
    for field, value in fields.items():
        setattr(project, field, value)
    session.flush()
    return ProjectOut.model_validate(project)


def delete(session: Session, project_id: str) -> None:
    session.delete(_get(session, project_id))
    session.flush()  # DB errors surface before any file is touched
    shutil.rmtree(project_dir(project_id), ignore_errors=True)


def resolve_id(session: Session, prefix: str) -> str:
    """Full id from a unique prefix, so the CLI can take `3fa8` instead of 32 hex chars."""
    ids = list(session.scalars(select(Project.id).where(Project.id.startswith(prefix)).limit(2)))
    if not ids:
        raise NotFound(f"Project {prefix} tidak ditemukan")
    if len(ids) > 1:
        raise ReelcraftError(
            f"Id {prefix} cocok dengan lebih dari satu project, ketik lebih panjang"
        )
    return ids[0]


def templates() -> dict[str, str]:
    """Narration presets: key to description (empty for the free-form one)."""
    return TEMPLATES
