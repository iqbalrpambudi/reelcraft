"""Narration segments to a timeline of footage clips. Ported from cliper-pro's matching.py,
keeping what works on the data we have: no embeddings, heatmap or script-named scenes yet."""

import re
from dataclasses import dataclass
from itertools import pairwise

FPS = 30  # the render's frame rate; every cut lands on a frame
MIN_SHOT, MAX_SHOT = 2.0, 3.5  # shorter flashes, longer drags (and reads as a re-upload)

STOPWORDS = {
    *("dan", "di", "ke", "dari", "yang", "ini", "itu", "untuk", "pada", "adalah", "cuma", "bisa"),
    *("lewat", "saat", "lalu", "akan", "jadi", "juga", "dengan"),
    *("the", "and", "in", "to", "of", "a", "is", "for", "on", "at", "by", "with"),
}
# Channel branding, not content: never picked while anything else is left
FILLER_TAGS = {"logo", "branding", "iklan", "intro", "outro", "end screen", "subscribe"}


def snap(t: float) -> float:
    return round(round(t * FPS) / FPS, 4)


@dataclass
class Shot:
    """A scene that can be cut in: its place in the source and what Tag saw in it."""

    id: str
    media_id: str
    start: float
    end: float
    text: str  # description + tags
    filler: bool = False


@dataclass
class Window:
    start: float
    end: float
    text: str
    segment: int  # index of the narration segment it starts in


@dataclass
class Clip:
    scene_id: str
    media_id: str
    source_start: float
    source_end: float  # the renderer fits source_end - source_start into end - start
    start: float  # on the timeline
    end: float
    text: str
    segment: int


def windows(segments: list[tuple[float, float, str]], duration: float) -> list[Window]:
    """Gapless shot slots over the narration: cuts sit in the pause between sentences; short
    sentences share a slot, long ones are split so no slot is outside MIN_SHOT..MAX_SHOT."""
    spans = []
    for i, (start, end, text) in enumerate(segments):
        before = segments[i - 1][1] if i else None
        after = segments[i + 1][0] if i < len(segments) - 1 else None
        lo = 0.0 if before is None else (before + start) / 2 if start > before else start
        hi = max(end, duration) if after is None else (end + after) / 2 if after > end else end
        spans.append((snap(lo), snap(hi), text, i))

    out: list[Window] = []
    open_: list[tuple[float, float, str, int]] = []
    w_start = 0.0
    for lo, hi, text, i in spans:
        if hi - lo > MAX_SHOT and hi - lo >= 2 * MIN_SHOT:
            if open_:
                out.append(Window(w_start, lo, " ".join(s[2] for s in open_), open_[0][3]))
                open_ = []
            length = hi - lo
            n = min(int(length // MIN_SHOT), max(2, round(length / ((MIN_SHOT + MAX_SHOT) / 2))))
            cuts = [snap(lo + (hi - lo) * k / n) for k in range(n)] + [hi]
            out += [Window(a, b, text, i) for a, b in pairwise(cuts)]
            w_start = hi
            continue
        if not open_:
            w_start = lo if not out else out[-1].end
        open_.append((lo, hi, text, i))
        if hi - w_start >= MIN_SHOT:
            out.append(Window(w_start, hi, " ".join(s[2] for s in open_), open_[0][3]))
            open_ = []
    if open_:
        text = " ".join(s[2] for s in open_)
        if out and open_[-1][1] - w_start < MIN_SHOT:
            out[-1].end, out[-1].text = open_[-1][1], f"{out[-1].text} {text}"
        else:
            out.append(Window(w_start, open_[-1][1], text, open_[0][3]))
    for a, b in pairwise(out):  # exactly continuous, whatever rounding did
        b.start = a.end
    if out:
        out[0].start = 0.0
    return out


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower())) - STOPWORDS


def _usable(shot: Shot) -> tuple[float, float]:
    """The shot minus a few frames at each cut, so no clip starts or ends on a flash."""
    start = shot.start + (0.12 if shot.start > 0.15 else 0.033)
    return round(start, 3), round(max(start + 0.4, shot.end - 0.15), 3)


def _fit(usable: float, target: float) -> float:
    """How well a shot of `usable` seconds fills a slot: a little spare beats an exact fit
    (room for a 1.06x speed-up); anything under MIN_SHOT is a flash cut."""
    if usable < MIN_SHOT:
        return 0.05
    if usable >= target * 1.08:
        return 1.18
    if usable >= target:
        return 1.08
    return 0.9 if usable / target >= 0.88 else 0.35


def match(wins: list[Window], shots: list[Shot], media_length: dict[str, float]) -> list[Clip]:
    """Pick a shot per window: words in common with the narration, not used before, long enough
    for the slot, and moving forward through the footage like the story does."""
    if not wins or not shots:
        return []
    pool = [s for s in shots if not s.filler] or shots
    # Position of every shot in all footage played back to back, 0..1
    offset, total = {}, 0.0
    for m in dict.fromkeys(s.media_id for s in shots):
        offset[m] = total
        total += media_length.get(m, max(s.end for s in shots if s.media_id == m))
    total = max(total, 1.0)
    audio = max(wins[-1].end, 1.0)
    strict_order = len(shots) > 4
    progress = 0.0
    used: set[str] = set()
    clips: list[Clip] = []
    texts = {s.id: _words(s.text) for s in pool}

    for win in wins:
        target = max(win.end - win.start, MIN_SHOT)
        p_win = (win.start + win.end) / (2 * audio)
        narration = _words(win.text)
        prev = clips[-1] if clips else None
        prev_end = next((s.end for s in shots if prev and s.id == prev.scene_id), 0.0)

        best, best_score = pool[0], -1.0
        for s in pool:
            lex = len(narration & texts[s.id]) / len(narration) if narration and texts[s.id] else 0
            relevance = 0.325 + 0.35 * min(1.0, lex * 2)
            fresh = 0.01 if prev and s.id == prev.scene_id else 0.03 if s.id in used else 1.0
            lo, hi = _usable(s)
            fit = _fit(hi - lo, target)
            p = (offset[s.media_id] + s.start) / total
            if strict_order and p < progress - 0.005:
                order = 0.04  # never jump back in the story
            elif strict_order and p > min(1.0, max(progress + 0.14, p_win + 0.15)):
                order = 0.06  # nor skip ahead to the ending
            else:
                order = 1.05 + 0.3 * max(0.0, 1 - abs(p_win - p) * 2.5)
            gap = s.start - prev_end if prev and s.media_id == prev.media_id else -1
            follows = prev is not None and prev.segment == win.segment and -0.05 <= gap <= 15
            score = relevance * fresh * fit * order * (1.5 if follows else 1.0)
            if score > best_score:
                best, best_score = s, score
        behind = strict_order and (offset[best.media_id] + best.start) / total < progress - 0.005
        if prev and (best.id in used or behind):  # nothing fresh ahead: the previous clip plays on
            _extend(prev, win.end, win.text, media_length)
            continue
        used.add(best.id)
        p_best = (offset[best.media_id] + best.start) / total
        progress = max(progress, min(p_best, p_win + 0.18))
        lo, hi = _usable(best)
        if hi - lo >= target:
            speed = 1.06 if hi - lo >= target * 1.06 else 1.0  # a touch faster reads as snappier
            length = min(hi - lo, target * speed)
            lo += (hi - lo - length) / 2  # the middle of the shot, away from both cuts
            hi = lo + length
        else:  # too short: play on into what follows in the source rather than slow-mo
            hi = min(lo + target, media_length.get(best.media_id, lo + target) - 0.05)
        clips.append(
            Clip(
                best.id,
                best.media_id,
                snap(lo),
                snap(hi),
                win.start,
                win.end,
                win.text,
                win.segment,
            )
        )
    return heal(clips, media_length)


def _extend(clip: Clip, end: float, text: str, media_length: dict[str, float]) -> None:
    """Grow a clip over the next slot by playing more of its source at the same speed."""
    speed = (clip.source_end - clip.source_start) / max(clip.end - clip.start, 0.001)
    clip.end = end
    if text not in clip.text:
        clip.text = f"{clip.text} {text}"
    want = clip.source_start + (end - clip.start) * speed
    clip.source_end = snap(min(want, media_length.get(clip.media_id, want)))


def heal(clips: list[Clip], media_length: dict[str, float]) -> list[Clip]:
    """No clip shorter than MIN_SHOT: it merges into the one before (the first absorbs the next)."""
    out: list[Clip] = []
    for c in clips:
        if out and c.end - c.start < MIN_SHOT:
            _extend(out[-1], c.end, c.text, media_length)
        else:
            out.append(c)
    if len(out) > 1 and out[0].end - out[0].start < MIN_SHOT:
        second = out.pop(1)
        _extend(out[0], second.end, second.text, media_length)
    return out
