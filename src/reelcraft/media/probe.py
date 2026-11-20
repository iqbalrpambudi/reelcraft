import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from reelcraft.core.errors import ReelcraftError
from reelcraft.media.tools import require


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float


def probe(path: Path) -> VideoInfo:
    out = subprocess.run(
        [
            require("ffprobe"),
            *("-v", "error", "-select_streams", "v:0", "-of", "json"),
            *("-show_entries", "stream=width,height,avg_frame_rate:format=duration"),
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    streams = json.loads(out.stdout or "{}").get("streams") if out.returncode == 0 else None
    if not streams:
        raise ReelcraftError(f"{path.name} bukan video yang bisa dibaca")
    stream = streams[0]
    num, den = (float(x) for x in stream.get("avg_frame_rate", "0/1").split("/"))
    return VideoInfo(
        duration=float(json.loads(out.stdout)["format"]["duration"]),
        width=int(stream["width"]),
        height=int(stream["height"]),
        fps=num / den if den else 0.0,
    )
