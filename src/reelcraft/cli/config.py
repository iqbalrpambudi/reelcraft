from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from reelcraft.cli.common import user_errors
from reelcraft.services import settings
from reelcraft.storage.db import session_scope
from reelcraft.storage.settings import SPECS

app = typer.Typer(help="Pengaturan: API key dan model AI.", no_args_is_help=True)
console = Console()

Key = Annotated[str, typer.Argument(help=f"Salah satu: {', '.join(SPECS)}.")]


@app.command("list")
def list_() -> None:
    """Semua pengaturan dan asal nilainya (db, env, default)."""
    with user_errors(), session_scope() as s:
        rows = settings.list_all(s)
    table = Table("Key", "Nilai", "Asal")
    for r in rows:
        table.add_row(r.key, r.value or "[dim]-[/dim]", r.source)
    console.print(table)


@app.command("set")
def set_(
    key: Key,
    value: Annotated[str | None, typer.Argument(help="Kosongkan untuk diminta tanpa echo.")] = None,
) -> None:
    """Simpan pengaturan. API key disimpan terenkripsi."""
    if key in SPECS and value is None:
        value = typer.prompt(SPECS[key].label, hide_input=SPECS[key].secret)
    with user_errors(), session_scope() as s:
        settings.update(s, {key: value})
    console.print(f"{key} disimpan.")


@app.command("unset")
def unset(key: Key) -> None:
    """Hapus nilai tersimpan; env atau default berlaku lagi."""
    with user_errors(), session_scope() as s:
        settings.update(s, {key: None})
    console.print(f"{key} dihapus.")


@app.command("check")
def check() -> None:
    """Uji koneksi ke model teks dan vision."""
    with user_errors():
        results = settings.check_ai()
    for r in results:
        mark = "[green]OK[/green]   " if r.ok else "[red]GAGAL[/red]"
        console.print(f"{mark} {r.task:<6} {r.model}  [dim]{r.message}[/dim]")
    if not all(r.ok for r in results):
        raise typer.Exit(1)
