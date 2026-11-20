import threading
import webbrowser
from typing import Annotated

import typer
import uvicorn

from reelcraft import __version__
from reelcraft.api.app import STATIC_DIR, create_app
from reelcraft.core.config import get_settings

app = typer.Typer(help="Reelcraft: a production line for short-form video.", no_args_is_help=True)


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
