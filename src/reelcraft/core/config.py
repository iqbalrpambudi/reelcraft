from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from REELCRAFT_* env vars or a .env file in the working directory."""

    model_config = SettingsConfigDict(env_prefix="REELCRAFT_", env_file=".env", extra="ignore")

    data_dir: Path = Path.home() / ".reelcraft"
    host: str = "127.0.0.1"  # local single-user app: never listen on all interfaces by default
    port: int = 8765


@lru_cache
def get_settings() -> Settings:
    return Settings()
