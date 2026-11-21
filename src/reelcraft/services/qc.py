from pydantic import BaseModel
from sqlalchemy.orm import Session

from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.pipeline import qc, runner
from reelcraft.storage.files import project_dir
from reelcraft.storage.models import Project, StepRun


class IssueOut(BaseModel):
    check: str
    severity: str
    message: str
    segment: int | None
    clip: int | None
    fixable: bool


class ReportOut(BaseModel):
    step: str
    issues: list[IssueOut]
    fixes: list[str]
    checked_at: str


def _out(report: qc.Report | None) -> ReportOut | None:
    return ReportOut.model_validate(report, from_attributes=True) if report else None


def _project(session: Session, project_id: str) -> None:
    if not session.get(Project, project_id):
        raise NotFound(f"Project {project_id} tidak ditemukan")


def reports(session: Session, project_id: str) -> dict[str, ReportOut | None]:
    """The last report of every gate, None where the step has not been checked yet."""
    _project(session, project_id)
    return {step: _out(qc.load(project_dir(project_id), step)) for step in qc.GATES}


def check(session: Session, project_id: str, step: str) -> ReportOut:
    """Check a step's current output again, e.g. after editing it by hand."""
    _project(session, project_id)
    if step not in qc.GATES:
        raise ReelcraftError(f"Step {step} tidak punya QC. Pilihan: {', '.join(qc.GATES)}")
    run = session.get(StepRun, (project_id, step))
    if not run or run.status != "done":
        raise ReelcraftError(f"Step {step} belum selesai")
    report = qc.run(step, project_dir(project_id))
    assert report is not None
    return ReportOut.model_validate(report, from_attributes=True)


def fix_script(session: Session, project_id: str) -> ReportOut:
    """Auto-fix the script; Voice and later rerun if anything changed."""
    _project(session, project_id)
    runner.ensure_idle(session, project_id)
    report = qc.run("script", project_dir(project_id), fix=True)
    assert report is not None
    if report.fixes:
        runner.invalidate(session, project_id, "voice")
    return ReportOut.model_validate(report, from_attributes=True)
