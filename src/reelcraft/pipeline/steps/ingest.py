import shutil
from pathlib import Path

from sqlalchemy import select

from reelcraft.core.errors import ReelcraftError
from reelcraft.media.download import download, is_url
from reelcraft.media.probe import probe
from reelcraft.pipeline.context import Cancelled, StepContext
from reelcraft.storage.db import session_scope
from reelcraft.storage.models import Media


def run(ctx: StepContext) -> None:
    """Make every pending media local (copy or download) and read its metadata."""
    with session_scope() as s:
        media = list(s.scalars(select(Media).where(Media.project_id == ctx.project_id)))
    if not media:
        raise ReelcraftError("Project belum punya media. Tambahkan dulu (`reelcraft media add`).")
    todo = [m for m in media if m.status != "ready"]
    failed = 0
    for i, m in enumerate(todo):
        label = f"Media {i + 1}/{len(todo)}"
        base = i * 100 // len(todo)

        def report(pct: int, base: int = base, label: str = label) -> None:
            ctx.progress(base + pct // len(todo), f"{label}: mengunduh {pct}%")

        try:
            ctx.progress(base, f"{label}: menyiapkan")
            stem = ctx.dir / "media" / m.id
            if is_url(m.source):
                path = download(m.source, stem, report)
            else:
                path = stem.with_suffix(Path(m.source).suffix.lower() or ".mp4")
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(m.source, path)
            info = probe(path)
            fields = {
                "status": "ready",
                "file": str(path.relative_to(ctx.dir)),
                "duration": info.duration,
                "width": info.width,
                "height": info.height,
                "fps": info.fps,
                "error": None,
            }
        except Cancelled:
            raise
        except Exception as e:
            failed += 1
            fields = {"status": "failed", "error": str(e)[:1000]}
        with session_scope() as s:
            row = s.get(Media, m.id)
            if row:  # removed meanwhile
                for k, v in fields.items():
                    setattr(row, k, v)
    if failed:
        raise ReelcraftError(f"{failed} dari {len(todo)} media gagal diproses")
