import shutil
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.media.download import is_url
from reelcraft.pipeline import runner
from reelcraft.storage.files import UPLOADS, project_dir
from reelcraft.storage.models import Media, Project, Scene


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    status: str
    file: str | None
    duration: float | None
    width: int | None
    height: int | None
    fps: float | None
    error: str | None
    created_at: datetime
    scene_count: int = 0


class SceneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    media_id: str
    position: int
    start: float
    end: float
    thumbnail: str | None


def add(session: Session, project_id: str, source: str) -> MediaOut:
    """Register a URL or local file; the Ingest step fetches it. Re-opens Ingest and later steps."""
    if not session.get(Project, project_id):
        raise NotFound(f"Project {project_id} tidak ditemukan")
    source = source.strip()
    if not is_url(source):
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise ReelcraftError(f"File tidak ditemukan: {source}")
        source = str(path)
    media = Media(project_id=project_id, source=source)
    session.add(media)
    runner.invalidate(session, project_id, "ingest")
    session.flush()
    return MediaOut.model_validate(media)


def upload(session: Session, project_id: str, filename: str, data: BinaryIO) -> MediaOut:
    """Store an uploaded file in the project, then register it like a local file."""
    if not session.get(Project, project_id):
        raise NotFound(f"Project {project_id} tidak ditemukan")
    # Only the extension of the client's name is kept, so it can't steer the path
    dest = project_dir(project_id) / UPLOADS / f"{uuid4().hex}{Path(filename).suffix.lower()}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        shutil.copyfileobj(data, out)
    return add(session, project_id, str(dest))


def list_for(session: Session, project_id: str) -> list[MediaOut]:
    counts = {
        media_id: n
        for media_id, n in session.execute(
            select(Scene.media_id, func.count())
            .join(Media, Media.id == Scene.media_id)
            .where(Media.project_id == project_id)
            .group_by(Scene.media_id)
        )
    }
    rows = session.scalars(
        select(Media).where(Media.project_id == project_id).order_by(Media.created_at)
    )
    return [
        MediaOut.model_validate(m).model_copy(update={"scene_count": counts.get(m.id, 0)})
        for m in rows
    ]


def scenes_for(session: Session, project_id: str) -> list[SceneOut]:
    rows = session.scalars(
        select(Scene)
        .join(Media, Media.id == Scene.media_id)
        .where(Media.project_id == project_id)
        .order_by(Media.created_at, Scene.position)
    )
    return [SceneOut.model_validate(s) for s in rows]


def remove(session: Session, project_id: str, media_id: str) -> None:
    media = session.get(Media, media_id)
    if not media or media.project_id != project_id:
        raise NotFound(f"Media {media_id} tidak ditemukan")
    file = media.file
    session.delete(media)
    runner.invalidate(session, project_id, "analyze")
    session.flush()
    if file:
        (project_dir(project_id) / file).unlink(missing_ok=True)
