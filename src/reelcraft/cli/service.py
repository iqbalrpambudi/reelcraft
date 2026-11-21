"""`reelcraft serve` as a background service that starts at login: launchd on macOS, a systemd
user unit on Linux."""

import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

import httpx
import typer

from reelcraft.core.config import get_settings

app = typer.Typer(help="Jalankan server di background, otomatis saat login.", no_args_is_help=True)
LABEL = "dev.reelcraft"
UNIT = "reelcraft.service"


def _command() -> list[str]:
    return [sys.executable, "-m", "reelcraft", "serve", "--no-open"]


def _environment() -> dict[str, str]:
    # A login service gets a bare PATH (no Homebrew ffmpeg) and none of this shell's variables
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    env.update({k: v for k, v in os.environ.items() if k.startswith("REELCRAFT_")})
    env["REELCRAFT_DATA_DIR"] = str(get_settings().data_dir.resolve())
    return env


def log_file() -> Path:
    return get_settings().data_dir / "logs" / "service.log"


def launchd_plist() -> bytes:
    log = str(log_file())
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": _command(),
            "EnvironmentVariables": _environment(),
            "WorkingDirectory": str(Path.cwd()),  # where a .env with settings may live
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},  # restart after a crash, not after a stop
            "StandardOutPath": log,
            "StandardErrorPath": log,
        }
    )


def systemd_unit() -> str:
    env = "\n".join(f'Environment="{k}={v}"' for k, v in _environment().items())
    return f"""[Unit]
Description=Reelcraft
After=network-online.target

[Service]
ExecStart={" ".join(_command())}
WorkingDirectory={Path.cwd()}
{env}
Restart=on-failure
StandardOutput=append:{log_file()}
StandardError=append:{log_file()}

[Install]
WantedBy=default.target
"""


def _path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    if sys.platform.startswith("linux"):
        return Path.home() / ".config" / "systemd" / "user" / UNIT
    typer.secho("Mode service hanya untuk macOS (launchd) dan Linux (systemd).", fg="red", err=True)
    raise typer.Exit(1)


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        typer.secho(f"{' '.join(args)} gagal: {result.stderr.strip()}", fg="red", err=True)
        raise typer.Exit(1)
    return result


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _start(path: Path) -> None:
    if sys.platform == "darwin":
        _run("launchctl", "bootout", f"{_domain()}/{LABEL}", check=False)  # reload if loaded
        _run("launchctl", "bootstrap", _domain(), str(path))
    else:
        _run("systemctl", "--user", "daemon-reload")
        _run("systemctl", "--user", "enable", "--now", UNIT)


def _stop() -> None:
    if sys.platform == "darwin":
        _run("launchctl", "bootout", f"{_domain()}/{LABEL}", check=False)
    else:
        _run("systemctl", "--user", "disable", "--now", UNIT, check=False)


def _url() -> str:
    s = get_settings()
    return f"http://{s.host}:{s.port}"


def _healthy(wait: float = 0) -> bool:
    end = time.monotonic() + wait
    while True:
        try:
            if httpx.get(f"{_url()}/api/v1/health", timeout=2).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        if time.monotonic() >= end:
            return False
        time.sleep(0.5)


@app.command()
def install() -> None:
    """Pasang dan jalankan; ikut menyala tiap login."""
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    log_file().parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        path.write_bytes(launchd_plist())
    else:
        path.write_text(systemd_unit())
    _start(path)
    if _healthy(wait=20):
        typer.echo(f"Reelcraft berjalan di {_url()} dan menyala otomatis saat login.")
    else:
        typer.secho(f"Terpasang, tapi belum menjawab. Lihat {log_file()}", fg="yellow")


@app.command()
def uninstall() -> None:
    """Hentikan dan lepas dari login."""
    path = _path()
    _stop()
    path.unlink(missing_ok=True)
    if sys.platform.startswith("linux"):
        _run("systemctl", "--user", "daemon-reload", check=False)
    typer.echo("Service dilepas.")


@app.command()
def start() -> None:
    """Nyalakan service yang sudah dipasang."""
    path = _path()
    if not path.is_file():
        typer.secho("Belum dipasang. Jalankan `reelcraft service install`.", fg="red", err=True)
        raise typer.Exit(1)
    _start(path)
    typer.echo("Dinyalakan." if _healthy(wait=20) else f"Belum menjawab. Lihat {log_file()}")


@app.command()
def stop() -> None:
    """Matikan sampai `start` atau login berikutnya."""
    _path()
    if sys.platform == "darwin":
        _stop()  # bootout; RunAtLoad brings it back at the next login
    else:
        _run("systemctl", "--user", "stop", UNIT, check=False)
    typer.echo("Dimatikan.")


@app.command()
def status() -> None:
    """Terpasang? Berjalan?"""
    path = _path()
    installed = path.is_file()
    running = _healthy()
    typer.echo(f"Terpasang: {'ya' if installed else 'tidak'} ({path})")
    typer.echo(f"Berjalan:  {'ya, ' + _url() if running else 'tidak'}")
    typer.echo(f"Log:       {log_file()}")
