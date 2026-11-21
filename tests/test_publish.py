import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from reelcraft.api.app import create_app
from reelcraft.cli import app
from reelcraft.core.secrets import encrypt
from reelcraft.pipeline import runner
from reelcraft.publish import facebook, youtube
from reelcraft.services import projects, publishing
from reelcraft.services.projects import ProjectCreate
from reelcraft.storage import settings
from reelcraft.storage.db import session_scope
from reelcraft.storage.files import project_dir
from reelcraft.storage.models import Account, Post, StepRun


def test_youtube_resumes_chunks_and_schedules(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube, "CHUNK_SIZE", 4)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"0123456789")
    seen = []

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "A"})
        if req.method == "POST":
            return httpx.Response(200, headers={"location": "https://up/session"})
        end = int(req.headers["content-range"].split("-")[1].split("/")[0])
        if end < 9:  # pretend only the first 3 bytes of the first chunk arrived
            return httpx.Response(308, headers={"range": f"bytes=0-{2 if end == 3 else end}"})
        return httpx.Response(200, json={"id": "vid1"})

    at = datetime.now(UTC) + timedelta(days=1)
    done = []
    vid = youtube.upload(
        "c", "s", "r", video, "T", "D", "public", at, done.append, httpx.MockTransport(handle)
    )
    assert vid == "vid1" and done[-1] == 100
    meta = json.loads(seen[1].content)
    assert meta["status"]["privacyStatus"] == "private"
    assert meta["status"]["publishAt"].endswith("Z")
    ranges = [r.headers["content-range"] for r in seen[2:]]
    assert ranges == ["bytes 0-3/10", "bytes 3-6/10", "bytes 7-9/10"]


def test_facebook_schedules_only_far_enough_ahead(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    finishes = []

    def handle(req: httpx.Request) -> httpx.Response:
        form = (
            parse_qs(req.content.decode())
            if req.headers.get("content-type", "").startswith("application/x-www")
            else {}
        )
        if form.get("upload_phase") == ["start"]:
            return httpx.Response(200, json={"video_id": "fb1", "upload_url": "https://rupload/x"})
        if form.get("upload_phase") == ["finish"]:
            finishes.append(form)
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"success": True})

    t = httpx.MockTransport(handle)
    soon, later = datetime.now(UTC) + timedelta(minutes=5), datetime.now(UTC) + timedelta(hours=2)
    assert facebook.upload("p", "tok", video, "d", soon, transport=t) == "fb1"
    facebook.upload("p", "tok", video, "d", later, transport=t)
    assert finishes[0]["video_state"] == ["PUBLISHED"]
    assert finishes[1]["video_state"] == ["SCHEDULED"]
    assert finishes[1]["scheduled_publish_time"] == [str(int(later.timestamp()))]


def _rendered_project() -> str:
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="Keris")).id
        projects.update(s, pid, projects.ProjectUpdate(topic="Cara membuat keris"))
        runner.ensure_runs(s, pid)
        s.get(StepRun, (pid, "render")).status = "done"
    project_dir(pid).mkdir(parents=True, exist_ok=True)
    (project_dir(pid) / "render.mp4").write_bytes(b"video")
    return pid


def test_connect_post_and_upload_through_the_api(monkeypatch):
    pid = _rendered_project()
    client = TestClient(create_app())
    no_keys = client.post("/api/v1/accounts/youtube/connect")
    assert "Isi youtube_client_id" in no_keys.json()["detail"]
    with session_scope() as s:
        settings.put(s, "youtube_client_id", "cid")
        settings.put(s, "youtube_client_secret", "sec")

    go = client.post("/api/v1/accounts/youtube/connect").json()
    query = parse_qs(urlparse(go["url"]).query)
    assert query["redirect_uri"] == ["http://testserver/api/v1/accounts/youtube/callback"]
    monkeypatch.setattr(youtube, "connect", lambda *a: ("UC1", "Channel Saya", "refresh"))
    back = client.get(
        "/api/v1/accounts/youtube/callback",
        params={"code": "c", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert back.headers["location"] == "/settings?connected=youtube"
    assert client.get("/api/v1/accounts").json()[0]["name"] == "Channel Saya"
    with session_scope() as s:
        assert s.get(Account, "youtube").token != "refresh"  # stored encrypted
    replay = client.get(
        "/api/v1/accounts/youtube/callback",
        params={"code": "c", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert "kedaluwarsa" in replay.headers["location"]

    base = f"/api/v1/projects/{pid}/posts"
    assert (
        "belum dihubungkan"
        in client.post(base, json={"platform": "facebook", "title": "x"}).json()["detail"]
    )
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert (
        "lewat"
        in client.post(base, json={"platform": "youtube", "title": "x", "publish_at": past}).json()[
            "detail"
        ]
    )
    at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    post = client.post(
        base, json={"platform": "youtube", "title": "Keris", "publish_at": at}
    ).json()
    assert post["status"] == "queued"

    calls = []
    monkeypatch.setattr(youtube, "upload", lambda *a: calls.append(a) or "vid9")
    assert publishing.upload()  # what the server's scheduler does
    assert publishing.upload() is None  # nothing left
    assert calls[0][2] == "refresh" and calls[0][4] == "Keris"
    (done,) = client.get("/api/v1/posts").json()
    assert (done["status"], done["url"]) == ("done", "https://youtube.com/shorts/vid9")
    assert client.delete(f"/api/v1/posts/{done['id']}").status_code == 400


def test_failed_upload_keeps_the_reason_and_can_retry(monkeypatch):
    pid = _rendered_project()
    with session_scope() as s:
        s.add(Account(platform="facebook", remote_id="page", name="Page", token=encrypt("t")))
        post_id = publishing.create(s, pid, publishing.PostIn(platform="facebook", title="T")).id

    def offline(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(facebook, "upload", offline)
    out = publishing.upload(post_id)
    assert out and out.status == "failed" and "ConnectError" in (out.error or "")
    client = TestClient(create_app())
    assert client.post(f"/api/v1/posts/{post_id}/retry").status_code == 204
    monkeypatch.setattr(facebook, "upload", lambda page, token, file, text, *a: "fb2")
    assert publishing.upload(post_id).url == "https://www.facebook.com/reel/fb2"

    with session_scope() as s:
        s.get(Post, post_id).status = "uploading"
    publishing.recover_interrupted()
    with session_scope() as s:
        assert s.get(Post, post_id).status == "failed"


def test_cli_publish_and_posts(monkeypatch):
    pid = _rendered_project()
    cli = CliRunner().invoke
    assert "belum dihubungkan" in cli(app, ["publish", pid[:8], "--to", "youtube"]).output
    with session_scope() as s:
        s.add(Account(platform="youtube", remote_id="UC", name="Ch", token=encrypt("r")))
        settings.put(s, "youtube_client_id", "cid")
        settings.put(s, "youtube_client_secret", "sec")
    monkeypatch.setattr(youtube, "upload", lambda *a: "vid3")
    out = cli(app, ["publish", pid[:8], "--to", "youtube", "--at", "2999-01-01 09:00"])
    assert out.exit_code == 0, out.output
    assert "youtube.com/shorts/vid3" in out.output and "2999-01-01 09:00" in out.output
    listed = cli(app, ["posts"])
    assert "Keris" in listed.output and "done" in listed.output
