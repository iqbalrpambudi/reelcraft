import plistlib
import sys

from typer.testing import CliRunner

from reelcraft.cli import app, service


def _fake_os(monkeypatch, tmp_path, platform: str) -> list[tuple[str, ...]]:
    calls = []
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(service.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(service, "_run", lambda *a, check=True: calls.append(a))
    monkeypatch.setattr(service, "_healthy", lambda wait=0: True)
    monkeypatch.setenv("PATH", "/opt/homebrew/bin:/usr/bin")
    return calls


def test_launchd_install_carries_path_and_data_dir(monkeypatch, tmp_path):
    calls = _fake_os(monkeypatch, tmp_path, "darwin")
    out = CliRunner().invoke(app, ["service", "install"])
    assert out.exit_code == 0 and "menyala otomatis" in out.output
    plist = plistlib.loads((tmp_path / "Library/LaunchAgents/dev.reelcraft.plist").read_bytes())
    assert plist["ProgramArguments"][1:] == ["-m", "reelcraft", "serve", "--no-open"]
    assert plist["EnvironmentVariables"]["PATH"] == "/opt/homebrew/bin:/usr/bin"  # finds ffmpeg
    assert plist["EnvironmentVariables"]["REELCRAFT_DATA_DIR"]
    assert plist["StandardOutPath"].endswith("logs/service.log")
    assert calls[-1][:2] == ("launchctl", "bootstrap")

    CliRunner().invoke(app, ["service", "uninstall"])
    assert not (tmp_path / "Library/LaunchAgents/dev.reelcraft.plist").exists()
    assert calls[-1][:2] == ("launchctl", "bootout")


def test_systemd_unit_is_enabled_for_the_user(monkeypatch, tmp_path):
    calls = _fake_os(monkeypatch, tmp_path, "linux")
    assert CliRunner().invoke(app, ["service", "install"]).exit_code == 0
    unit = (tmp_path / ".config/systemd/user/reelcraft.service").read_text()
    assert "-m reelcraft serve --no-open" in unit and "Restart=on-failure" in unit
    assert 'Environment="PATH=/opt/homebrew/bin:/usr/bin"' in unit
    assert ("systemctl", "--user", "enable", "--now", "reelcraft.service") in calls


def test_start_needs_install(monkeypatch, tmp_path):
    _fake_os(monkeypatch, tmp_path, "darwin")
    out = CliRunner().invoke(app, ["service", "start"])
    assert out.exit_code == 1 and "Belum dipasang" in out.output
