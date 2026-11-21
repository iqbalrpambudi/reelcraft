import shutil

import pytest
from typer.testing import CliRunner

from reelcraft.cli import app
from reelcraft.core.errors import ReelcraftError
from reelcraft.pipeline import runner, worker
from reelcraft.pipeline.context import StepContext
from reelcraft.pipeline.steps import ingest
from reelcraft.services import media, pipeline, projects
from reelcraft.services.projects import ProjectCreate
from reelcraft.storage.db import session_scope
from reelcraft.storage.files import project_dir
from reelcraft.storage.models import StepRun


def _project_with(source) -> str:
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        media.add(s, pid, str(source))
    return pid


def _expect(status: str, **first: str) -> dict[str, str]:
    """Every step in `status`, except the ones named."""
    return {step: first.get(step, status) for step in runner.STEPS}


def _statuses(pid: str) -> dict[str, str]:
    with session_scope() as s:
        return {r.step: r.status for r in pipeline.status(s, pid)}


def test_full_run_ingests_and_analyzes(sample_video):
    pid = _project_with(sample_video)
    events = []
    assert runner.run(pid, listener=lambda *e: events.append(e)) == "done"
    assert _statuses(pid) == _expect("done")

    with session_scope() as s:
        [m] = media.list_for(s, pid)
        found = media.scenes_for(s, pid)
    assert m.status == "ready" and m.width == 320 and m.scene_count == 2
    assert all((project_dir(pid) / sc.thumbnail).is_file() for sc in found if sc.thumbnail)
    assert ("analyze", 100, "done") in events

    # Nothing left to do; adding media re-opens ingest and everything after it
    assert runner.claim(pid, None, None) == []
    with session_scope() as s:
        media.add(s, pid, str(sample_video))
    assert _statuses(pid) == _expect("pending")


def test_failed_media_fails_the_step_and_stops(tmp_path):
    bogus = tmp_path / "bad.mp4"
    bogus.write_text("nope")
    pid = _project_with(bogus)
    assert runner.run(pid) == "failed"
    assert _statuses(pid) == _expect("pending", ingest="failed")
    with session_scope() as s:
        [m] = media.list_for(s, pid)
    assert m.status == "failed" and "bukan video" in (m.error or "")


def test_url_media_goes_through_downloader(sample_video, monkeypatch):
    def fake_download(url, stem, on_progress):
        on_progress(50)
        stem.parent.mkdir(parents=True, exist_ok=True)
        return shutil.copy(sample_video, stem.with_suffix(".mp4"))

    monkeypatch.setattr(ingest, "download", fake_download)
    pid = _project_with("https://example.com/video")
    assert runner.run(pid, end="ingest") == "done"
    assert _statuses(pid)["analyze"] == "pending"


def test_cancel_request_stops_at_next_progress(sample_video, monkeypatch):
    def slow_step(ctx: StepContext) -> None:
        runner.request_cancel(ctx.project_id)
        ctx.progress(10, "masih jalan")
        raise AssertionError("should have stopped")

    monkeypatch.setitem(runner.STEPS, "ingest", slow_step)
    pid = _project_with(sample_video)
    assert runner.run(pid) == "cancelled"
    assert _statuses(pid) == _expect("pending", ingest="cancelled")


def test_claim_rejects_double_run_and_bad_ranges(sample_video):
    pid = _project_with(sample_video)
    with pytest.raises(ReelcraftError, match="tidak dikenal"):
        runner.claim(pid, "nope", None)
    with pytest.raises(ReelcraftError, match="setelah"):
        runner.claim(pid, "analyze", "ingest")
    assert runner.claim(pid, None, None) == list(runner.STEPS)
    assert _statuses(pid) == _expect("reserved")
    with pytest.raises(ReelcraftError, match="sedang diproses"):
        runner.claim(pid, None, None, queue=True)
    runner.recover_interrupted()  # the reserving process is gone
    assert _statuses(pid) == _expect("pending")


def test_server_queue_is_fifo_and_ignores_cli_reservations(sample_video):
    first, second, cli = (_project_with(sample_video) for _ in range(3))
    runner.claim(first, None, "ingest", queue=True)
    runner.claim(second, None, None, queue=True)
    runner.claim(cli, None, None)  # reserved for an in-process run, not for the worker

    assert runner.next_queued() == (first, ["ingest"])
    assert worker.run_next()
    assert runner.next_queued() == (second, list(runner.STEPS))
    assert worker.run_next()
    assert not worker.run_next()
    assert _statuses(first) == _expect("pending", ingest="done")
    assert _statuses(second) == _expect("done")
    assert _statuses(cli) == _expect("reserved")


def test_recovery_drops_steps_behind_a_dead_run_but_keeps_other_queues(sample_video):
    dead, waiting = _project_with(sample_video), _project_with(sample_video)
    runner.claim(dead, None, None, queue=True)
    runner.claim(waiting, None, None, queue=True)
    with session_scope() as s:  # simulate a crash in the middle of `dead`'s ingest
        s.get(StepRun, (dead, "ingest")).status = "running"

    runner.recover_interrupted()
    assert _statuses(dead) == _expect("pending", ingest="failed")
    assert _statuses(waiting) == _expect("queued")


def test_add_missing_local_file_is_rejected():
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        with pytest.raises(ReelcraftError, match="tidak ditemukan"):
            media.add(s, pid, "/nope/missing.mp4")


def test_delete_project_removes_its_files(sample_video):
    pid = _project_with(sample_video)
    runner.run(pid, end="ingest")
    assert project_dir(pid).is_dir()
    with session_scope() as s:
        projects.delete(s, pid)
    assert not project_dir(pid).exists()


def test_cli_media_run_status(sample_video):
    cli = CliRunner().invoke
    assert cli(app, ["project", "new", "cli"]).exit_code == 0
    with session_scope() as s:
        pid = projects.list_all(s)[0].id
    assert cli(app, ["media", "add", pid[:6], str(sample_video)]).exit_code == 0
    result = cli(app, ["run", pid[:6]])
    assert result.exit_code == 0, result.output
    assert "done" in cli(app, ["status", pid[:6]]).output
    assert "Semua step sudah selesai" in cli(app, ["run", pid[:6]]).output
    assert cli(app, ["run", pid[:6], "--from", "nope"]).exit_code == 1
