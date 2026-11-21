from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from reelcraft.core.config import get_settings
from reelcraft.core.errors import ReelcraftError
from reelcraft.core.secrets import decrypt, encrypt
from reelcraft.storage.models import Setting

Source = Literal["db", "env", "default", "unset"]


@dataclass(frozen=True)
class Spec:
    key: str
    label: str
    secret: bool = False
    default: str | None = None
    help: str = ""


SPECS: dict[str, Spec] = {
    s.key: s
    for s in [
        Spec(
            "gemini_api_key",
            "Gemini API key",
            secret=True,
            help="Buat di aistudio.google.com/apikey",
        ),
        Spec("openai_api_key", "OpenAI-compatible API key", secret=True),
        Spec(
            "pexels_api_key",
            "Pexels API key",
            secret=True,
            help="Untuk cari footage. Gratis di pexels.com/api",
        ),
        Spec(
            "pixabay_api_key",
            "Pixabay API key",
            secret=True,
            help="Untuk cari footage. Gratis di pixabay.com/api/docs",
        ),
        Spec(
            "youtube_client_id",
            "YouTube OAuth client ID",
            help="Google Cloud > Credentials > OAuth client (Web). Redirect URI: lihat di atas.",
        ),
        Spec("youtube_client_secret", "YouTube OAuth client secret", secret=True),
        Spec(
            "facebook_app_id",
            "Facebook App ID",
            help="developers.facebook.com, produk Facebook Login. Redirect URI: lihat di atas.",
        ),
        Spec("facebook_app_secret", "Facebook App secret", secret=True),
        Spec(
            "openai_base_url",
            "OpenAI-compatible base URL",
            help="Kosongkan untuk api.openai.com; isi untuk OpenRouter, Ollama, LM Studio, dll.",
        ),
        Spec(
            "text_model",
            "Model teks",
            default="google:gemini-flash-latest",
            help="Format provider:model, provider = google atau openai. Dipakai untuk naskah.",
        ),
        Spec(
            "vision_model",
            "Model vision",
            default="google:gemini-flash-lite-latest",
            help="Format provider:model. Dipakai untuk mendeskripsikan scene.",
        ),
        Spec(
            "tts_model",
            "Model suara (TTS)",
            default="google:gemini-3.8-flash-tts",
            help="Format provider:model. Saat ini provider = google.",
        ),
        Spec(
            "tts_voice",
            "Suara TTS",
            default="Kore",
            help="Nama voice Gemini, mis. Kore, Puck, Charon, Aoede.",
        ),
        Spec(
            "background",
            "Background video",
            default="blur",
            help="Isi frame 9:16: blur (video diburamkan), cover (dipotong penuh), atau #RRGGBB.",
        ),
        Spec("subtitle_font", "Font subtitle", default="Arial", help="Font yang terpasang."),
        Spec(
            "subtitle_color",
            "Warna kata aktif",
            default="#FFE600",
            help="Warna kata yang sedang dibacakan, #RRGGBB.",
        ),
        Spec("watermark", "Watermark", help="Teks di pojok kanan atas. Kosongkan jika tidak ada."),
        Spec(
            "whisper_model",
            "Model faster-whisper",
            default="small",
            help="Untuk timestamp per kata: tiny, base, small, medium, large-v3. Diunduh sekali.",
        ),
    ]
}


def _spec(key: str) -> Spec:
    if key not in SPECS:
        raise ReelcraftError(f"Setting tidak dikenal: {key}. Pilihan: {', '.join(SPECS)}")
    return SPECS[key]


def resolve(session: Session, key: str) -> tuple[str | None, Source]:
    """Value and where it came from: saved (db) > environment / .env > built-in default."""
    spec = _spec(key)
    row = session.get(Setting, key)
    if row:
        return (decrypt(row.value) if spec.secret else row.value), "db"
    env = getattr(get_settings(), key, None)
    if env:
        return env, "env"
    return spec.default, "default" if spec.default else "unset"


def get(session: Session, key: str) -> str | None:
    return resolve(session, key)[0]


def put(session: Session, key: str, value: str | None) -> None:
    """Save a value; None or blank removes it so env / default apply again."""
    spec = _spec(key)
    row = session.get(Setting, key)
    value = value.strip() if value else None
    if not value:
        if row:
            session.delete(row)
    elif row:
        row.value = encrypt(value) if spec.secret else value
    else:
        session.add(Setting(key=key, value=encrypt(value) if spec.secret else value))
    session.flush()  # later reads in the same session must see the change
