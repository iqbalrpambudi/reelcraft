import json
import shutil

from sqlalchemy import select

from reelcraft.core.errors import ReelcraftError
from reelcraft.media import render, subtitles
from reelcraft.pipeline.context import StepContext
from reelcraft.pipeline.steps import edit, voice
from reelcraft.storage import music, settings
from reelcraft.storage.db import session_scope
from reelcraft.storage.models import Media, Project

OUTPUT, PREVIEW = "render.mp4", "preview.mp4"


def preview(ctx: StepContext) -> None:
    """A quick half-size render, to check the cut before waiting for the full one."""
    _render(ctx, PREVIEW, preview=True)


def run(ctx: StepContext) -> None:
    """The timeline as a 9:16 video with the narration and karaoke subtitles burned in."""
    _render(ctx, OUTPUT, preview=False)


def _render(ctx: StepContext, output: str, preview: bool) -> None:
    timeline_file, timings_file = ctx.dir / edit.TIMELINE, ctx.dir / voice.TIMINGS
    if not timeline_file.is_file() or not timings_file.is_file():
        raise ReelcraftError("Belum ada timeline. Jalankan step edit dulu.")
    timeline = json.loads(timeline_file.read_text())
    with session_scope() as s:
        files = dict(
            s.execute(select(Media.id, Media.file).where(Media.project_id == ctx.project_id)).all()
        )
        background = settings.get(s, "background") or "blur"
        font = settings.get(s, "subtitle_font") or "Arial"
        color = settings.get(s, "subtitle_color") or "#FFE600"
        watermark = settings.get(s, "watermark")
        project = s.get(Project, ctx.project_id)
        assert project is not None
        mood = project.music
    track = music.pick(mood, ctx.project_id) if mood else None
    if mood and not track:
        raise ReelcraftError(f"Folder musik '{mood}' kosong. Isi {music.music_dir()}/{mood}/")
    render.check_background(background)

    work = ctx.dir / f"{output}.work"  # scratch dir, removed after a successful render
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    subtitles.karaoke(
        json.loads(timings_file.read_text())["segments"], font, color, work / "subs.ass"
    )
    clips = timeline["clips"]
    chunks = []
    for i, c in enumerate(clips):
        ctx.progress(i * 85 // len(clips), f"Klip {i + 1}/{len(clips)}")
        src = files.get(c["media_id"])
        if not src:
            raise ReelcraftError(
                "Media untuk timeline ini sudah dihapus. Jalankan ulang step edit."
            )
        chunks.append(work / f"{i:04d}.mp4")
        render.clip(
            ctx.dir / src,
            chunks[-1],
            c["source_start"],
            c["source_end"] - c["source_start"],
            c["end"] - c["start"],
            background,
            preview,
        )
    ctx.progress(85, "Menggabung klip")
    render.concat(chunks, work / "video.mp4")
    ctx.progress(90, "Subtitle, watermark, suara, dan musik")
    render.finish(
        work, ctx.dir / voice.AUDIO, track, watermark, timeline["duration"], work / output, preview
    )
    (work / output).replace(ctx.dir / output)  # the old render stays until the new one is whole
    shutil.rmtree(work)
