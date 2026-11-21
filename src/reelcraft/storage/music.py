import zlib
from pathlib import Path

from reelcraft.core.config import get_settings

AUDIO = {".mp3", ".m4a", ".wav", ".ogg", ".flac"}


def music_dir() -> Path:
    """Background music the user drops in by hand: one folder per mood, e.g. music/tenang/."""
    return get_settings().data_dir / "music"


def tracks(mood: str) -> list[Path]:
    folder = music_dir() / Path(mood).name  # .name: a mood can't climb out of the folder
    return (
        sorted(f for f in folder.iterdir() if f.suffix.lower() in AUDIO) if folder.is_dir() else []
    )


def moods() -> list[str]:
    root = music_dir()
    return sorted(d.name for d in root.iterdir() if tracks(d.name)) if root.is_dir() else []


def pick(mood: str, seed: str) -> Path | None:
    """Same project, same track: a re-render keeps its music."""
    found = tracks(mood)
    return found[zlib.crc32(seed.encode()) % len(found)] if found else None
