import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskID, TextColumn
from rich.table import Table

from reelcraft.cli.common import ProjectId, user_errors
from reelcraft.core.errors import ReelcraftError
from reelcraft.pipeline import runner
from reelcraft.services import jobs as job_service
from reelcraft.services import pipeline, projects, scripts
from reelcraft.services import qc as qc_service
from reelcraft.storage.db import session_scope

console = Console()
STATUS_STYLE = {"done": "green", "failed": "red", "running": "cyan", "cancelled": "yellow"}

StepOpt = Annotated[str | None, typer.Option(help=f"Salah satu: {', '.join(runner.STEPS)}.")]


def _resolve(project_id: str) -> str:
    with session_scope() as s:
        return projects.resolve_id(s, project_id)


def run(
    project_id: ProjectId,
    from_: Annotated[
        str | None,
        typer.Option(
            "--from",
            help="Mulai dari step ini. Default: step pertama yang belum selesai.",
        ),
    ] = None,
    to: StepOpt = None,
) -> None:
    """Jalankan pipeline project di proses ini (Ctrl+C untuk batal)."""
    with user_errors():
        pid = _resolve(project_id)
        steps = runner.claim(pid, from_, to)
        if not steps:
            console.print("Semua step sudah selesai. Pakai [bold]--from[/bold] untuk mengulang.")
            return
        with Progress(
            TextColumn("{task.fields[step]:<8}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%  {task.description}"),
            console=console,
        ) as bar:
            tasks: dict[str, TaskID] = {
                step: bar.add_task("menunggu", total=100, step=step) for step in steps
            }

            def listener(step: str, pct: int, message: str) -> None:
                if pct >= 0:
                    bar.update(
                        tasks[step], completed=pct, description=message if pct < 100 else "selesai"
                    )
                else:
                    bar.update(tasks[step], description=f"[red]{message}[/red]")

            try:
                status = runner.execute(pid, steps, listener)
            except KeyboardInterrupt:
                console.print("[yellow]Dibatalkan.[/yellow]")
                raise typer.Exit(130) from None
    if status != "done":
        raise typer.Exit(1)


def status(project_id: ProjectId) -> None:
    """Status tiap step pipeline project."""
    with user_errors(), session_scope() as s:
        rows = pipeline.status(s, projects.resolve_id(s, project_id))
    table = Table("Step", "Status", "Progress", "Keterangan")
    for r in rows:
        style = STATUS_STYLE.get(r.status, "")
        table.add_row(
            r.step,
            f"[{style}]{r.status}[/{style}]" if style else r.status,
            f"{r.progress}%",
            r.error or r.message or "",
        )
    console.print(table)


def script(project_id: ProjectId) -> None:
    """Edit naskah di $EDITOR. Menyimpan berarti step voice dan setelahnya diulang."""
    with user_errors(), session_scope() as s:
        pid = projects.resolve_id(s, project_id)
        before = scripts.get(s, pid).text or "# Judul\n\nParagraf pertama narasi.\n"
    with user_errors():
        after = _edit(before)
    if after.strip() == before.strip():
        console.print("Tidak ada perubahan.")
        return
    with user_errors(), session_scope() as s:
        scripts.save(s, pid, after)
    console.print("Naskah disimpan. Jalankan [bold]reelcraft run[/bold] untuk membuat suara.")


def _edit(text: str) -> str:
    """Text after the user's $EDITOR closes (vi when unset)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "naskah.md"
        path.write_text(text)
        editor = shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi")
        if subprocess.run([*editor, str(path)]).returncode != 0:
            raise ReelcraftError("Editor keluar dengan error; naskah tidak disimpan.")
        return path.read_text()


def jobs(
    limit: Annotated[int, typer.Option(help="Jumlah riwayat yang ditampilkan.")] = 15,
) -> None:
    """Antrean semua project dan riwayat run terakhir."""
    with session_scope() as s:
        active = job_service.queue(s)
        past = job_service.history(s, limit)
    if active:
        table = Table("Project", "Step", "Status", "Progress", title="Antrean")
        for a in active:
            table.add_row(a.project_name, a.step, a.status, f"{a.progress}%")
        console.print(table)
    else:
        console.print("Antrean kosong.")
    table = Table("Mulai", "Project", "Step", "Status", "Keterangan", title="Riwayat")
    for j in past:
        style = STATUS_STYLE.get(j.status, "")
        table.add_row(
            j.started_at.astimezone().strftime("%m-%d %H:%M"),
            j.project_name,
            f"{j.steps[0]}..{j.steps[-1]}" if len(j.steps) > 1 else j.steps[0],
            f"[{style}]{j.status}[/{style}]" if style else j.status,
            f"di {j.step}: {j.error}" if j.error else "",
        )
    console.print(table)


SEVERITY_STYLE = {"blocker": "red", "major": "yellow", "minor": "dim"}


def qc(
    project_id: ProjectId,
    fix: Annotated[bool, typer.Option("--fix", help="Perbaiki naskah otomatis dulu.")] = False,
) -> None:
    """Laporan QC per step; --fix memperbaiki naskah (voice dst. perlu dijalankan ulang)."""
    with user_errors(), session_scope() as s:
        pid = projects.resolve_id(s, project_id)
        if fix:
            for change in qc_service.fix_script(s, pid).fixes or [
                "Tidak ada yang perlu diperbaiki."
            ]:
                console.print(f"[green]✓[/green] {change}")
        found = qc_service.reports(s, pid)
    for step, report in found.items():
        if report is None:
            console.print(f"[bold]{step}[/bold]  [dim]belum dicek[/dim]")
            continue
        console.print(
            f"[bold]{step}[/bold]  {'OK' if not report.issues else f'{len(report.issues)} catatan'}"
        )
        for issue in report.issues:
            style = SEVERITY_STYLE[issue.severity]
            console.print(f"  [{style}]{issue.severity:<7}[/{style}] {issue.message}")
