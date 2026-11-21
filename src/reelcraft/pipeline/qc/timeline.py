"""Timeline checks before rendering: continuity, cut lengths, repeats, footage quality."""

import json
from itertools import pairwise
from pathlib import Path

from sqlalchemy import select

from reelcraft.pipeline.qc import Issue
from reelcraft.pipeline.steps.edit import TIMELINE
from reelcraft.storage.db import session_scope
from reelcraft.storage.models import Scene

FLASH, STATIC = 0.8, 6.5  # seconds: shorter reads as a glitch, longer as a still
TOLERANCE = 0.05  # more than a frame and a bit
# Words Tag uses for footage that should not be on screen
LOW_QUALITY = (
    "blur", "buram", "gelap", "layar hitam", "layar kosong", "watermark", "subtitle bawaan",
    "hardsub", "letterbox", "pecah", "kualitas rendah",
)  # fmt: skip


def check(project_dir: Path) -> list[Issue]:
    path = project_dir / TIMELINE
    if not path.is_file():
        return [Issue("no-timeline", "blocker", "Timeline tidak ada.")]
    timeline = json.loads(path.read_text())
    clips = timeline["clips"]
    if not clips:
        return [Issue("empty", "blocker", "Timeline tanpa klip.")]
    issues = []
    if clips[0]["start"] > TOLERANCE:
        issues.append(
            Issue("late-start", "major", f"Klip pertama mulai di {clips[0]['start']:.2f}s.", clip=0)
        )
    for i, (a, b) in enumerate(pairwise(clips), 1):
        if abs(b["start"] - a["end"]) > TOLERANCE:
            issues.append(
                Issue("gap", "major", f"Celah/tumpang tindih antara klip {i} dan {i + 1}.", clip=i)
            )
        if a["scene_id"] == b["scene_id"]:
            issues.append(
                Issue("repeat", "minor", f"Klip {i + 1} mengulang scene klip {i}.", clip=i)
            )
    for i, c in enumerate(clips):
        length = c["end"] - c["start"]
        if length < FLASH:
            issues.append(Issue("flash", "major", f"Klip {i + 1} hanya {length:.2f}s.", clip=i))
        elif length > STATIC:
            issues.append(
                Issue("static", "minor", f"Klip {i + 1} {length:.1f}s; terasa diam.", clip=i)
            )
    if abs(clips[-1]["end"] - timeline["duration"]) > 0.5:
        issues.append(
            Issue(
                "length-mismatch",
                "major",
                f"Video {clips[-1]['end']:.1f}s, suara {timeline['duration']:.1f}s.",
            )
        )
    with session_scope() as s:
        found = s.execute(
            select(Scene.id, Scene.description).where(Scene.id.in_({c["scene_id"] for c in clips}))
        ).all()
    descriptions = {scene_id: (text or "").lower() for scene_id, text in found}
    for i, c in enumerate(clips):
        if c["scene_id"] not in descriptions:
            issues.append(
                Issue("missing-scene", "blocker", f"Scene klip {i + 1} sudah dihapus.", clip=i)
            )
        elif bad := next((w for w in LOW_QUALITY if w in descriptions[c["scene_id"]]), None):
            issues.append(
                Issue("low-quality", "minor", f"Klip {i + 1} terdeteksi '{bad}'.", clip=i)
            )
    return issues
