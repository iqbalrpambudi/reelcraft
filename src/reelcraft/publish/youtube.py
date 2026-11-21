"""YouTube Data API v3: OAuth (web client) + resumable upload. Ported from cliper-pro."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from reelcraft.core.errors import ReelcraftError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
CHUNK_SIZE = 8 * 1024 * 1024  # must be a multiple of 256 KiB


def _error(resp: httpx.Response) -> ReelcraftError:
    try:
        body = resp.json()
        err = body.get("error")
        msg = err.get("message") if isinstance(err, dict) else body.get("error_description") or err
    except ValueError:
        msg = resp.text[:300]
    return ReelcraftError(f"YouTube {resp.status_code}: {msg}")


def auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",  # always return a refresh token, even on re-connect
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(query)}"


def _token(client: httpx.Client, data: dict[str, str]) -> dict[str, Any]:
    resp = client.post(TOKEN_URL, data=data)
    if resp.status_code != 200:
        raise _error(resp)
    return resp.json()


def connect(
    client_id: str,
    secret: str,
    code: str,
    redirect_uri: str,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, str, str]:
    """Authorisation code to (channel id, channel title, refresh token)."""
    with httpx.Client(timeout=30, transport=transport) as client:
        tokens = _token(
            client,
            {
                "code": code,
                "client_id": client_id,
                "client_secret": secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp = client.get(
            CHANNELS_URL,
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
    if resp.status_code != 200:
        raise _error(resp)
    items = resp.json().get("items") or []
    if not items:
        raise ReelcraftError("Akun Google ini belum punya channel YouTube")
    return items[0]["id"], items[0]["snippet"].get("title", ""), tokens["refresh_token"]


def upload(
    client_id: str,
    secret: str,
    refresh_token: str,
    file: Path,
    title: str,
    description: str,
    privacy: str,
    publish_at: datetime | None,
    on_progress: Callable[[int], None] = lambda _: None,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Resumable upload in CHUNK_SIZE pieces; returns the video id. With publish_at in the
    future, YouTube keeps it private and makes it public at that time."""
    scheduled = publish_at is not None and publish_at > datetime.now(UTC)
    status: dict[str, Any] = {"privacyStatus": "private" if scheduled else privacy}
    if scheduled and publish_at:
        status["publishAt"] = publish_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    status["selfDeclaredMadeForKids"] = False
    metadata = {
        "snippet": {"title": title[:100], "description": description[:5000]},
        "status": status,
    }
    size = file.stat().st_size
    with httpx.Client(timeout=120, transport=transport) as client:
        access = _token(
            client,
            {
                "client_id": client_id,
                "client_secret": secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )["access_token"]
        auth = {"Authorization": f"Bearer {access}"}
        init = client.post(
            UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                **auth,
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(size),
            },
            json=metadata,
        )
        if init.status_code != 200 or "location" not in init.headers:
            raise _error(init)
        session_url = init.headers["location"]
        offset = 0
        with file.open("rb") as f:
            while True:
                f.seek(offset)
                chunk = f.read(CHUNK_SIZE)
                end = offset + len(chunk) - 1
                resp = client.put(
                    session_url,
                    content=chunk,
                    headers={**auth, "Content-Range": f"bytes {offset}-{end}/{size}"},
                )
                if resp.status_code in (200, 201):
                    on_progress(100)
                    return resp.json()["id"]
                if resp.status_code != 308:
                    raise _error(resp)
                # 308: the server says how much it has; resume from there
                received = resp.headers.get("range")
                offset = int(received.split("-")[1]) + 1 if received else 0
                on_progress(min(99, offset * 100 // size))


def video_url(video_id: str) -> str:
    return f"https://youtube.com/shorts/{video_id}"
