import json
from dataclasses import asdict

from sqlalchemy import select

from reelcraft.core.errors import ReelcraftError
from reelcraft.pipeline import matching
from reelcraft.pipeline.context import StepContext
from reelcraft.pipeline.steps import voice
from reelcraft.storage.db import session_scope
from reelcraft.storage.models import Media, Scene

TIMELINE = "timeline.json"


def run(ctx: StepContext) -> None:
    """Pick a scene for every stretch of narration: the timeline the Render step plays."""
    timings_file = ctx.dir / voice.TIMINGS
    if not timings_file.is_file():
        raise ReelcraftError("Belum ada suara. Jalankan step voice dulu.")
    timings = json.loads(timings_file.read_text())
    with session_scope() as s:
        rows = s.execute(
            select(Scene, Media.duration)
            .join(Media, Media.id == Scene.media_id)
            .where(Media.project_id == ctx.project_id, Media.status == "ready")
            .order_by(Media.created_at, Scene.position)
        ).all()
    if not rows:
        raise ReelcraftError("Belum ada scene. Jalankan step analyze dulu.")
    shots = [
        matching.Shot(
            sc.id,
            sc.media_id,
            sc.start,
            sc.end,
            f"{sc.description or ''} {' '.join(sc.tags or [])}",
            filler=bool({t.lower() for t in sc.tags or []} & matching.FILLER_TAGS),
        )
        for sc, _ in rows
    ]
    media_length = {sc.media_id: duration for sc, duration in rows if duration}
    ctx.progress(30, "Mencocokkan scene dengan narasi")
    segments = [(seg["start"], seg["end"], seg["text"]) for seg in timings["segments"]]
    clips = matching.match(matching.windows(segments, timings["duration"]), shots, media_length)
    (ctx.dir / TIMELINE).write_text(
        json.dumps({"duration": timings["duration"], "clips": [asdict(c) for c in clips]})
    )
