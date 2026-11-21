"""Narration checks before it is voiced: hook, sentence length, words TTS would read aloud."""

import re
from pathlib import Path

from reelcraft.pipeline.qc import Issue
from reelcraft.storage import script

WORDS_PER_SECOND = 2.4  # Indonesian narration pace measured in cliper-pro
HOOK_MIN, HOOK_MAX = 3, 22
SEGMENT_MAX = 28
# Labels, markdown and hashtags the model sometimes writes; TTS would read them out
ARTIFACT = re.compile(
    r"\[[^\]]*\]|\([^)]*\b(?:musik|jeda|scene|shot)\b[^)]*\)|\*+|#\w+"
    r"|(?:^|\s)(?:hook|narator|narasi|voiceover|vo|scene|shot|segmen \d+)\s*:",
    re.IGNORECASE,
)
CONNECTORS = ("namun", "tetapi", "tapi", "sehingga", "bahkan", "sementara", "karena", "lalu", "dan")


def _count(text: str) -> int:
    return len(text.split())


def check(project_dir: Path) -> list[Issue]:
    current = script.load(project_dir.name)
    if not current or not current.segments:
        return [Issue("script-empty", "blocker", "Naskah kosong.")]
    issues = []
    for i, text in enumerate(current.segments):
        words = _count(text)
        if ARTIFACT.search(text):
            issues.append(
                Issue(
                    "artifact",
                    "major",
                    f"Segmen {i + 1} berisi label/simbol yang ikut terbaca TTS.",
                    segment=i,
                    fixable=True,
                )
            )
        if i == 0 and words < HOOK_MIN:
            issues.append(
                Issue(
                    "hook-too-short",
                    "major",
                    "Hook terlalu pendek untuk menahan scroll.",
                    0,
                    fixable=True,
                )
            )
        elif i == 0 and words > HOOK_MAX:
            issues.append(
                Issue(
                    "hook-too-long",
                    "major",
                    f"Hook {words} kata; maksimal {HOOK_MAX} agar padat di 3 detik awal.",
                    0,
                    fixable=True,
                )
            )
        elif words > SEGMENT_MAX:
            issues.append(
                Issue(
                    "long-segment",
                    "major",
                    f"Segmen {i + 1} terlalu panjang ({words} kata); napas TTS jadi tidak natural.",
                    i,
                    fixable=True,
                )
            )
        elif i > 0 and words < 2:
            issues.append(
                Issue(
                    "stub-segment", "minor", f"Segmen {i + 1} hanya {words} kata.", i, fixable=True
                )
            )
    seconds = sum(_count(t) for t in current.segments) / WORDS_PER_SECOND
    if seconds > 90:
        issues.append(
            Issue(
                "too-long", "major", f"Perkiraan {seconds:.0f} detik; Reels Facebook maksimal 90."
            )
        )
    elif seconds > 65:
        issues.append(Issue("long", "minor", f"Perkiraan {seconds:.0f} detik; target 30-60."))
    elif seconds < 15:
        issues.append(Issue("too-short", "minor", f"Perkiraan {seconds:.0f} detik; target 30-60."))
    return issues


def _split(text: str, limit: int) -> list[str]:
    """In two at the connector or comma nearest the middle; recursively while still too long."""
    words = text.split()
    if len(words) <= limit:
        return [text]
    middle = len(words) // 2
    cuts = [
        i
        for i in range(2, len(words) - 2)
        if words[i - 1].endswith((",", ";")) or words[i].lower().strip(",") in CONNECTORS
    ]
    at = min(cuts, key=lambda i: abs(i - middle)) if cuts else middle
    first = " ".join(words[:at]).rstrip(",;") + "."
    rest = " ".join(words[at:])
    if rest.lower().startswith("dan "):  # a sentence does not open with "dan"
        rest = rest[4:]
    rest = rest[:1].upper() + rest[1:]
    return _split(first, limit) + _split(rest, limit)


def fix(project_dir: Path) -> list[str]:
    """Repair what needs no judgement; returns what was changed. Saved only if something was."""
    current = script.load(project_dir.name)
    if not current:
        return []
    fixes = []
    segments = []
    for i, text in enumerate(current.segments):
        clean = " ".join(ARTIFACT.sub(" ", text).split())
        if clean != text:
            fixes.append(f"Segmen {i + 1}: label/simbol dihapus")
        if clean:
            segments.append(clean)
    out: list[str] = []
    for i, text in enumerate(segments):
        parts = _split(text, HOOK_MAX if i == 0 else SEGMENT_MAX)
        if len(parts) > 1:
            fixes.append(f"Segmen {i + 1} dipecah jadi {len(parts)}")
        out += parts
    merged: list[str] = []
    for i, text in enumerate(out):
        short = _count(text) < (HOOK_MIN if not merged else 2)
        if short and i + 1 < len(out):  # carried into the next one
            following = out[i + 1]
            if not text.endswith((".", "!", "?")):  # one sentence now: no capital mid-way
                following = following[:1].lower() + following[1:]
            out[i + 1] = f"{text} {following}"
            fixes.append(f"Segmen pendek '{text}' digabung ke berikutnya")
        elif short and merged:  # its own sentence after the previous one
            end = "" if merged[-1].endswith((".", "!", "?")) else "."
            merged[-1] = f"{merged[-1]}{end} {text}"
            fixes.append(f"Segmen pendek '{text}' digabung ke sebelumnya")
        else:
            merged.append(text)
    if fixes:
        script.save(project_dir.name, script.Script(current.title, merged))
    return fixes
