import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from reelcraft.api.app import create_app
from reelcraft.cli import app
from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.services import projects
from reelcraft.services.projects import ProjectCreate, ProjectUpdate
from reelcraft.storage.db import session_scope


def test_service_crud_and_timestamps_are_utc():
    with session_scope() as s:
        p = projects.create(s, ProjectCreate(name="  Jawa vs Eropa  "))
    assert p.name == "Jawa vs Eropa"
    assert p.created_at.tzinfo is not None

    with session_scope() as s:
        assert [x.id for x in projects.list_all(s)] == [p.id]
        renamed = projects.update(s, p.id, ProjectUpdate(name="Kalimantan"))
        assert renamed.name == "Kalimantan"
        assert renamed.updated_at >= p.updated_at
        projects.delete(s, p.id)

    with session_scope() as s, pytest.raises(NotFound):
        projects.get(s, p.id)


def test_blank_name_rejected():
    with pytest.raises(ValidationError):
        ProjectCreate(name="   ")


def test_resolve_id_by_unique_prefix():
    with session_scope() as s:
        a = projects.create(s, ProjectCreate(name="a"))
        projects.create(s, ProjectCreate(name="b"))
        assert projects.resolve_id(s, a.id[:6]) == a.id
        with pytest.raises(NotFound):
            projects.resolve_id(s, "zz")
        with pytest.raises(ReelcraftError, match="lebih dari satu"):
            projects.resolve_id(s, "")


def test_api_crud():
    client = TestClient(create_app())
    created = client.post("/api/v1/projects", json={"name": "Demo"})
    assert created.status_code == 201
    pid = created.json()["id"]

    assert client.get("/api/v1/projects").json()[0]["id"] == pid
    assert client.patch(f"/api/v1/projects/{pid}", json={"name": "Baru"}).json()["name"] == "Baru"
    assert client.post("/api/v1/projects", json={"name": ""}).status_code == 422
    assert client.delete(f"/api/v1/projects/{pid}").status_code == 204
    missing = client.get(f"/api/v1/projects/{pid}")
    assert missing.status_code == 404
    assert "tidak ditemukan" in missing.json()["detail"]


def test_cli_crud():
    run = CliRunner().invoke
    assert run(app, ["project", "new", "Demo CLI"]).exit_code == 0

    with session_scope() as s:
        pid = projects.list_all(s)[0].id
    assert "Demo CLI" in run(app, ["project", "list"]).output
    assert "Lain" in run(app, ["project", "rename", pid[:6], "Lain"]).output

    blank = run(app, ["project", "new", " "])
    assert blank.exit_code == 1

    assert run(app, ["project", "delete", pid[:6]], input="n\n").exit_code == 1
    assert run(app, ["project", "delete", pid[:6], "-y"]).exit_code == 0
    missing = run(app, ["project", "show", pid[:6]])
    assert missing.exit_code == 1
