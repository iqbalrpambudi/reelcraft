from sqlalchemy import delete, select

from reelcraft.core.errors import ReelcraftError
from reelcraft.media import scenes
from reelcraft.pipeline.context import StepContext
from reelcraft.storage.db import session_scope
from reelcraft.storage.models import Media, Scene


def run(ctx: StepContext) -> None:
    """Split every ready media into scenes, with a thumbnail from the middle of each."""
    with session_scope() as s:
        media = list(
            s.scalars(
                select(Media)
                .where(Media.project_id == ctx.project_id, Media.status == "ready")
                .order_by(Media.created_at)
            )
        )
    if not media:
        raise ReelcraftError("Belum ada media siap. Jalankan step ingest dulu.")
    for i, m in enumerate(media):
        assert m.file is not None
        video = ctx.dir / m.file
        base, share = i * 100 // len(media), 100 // len(media)
        label = f"Media {i + 1}/{len(media)}"

        def report(pct: int, base: int = base, share: int = share, label: str = label) -> None:
            ctx.progress(base + pct * share // 200, f"{label}: deteksi scene")

        spans = scenes.detect(video, report)
        rows = []
        for pos, span in enumerate(spans):
            thumb = f"thumbs/{m.id}_{pos}.jpg"  # stable name: a rerun overwrites, never orphans
            scenes.thumbnail(video, (span.start + span.end) / 2, ctx.dir / thumb)
            rows.append(
                Scene(media_id=m.id, position=pos, start=span.start, end=span.end, thumbnail=thumb)
            )
            ctx.progress(base + share // 2 + pos * share // (2 * len(spans)), f"{label}: thumbnail")
        with session_scope() as s:
            s.execute(delete(Scene).where(Scene.media_id == m.id))
            s.add_all(rows)
