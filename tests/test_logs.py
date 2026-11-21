import json
import logging

from typer.testing import CliRunner

from reelcraft.cli import app
from reelcraft.core import logs
from reelcraft.services import media, projects
from reelcraft.services.projects import ProjectCreate
from reelcraft.storage.db import session_scope


def test_cli_runs_are_logged_as_json_and_read_back(sample_video):
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        media.add(s, pid, str(sample_video))
    cli = CliRunner().invoke
    assert cli(app, ["run", pid[:8], "--to", "analyze"]).exit_code == 0
    logging.getLogger("reelcraft.test").error("kaput", exc_info=ValueError("boom"))

    entries = [json.loads(line) for line in logs.log_file().read_text().splitlines()]
    steps = [e for e in entries if e["event"] == "step"]
    assert [(e["step"], e["status"]) for e in steps] == [("ingest", "done"), ("analyze", "done")]
    assert all(e["project"] == pid and "seconds" in e and e["level"] == "info" for e in steps)

    shown = cli(app, ["logs", "--project", pid[:8]]).output
    assert "step" in shown and "step=analyze" in shown and "kaput" not in shown
    errors = cli(app, ["logs", "--level", "error"]).output
    assert "kaput" in errors and "ValueError: boom" in errors and "step=" not in errors
    assert cli(app, ["logs", "-n", "1", "--level", "error"]).output.count("kaput") == 1
    assert cli(app, ["logs", "--level", "loud"]).exit_code == 2
