"""Quality gates run after a step. Ported from cliper-pro's qc.py, rule checks only, one module
per gate. A blocker fails the step; major and minor issues are reported for a person to judge."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from reelcraft.core.errors import ReelcraftError

Severity = Literal["blocker", "major", "minor"]
GATES = ("script", "voice", "edit", "render")  # steps checked after they run


@dataclass
class Issue:
    check: str  # stable id of the check, e.g. "hook-too-long"
    severity: Severity
    message: str
    segment: int | None = None  # 0-based narration segment
    clip: int | None = None  # 0-based timeline clip
    fixable: bool = False


@dataclass
class Report:
    step: str
    issues: list[Issue]
    fixes: list[str] = field(default_factory=list)  # what auto-fix changed before checking
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def blockers(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "blocker"]


Check = Callable[[Path], list[Issue]]


def _file(project_dir: Path, step: str) -> Path:
    return project_dir / "qc" / f"{step}.json"


def save(project_dir: Path, report: Report) -> None:
    path = _file(project_dir, report.step)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), ensure_ascii=False))


def load(project_dir: Path, step: str) -> Report | None:
    path = _file(project_dir, step)
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    return Report(
        data["step"], [Issue(**i) for i in data["issues"]], data["fixes"], data["checked_at"]
    )


def run(step: str, project_dir: Path, fix: bool = False) -> Report | None:
    """Check a step's output and store the report; None for a step without a gate. With fix,
    what can be repaired without a person (only the script, so far) is repaired first."""
    from reelcraft.pipeline.qc import render, script, timeline, voice

    gates: dict[str, Check] = {
        "script": script.check,
        "voice": voice.check,
        "edit": timeline.check,
        "render": render.check,
    }
    if step not in GATES:
        return None
    fixes = script.fix(project_dir) if fix and step == "script" else []
    report = Report(step, gates[step](project_dir), fixes)
    save(project_dir, report)
    return report


def gate(step: str, project_dir: Path) -> None:
    """After a step in the pipeline: fix what can be fixed, check, stop on a blocker."""
    report = run(step, project_dir, fix=True)
    if report and report.blockers:
        raise ReelcraftError("QC: " + "; ".join(i.message for i in report.blockers))
