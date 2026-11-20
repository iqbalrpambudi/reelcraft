from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from reelcraft.api.deps import get_session
from reelcraft.services import projects
from reelcraft.services.projects import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])
Db = Annotated[Session, Depends(get_session)]


@router.get("")
def list_projects(db: Db) -> list[ProjectOut]:
    return projects.list_all(db)


@router.post("", status_code=201)
def create_project(data: ProjectCreate, db: Db) -> ProjectOut:
    return projects.create(db, data)


@router.get("/{project_id}")
def get_project(project_id: str, db: Db) -> ProjectOut:
    return projects.get(db, project_id)


@router.patch("/{project_id}")
def update_project(project_id: str, data: ProjectUpdate, db: Db) -> ProjectOut:
    return projects.update(db, project_id, data)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Db) -> None:
    projects.delete(db, project_id)
