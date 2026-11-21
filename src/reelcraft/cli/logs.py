import json
import time
from datetime import datetime
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape

from reelcraft.core.logs import log_file

console = Console(highlight=False, soft_wrap=True)  # one entry, one line: greppable
LEVELS = ["debug", "info", "warning", "error", "critical"]
STYLE = {"warning": "yellow", "error": "red", "critical": "red"}
SKIP = {"event", "level", "timestamp", "logger", "exception"}


def _line(raw: str, level: int, project: str | None) -> str | None:
    """A JSON log line as one readable line, or None when filtered out."""
    try:
        entry: dict[str, Any] = json.loads(raw)
    except ValueError:
        return None
    name = entry.get("level", "info")
    if name in LEVELS and LEVELS.index(name) < level:
        return None
    if project and not str(entry.get("project", "")).startswith(project):
        return None
    when = datetime.fromisoformat(entry["timestamp"]).astimezone().strftime("%m-%d %H:%M:%S")
    fields = " ".join(
        f"{k}={str(v)[:8] if k in ('project', 'post') else v}"
        for k, v in entry.items()
        if k not in SKIP and v is not None
    )
    style = STYLE.get(name, "")
    text = (
        f"{when} {f'[{style}]' if style else ''}{name.upper():<7}{f'[/{style}]' if style else ''} "
    )
    text += f"{escape(str(entry.get('event', '')))} [dim]{escape(fields)}[/dim]"
    if entry.get("exception"):
        text += f"\n[dim]{escape(entry['exception'])}[/dim]"
    return text


def logs(
    lines: Annotated[int, typer.Option("--lines", "-n", help="Jumlah baris terakhir.")] = 40,
    follow: Annotated[
        bool, typer.Option("--follow", "-f", help="Terus tampilkan yang baru.")
    ] = False,
    level: Annotated[str, typer.Option(help=f"Minimal: {', '.join(LEVELS)}.")] = "info",
    project: Annotated[
        str | None, typer.Option(help="Hanya project ini (id atau awalannya).")
    ] = None,
) -> None:
    """Log server dan CLI: step, upload, Autopilot, error."""
    if level not in LEVELS:
        raise typer.BadParameter(f"Pilihan: {', '.join(LEVELS)}", param_hint="--level")
    path = log_file()
    if not path.is_file():
        console.print(f"Belum ada log di {path}.")
        return
    minimum = LEVELS.index(level)
    shown = [
        t
        for raw in path.read_text(encoding="utf-8").splitlines()
        if (t := _line(raw, minimum, project))
    ]
    for text in shown[-lines:]:
        console.print(text)
    if not follow:
        return
    handle = path.open(encoding="utf-8")
    handle.seek(0, 2)
    try:
        while True:
            raw = handle.readline()
            if raw:
                if text := _line(raw, minimum, project):
                    console.print(text)
                continue
            if path.stat().st_size < handle.tell():  # rotated: start on the new file
                handle.close()
                handle = path.open(encoding="utf-8")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        handle.close()
