from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from reelcraft.cli.common import ProjectId, user_errors
from reelcraft.media.discover import SOURCES
from reelcraft.services import discovery, media, projects
from reelcraft.storage.db import session_scope

app = typer.Typer(help="Kelola media sumber project.", no_args_is_help=True)
console = Console()


@app.command("add")
def add(
    project_id: ProjectId,
    sources: Annotated[list[str], typer.Argument(help="Path file video atau URL.")],
) -> None:
    """Tambah media; diproses saat step ingest berjalan."""
    with user_errors(), session_scope() as s:
        pid = projects.resolve_id(s, project_id)
        for source in sources:
            m = media.add(s, pid, source)
            console.print(f"Ditambahkan [dim]{m.id[:8]}[/dim] {m.source}")
    console.print("Jalankan [bold]reelcraft run[/bold] untuk memproses.")


@app.command("list")
def list_(project_id: ProjectId) -> None:
    """Daftar media project."""
    with user_errors(), session_scope() as s:
        rows = media.list_for(s, projects.resolve_id(s, project_id))
    if not rows:
        console.print("Belum ada media.")
        return
    table = Table("Id", "Status", "Durasi", "Resolusi", "Scene", "Sumber")
    for m in rows:
        table.add_row(
            m.id[:8],
            m.status if not m.error else f"{m.status}: {m.error[:60]}",
            f"{m.duration:.1f}s" if m.duration else "-",
            f"{m.width}x{m.height}" if m.width else "-",
            str(m.scene_count),
            m.source,
        )
    console.print(table)


@app.command("remove")
def remove(project_id: ProjectId, media_id: Annotated[str, typer.Argument()]) -> None:
    """Hapus media beserta filenya."""
    with user_errors(), session_scope() as s:
        pid = projects.resolve_id(s, project_id)
        match = [m.id for m in media.list_for(s, pid) if m.id.startswith(media_id)]
        if len(match) != 1:
            raise typer.BadParameter(f"Id media {media_id} tidak ditemukan atau ambigu")
        media.remove(s, pid, match[0])
    console.print("Media dihapus.")


@app.command("find")
def find(
    project_id: ProjectId,
    query: Annotated[str, typer.Argument(help="Kata kunci.")],
    source: Annotated[
        list[str] | None, typer.Option(help=f"Ulangi untuk beberapa: {', '.join(SOURCES)}.")
    ] = None,
    limit: Annotated[int, typer.Option(help="Hasil per sumber.")] = 8,
    min_duration: Annotated[float | None, typer.Option("--min", help="Durasi min (detik).")] = None,
    max_duration: Annotated[
        float | None, typer.Option("--max", help="Durasi maks (detik).")
    ] = None,
    free: Annotated[
        bool, typer.Option("--free", help="Hanya lisensi yang boleh diedit & dimonetisasi.")
    ] = False,
    add: Annotated[
        list[int] | None,
        typer.Option("--add", help="Impor hasil nomor ini (ulangi untuk beberapa)."),
    ] = None,
) -> None:
    """Cari footage di YouTube, Pexels, Pixabay, Archive.org; impor dengan --add."""
    with user_errors(), session_scope() as s:
        pid = projects.resolve_id(s, project_id)
        found = discovery.search(
            s, pid, query, source, limit, min_duration, max_duration, free, hide_imported=False
        )
        for name, error in found.errors.items():
            console.print(f"[yellow]{name}:[/yellow] {error}")
        if add:
            picked = [found.results[n - 1].url for n in add if 0 < n <= len(found.results)]
            for m in media.add_many(s, pid, picked):
                console.print(f"Ditambahkan [dim]{m.id[:8]}[/dim] {m.source}")
            console.print("Jalankan [bold]reelcraft run[/bold] untuk memproses.")
            return
    table = Table("No", "Sumber", "Durasi", "Lisensi", "Judul")
    table.add_column("URL", overflow="fold")  # wrapped, never cut: it gets copied
    for n, f in enumerate(found.results, 1):
        table.add_row(
            str(n) + (" ✓" if f.imported else ""),
            f.source,
            f"{f.duration:.0f}s" if f.duration else "-",
            "bebas" if f.free else f.license[:30],
            f.title[:50],
            f.url,
        )
    console.print(table)
