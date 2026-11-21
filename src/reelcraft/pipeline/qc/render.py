"""Checks on the rendered file: what the platforms accept and that nothing was cut off."""

import json
from pathlib import Path

from reelcraft.core.errors import ReelcraftError
from reelcraft.media.probe import probe
from reelcraft.media.subtitles import HEIGHT, WIDTH
from reelcraft.pipeline.qc import Issue
from reelcraft.pipeline.steps.edit import TIMELINE
from reelcraft.pipeline.steps.render import OUTPUT


def check(project_dir: Path) -> list[Issue]:
    try:
        info = probe(project_dir / OUTPUT)
    except ReelcraftError:
        return [Issue("unreadable", "blocker", "File render tidak bisa dibaca.")]
    issues = []
    if (info.width, info.height) != (WIDTH, HEIGHT):
        issues.append(
            Issue("size", "major", f"Ukuran {info.width}x{info.height}, bukan {WIDTH}x{HEIGHT}.")
        )
    timeline = project_dir / TIMELINE
    if timeline.is_file():
        expected = json.loads(timeline.read_text())["duration"]
        if abs(info.duration - expected) > 0.5:
            issues.append(
                Issue(
                    "cut-off",
                    "major",
                    f"Video {info.duration:.1f}s, seharusnya {expected:.1f}s.",
                )
            )
    if info.duration > 90:
        issues.append(Issue("too-long", "major", f"{info.duration:.0f} detik; Reels maksimal 90."))
    return issues
