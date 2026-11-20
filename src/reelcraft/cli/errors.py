from collections.abc import Iterator
from contextlib import contextmanager

import typer

from reelcraft.core.errors import ReelcraftError


@contextmanager
def user_errors() -> Iterator[None]:
    """Expected failures print one line and exit 1 instead of a traceback."""
    try:
        yield
    except ReelcraftError as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(1) from e
