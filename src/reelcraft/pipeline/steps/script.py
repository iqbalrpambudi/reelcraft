import asyncio

from sqlalchemy import select

from reelcraft.ai import scripting
from reelcraft.ai.models import model_for, retrying
from reelcraft.core.errors import ReelcraftError
from reelcraft.pipeline.context import StepContext
from reelcraft.storage import script
from reelcraft.storage.db import session_scope
from reelcraft.storage.models import Media, Project, Scene


def run(ctx: StepContext) -> None:
    """Draft the narration from the project's brief and the scene descriptions."""
    with session_scope() as s:
        project = s.get(Project, ctx.project_id)
        assert project is not None
        topic, template, instructions = project.topic, project.template, project.instructions
        scenes = [
            f"{sc.end - sc.start:.1f} detik: {sc.description}"
            for sc in s.scalars(
                select(Scene)
                .join(Media, Media.id == Scene.media_id)
                .where(Media.project_id == ctx.project_id, Scene.description.is_not(None))
                .order_by(Media.created_at, Scene.position)
            )
        ]
    if not topic and not scenes:
        raise ReelcraftError(
            "Isi topik project dulu, atau jalankan step tag agar scene terdeskripsi."
        )
    ctx.progress(10, "Menulis naskah")
    model = model_for("text")
    draft = retrying(
        lambda: asyncio.run(
            scripting.write(model, topic or "tentukan dari scene", template, instructions, scenes)
        )
    )
    segments = [" ".join(seg.split()) for seg in draft.segments if seg.strip()]
    if not segments:
        raise ReelcraftError("AI mengembalikan naskah kosong. Jalankan ulang step ini.")
    script.save(ctx.project_id, script.Script(draft.title.strip(), segments))
