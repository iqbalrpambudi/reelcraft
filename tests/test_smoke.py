from fastapi.testclient import TestClient
from typer.testing import CliRunner

from reelcraft import __version__
from reelcraft.api.app import create_app
from reelcraft.cli import app


def test_cli_version():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"reelcraft {__version__}"


def test_api_health_and_version():
    client = TestClient(create_app())
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/version").json() == {"version": __version__}
