from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from reelcraft.api.deps import get_session
from reelcraft.services import jobs
from reelcraft.services.jobs import ActiveStep, JobOut

router = APIRouter(tags=["jobs"])
Db = Annotated[Session, Depends(get_session)]


@router.get("/queue")
def get_queue(db: Db) -> list[ActiveStep]:
    """Steps running or waiting, across all projects."""
    return jobs.queue(db)


@router.get("/jobs")
def list_jobs(db: Db, limit: int = 50) -> list[JobOut]:
    """Past and current runs, newest first."""
    return jobs.history(db, min(limit, 500))
