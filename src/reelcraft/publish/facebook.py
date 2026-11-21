"""Facebook Graph API: OAuth (Facebook Login) + Page Reels upload. Ported from cliper-pro."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from reelcraft.core.errors import ReelcraftError

GRAPH_VERSION = "v24.0"
AUTH_URL = f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
SCOPES = ["pages_show_list", "pages_read_engagement", "pages_manage_posts"]
# Facebook rejects scheduled_publish_time less than 10 minutes ahead; closer than this, post now
MIN_SCHEDULE_LEAD = timedelta(minutes=11)


def _error(resp: httpx.Response) -> ReelcraftError:
    try:
        err = resp.json().get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else err
    except ValueError:
        msg = None
    return ReelcraftError(f"Facebook {resp.status_code}: {msg or resp.text[:300]}")


def auth_url(app_id: str, redirect_uri: str, state: str) -> str:
    query = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": ",".join(SCOPES),
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(query)}"


def _get(client: httpx.Client, path: str, **params: str) -> dict[str, Any]:
    resp = client.get(f"{GRAPH_URL}{path}", params=params)
    if resp.status_code != 200:
        raise _error(resp)
    return resp.json()


def connect(
    app_id: str,
    secret: str,
    code: str,
    redirect_uri: str,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, str, str]:
    """Code to long-lived user token to (page id, page name, page token that does not expire)."""
    with httpx.Client(timeout=30, transport=transport) as client:
        app = {"client_id": app_id, "client_secret": secret}
        short = _get(client, "/oauth/access_token", **app, redirect_uri=redirect_uri, code=code)
        long = _get(
            client,
            "/oauth/access_token",
            **app,
            grant_type="fb_exchange_token",
            fb_exchange_token=short["access_token"],
        )
        pages = _get(
            client, "/me/accounts", fields="id,name,access_token", access_token=long["access_token"]
        ).get("data")
    if not pages:
        raise ReelcraftError("Tidak ada Page yang diizinkan. Saat login, pilih Page tujuan upload.")
    # shortcut: takes the first granted Page; to post to another, reconnect and grant only that one
    page = pages[0]
    return page["id"], page.get("name", ""), page["access_token"]


def upload(
    page_id: str,
    page_token: str,
    file: Path,
    description: str,
    publish_at: datetime | None,
    on_progress: Callable[[int], None] = lambda _: None,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Three-phase Reels upload (start, binary, finish); returns the video id."""
    url = f"{GRAPH_URL}/{page_id}/video_reels"
    with httpx.Client(timeout=300, transport=transport) as client:
        start = client.post(url, data={"upload_phase": "start", "access_token": page_token})
        if start.status_code != 200:
            raise _error(start)
        video_id = start.json()["video_id"]
        on_progress(5)
        data = file.read_bytes()  # Shorts are tens of MB, fine to hold in memory
        up = client.post(
            start.json().get("upload_url")
            or f"https://rupload.facebook.com/video-upload/{GRAPH_VERSION}/{video_id}",
            content=data,
            headers={
                "Authorization": f"OAuth {page_token}",
                "offset": "0",
                "file_size": str(len(data)),
            },
        )
        if up.status_code != 200:
            raise _error(up)
        on_progress(90)
        finish = {
            "upload_phase": "finish",
            "video_id": video_id,
            "description": description,
            "video_state": "PUBLISHED",
            "access_token": page_token,
        }
        if publish_at and publish_at - datetime.now(UTC) >= MIN_SCHEDULE_LEAD:
            finish["video_state"] = "SCHEDULED"
            finish["scheduled_publish_time"] = str(int(publish_at.timestamp()))
        done = client.post(url, data=finish)
        if done.status_code != 200 or not done.json().get("success"):
            raise _error(done)
    on_progress(100)
    return video_id


def video_url(video_id: str) -> str:
    return f"https://www.facebook.com/reel/{video_id}"
