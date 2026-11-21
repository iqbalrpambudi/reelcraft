from datetime import datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from reelcraft.cli.common import ProjectId, user_errors
from reelcraft.core.errors import ReelcraftError
from reelcraft.services import projects, publishing
from reelcraft.services.publishing import PostIn
from reelcraft.storage.db import session_scope

console = Console()


def _when(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).astimezone()  # no zone given = this computer's
    except ValueError as e:
        raise ReelcraftError(f"Format waktu salah: {text}. Contoh: 2026-11-22 09:00") from e


def publish(
    project_id: ProjectId,
    to: Annotated[
        list[str], typer.Option(help="youtube dan/atau facebook; ulangi untuk keduanya.")
    ],
    title: Annotated[str | None, typer.Option(help="Judul. Default: nama project.")] = None,
    description: Annotated[str | None, typer.Option(help="Deskripsi. Default: topik.")] = None,
    at: Annotated[
        str | None, typer.Option(help='Jadwal tayang, mis. "2026-11-22 09:00". Default: sekarang.')
    ] = None,
    privacy: Annotated[str, typer.Option(help="YouTube: public, unlisted, private.")] = "public",
) -> None:
    """Unggah hasil render ke YouTube / Facebook Page, sekarang atau terjadwal."""
    with user_errors():
        with session_scope() as s:
            pid = projects.resolve_id(s, project_id)
            p = projects.get(s, pid)
            ids = [
                publishing.create(
                    s,
                    pid,
                    PostIn(
                        platform=platform,  # pyright: ignore[reportArgumentType]
                        title=title or p.name,
                        description=description if description is not None else p.topic or "",
                        privacy=privacy,  # pyright: ignore[reportArgumentType]
                        publish_at=_when(at),
                    ),
                ).id
                for platform in to
            ]
        for post_id in ids:
            console.print("Mengunggah...")
            out = publishing.upload(post_id)  # the server may run too; first to claim uploads
            if out is None:
                console.print(
                    "Diunggah server yang sedang jalan; cek [bold]reelcraft posts[/bold]."
                )
            elif out.error:
                raise ReelcraftError(f"{out.platform}: {out.error}")
            else:
                when = out.publish_at and f" tayang {out.publish_at.astimezone():%Y-%m-%d %H:%M}"
                console.print(f"{out.platform}: {out.url}{when or ''}")


def posts(
    project_id: Annotated[str | None, typer.Argument(help="Hanya project ini.")] = None,
    limit: Annotated[int, typer.Option(help="Jumlah yang ditampilkan.")] = 20,
) -> None:
    """Riwayat dan jadwal posting."""
    with user_errors(), session_scope() as s:
        pid = projects.resolve_id(s, project_id) if project_id else None
        rows = publishing.list_posts(s, pid, limit)
        linked = publishing.accounts(s)
    console.print(
        "Akun: "
        + (
            ", ".join(f"{a.platform} ({a.name})" for a in linked)
            or "belum ada, hubungkan di Settings web"
        )
    )
    table = Table("Tayang", "Project", "Platform", "Status", "URL / keterangan")
    table.columns[-1].overflow = "fold"
    for p in rows:
        when = p.publish_at.astimezone().strftime("%m-%d %H:%M") if p.publish_at else "langsung"
        status = f"{p.status} {p.progress}%" if p.status == "uploading" else p.status
        table.add_row(when, p.project_name, p.platform, status, p.error or p.url or "")
    console.print(table)
