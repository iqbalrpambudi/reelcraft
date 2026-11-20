import shutil

from reelcraft.core.errors import ReelcraftError

REQUIRED_TOOLS = ("ffmpeg", "ffprobe")


def require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise ReelcraftError(f"{tool} tidak ditemukan di PATH. Jalankan `reelcraft doctor`.")
    return path
