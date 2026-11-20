from pydantic import BaseModel
from pydantic_ai import Agent
from sqlalchemy.orm import Session

from reelcraft.ai.models import Task, ai_errors, model_for
from reelcraft.core.errors import ReelcraftError
from reelcraft.core.secrets import mask
from reelcraft.storage import settings
from reelcraft.storage.db import session_scope


class SettingOut(BaseModel):
    key: str
    label: str
    help: str
    secret: bool
    value: str | None  # secrets are masked
    source: settings.Source
    default: str | None


class AICheck(BaseModel):
    task: Task
    model: str
    ok: bool
    message: str


def list_all(session: Session) -> list[SettingOut]:
    out = []
    for spec in settings.SPECS.values():
        value, source = settings.resolve(session, spec.key)
        out.append(
            SettingOut(
                key=spec.key,
                label=spec.label,
                help=spec.help,
                secret=spec.secret,
                value=mask(value) if spec.secret and value else value,
                source=source,
                default=spec.default,
            )
        )
    return out


def update(session: Session, values: dict[str, str | None]) -> list[SettingOut]:
    """Save several settings at once; a blank or null value falls back to env / default."""
    for key, value in values.items():
        settings.put(session, key, value)
    session.flush()
    return list_all(session)


def check_ai() -> list[AICheck]:
    """One tiny request per model, so a wrong key or model name shows up before a long run."""
    results = []
    for task in ("text", "vision"):
        with session_scope() as s:
            spec = settings.get(s, f"{task}_model") or ""
        try:
            with ai_errors():
                reply = Agent(model_for(task)).run_sync("Balas hanya dengan kata: OK").output
            results.append(AICheck(task=task, model=spec, ok=True, message=str(reply).strip()))
        except ReelcraftError as e:
            results.append(AICheck(task=task, model=spec, ok=False, message=str(e)))
    return results
