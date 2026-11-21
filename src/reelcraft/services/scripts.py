from pydantic import BaseModel
from sqlalchemy.orm import Session

from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.pipeline import runner
from reelcraft.storage import script
from reelcraft.storage.db import utcnow
from reelcraft.storage.models import Project


class ScriptText(BaseModel):
    text: str | None  # `# Title`, blank line, then one paragraph per segment; None = no script


def get(session: Session, project_id: str) -> ScriptText:
    if not session.get(Project, project_id):
        raise NotFound(f"Project {project_id} tidak ditemukan")
    current = script.load(project_id)
    return ScriptText(text=script.to_text(current) if current else None)


def save(session: Session, project_id: str, text: str) -> ScriptText:
    """Replace the script. It counts as the Script step's result; Voice and later rerun."""
    if not session.get(Project, project_id):
        raise NotFound(f"Project {project_id} tidak ditemukan")
    parsed = script.parse(text)
    if not parsed.segments:
        raise ReelcraftError("Naskah kosong. Tulis minimal satu paragraf narasi.")
    runs = runner.ensure_runs(session, project_id)
    if any(r.status in runner.BUSY for r in runs):
        raise ReelcraftError("Project ini sedang diproses. Tunggu atau batalkan dulu.")
    script.save(project_id, parsed)
    runner.invalidate(session, project_id, "voice")
    for r in runs:
        if r.step == "script":
            r.status, r.progress, r.message, r.error = "done", 100, None, None
            r.finished_at = utcnow()
    return get(session, project_id)
