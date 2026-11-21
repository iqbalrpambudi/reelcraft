"""Narration audio checks: length for the platforms and timings Edit and subtitles rely on."""

import json
from pathlib import Path

from reelcraft.pipeline.qc import Issue
from reelcraft.pipeline.steps.voice import TIMINGS


def check(project_dir: Path) -> list[Issue]:
    path = project_dir / TIMINGS
    if not path.is_file():
        return [Issue("no-voice", "blocker", "Timing suara tidak ada.")]
    timings = json.loads(path.read_text())
    duration = timings["duration"]
    issues = []
    if duration > 90:
        issues.append(
            Issue("too-long", "major", f"Suara {duration:.0f} detik; Reels Facebook maksimal 90.")
        )
    for i, seg in enumerate(timings["segments"]):
        if seg["end"] <= seg["start"] or not seg.get("words"):
            issues.append(
                Issue(
                    "unaligned",
                    "major",
                    f"Segmen {i + 1} tidak tertangkap di audio; subtitle-nya akan meleset.",
                    segment=i,
                )
            )
    return issues
