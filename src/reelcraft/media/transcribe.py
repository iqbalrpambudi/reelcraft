import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

from reelcraft.media.tools import require

SAMPLE_RATE = 16_000  # what Whisper expects


@dataclass
class Word:
    text: str
    start: float  # seconds
    end: float


def transcribe(audio: Path, model: str, report: Callable[[int], None]) -> list[Word]:
    """Words Whisper hears, with timestamps."""
    from faster_whisper import WhisperModel  # slow import; only the Voice step needs it

    # Decoded by ffmpeg, not faster-whisper: its PyAV call breaks on PyAV 19 (faster-whisper 1.2.1)
    pcm = subprocess.run(
        [
            *(require("ffmpeg"), "-v", "error", "-i", str(audio)),
            *("-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"),
        ],
        capture_output=True,
        check=True,
    ).stdout
    samples = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    segments, info = WhisperModel(model, compute_type="int8").transcribe(
        samples, word_timestamps=True
    )
    words = []
    for seg in segments:  # a generator: decoding happens while iterating
        words += [Word(w.word.strip(), float(w.start), float(w.end)) for w in seg.words or []]
        report(int(seg.end * 100 / info.duration) if info.duration else 0)
    return words


def _norm(word: str) -> str:
    return re.sub(r"\W+", "", word.lower())


def align(words: list[str], heard: list[Word], duration: float) -> list[Word]:
    """The script's words with times from what was heard; the script's spelling wins.

    Words Whisper got differently (numbers, names) take an even share of the gap between
    their matched neighbours."""
    times: list[tuple[float, float] | None] = [None] * len(words)
    matcher = SequenceMatcher(
        None, [_norm(w) for w in words], [_norm(h.text) for h in heard], autojunk=False
    )
    for a, b, n in matcher.get_matching_blocks():
        for k in range(n):
            times[a + k] = (heard[b + k].start, heard[b + k].end)
    out: list[Word] = []
    i = 0
    while i < len(words):
        t = times[i]
        if t:
            out.append(Word(words[i], *t))
            i += 1
            continue
        j = next((k for k in range(i, len(words)) if times[k]), len(words))
        lo = out[-1].end if out else 0.0
        nxt = times[j] if j < len(words) else None
        share = max((nxt[0] if nxt else duration) - lo, 0.0) / (j - i)
        out += [Word(words[k], lo + (k - i) * share, lo + (k - i + 1) * share) for k in range(i, j)]
        i = j
    return out
