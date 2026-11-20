import asyncio
from itertools import batched

from sqlalchemy import select

from reelcraft.ai.models import ProviderUnavailable, model_for
from reelcraft.ai.tagging import describe
from reelcraft.core.errors import ReelcraftError
from reelcraft.pipeline.context import StepContext
from reelcraft.storage.db import session_scope
from reelcraft.storage.models import Media, Scene

BATCH = 8  # images per request: fewer calls, same quality
CONCURRENCY = 3
# Seconds before each retry of a batch the provider was too busy for (503 "overloaded" came
# in bursts of tens of seconds when tested); other errors are not retried
RETRY_WAITS = (5, 15, 45)


def run(ctx: StepContext) -> None:
    """Describe every scene that has no description yet (so a rerun only retries the gaps)."""
    with session_scope() as s:
        scenes = list(
            s.scalars(
                select(Scene)
                .join(Media, Media.id == Scene.media_id)
                .where(Media.project_id == ctx.project_id)
                .order_by(Media.created_at, Scene.position)
            )
        )
    if not scenes:
        raise ReelcraftError("Belum ada scene. Jalankan step analyze dulu.")
    todo = [sc for sc in scenes if sc.description is None and sc.thumbnail]
    if not todo:
        return
    model = model_for("vision")
    failed = asyncio.run(_tag_all(ctx, model, todo))
    if failed:
        n, error = failed
        raise ReelcraftError(
            f"{n} dari {len(todo)} scene gagal dideskripsi ({error}). "
            "Jalankan ulang step ini untuk mencoba scene yang tersisa."
        )


async def _tag_all(ctx: StepContext, model, todo: list[Scene]) -> tuple[int, str] | None:
    limit = asyncio.Semaphore(CONCURRENCY)
    done = failed = 0
    last_error = ""

    async def one(batch: tuple[Scene, ...]) -> None:
        nonlocal done, failed, last_error
        async with limit:
            images = [(ctx.dir / sc.thumbnail).read_bytes() for sc in batch if sc.thumbnail]
            error = ""
            results = None
            for wait in (*RETRY_WAITS, None):
                try:
                    results = await describe(model, images)
                    break
                except ProviderUnavailable as e:
                    error = str(e)
                    if wait is None:
                        break
                    await asyncio.sleep(wait)
                except ReelcraftError as e:  # bad key, quota, bad output: retrying won't help
                    error = str(e)
                    break
        with session_scope() as s:
            for i, sc in enumerate(batch):
                row = s.get(Scene, sc.id)
                tag = results[i] if results else None
                if not row:
                    continue
                if tag:
                    row.description, row.tags, row.tag_error = tag.description, tag.tags, None
                else:
                    row.tag_error = error or "AI tidak mengembalikan deskripsi untuk scene ini"
                    failed += 1
                    last_error = row.tag_error
        done += len(batch)
        ctx.progress(done * 100 // len(todo), f"{done}/{len(todo)} scene dideskripsi")

    await asyncio.gather(*(one(b) for b in batched(todo, BATCH)))
    return (failed, last_error[:300]) if failed else None
