from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.media import discover
from reelcraft.storage import settings
from reelcraft.storage.models import Media, Project


class FootageOut(BaseModel):
    source: str
    url: str
    page: str
    title: str
    thumbnail: str | None
    duration: float | None
    license: str
    free: bool
    author: str | None
    imported: bool  # already among this project's media


class DiscoverOut(BaseModel):
    results: list[FootageOut]
    errors: dict[str, str]  # per source that failed (no key, offline); the others still answer


def search(
    session: Session,
    project_id: str,
    query: str,
    sources: list[str] | None = None,
    limit: int = 12,
    min_duration: float | None = None,
    max_duration: float | None = None,
    free_only: bool = False,
    hide_imported: bool = False,
) -> DiscoverOut:
    """Footage for a project from several sources at once, filtered."""
    if not session.get(Project, project_id):
        raise NotFound(f"Project {project_id} tidak ditemukan")
    query = query.strip()
    if not query:
        raise ReelcraftError("Kata kunci pencarian kosong")
    sources = sources or list(discover.SOURCES)
    keys = {s: settings.get(session, f"{s}_api_key") for s in ("pexels", "pixabay")}
    imported = set(session.scalars(select(Media.source).where(Media.project_id == project_id)))

    def one(source: str) -> list[discover.Footage] | str:
        try:
            return discover.search(source, query, limit, keys.get(source), free_only)
        except ReelcraftError as e:
            return str(e)

    with ThreadPoolExecutor(len(sources)) as pool:  # network-bound: wait on all at once
        answers = dict(zip(sources, pool.map(one, sources), strict=True))
    results, errors = [], {}
    for source, answer in answers.items():
        if isinstance(answer, str):
            errors[source] = answer
            continue
        for f in answer:
            seconds = f.duration
            if (min_duration and (seconds is None or seconds < min_duration)) or (
                max_duration and (seconds is None or seconds > max_duration)
            ):
                continue
            if (free_only and not f.free) or (hide_imported and f.url in imported):
                continue
            results.append(FootageOut(**vars(f), imported=f.url in imported))
    return DiscoverOut(results=results, errors=errors)
