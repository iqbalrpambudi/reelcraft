import pysubs2
import pytest

from reelcraft.core.errors import ReelcraftError
from reelcraft.media import render, subtitles
from reelcraft.media.probe import probe
from reelcraft.pipeline import runner
from reelcraft.pipeline.steps.render import OUTPUT, WORK
from reelcraft.services import media, projects
from reelcraft.services.projects import ProjectCreate, ProjectUpdate
from reelcraft.storage import settings
from reelcraft.storage.db import session_scope
from reelcraft.storage.files import project_dir

WORDS = [
    {"text": w, "start": i * 0.5, "end": i * 0.5 + 0.4}
    for i, w in enumerate(["satu", "dua", "tiga", "{empat}"])
]


def test_karaoke_groups_words_and_highlights_the_spoken_one(tmp_path):
    subtitles.karaoke([{"words": WORDS}], "Arial", "#FFE600", tmp_path / "s.ass")
    events = pysubs2.load(str(tmp_path / "s.ass")).events
    assert len(events) == 4  # one per word
    assert events[0].text.startswith(r"{\c&H00E6FF&") and "DUA TIGA" in events[0].text
    assert events[0].end == events[1].start == 500  # no blink between words of a group
    assert events[3].plaintext == "EMPAT"  # the fourth word opens a new group, braces dropped
    with pytest.raises(ReelcraftError, match="#RRGGBB"):
        subtitles.karaoke([], "Arial", "kuning", tmp_path / "s.ass")


def test_background_must_be_known():
    for ok in ("blur", "cover", "#101010"):
        render.check_background(ok)
    with pytest.raises(ReelcraftError, match="blur, cover"):
        render.check_background("hijau")


@pytest.mark.parametrize("background", ["blur", "#000000"])
def test_pipeline_renders_a_vertical_video_with_the_narration(sample_video, background):
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        projects.update(s, pid, ProjectUpdate(topic="Warna"))
        media.add(s, pid, str(sample_video))
        settings.put(s, "background", background)
        settings.put(s, "watermark", "@reelcraft: 100%")  # ':' and '%' are special in drawtext
    status = runner.run(pid)
    with session_scope() as s:
        errors = [r.error for r in runner.ensure_runs(s, pid) if r.error]
    assert status == "done", errors
    info = probe(project_dir(pid) / OUTPUT)
    assert (info.width, info.height) == (1080, 1920)
    assert info.duration == pytest.approx(1.0, abs=0.1)  # the narration, not the 4 s source
    assert not (project_dir(pid) / WORK).exists()
