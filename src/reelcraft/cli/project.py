from datetime import datetime
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from reelcraft.cli.common import ProjectId, user_errors
from reelcraft.core.errors import ReelcraftError
from reelcraft.services import projects
from reelcraft.services.projects import ProjectCreate, ProjectOut, ProjectUpdate
from reelcraft.storage.db import session_scope

app = typer.Typer(help="Kelola project.", no_args_is_help=True)
console = Console()


def _local(dt: datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def _show(p: ProjectOut) -> None:
    console.print(f"[bold]{p.name}[/bold]  [dim]{p.id}[/dim]  dibuat {_local(p.created_at)}")


def _validated[T](model: type[T], **data: object) -> T:
    try:
        return model(**data)
    except ValidationError as e:
        raise ReelcraftError(e.errors()[0]["msg"]) from e


@app.command("new")
def new(name: Annotated[str, typer.Argument(help="Nama project.")]) -> None:
    """Buat project baru."""
    with user_errors(), session_scope() as s:
        _show(projects.create(s, _validated(ProjectCreate, name=name)))


@app.command("list")
def list_() -> None:
    """Daftar project, terbaru di atas."""
    with session_scope() as s:
        rows = projects.list_all(s)
    if not rows:
        console.print("Belum ada project. Buat dengan [bold]reelcraft project new <nama>[/bold].")
        return
    table = Table("Id", "Nama", "Dibuat", "Diubah")
    for p in rows:
        table.add_row(p.id[:8], p.name, _local(p.created_at), _local(p.updated_at))
    console.print(table)


@app.command("show")
def show(project_id: ProjectId) -> None:
    """Detail satu project."""
    with user_errors(), session_scope() as s:
        _show(projects.get(s, projects.resolve_id(s, project_id)))


@app.command("rename")
def rename(project_id: ProjectId, name: Annotated[str, typer.Argument(help="Nama baru.")]) -> None:
    """Ganti nama project."""
    with user_errors(), session_scope() as s:
        data = _validated(ProjectUpdate, name=name)
        _show(projects.update(s, projects.resolve_id(s, project_id), data))


@app.command("delete")
def delete(
    project_id: ProjectId,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Tanpa konfirmasi.")] = False,
) -> None:
    """Hapus project."""
    with user_errors(), session_scope() as s:
        p = projects.get(s, projects.resolve_id(s, project_id))
        if not yes:
            typer.confirm(f"Hapus project '{p.name}'?", abort=True)
        projects.delete(s, p.id)
    console.print(f"Project '{p.name}' dihapus.")
