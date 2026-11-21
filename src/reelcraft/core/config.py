from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from REELCRAFT_* env vars or a .env file in the working directory."""

    model_config = SettingsConfigDict(env_prefix="REELCRAFT_", env_file=".env", extra="ignore")

    data_dir: Path = Path.home() / ".reelcraft"
    host: str = "127.0.0.1"  # local single-user app: never listen on all interfaces by default
    port: int = 8765

    # Fallbacks for settings not saved in the database (see reelcraft.storage.settings)
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    pexels_api_key: str | None = None
    pixabay_api_key: str | None = None
    openai_base_url: str | None = None
    text_model: str | None = None
    vision_model: str | None = None
    tts_model: str | None = None
    tts_voice: str | None = None
    whisper_model: str | None = None
    background: str | None = None
    subtitle_font: str | None = None
    subtitle_color: str | None = None
    watermark: str | None = None

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'reelcraft.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
