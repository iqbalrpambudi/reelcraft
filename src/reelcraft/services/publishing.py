import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.core.secrets import decrypt, encrypt
from reelcraft.pipeline.steps.render import OUTPUT
from reelcraft.publish import facebook, youtube
from reelcraft.storage import settings
from reelcraft.storage.db import session_scope, utcnow
from reelcraft.storage.files import project_file
from reelcraft.storage.models import Account, Post, Project, StepRun

log = logging.getLogger(__name__)
Platform = Literal["youtube", "facebook"]
PLATFORMS: tuple[Platform, ...] = ("youtube", "facebook")
CREDENTIALS = {
    "youtube": ("youtube_client_id", "youtube_client_secret"),
    "facebook": ("facebook_app_id", "facebook_app_secret"),
}
# shortcut: OAuth states live in memory, so a login started before a restart must be redone
_states: dict[str, str] = {}


class AccountOut(BaseModel):
    platform: str
    name: str
    remote_id: str
    connected_at: datetime


class PostIn(BaseModel):
    platform: Platform
    title: str = Field(min_length=1, max_length=100)
    description: str = ""
    privacy: Literal["public", "unlisted", "private"] = "public"
    publish_at: datetime | None = None  # with a timezone; None = right away


class PostOut(BaseModel):
    id: str
    project_id: str
    project_name: str
    platform: str
    title: str
    description: str
    privacy: str
    publish_at: datetime | None
    status: str
    progress: int
    url: str | None
    error: str | None
    created_at: datetime


def _credentials(session: Session, platform: str) -> tuple[str, str]:
    if platform not in CREDENTIALS:
        raise ReelcraftError(f"Platform tidak dikenal: {platform}")
    id_key, secret_key = CREDENTIALS[platform]
    client_id, secret = settings.get(session, id_key), settings.get(session, secret_key)
    if not client_id or not secret:
        raise ReelcraftError(f"Isi {id_key} dan {secret_key} di Settings dulu")
    return client_id, secret


def accounts(session: Session) -> list[AccountOut]:
    rows = session.scalars(select(Account).order_by(Account.platform))
    return [AccountOut.model_validate(a, from_attributes=True) for a in rows]


def connect_url(session: Session, platform: str, redirect_uri: str) -> str:
    client_id, _ = _credentials(session, platform)
    state = secrets.token_urlsafe(16)
    _states[state] = platform
    module = youtube if platform == "youtube" else facebook
    return module.auth_url(client_id, redirect_uri, state)


def finish_connect(
    session: Session, platform: str, code: str, state: str, redirect_uri: str
) -> AccountOut:
    if _states.pop(state, None) != platform:
        raise ReelcraftError("Sesi login kedaluwarsa. Ulangi hubungkan akun.")
    client_id, secret = _credentials(session, platform)
    module = youtube if platform == "youtube" else facebook
    remote_id, name, token = module.connect(client_id, secret, code, redirect_uri)
    account = session.get(Account, platform) or Account(platform=platform)
    account.remote_id, account.name, account.token = remote_id, name, encrypt(token)
    account.connected_at = utcnow()
    session.add(account)
    session.flush()
    return AccountOut.model_validate(account, from_attributes=True)


def disconnect(session: Session, platform: str) -> None:
    account = session.get(Account, platform)
    if account:
        session.delete(account)


def rendered(session: Session, project_id: str) -> bool:
    run = session.get(StepRun, (project_id, "render"))
    return bool(run and run.status == "done" and project_file(project_id, OUTPUT))


def create(session: Session, project_id: str, data: PostIn) -> PostOut:
    project = session.get(Project, project_id)
    if not project:
        raise NotFound(f"Project {project_id} tidak ditemukan")
    if not rendered(session, project_id):
        raise ReelcraftError("Render video dulu sebelum diposting")
    if not session.get(Account, data.platform):
        raise ReelcraftError(f"Akun {data.platform} belum dihubungkan. Hubungkan di Settings.")
    publish_at = data.publish_at
    if publish_at:
        if publish_at.tzinfo is None:
            raise ReelcraftError("Waktu posting harus menyertakan zona waktu")
        if publish_at < datetime.now(UTC) - timedelta(minutes=1):
            raise ReelcraftError("Waktu posting sudah lewat")
    post = Post(project_id=project_id, **data.model_dump())
    session.add(post)
    session.flush()
    return _out(post, project.name)


def _out(post: Post, project_name: str) -> PostOut:
    return PostOut(
        project_name=project_name,
        **{k: getattr(post, k) for k in PostOut.model_fields if k != "project_name"},
    )


def list_posts(session: Session, project_id: str | None = None, limit: int = 100) -> list[PostOut]:
    """Newest first."""
    query = select(Post, Project.name).join(Project, Project.id == Post.project_id)
    if project_id:
        query = query.where(Post.project_id == project_id)
    rows = session.execute(query.order_by(Post.created_at.desc()).limit(limit))
    return [_out(post, name) for post, name in rows]


def cancel(session: Session, post_id: str) -> None:
    """Remove a post not uploaded yet, or a failed one."""
    post = session.get(Post, post_id)
    if not post:
        raise NotFound(f"Post {post_id} tidak ditemukan")
    if post.status not in ("queued", "failed"):
        raise ReelcraftError("Post yang sedang/sudah diunggah tidak bisa dibatalkan")
    session.delete(post)


def _claim(post_id: str | None) -> str | None:
    """Mark one queued post uploading; atomic, so the server and the CLI never both take it."""
    with session_scope() as s:
        if post_id is None:
            post_id = s.scalar(
                select(Post.id).where(Post.status == "queued").order_by(Post.created_at)
            )
            if post_id is None:
                return None
        taken = s.execute(
            update(Post)
            .where(Post.id == post_id, Post.status == "queued")
            .values(status="uploading", progress=0)
        )
        return post_id if taken.rowcount else None  # pyright: ignore[reportAttributeAccessIssue]


def upload(post_id: str | None = None) -> PostOut | None:
    """Upload the given queued post, or the oldest one. None when there was nothing to take."""
    post_id = _claim(post_id)
    if post_id is None:
        return None
    with session_scope() as s:
        post = s.get(Post, post_id)
        assert post is not None
        account = s.get(Account, post.platform)
        job = (
            post.platform,
            post.project_id,
            post.title,
            post.description,
            post.privacy,
            post.publish_at,
        )
        creds = _credentials(s, post.platform) if post.platform == "youtube" else None
        token = decrypt(account.token) if account else None
        page = account.remote_id if account else None

    def progress(pct: int) -> None:
        with session_scope() as s:
            s.execute(update(Post).where(Post.id == post_id).values(progress=pct))

    platform, project_id, title, description, privacy, publish_at = job
    error = remote_id = url = None
    try:
        file = project_file(project_id, OUTPUT)
        if not file:
            raise ReelcraftError("File render hilang. Render ulang project ini.")
        if not token or not page:
            raise ReelcraftError(f"Akun {platform} belum dihubungkan")
        if platform == "youtube" and creds:
            remote_id = youtube.upload(
                *creds, token, file, title, description, privacy, publish_at, progress
            )
            url = youtube.video_url(remote_id)
        else:
            text = f"{title}\n\n{description}".strip()
            remote_id = facebook.upload(page, token, file, text, publish_at, progress)
            url = facebook.video_url(remote_id)
    except ReelcraftError as e:
        error = str(e)
    except Exception as e:  # network errors and the like: keep the post, say what happened
        log.exception("Upload %s failed", post_id)
        error = f"{type(e).__name__}: {e}"
    with session_scope() as s:
        post = s.get(Post, post_id)
        if post:
            post.status = "failed" if error else "done"
            post.error, post.remote_id, post.url = error, remote_id, url
            if not error:
                post.progress = 100
        project = s.get(Project, project_id)
        return _out(post, project.name if project else "") if post else None


def retry(session: Session, post_id: str) -> None:
    post = session.get(Post, post_id)
    if not post:
        raise NotFound(f"Post {post_id} tidak ditemukan")
    if post.status != "failed":
        raise ReelcraftError("Hanya post yang gagal yang bisa diulang")
    post.status, post.error, post.progress = "queued", None, 0


def recover_interrupted() -> None:
    """An upload cut by a restart may or may not have reached the platform: mark it failed
    for a person to check, rather than upload a possible duplicate."""
    with session_scope() as s:
        s.execute(
            update(Post)
            .where(Post.status == "uploading")
            .values(
                status="failed",
                error="Terhenti saat mengunggah. Cek di platform, lalu ulangi bila belum ada.",
            )
        )
