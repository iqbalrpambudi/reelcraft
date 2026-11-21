"""Autopilot: at production times a new video is thought up, sourced and queued; finished
videos wait in a pool and take the next free posting slot. State lives in projects and posts,
so a restart loses nothing (ADR 0003)."""

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock

import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from reelcraft.ai import ideas
from reelcraft.ai.models import model_for, retrying
from reelcraft.core.errors import ReelcraftError
from reelcraft.pipeline import runner
from reelcraft.services import discovery, media, publishing
from reelcraft.services.publishing import PostIn
from reelcraft.storage import script, settings
from reelcraft.storage.db import session_scope
from reelcraft.storage.models import Account, Post, Project, StepRun

log = structlog.get_logger(__name__)
CLIPS = 3  # footage per video
SLOT_LEAD = timedelta(minutes=15)  # time to upload before a slot
SLOT_DAYS = 3  # how far ahead slots are filled
RETRY_AFTER = 600.0  # seconds between failed production attempts, not to burn AI quota
_last_attempt = 0.0


@dataclass
class Config:
    enabled: bool
    niche: str
    production: list[clock]
    slots: list[clock]
    platforms: list[str]
    pool: int


class PoolItem(BaseModel):
    project_id: str
    name: str
    state: str  # producing, ready, failed


class AutopilotOut(BaseModel):
    enabled: bool
    platforms: list[str]  # the configured ones that are connected
    pool: list[PoolItem]
    pool_size: int
    next_production: datetime | None
    free_slots: list[datetime]


def _times(text: str | None, key: str) -> list[clock]:
    out = []
    for part in filter(None, (p.strip() for p in (text or "").split(","))):
        if not re.fullmatch(r"\d{1,2}:\d{2}", part):
            raise ReelcraftError(f"{key}: '{part}' bukan jam HH:MM")
        hour, minute = map(int, part.split(":"))
        out.append(clock(hour, minute))
    return sorted(out)


def config(session: Session) -> Config:
    get = lambda key: settings.get(session, key) or ""  # noqa: E731
    try:
        pool = int(get("autopilot_pool"))
    except ValueError as e:
        raise ReelcraftError("autopilot_pool harus angka") from e
    return Config(
        enabled=get("autopilot").strip().lower() in ("on", "1", "true", "ya"),
        niche=get("autopilot_niche"),
        production=_times(get("autopilot_production"), "autopilot_production"),
        slots=_times(get("autopilot_slots"), "autopilot_slots"),
        platforms=[p.strip() for p in get("autopilot_platforms").split(",") if p.strip()],
        pool=pool,
    )


def _local(day: date, at: clock) -> datetime:
    # shortcut: the zone's current offset is used for every day; fine without DST (e.g. WIB)
    return datetime.combine(day, at, tzinfo=datetime.now().astimezone().tzinfo)


def _state(session: Session, project: Project) -> str | None:
    """Where an autopilot video is; None once it has posts (left the pool)."""
    if session.scalar(select(Post.id).where(Post.project_id == project.id).limit(1)):
        return None
    runs = session.scalars(select(StepRun.status).where(StepRun.project_id == project.id)).all()
    if "failed" in runs:
        return "failed"
    return "ready" if publishing.rendered(session, project.id) else "producing"


def _pool(session: Session) -> list[tuple[Project, str]]:
    projects = session.scalars(
        select(Project).where(Project.autopilot.is_(True)).order_by(Project.created_at)
    )
    return [(p, state) for p in projects if (state := _state(session, p))]


def _window(cfg: Config, now: datetime) -> datetime | None:
    """Start of the latest production time already passed today."""
    passed = [t for t in cfg.production if _local(now.date(), t) <= now]
    return _local(now.date(), passed[-1]) if passed else None


def _due(session: Session, cfg: Config, now: datetime) -> bool:
    window = _window(cfg, now)
    if window is None:
        return False
    made = session.scalar(
        select(Project.id).where(Project.autopilot.is_(True), Project.created_at >= window).limit(1)
    )
    in_pool = [state for _, state in _pool(session) if state != "failed"]
    return made is None and len(in_pool) < cfg.pool


def _free_slots(session: Session, cfg: Config, now: datetime) -> list[datetime]:
    taken = {
        p.astimezone(UTC).replace(second=0, microsecond=0)
        for p in session.scalars(select(Post.publish_at).where(Post.publish_at >= now))
        if p
    }
    slots = [_local(now.date() + timedelta(days=d), t) for d in range(SLOT_DAYS) for t in cfg.slots]
    return [s for s in slots if s >= now + SLOT_LEAD and s.astimezone(UTC) not in taken]


def status(session: Session) -> AutopilotOut:
    cfg = config(session)
    now = datetime.now().astimezone()
    upcoming = [_local(now.date() + timedelta(days=d), t) for d in (0, 1) for t in cfg.production]
    return AutopilotOut(
        enabled=cfg.enabled,
        platforms=[p for p in cfg.platforms if session.get(Account, p)],
        pool=[PoolItem(project_id=p.id, name=p.name, state=s) for p, s in _pool(session)],
        pool_size=cfg.pool,
        next_production=next((t for t in upcoming if t > now), None),
        free_slots=_free_slots(session, cfg, now)[:6],
    )


def schedule(session: Session, cfg: Config, now: datetime) -> int:
    """Give ready videos the free slots, oldest first, on every connected platform."""
    platforms = [p for p in cfg.platforms if session.get(Account, p)]
    ready = [p for p, state in _pool(session) if state == "ready"]
    if not platforms or not ready:
        return 0
    pairs = list(zip(ready, _free_slots(session, cfg, now), strict=False))
    for project, slot in pairs:
        draft = script.load(project.id)
        for platform in platforms:
            data = PostIn(
                platform=platform,  # pyright: ignore[reportArgumentType]
                title=(draft.title if draft else project.name)[:100],
                description=project.topic or "",
                publish_at=slot,
            )
            publishing.create(session, project.id, data)
    return len(pairs)


def produce(niche: str) -> str:
    """Think up a video, find its footage and queue the whole pipeline. Returns the project id."""
    with session_scope() as s:
        recent = list(
            s.scalars(
                select(Project.name)
                .where(Project.autopilot.is_(True))
                .order_by(Project.created_at.desc())
                .limit(20)
            )
        )
    model = model_for("text")
    idea = retrying(lambda: asyncio.run(ideas.suggest(model, niche, recent)))
    with session_scope() as s:
        project = Project(name=idea.title[:200], topic=idea.topic, autopilot=True)
        s.add(project)
        s.flush()
        pid = project.id
    try:
        with session_scope() as s:
            found = discovery.search(s, pid, idea.query, limit=6, min_duration=5, max_duration=600)
            # Reusable licences first, then the rest in the order the sources ranked them
            picked = sorted(found.results, key=lambda r: not r.free)[:CLIPS]
            if not picked:
                problems = "; ".join(found.errors.values())
                raise ReelcraftError(f"Footage untuk '{idea.query}' tidak ditemukan. {problems}")
            media.add_many(s, pid, [r.url for r in picked])
    except Exception:
        with session_scope() as s:  # an empty project would only clutter the list
            s.delete(s.get(Project, pid))
        raise
    runner.claim(pid, None, None, queue=True)
    log.info("autopilot.produced", project=pid, title=idea.title, query=idea.query)
    return pid


def tick(now: datetime | None = None) -> None:
    """One scheduler pass: fill slots, then start a production if one is due."""
    global _last_attempt
    now = now or datetime.now().astimezone()
    with session_scope() as s:
        cfg = config(s)
        if not cfg.enabled:
            return
        schedule(s, cfg, now)
        due = _due(s, cfg, now)
    if due and time.monotonic() - _last_attempt >= RETRY_AFTER:
        _last_attempt = time.monotonic()
        produce(cfg.niche)
