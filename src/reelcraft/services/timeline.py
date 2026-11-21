from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.pipeline import runner
from reelcraft.pipeline.steps.edit import TIMELINE
from reelcraft.storage.files import project_dir
from reelcraft.storage.models import Media, Project


class TimelineClip(BaseModel):
    scene_id: str
    media_id: str
    source_start: float
    source_end: float
    start: float  # slot on the timeline, set by the narration
    end: float
    text: str
    segment: int


class Timeline(BaseModel):
    duration: float
    clips: list[TimelineClip]


def get(session: Session, project_id: str) -> Timeline | None:
    if not session.get(Project, project_id):
        raise NotFound(f"Project {project_id} tidak ditemukan")
    path = project_dir(project_id) / TIMELINE
    return Timeline.model_validate_json(path.read_text()) if path.is_file() else None


def reorder(session: Session, project_id: str, order: list[int]) -> Timeline:
    """Play the footage in a new order. Slots stay with the narration; each footage keeps its
    start in the source and runs as long as its new slot. Preview and Render run again."""
    timeline = get(session, project_id)
    if not timeline:
        raise ReelcraftError("Belum ada timeline. Jalankan step edit dulu.")
    if sorted(order) != list(range(len(timeline.clips))):
        raise ReelcraftError("Urutan harus memuat setiap klip tepat satu kali")
    runner.ensure_idle(session, project_id)
    lengths = dict(
        session.execute(
            select(Media.id, Media.duration).where(Media.project_id == project_id)
        ).all()
    )
    footage = [timeline.clips[i] for i in order]
    timeline.clips = [
        slot.model_copy(
            update={
                "scene_id": f.scene_id,
                "media_id": f.media_id,
                "source_start": f.source_start,
                "source_end": min(
                    f.source_start + slot.end - slot.start,
                    lengths.get(f.media_id) or f.source_end,
                ),
            }
        )
        for slot, f in zip(timeline.clips, footage, strict=True)
    ]
    (project_dir(project_id) / TIMELINE).write_text(timeline.model_dump_json())
    runner.invalidate(session, project_id, "preview")
    return timeline
