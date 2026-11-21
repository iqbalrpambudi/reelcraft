from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from reelcraft.api.deps import get_session
from reelcraft.core.errors import ReelcraftError
from reelcraft.services import publishing
from reelcraft.services.publishing import AccountOut, PostIn, PostOut

router = APIRouter(tags=["publish"])
Db = Annotated[Session, Depends(get_session)]


def _callback(request: Request, platform: str) -> str:
    return str(request.url_for("oauth_callback", platform=platform))


@router.get("/accounts")
def list_accounts(db: Db) -> list[AccountOut]:
    return publishing.accounts(db)


@router.post("/accounts/{platform}/connect")
def connect_account(platform: str, request: Request, db: Db) -> dict[str, str]:
    """The platform's login page; it comes back to the callback below."""
    return {"url": publishing.connect_url(db, platform, _callback(request, platform))}


@router.get("/accounts/{platform}/callback", name="oauth_callback")
def oauth_callback(
    platform: str,
    request: Request,
    db: Db,
    code: str | None = None,
    state: str = "",
    error_description: str | None = None,
) -> RedirectResponse:
    """Back from the platform's login: save the account and return to Settings."""
    try:
        if not code:
            raise ReelcraftError(error_description or "Login dibatalkan")
        publishing.finish_connect(db, platform, code, state, _callback(request, platform))
        return RedirectResponse(f"/settings?connected={platform}", status_code=303)
    except ReelcraftError as e:
        db.rollback()
        return RedirectResponse(f"/settings?{urlencode({'error': str(e)})}", status_code=303)


@router.delete("/accounts/{platform}", status_code=204)
def disconnect_account(platform: str, db: Db) -> None:
    publishing.disconnect(db, platform)


@router.get("/posts")
def list_posts(db: Db, project_id: str | None = None, limit: int = 100) -> list[PostOut]:
    return publishing.list_posts(db, project_id, min(limit, 500))


@router.post("/projects/{project_id}/posts", status_code=201)
def create_post(project_id: str, data: PostIn, db: Db) -> PostOut:
    """Queue an upload; the server sends it within seconds."""
    return publishing.create(db, project_id, data)


@router.post("/posts/{post_id}/retry", status_code=204)
def retry_post(post_id: str, db: Db) -> None:
    publishing.retry(db, post_id)


@router.delete("/posts/{post_id}", status_code=204)
def cancel_post(post_id: str, db: Db) -> None:
    publishing.cancel(db, post_id)
