import json

import pytest
from fastapi.testclient import TestClient

from reelcraft.api import app as app_module
from reelcraft.api.app import create_app
from reelcraft.pipeline import runner, worker
from reelcraft.storage.files import UPLOADS, project_dir


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())  # no `with`: lifespan (and its worker thread) stays off


def _project(client: TestClient) -> str:
    return client.post("/api/v1/projects", json={"name": "web"}).json()["id"]


def test_upload_run_and_browse_results(client, sample_video):
    pid = _project(client)
    base = f"/api/v1/projects/{pid}"
    with sample_video.open("rb") as f:
        up = client.post(f"{base}/media/upload", files={"file": ("../../evil.MP4", f)})
    assert up.status_code == 201
    assert "/uploads/" in up.json()["source"] and up.json()["source"].endswith(".mp4")

    queued = client.post(f"{base}/run", json={})
    assert queued.status_code == 202
    assert [s["status"] for s in queued.json()] == ["queued"] * len(runner.STEPS)
    assert client.post(f"{base}/run", json={}).status_code == 400  # already busy

    assert worker.run_next()
    assert [s["status"] for s in client.get(f"{base}/steps").json()] == ["done"] * len(runner.STEPS)
    [m] = client.get(f"{base}/media").json()
    assert m["status"] == "ready" and m["scene_count"] == 2
    assert not any((project_dir(pid) / UPLOADS).iterdir())  # moved into media/, not copied

    scenes = client.get(f"{base}/scenes").json()
    thumb = client.get(f"{base}/files/{scenes[0]['thumbnail']}")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert client.get(f"{base}/files/../../reelcraft.db").status_code == 404


def test_add_url_remove_and_cancel(client):
    pid = _project(client)
    base = f"/api/v1/projects/{pid}"
    m = client.post(f"{base}/media", json={"source": "https://example.com/v"}).json()
    assert client.post(f"{base}/media", json={"source": "/no/such.mp4"}).status_code == 400
    client.post(f"{base}/run", json={})
    assert client.post(f"{base}/cancel").status_code == 204
    assert {s["status"] for s in client.get(f"{base}/steps").json()} == {"pending"}
    assert client.delete(f"{base}/media/{m['id']}").status_code == 204
    assert client.get(f"{base}/media").json() == []


def test_events_stream_starts_with_current_steps(client):
    pid = _project(client)
    with client.stream("GET", f"/api/v1/projects/{pid}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        first = next(r.iter_lines())
    assert [s["step"] for s in json.loads(first.removeprefix("data: "))] == list(runner.STEPS)
    assert client.get("/api/v1/projects/nope/events").status_code == 404


def test_spa_fallback_serves_index_but_not_for_api(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<title>Reelcraft</title>")
    monkeypatch.setattr(app_module, "STATIC_DIR", tmp_path)
    client = TestClient(create_app())
    assert "Reelcraft" in client.get("/projects/abc").text
    assert client.get("/api/v1/nope").status_code == 404
