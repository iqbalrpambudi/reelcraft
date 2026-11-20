from collections.abc import Callable
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

from reelcraft.core.errors import ReelcraftError


def is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def download(url: str, dest_stem: Path, on_progress: Callable[[int], None]) -> Path:
    """Best video up to 1080p merged to mp4 (needs ffmpeg); returns the final file path."""

    def hook(d: dict[str, Any]) -> None:
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if d["status"] == "downloading" and total:
            on_progress(int(d.get("downloaded_bytes", 0) * 100 / total))

    opts = {
        "outtmpl": f"{dest_stem}.%(ext)s",
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "progress_hooks": [hook],
        # YouTube hides HD formats behind a JS challenge; the solver ships in yt-dlp[default]
        # (yt-dlp-ejs) and node comes bundled with it, so no remote script download is needed
        "js_runtimes": {"deno": {}, "node": {}},
    }
    dest_stem.parent.mkdir(parents=True, exist_ok=True)
    with YoutubeDL(opts) as ydl:  # pyright: ignore[reportArgumentType]
        info = ydl.extract_info(url, download=True)
    files = [d["filepath"] for d in (info or {}).get("requested_downloads") or []]
    if not files:
        raise ReelcraftError(f"Gagal mengunduh {url}")
    return Path(files[0])
