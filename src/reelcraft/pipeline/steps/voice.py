import json
import wave

from reelcraft.ai.models import retrying
from reelcraft.ai.tts import synthesize
from reelcraft.core.errors import ReelcraftError
from reelcraft.media.transcribe import align, transcribe
from reelcraft.pipeline.context import StepContext
from reelcraft.storage import script, settings
from reelcraft.storage.db import session_scope

AUDIO, TIMINGS = "voice.wav", "voice.json"


def run(ctx: StepContext) -> None:
    """Narration audio of the script, plus when each word (and so each segment) is spoken."""
    current = script.load(ctx.project_id)
    if not current or not current.segments:
        raise ReelcraftError("Belum ada naskah. Jalankan step script atau tulis naskah dulu.")
    ctx.progress(5, "Membuat suara")
    audio = ctx.dir / AUDIO
    audio.write_bytes(retrying(lambda: synthesize("\n\n".join(current.segments))))
    with wave.open(str(audio)) as w:
        duration = w.getnframes() / w.getframerate()

    ctx.progress(40, "Timestamp per kata (model whisper diunduh sekali di awal)")
    with session_scope() as s:
        model = settings.get(s, "whisper_model") or "small"
    heard = transcribe(audio, model, lambda pct: ctx.progress(40 + pct // 2, "Timestamp per kata"))

    per_segment = [seg.split() for seg in current.segments]
    words = align([w for ws in per_segment for w in ws], heard, duration)
    segments, i = [], 0
    for text, ws in zip(current.segments, per_segment, strict=True):
        own = words[i : i + len(ws)]
        i += len(ws)
        segments.append(
            {
                "text": text,
                "start": own[0].start,
                "end": own[-1].end,
                "words": [{"text": w.text, "start": w.start, "end": w.end} for w in own],
            }
        )
    (ctx.dir / TIMINGS).write_text(json.dumps({"duration": duration, "segments": segments}))
