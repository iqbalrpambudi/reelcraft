from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.storage.models import Project

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ProjectCreate(BaseModel):
    name: Name


class ProjectUpdate(BaseModel):
    name: Name | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
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
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    session.flush()
    return ProjectOut.model_validate(project)


def delete(session: Session, project_id: str) -> None:
    session.delete(_get(session, project_id))


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
