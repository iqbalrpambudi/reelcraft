import re
import subprocess
from pathlib import Path

from reelcraft.core.errors import ReelcraftError
from reelcraft.media.subtitles import HEIGHT, WIDTH
from reelcraft.media.tools import require

FPS = 30
COVER = f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}"
CONTAIN = f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:force_divisible_by=2"


def check_background(background: str) -> None:
    if background not in ("blur", "cover") and not re.fullmatch(r"#[0-9a-fA-F]{6}", background):
        raise ReelcraftError(
            f"Background '{background}' tidak dikenal. Pilihan: blur, cover, #RRGGBB"
        )


def clip(src: Path, dest: Path, start: float, length: float, slot: float, background: str) -> None:
    """`length` s of `src` from `start`, sped up or slowed to fill `slot` s, as a 9:16 frame:
    blur (the clip over a blurred copy of itself), cover (cropped to fill), or a #RRGGBB colour."""
    fit = f"trim=duration={length:.4f},setpts={slot / length:.5f}*(PTS-STARTPTS)"
    # A source ending early would leave the slot short and the voice drifting: hold the last frame
    tail = f"setsar=1,fps={FPS},tpad=stop_mode=clone:stop_duration={slot:.3f}"
    if background == "blur":
        graph = (
            f"[0:v]{fit},split[a][b];"
            f"[a]{COVER},boxblur=28:6,eq=brightness=-0.08:saturation=0.85[bg];"
            f"[b]{CONTAIN}[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,{tail}[v]"
        )
    elif background == "cover":
        graph = f"[0:v]{fit},{COVER},{tail}[v]"
    else:
        pad = f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color={background}"
        graph = f"[0:v]{fit},{CONTAIN},{pad},{tail}[v]"
    _ffmpeg(
        *("-ss", f"{start:.4f}", "-t", f"{length + 0.3:.4f}", "-i", str(src)),
        *("-filter_complex", graph, "-map", "[v]", "-t", f"{slot:.4f}", "-an"),
        *("-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p"),
        str(dest),
    )


def concat(chunks: list[Path], dest: Path) -> None:
    listing = dest.with_suffix(".txt")
    listing.write_text("".join(f"file '{c.resolve()}'\n" for c in chunks))
    _ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(dest))


def finish(work: Path, voice: Path, watermark: str | None, duration: float, dest: Path) -> None:
    """work/video.mp4 + voice + work/subs.ass (+ watermark) -> dest.

    Runs inside `work` so the filter graph names its files relatively: no path escaping."""
    filters = ["ass=subs.ass"]
    if watermark:
        (work / "watermark.txt").write_text(watermark)
        filters.append(
            "drawtext=textfile=watermark.txt:expansion=none:fontsize=40:fontcolor=white@0.85"
            ":borderw=2:bordercolor=black@0.5:x=w-tw-40:y=80"
        )
    _ffmpeg(
        *("-i", "video.mp4", "-i", str(voice.resolve()), "-vf", ",".join(filters)),
        *("-map", "0:v", "-map", "1:a", "-t", f"{duration:.3f}"),
        *("-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"),
        *("-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dest.resolve())),
        cwd=work,
    )


def _ffmpeg(*args: str, cwd: Path | None = None) -> None:
    out = subprocess.run(
        [require("ffmpeg"), "-y", "-v", "error", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if out.returncode != 0:
        raise ReelcraftError(f"ffmpeg gagal: {out.stderr.strip()[-500:]}")
