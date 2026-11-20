from pathlib import Path

from reelcraft.core.config import get_settings


def project_dir(project_id: str) -> Path:
    """Where a project's media, thumbnails and renders live; removed with the project."""
    return get_settings().data_dir / "projects" / project_id
