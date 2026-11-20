from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from reelcraft.storage.db import Base, UTCDateTime, utcnow


def _uuid() -> str:
    return uuid4().hex


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Media(Base):
    """A source video: added as a path or URL (pending), made local and probed by Ingest (ready)."""

    __tablename__ = "media"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(Text)  # URL or absolute local path, as added
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, ready, failed
    file: Mapped[str | None] = mapped_column(String(500))  # relative to the project dir
    duration: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    media_id: Mapped[str] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    start: Mapped[float] = mapped_column(Float)  # seconds
    end: Mapped[float] = mapped_column(Float)
    thumbnail: Mapped[str | None] = mapped_column(String(500))  # relative to the project dir


class StepRun(Base):
    """Latest state of one pipeline step of one project."""

    __tablename__ = "step_runs"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    step: Mapped[str] = mapped_column(String(20), primary_key=True)
    # pending; reserved (claimed by an in-process run, e.g. the CLI) or queued (waiting for the
    # server worker); running; done, failed, cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending")
    queued_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # FIFO order of the queue
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
