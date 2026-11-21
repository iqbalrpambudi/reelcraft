"""Footage search across sources. Every result's `url` is something media.add can fetch."""

import re
from dataclasses import dataclass
from typing import Any

import httpx
from yt_dlp import YoutubeDL

from reelcraft.core.errors import ReelcraftError

TIMEOUT = 20.0
SOURCES = ("youtube", "pexels", "pixabay", "archive")
# Licences that allow editing and monetised use: public domain, CC BY, CC BY-SA (not NC / ND)
REUSABLE = ("publicdomain", "licenses/by/", "licenses/by-sa/")


@dataclass
class Footage:
    source: str
    url: str  # what gets imported
    page: str  # where a person reads about it
    title: str
    thumbnail: str | None
    duration: float | None  # seconds
    license: str
    free: bool  # licensed for reuse without asking; YouTube never is by default
    author: str | None = None


def search(
    source: str, query: str, limit: int, key: str | None = None, free_only: bool = False
) -> list[Footage]:
    if source not in SOURCES:
        raise ReelcraftError(f"Sumber tidak dikenal: {source}. Pilihan: {', '.join(SOURCES)}")
    if source in ("pexels", "pixabay") and not key:
        raise ReelcraftError(f"API key {source} belum diatur. Isi di Settings.")
    if source == "archive":  # mostly unlicensed: ask for licensed items rather than filter after
        return _archive(query, limit, free_only)
    return {"youtube": _youtube, "pexels": _pexels, "pixabay": _pixabay}[source](query, limit, key)


def _get_json(url: str, params: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    try:
        response = httpx.get(url, params=params, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise ReelcraftError(f"Tidak bisa menghubungi {httpx.URL(url).host}: {e}") from e
    if response.status_code in (401, 403):
        raise ReelcraftError(f"{httpx.URL(url).host} menolak API key ({response.status_code})")
    if response.status_code >= 400:
        raise ReelcraftError(f"{httpx.URL(url).host} membalas {response.status_code}")
    return response.json()


def _ytsearch(query: str, limit: int) -> list[dict[str, Any]]:
    opts = {"extract_flat": True, "quiet": True, "noprogress": True}
    with YoutubeDL(opts) as ydl:  # pyright: ignore[reportArgumentType]
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    # A search answers with a plain list; the stubs also allow lazy paged playlists
    return list((info or {}).get("entries") or [])  # pyright: ignore[reportArgumentType]


def _youtube(query: str, limit: int, _key: str | None = None) -> list[Footage]:
    return [
        Footage(
            source="youtube",
            url=e["url"],
            page=e["url"],
            title=e.get("title") or e["url"],
            thumbnail=next((t["url"] for t in e.get("thumbnails") or []), None),
            duration=e.get("duration"),
            license="YouTube (cek izin pemilik)",
            free=False,
            author=e.get("channel"),
        )
        for e in _ytsearch(query, limit)
        if e.get("url")
    ]


def _pexels(query: str, limit: int, key: str | None) -> list[Footage]:
    data = _get_json(
        "https://api.pexels.com/videos/search",
        {"query": query, "per_page": limit},
        {"Authorization": key or ""},
    )
    out = []
    for v in data.get("videos") or []:
        files = [f for f in v.get("video_files") or [] if f.get("file_type") == "video/mp4"]
        # The biggest file that is still at most 1080p, like the downloader's own limit
        fits = [f for f in files if min(f.get("width") or 0, f.get("height") or 0) <= 1080]
        best = max(
            fits or files,
            key=lambda f: (f.get("width") or 0) * (f.get("height") or 0),
            default=None,
        )
        if best:
            out.append(
                Footage(
                    source="pexels",
                    url=best["link"],
                    page=v.get("url") or best["link"],
                    title=_title_from_page(v.get("url")) or f"Pexels {v.get('id')}",
                    thumbnail=v.get("image"),
                    duration=v.get("duration"),
                    license="Pexels License",
                    free=True,
                    author=(v.get("user") or {}).get("name"),
                )
            )
    return out


def _pixabay(query: str, limit: int, key: str | None) -> list[Footage]:
    data = _get_json(
        "https://pixabay.com/api/videos/",
        {"key": key, "q": query, "per_page": max(3, min(limit, 200))},  # Pixabay's bounds
    )
    out = []
    for h in data.get("hits") or []:
        videos = h.get("videos") or {}
        best = next(
            (
                videos[size]
                for size in ("large", "medium", "small")
                if (videos.get(size) or {}).get("url")
            ),
            None,
        )
        if best:
            out.append(
                Footage(
                    source="pixabay",
                    url=best["url"],
                    page=h.get("pageURL") or best["url"],
                    title=h.get("tags") or f"Pixabay {h.get('id')}",
                    thumbnail=best.get("thumbnail")
                    or (videos.get("medium") or {}).get("thumbnail"),
                    duration=h.get("duration"),
                    license="Pixabay Content License",
                    free=True,
                    author=h.get("user"),
                )
            )
    return out[:limit]


def _archive(query: str, limit: int, free_only: bool) -> list[Footage]:
    # Lucene: one field per wildcard term; '/' would open a regex, so it is escaped
    terms = " OR ".join(f"licenseurl:*{p.replace('/', r'\/')}*" for p in REUSABLE)
    licensed = f" AND ({terms})" if free_only else ""
    data = _get_json(
        "https://archive.org/advancedsearch.php",
        {
            "q": f"({query}) AND mediatype:movies{licensed}",
            "fl[]": ["identifier", "title", "licenseurl", "runtime", "creator"],
            "rows": limit,
            "output": "json",
        },
    )
    out = []
    for d in (data.get("response") or {}).get("docs") or []:
        page = f"https://archive.org/details/{d['identifier']}"
        license_url = d.get("licenseurl") or ""
        free = any(p in license_url for p in REUSABLE)
        creator = d.get("creator")
        out.append(
            Footage(
                source="archive",
                url=page,
                page=page,
                title=d.get("title") or d["identifier"],
                thumbnail=f"https://archive.org/services/img/{d['identifier']}",
                duration=_seconds(d.get("runtime")),
                license=license_url or "Archive.org (lisensi tidak dicantumkan)",
                free=free,
                author=creator[0] if isinstance(creator, list) else creator,
            )
        )
    return out


def _seconds(runtime: Any) -> float | None:
    """Archive.org runtimes come as "1:02:03", "12:30", "95" or free text."""
    if not isinstance(runtime, str) or not re.fullmatch(r"\d+(:\d+){0,2}", runtime.strip()):
        return None
    total = 0
    for part in runtime.strip().split(":"):
        total = total * 60 + int(part)
    return float(total)


def _title_from_page(url: str | None) -> str | None:
    """Pexels pages are /video/<words>-<id>/; the API has no title."""
    match = re.search(r"/video/(.+)-\d+/?$", url or "")
    return match.group(1).replace("-", " ").capitalize() if match else None
