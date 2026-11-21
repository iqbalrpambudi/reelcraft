import io
import wave

import httpx
from google import genai
from google.genai import errors, types

from reelcraft.ai.models import TIMEOUT, ProviderUnavailable, error_kind
from reelcraft.core.errors import ReelcraftError
from reelcraft.storage import settings
from reelcraft.storage.db import session_scope

RATE = 24_000  # Gemini TTS returns raw 16-bit mono PCM at this rate


def synthesize(text: str) -> bytes:
    """Narration as WAV bytes, with the TTS model and voice from Settings."""
    with session_scope() as s:
        spec = settings.get(s, "tts_model") or ""
        voice = settings.get(s, "tts_voice") or ""
        key = settings.get(s, "gemini_api_key")
    provider, _, name = spec.partition(":")
    if provider != "google" or not name:
        raise ReelcraftError(f"Model TTS '{spec}' tidak didukung. Format: google:<model>")
    if not key:
        raise ReelcraftError("Gemini API key belum diatur. Isi di Settings.")
    return _wav(_gemini(key, name, voice, text))


def _gemini(key: str, model: str, voice: str, text: str) -> bytes:
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
    )
    # Kept in a name: a dropped Client closes its connection. Timeout is in milliseconds.
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT * 1000))
    try:
        response = client.models.generate_content(model=model, contents=text, config=config)
    except errors.APIError as e:
        raise error_kind(e.code)(f"TTS menolak permintaan ({e.code}): {e.message}") from e
    except httpx.TransportError as e:  # timeouts included
        raise ProviderUnavailable(f"TTS tidak bisa dihubungi: {e}") from e
    parts = (response.candidates or [None])[0]
    for part in (parts and parts.content and parts.content.parts) or []:
        if part.inline_data and part.inline_data.data:
            return part.inline_data.data
    raise ReelcraftError("TTS tidak mengembalikan audio. Coba lagi atau ganti voice.")


def _wav(pcm: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return out.getvalue()
