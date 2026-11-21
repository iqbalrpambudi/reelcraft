from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from reelcraft.storage.db import Base, UTCDateTime, utcnow


def _uuid() -> str:
    return uuid4().hex


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    # Brief for the Script step: what the video is about and how to tell it
    topic: Mapped[str | None] = mapped_column(Text)
    template: Mapped[str] = mapped_column(String(40), default="fakta")  # preset key
    instructions: Mapped[str | None] = mapped_column(Text)  # custom, added to the preset
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
    # Filled by the Tag step; None = not described yet
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str] | None] = mapped_column(JSON)
    tag_error: Mapped[str | None] = mapped_column(Text)


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


class Setting(Base):
    """A value saved from the web or CLI; secrets are stored encrypted."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
