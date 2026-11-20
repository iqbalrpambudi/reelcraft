import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from typer.testing import CliRunner

from reelcraft.ai import models
from reelcraft.api.app import create_app
from reelcraft.cli import app
from reelcraft.core.config import get_settings
from reelcraft.core.errors import ReelcraftError
from reelcraft.pipeline import runner
from reelcraft.pipeline.steps import tag
from reelcraft.services import media, projects
from reelcraft.services import settings as settings_service
from reelcraft.services.projects import ProjectCreate
from reelcraft.storage import settings
from reelcraft.storage.db import session_scope
from reelcraft.storage.models import Setting

KEY = "AIzaSy-test-key-1234"


def test_secret_is_encrypted_at_rest_and_masked():
    with session_scope() as s:
        settings.put(s, "gemini_api_key", KEY)
    with session_scope() as s:
        assert s.get(Setting, "gemini_api_key").value != KEY
        assert settings.get(s, "gemini_api_key") == KEY
        out = {o.key: o for o in settings_service.list_all(s)}
    assert out["gemini_api_key"].value == "••••1234"
    assert out["gemini_api_key"].source == "db"
    assert (get_settings().data_dir / "secret.key").stat().st_mode & 0o777 == 0o600


def test_resolution_order_db_then_env_then_default(monkeypatch):
    with session_scope() as s:
        assert settings.resolve(s, "vision_model") == ("google:gemini-flash-lite-latest", "default")
        monkeypatch.setenv("REELCRAFT_VISION_MODEL", "openai:gpt-x")
        get_settings.cache_clear()
        assert settings.resolve(s, "vision_model") == ("openai:gpt-x", "env")
        settings.put(s, "vision_model", "google:custom")
        assert settings.resolve(s, "vision_model") == ("google:custom", "db")
        settings.put(s, "vision_model", "  ")  # blank removes the saved value
        assert settings.resolve(s, "vision_model")[1] == "env"
        with pytest.raises(ReelcraftError, match="tidak dikenal"):
            settings.put(s, "nope", "x")


def test_build_model_errors_are_actionable():
    with session_scope() as s:
        with pytest.raises(ReelcraftError, match="Gemini API key belum diatur"):
            models.build(s, "google:gemini-x")
        with pytest.raises(ReelcraftError, match="provider:model"):
            models.build(s, "gemini-x")
        with pytest.raises(ReelcraftError, match="tidak dikenal"):
            models.build(s, "anthropic:x")
        settings.put(s, "openai_base_url", "http://localhost:11434/v1")
        assert models.build(s, "openai:llama3").model_name == "llama3"  # local server, no key


def _analyzed_project(sample_video) -> str:
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        media.add(s, pid, str(sample_video))
    assert runner.run(pid, end="analyze") == "done"
    return pid


def test_tag_step_describes_scenes_and_rerun_only_retries_gaps(sample_video, monkeypatch):
    pid = _analyzed_project(sample_video)
    answer = {"scenes": [{"image": 1, "description": "Layar merah polos.", "tags": ["merah"]}]}
    monkeypatch.setattr(tag, "model_for", lambda task: TestModel(custom_output_args=answer))

    # Image 2 missing from the answer: that scene fails, the step fails, image 1 is kept
    assert runner.run(pid) == "failed"
    with session_scope() as s:
        first, second = media.scenes_for(s, pid)
    assert first.description == "Layar merah polos." and first.tags == ["merah"]
    assert second.description is None and second.tag_error

    monkeypatch.setattr(
        tag,
        "model_for",
        lambda task: TestModel(
            custom_output_args={"scenes": [{"image": 1, "description": "Biru.", "tags": ["biru"]}]}
        ),
    )
    assert runner.run(pid, start="tag") == "done"
    with session_scope() as s:
        first, second = media.scenes_for(s, pid)
    assert first.description == "Layar merah polos."  # untouched by the rerun
    assert second.description == "Biru." and second.tag_error is None


def test_tag_step_retries_overload_but_not_bad_requests(sample_video, monkeypatch):
    pid = _analyzed_project(sample_video)
    monkeypatch.setattr(tag, "RETRY_WAITS", (0, 0))
    attempts = []

    def failing(status: int):
        def fn(messages, info):
            attempts.append(status)
            raise ModelHTTPError(
                status_code=status, model_name="m", body={"error": {"message": "sibuk"}}
            )

        return FunctionModel(fn)

    monkeypatch.setattr(tag, "model_for", lambda task: failing(503))
    assert runner.run(pid, start="tag") == "failed"
    assert attempts == [503, 503, 503]  # first try + 2 retries

    attempts.clear()
    monkeypatch.setattr(tag, "model_for", lambda task: failing(400))
    assert runner.run(pid, start="tag") == "failed"
    assert attempts == [400]
    with session_scope() as s:
        assert "sibuk" in (media.scenes_for(s, pid)[0].tag_error or "")


def test_settings_api_and_cli(monkeypatch):
    client = TestClient(create_app())
    out = client.patch("/api/v1/settings", json={"gemini_api_key": KEY, "text_model": "google:x"})
    assert out.status_code == 200
    by_key = {o["key"]: o for o in out.json()}
    assert by_key["gemini_api_key"]["value"] == "••••1234"
    assert by_key["text_model"] == {**by_key["text_model"], "value": "google:x", "source": "db"}
    assert client.patch("/api/v1/settings", json={"bogus": "1"}).status_code == 400

    monkeypatch.setattr(models, "build", lambda s, spec: TestModel(custom_output_text="OK"))
    checks = client.post("/api/v1/settings/check-ai").json()
    assert [c["ok"] for c in checks] == [True, True]

    cli = CliRunner().invoke
    assert cli(app, ["config", "set", "openai_api_key"], input="sk-rahasia-9999\n").exit_code == 0
    listed = cli(app, ["config", "list"]).output
    assert "••••9999" in listed and "sk-rahasia" not in listed
    assert cli(app, ["config", "unset", "openai_api_key"]).exit_code == 0
    assert cli(app, ["config", "check"]).exit_code == 0
