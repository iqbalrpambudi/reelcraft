from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from reelcraft.ai import ideas
from reelcraft.cli import app
from reelcraft.core.errors import ReelcraftError
from reelcraft.core.secrets import encrypt
from reelcraft.pipeline import runner
from reelcraft.services import autopilot, discovery
from reelcraft.services.discovery import DiscoverOut, FootageOut
from reelcraft.storage import settings
from reelcraft.storage.db import session_scope
from reelcraft.storage.files import project_dir
from reelcraft.storage.models import Account, Media, Post, Project, StepRun

NOON = datetime(2026, 11, 21, 13, 0).astimezone()  # local time, after the 12:00 production


def _footage(url: str, free: bool) -> FootageOut:
    return FootageOut(
        source="pexels" if free else "youtube",
        url=url,
        page=url,
        title=url,
        thumbnail=None,
        duration=20,
        license="",
        free=free,
        author=None,
        imported=False,
    )


@pytest.fixture
def ai_and_search(monkeypatch):
    seen = {}

    async def suggest(model, niche, recent):
        seen["recent"] = recent
        return ideas.Idea(title=f"Ide {len(recent) + 1}", topic="Cara pandai besi", query="forge")

    monkeypatch.setattr(autopilot, "model_for", lambda task: None)
    monkeypatch.setattr(ideas, "suggest", suggest)
    results = [_footage(f"https://yt/{i}", False) for i in range(3)] + [
        _footage("https://px/1", True)
    ]
    monkeypatch.setattr(
        discovery, "search", lambda *a, **k: DiscoverOut(results=results, errors={})
    )
    monkeypatch.setattr(autopilot, "_last_attempt", 0.0)
    with session_scope() as s:
        settings.put(s, "autopilot", "on")
    return seen


def test_production_runs_once_per_window_and_stops_at_a_full_pool(ai_and_search, monkeypatch):
    autopilot.tick(NOON.replace(hour=11))  # before the first production time
    with session_scope() as s:
        assert s.query(Project).count() == 0

    autopilot.tick(NOON)
    with session_scope() as s:
        (project,) = s.query(Project).all()
        assert (project.name, project.autopilot) == ("Ide 1", True)
        sources = [m.source for m in s.query(Media).order_by(Media.created_at)]
        assert sources[0] == "https://px/1" and len(sources) == autopilot.CLIPS  # free first
        assert s.get(StepRun, (project.id, "ingest")).status == "queued"

    monkeypatch.setattr(autopilot, "_last_attempt", 0.0)
    autopilot.tick(NOON + timedelta(hours=1))  # same window: already made
    autopilot.tick(NOON.replace(hour=18, minute=5))
    with session_scope() as s:
        assert s.query(Project).count() == 2
        settings.put(s, "autopilot_pool", "2")
    assert ai_and_search["recent"] == ["Ide 1"]
    monkeypatch.setattr(autopilot, "_last_attempt", 0.0)
    autopilot.tick(NOON + timedelta(days=1))
    with session_scope() as s:
        assert s.query(Project).count() == 2  # pool of 2 is full


def test_no_footage_leaves_no_project(ai_and_search, monkeypatch):
    monkeypatch.setattr(
        discovery, "search", lambda *a, **k: DiscoverOut(results=[], errors={"pexels": "no key"})
    )
    with pytest.raises(ReelcraftError, match="no key"):
        autopilot.produce("niche")
    with session_scope() as s:
        assert s.query(Project).count() == 0


def _video(name: str, created: datetime, failed: bool = False) -> str:
    with session_scope() as s:
        project = Project(name=name, topic=f"tentang {name}", autopilot=True, created_at=created)
        s.add(project)
        s.flush()
        runner.ensure_runs(s, project.id)
        s.get(StepRun, (project.id, "render")).status = "failed" if failed else "done"
        pid = project.id
    project_dir(pid).mkdir(parents=True, exist_ok=True)
    (project_dir(pid) / "render.mp4").write_bytes(b"v")
    return pid


def test_ready_videos_take_the_next_free_slots_on_connected_platforms():
    morning = NOON.replace(hour=10)
    first = _video("Satu", morning - timedelta(hours=2))
    second = _video("Dua", morning - timedelta(hours=1))
    broken = _video("Rusak", morning, failed=True)
    with session_scope() as s:
        settings.put(s, "autopilot", "on")
        settings.put(s, "autopilot_production", "")
        settings.put(s, "autopilot_platforms", "youtube, facebook")
        s.add(Account(platform="youtube", remote_id="UC", name="Ch", token=encrypt("r")))
        assert autopilot.status(s).platforms == ["youtube"]  # facebook is not connected

    autopilot.tick(morning)
    with session_scope() as s:
        posts = {p.project_id: p for p in s.query(Post)}
        assert set(posts) == {first, second}
        assert posts[first].publish_at == morning.replace(hour=17).astimezone(UTC)
        assert posts[second].publish_at == (morning + timedelta(days=1)).replace(hour=7).astimezone(
            UTC
        )
        assert (posts[first].platform, posts[first].description) == ("youtube", "tentang Satu")
        out = autopilot.status(s)
        assert [(i.project_id, i.state) for i in out.pool] == [(broken, "failed")]
        assert morning.replace(hour=17) not in out.free_slots

    autopilot.tick(morning + timedelta(minutes=1))  # nothing new to place
    with session_scope() as s:
        assert s.query(Post).count() == 2


def test_bad_settings_are_reported():
    with session_scope() as s:
        settings.put(s, "autopilot_slots", "7 pagi")
        with pytest.raises(ReelcraftError, match="bukan jam"):
            autopilot.config(s)


def test_cli_shows_status():
    out = CliRunner().invoke(app, ["autopilot"])
    assert out.exit_code == 0, out.output
    assert "Autopilot OFF" in out.output and "Pool 0/4" in out.output
