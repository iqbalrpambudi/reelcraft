import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from reelcraft.api.app import create_app
from reelcraft.cli import app
from reelcraft.pipeline import runner
from reelcraft.services import media, projects
from reelcraft.services.projects import ProjectCreate
from reelcraft.storage.db import session_scope
from reelcraft.storage.models import Job, StepRun


def _project(name: str, source) -> str:
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name=name)).id
        media.add(s, pid, str(source))
    return pid


def test_every_run_is_recorded_with_where_it_ended(sample_video, tmp_path, monkeypatch):
    ok = _project("bagus", sample_video)
    assert runner.run(ok, end="analyze") == "done"
    broken = tmp_path / "rusak.mp4"
    broken.write_bytes(b"bukan video")
    bad = _project("rusak", broken)
    assert runner.run(bad) == "failed"

    def interrupted(ctx):
        raise KeyboardInterrupt

    monkeypatch.setitem(runner.STEPS, "tag", interrupted)
    with pytest.raises(KeyboardInterrupt):
        runner.run(ok, start="tag")

    history = TestClient(create_app()).get("/api/v1/jobs").json()
    assert [(j["project_name"], j["status"], j["step"]) for j in history] == [
        ("bagus", "cancelled", "tag"),
        ("rusak", "failed", "ingest"),
        ("bagus", "done", "analyze"),
    ]
    assert history[2]["steps"] == ["ingest", "analyze"]
    assert "gagal" in history[1]["error"]
    out = CliRunner().invoke(app, ["jobs"])
    assert out.exit_code == 0 and "rusak" in out.output


def test_queue_lists_running_first_then_fifo_in_step_order(sample_video):
    first, second = _project("satu", sample_video), _project("dua", sample_video)
    runner.claim(first, None, "analyze", queue=True)
    runner.claim(second, None, "analyze", queue=True)
    with session_scope() as s:
        s.get(StepRun, (second, "ingest")).status = "running"
    queue = TestClient(create_app()).get("/api/v1/queue").json()
    assert [(q["project_name"], q["step"], q["status"]) for q in queue] == [
        ("dua", "ingest", "running"),
        ("satu", "ingest", "queued"),
        ("satu", "analyze", "queued"),
        ("dua", "analyze", "queued"),
    ]


def test_recovery_fails_jobs_left_running():
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        s.add(Job(project_id=pid, steps=["ingest"]))
    runner.recover_interrupted()
    with session_scope() as s:
        job = s.query(Job).one()
        assert (job.status, job.error) == ("failed", "Terhenti karena proses berhenti")
