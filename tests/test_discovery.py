from fastapi.testclient import TestClient
from typer.testing import CliRunner

from reelcraft.api.app import create_app
from reelcraft.cli import app
from reelcraft.media import discover
from reelcraft.services import projects
from reelcraft.services.projects import ProjectCreate
from reelcraft.storage import settings
from reelcraft.storage.db import session_scope

PEXELS = {
    "videos": [
        {
            "id": 1,
            "url": "https://www.pexels.com/video/waves-on-a-beach-1/",
            "image": "https://images.pexels.com/1.jpg",
            "duration": 12,
            "user": {"name": "Ana"},
            "video_files": [
                {
                    "file_type": "video/mp4",
                    "width": 3840,
                    "height": 2160,
                    "link": "https://p/4k.mp4",
                },
                {
                    "file_type": "video/mp4",
                    "width": 1920,
                    "height": 1080,
                    "link": "https://p/hd.mp4",
                },
                {"file_type": "video/mp4", "width": 640, "height": 360, "link": "https://p/sd.mp4"},
            ],
        }
    ]
}
PIXABAY = {
    "hits": [
        {
            "id": 7,
            "pageURL": "https://pixabay.com/videos/7",
            "tags": "beach, sea",
            "duration": 40,
            "user": "Budi",
            "videos": {
                "large": {"url": ""},
                "medium": {"url": "https://x/m.mp4", "thumbnail": "t"},
            },
        }
    ]
}
ARCHIVE = {
    "response": {
        "docs": [
            {
                "identifier": "a",
                "title": "Bebas",
                "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                "runtime": "0:25",
            },
            {
                "identifier": "b",
                "title": "NC",
                "licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/",
                "runtime": "about 3 min",
            },
        ]
    }
}
YOUTUBE = [
    {"url": "https://www.youtube.com/watch?v=x", "title": "Pantai", "duration": 300, "channel": "C"}
]


def _offline(monkeypatch, calls: list) -> None:
    answers = {"api.pexels.com": PEXELS, "pixabay.com": PIXABAY, "archive.org": ARCHIVE}

    def get_json(url, params, headers=None):
        calls.append((url, params, headers))
        return next(v for host, v in answers.items() if host in url)

    monkeypatch.setattr(discover, "_get_json", get_json)
    monkeypatch.setattr(discover, "_ytsearch", lambda q, n: YOUTUBE)


def test_sources_normalise_to_importable_footage(monkeypatch):
    calls = []
    _offline(monkeypatch, calls)
    (pexels,) = discover.search("pexels", "pantai", 5, key="k")
    assert pexels.url == "https://p/hd.mp4"  # biggest file at most 1080p
    assert (pexels.title, pexels.author, pexels.free) == ("Waves on a beach", "Ana", True)
    assert calls[-1][2] == {"Authorization": "k"}
    (pixabay,) = discover.search("pixabay", "pantai", 5, key="k")
    assert pixabay.url == "https://x/m.mp4"  # empty large skipped
    free, nc = discover.search("archive", "pantai", 5, free_only=True)
    assert (free.free, free.duration, free.url) == (True, 25.0, "https://archive.org/details/a")
    assert (nc.free, nc.duration) == (False, None)  # non-commercial is not reusable
    assert r"licenseurl:*licenses\/by\/*" in calls[-1][1]["q"]
    (yt,) = discover.search("youtube", "pantai", 5)
    assert not yt.free


def test_search_filters_marks_imported_and_reports_missing_keys(monkeypatch):
    _offline(monkeypatch, [])
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        settings.put(s, "pexels_api_key", "k")
    client = TestClient(create_app())
    base = f"/api/v1/projects/{pid}"
    assert (
        client.post(f"{base}/media/batch", json={"sources": ["https://p/hd.mp4"]}).status_code
        == 201
    )

    out = client.get(f"{base}/discover", params={"q": "pantai"}).json()
    assert set(out["errors"]) == {"pixabay"}  # no key; the others still answer
    assert {r["source"] for r in out["results"]} == {"youtube", "pexels", "archive"}
    assert next(r for r in out["results"] if r["source"] == "pexels")["imported"]

    params = {"q": "pantai", "max_duration": 60, "free_only": True, "hide_imported": True}
    out = client.get(f"{base}/discover", params=params).json()
    assert [r["url"] for r in out["results"]] == ["https://archive.org/details/a"]
    assert client.get(f"{base}/discover", params={"q": " "}).status_code == 400


def test_cli_find_lists_and_imports(monkeypatch):
    _offline(monkeypatch, [])
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
    cli = CliRunner().invoke
    listed = cli(
        app, ["media", "find", pid[:8], "pantai", "--source", "youtube", "--source", "archive"]
    )
    assert listed.exit_code == 0 and "Pantai" in listed.output and "Bebas" in listed.output
    added = cli(app, ["media", "find", pid[:8], "pantai", "--source", "youtube", "--add", "1"])
    assert added.exit_code == 0 and "Ditambahkan" in added.output
    assert "youtube.com" in cli(app, ["media", "list", pid[:8]]).output
