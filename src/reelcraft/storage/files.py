from pathlib import Path

from reelcraft.core.config import get_settings

UPLOADS = "uploads"  # web uploads wait here until Ingest moves them into media/


def project_dir(project_id: str) -> Path:
    """Where a project's media, thumbnails and renders live; removed with the project."""
    return get_settings().data_dir / "projects" / project_id


def project_file(project_id: str, relative: str) -> Path | None:
    """A file inside the project dir, or None if missing or the path escapes the dir."""
    root = project_dir(project_id).resolve()
    path = (root / relative).resolve()
    return path if path.is_relative_to(root) and path.is_file() else None
