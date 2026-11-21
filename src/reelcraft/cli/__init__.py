import shutil
import threading
import webbrowser
from typing import Annotated

import typer
import uvicorn

from reelcraft import __version__
from reelcraft.api.app import STATIC_DIR, create_app
from reelcraft.cli import config, media, pipeline, project
from reelcraft.core.config import get_settings
from reelcraft.media.tools import REQUIRED_TOOLS

app = typer.Typer(help="Reelcraft: a production line for short-form video.", no_args_is_help=True)
app.add_typer(project.app, name="project")
app.add_typer(media.app, name="media")
app.add_typer(config.app, name="config")
app.command()(pipeline.run)
app.command()(pipeline.status)
app.command()(pipeline.script)
app.command()(pipeline.jobs)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"reelcraft {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", "-V", callback=_print_version, is_eager=True, help="Show version."
        ),
    ] = False,
) -> None:
    pass


@app.command()
def serve(
    host: Annotated[str | None, typer.Option(help="Bind address.")] = None,
    port: Annotated[int | None, typer.Option(help="Port.")] = None,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the dashboard.")
    ] = True,
) -> None:
    """Run the API and the web dashboard."""
    settings = get_settings()
    host, port = host or settings.host, port or settings.port
    url = f"http://{host}:{port}"
    if not STATIC_DIR.is_dir():
        typer.echo(
            "Web build not found; API only. Run `make web-build` for the dashboard.", err=True
        )
    elif open_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()  # after uvicorn is listening
    typer.echo(f"Reelcraft {__version__} at {url}")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


@app.command()
def doctor() -> None:
    """Cek kesiapan: tool eksternal, data dir, dan dashboard."""
    settings = get_settings()
    checks = [(f"{tool} di PATH", shutil.which(tool) is not None) for tool in REQUIRED_TOOLS]
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.data_dir / ".write-test"
        probe.touch()
        probe.unlink()
        writable = True
    except OSError:
        writable = False
    checks += [
        (f"data dir bisa ditulis ({settings.data_dir})", writable),
        ("dashboard web ter-build", STATIC_DIR.is_dir()),
    ]
    typer.echo(f"reelcraft {__version__}")
    for label, ok in checks:
        typer.secho(f"  {'OK ' if ok else 'GAGAL'}  {label}", fg="green" if ok else "red")
    if not all(ok for _, ok in checks):
        raise typer.Exit(1)
