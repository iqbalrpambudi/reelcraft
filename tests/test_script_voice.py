import json
import sys

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from reelcraft.ai import models, tts
from reelcraft.ai.models import ProviderUnavailable
from reelcraft.api.app import create_app
from reelcraft.cli import app
from reelcraft.core.errors import ReelcraftError
from reelcraft.media.transcribe import Word, align
from reelcraft.pipeline import runner
from reelcraft.pipeline.context import StepContext
from reelcraft.pipeline.steps import voice
from reelcraft.services import media, projects
from reelcraft.services.projects import ProjectCreate, ProjectUpdate
from reelcraft.storage import script, settings
from reelcraft.storage.db import session_scope
from reelcraft.storage.files import project_dir
from reelcraft.storage.models import StepRun


def _status(pid: str, step: str) -> str:
    with session_scope() as s:
        run = s.get(StepRun, (pid, step))
        return run.status if run else "pending"


def _voiced(sample_video) -> str:
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        projects.update(s, pid, ProjectUpdate(topic="Warna", template="cerita"))
        media.add(s, pid, str(sample_video))
    assert runner.run(pid) == "done"
    return pid


def test_align_keeps_script_spelling_and_fills_unheard_words():
    heard = [Word("halo", 0.0, 0.4), Word("dua", 1.0, 1.2), Word("puluh", 1.2, 1.4)]
    words = align(["Halo,", "20", "orang!"], heard, duration=3.0)
    assert [w.text for w in words] == ["Halo,", "20", "orang!"]
    assert (words[0].start, words[0].end) == (0.0, 0.4)
    # Nothing matched after "Halo": the rest share the time up to the end of the audio
    assert words[1].start == 0.4 and words[2].end == 3.0
    assert words[1].end == words[2].start


def test_script_parse_roundtrip():
    text = "# Judul\n\nKalimat satu\nlanjut.\n\n\nKalimat dua.\n"
    parsed = script.parse(text)
    assert parsed == script.Script("Judul", ["Kalimat satu lanjut.", "Kalimat dua."])
    assert script.parse(script.to_text(parsed)) == parsed
    assert script.parse("Tanpa judul.").segments == ["Tanpa judul."]


def test_run_writes_script_audio_and_word_timings(sample_video):
    pid = _voiced(sample_video)
    assert script.load(pid) == script.Script(
        "Judul uji", ["Tahukah kamu warna ini?", "Ini scene kedua."]
    )
    timings = json.loads((project_dir(pid) / voice.TIMINGS).read_text())
    assert timings["duration"] == 1.0
    first, second = timings["segments"]
    assert [w["text"] for w in first["words"]] == ["Tahukah", "kamu", "warna", "ini?"]
    assert (first["start"], second["start"]) == (0.0, 0.4)
    assert (project_dir(pid) / voice.AUDIO).stat().st_size > 40_000


def test_saving_script_counts_as_done_and_reopens_voice(sample_video):
    pid = _voiced(sample_video)
    client = TestClient(create_app())
    base = f"/api/v1/projects/{pid}/script"
    saved = client.put(base, json={"text": "# Baru\n\nSatu.\n\nDua."})
    assert saved.status_code == 200 and saved.json()["text"] == "# Baru\n\nSatu.\n\nDua.\n"
    assert (_status(pid, "script"), _status(pid, "voice")) == ("done", "pending")
    assert client.put(base, json={"text": "# Judul saja"}).status_code == 400
    assert client.get("/api/v1/projects/nope/script").status_code == 404

    runner.claim(pid, "voice", None)
    assert client.put(base, json={"text": "Lagi."}).status_code == 400  # busy


def test_brief_validates_template_and_stales_the_script(sample_video):
    pid = _voiced(sample_video)
    with session_scope() as s:
        with pytest.raises(ReelcraftError, match="Template tidak dikenal"):
            projects.update(s, pid, ProjectUpdate(template="nope"))
        projects.update(s, pid, ProjectUpdate(template="cerita"))  # unchanged: nothing reruns
    assert _status(pid, "script") == "done"
    with session_scope() as s:
        out = projects.update(s, pid, ProjectUpdate(topic=" ", instructions="Lucu"))
    assert (out.topic, out.instructions) == (None, "Lucu")
    assert (_status(pid, "script"), _status(pid, "voice")) == ("pending", "pending")
    assert "bebas" in TestClient(create_app()).get("/api/v1/templates").json()


def test_script_needs_topic_or_described_scenes():
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
    with pytest.raises(ReelcraftError, match="topik"):
        runner.STEPS["script"](StepContext(pid, "script", project_dir(pid)))


def test_voice_retries_overload(sample_video, monkeypatch):
    pid = _voiced(sample_video)
    monkeypatch.setattr(models, "RETRY_WAITS", (0,))
    calls = []

    def busy(text):
        calls.append(text)
        raise ProviderUnavailable("sibuk")

    monkeypatch.setattr(voice, "synthesize", busy)
    assert runner.run(pid, start="voice") == "failed"
    assert len(calls) == 2


def test_tts_settings_errors():
    with pytest.raises(ReelcraftError, match="Gemini API key"):
        tts.synthesize("halo")
    with session_scope() as s:
        settings.put(s, "tts_model", "elevenlabs:x")
    with pytest.raises(ReelcraftError, match="tidak didukung"):
        tts.synthesize("halo")


def test_cli_brief_and_script_editor(sample_video, monkeypatch, tmp_path):
    pid = _voiced(sample_video)
    cli = CliRunner().invoke
    out = cli(app, ["project", "brief", pid[:8], "--topic", "Laut", "--template", "edukasi"])
    assert out.exit_code == 0 and "topik: Laut" in out.output and "edukasi" in out.output
    assert cli(app, ["project", "brief", pid[:8], "--template", "x"]).exit_code == 1

    editor = tmp_path / "editor.py"  # stands in for $EDITOR: edits the file it is given
    editor.write_text(
        "import pathlib, sys\n"
        "p = pathlib.Path(sys.argv[1])\n"
        "p.write_text(p.read_text().replace('Tahukah', 'Tahu'))\n"
    )
    monkeypatch.setenv("EDITOR", f"{sys.executable} {editor}")
    assert cli(app, ["script", pid[:8]]).exit_code == 0
    assert script.load(pid).segments[0] == "Tahu kamu warna ini?"
    monkeypatch.setenv("EDITOR", "true")
    assert "Tidak ada perubahan" in cli(app, ["script", pid[:8]]).output
    monkeypatch.setenv("EDITOR", "false")
    assert cli(app, ["script", pid[:8]]).exit_code == 1


def test_timeouts_are_transient_and_models_carry_a_limit():
    from pydantic_ai.exceptions import ModelTimeoutError

    with pytest.raises(ProviderUnavailable, match="tidak bisa dihubungi"), models.ai_errors():
        raise ModelTimeoutError(model_name="m", message="ReadTimeout")
    with session_scope() as s:
        settings.put(s, "gemini_api_key", "k")
        model = models.build(s, "google:gemini-flash-lite-latest")
    assert (model.settings or {}).get("timeout") == models.TIMEOUT
