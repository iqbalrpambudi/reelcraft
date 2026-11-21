from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.types import Scope

from reelcraft import __version__
from reelcraft.api import pipeline, projects, settings
from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.pipeline import runner, worker
from reelcraft.services import projects as project_service
from reelcraft.storage.db import get_engine

# The web build lands here (see web/vite.config.ts) and ships inside the wheel
STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(prefix="/api/v1")
router.include_router(projects.router)
router.include_router(pipeline.router)
router.include_router(settings.router)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/templates")
def list_templates() -> dict[str, str]:
    return project_service.templates()


@router.get("/music")
def list_music() -> list[str]:
    return project_service.music_moods()


@router.get("/version")
def get_version() -> dict[str, str]:
    return {"version": __version__}


def _error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=404 if isinstance(exc, NotFound) else 400)


class SPAStaticFiles(StaticFiles):
    """Unknown paths get index.html, so client-side routes like /projects/abc survive a reload."""

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as e:
            if e.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_engine()  # fail at startup, not on the first request, if the DB can't be migrated
    runner.recover_interrupted()
    stop = worker.start()
    yield
    stop.set()  # a step in progress keeps its daemon thread until the process exits


def create_app() -> FastAPI:
    app = FastAPI(title="Reelcraft", version=__version__, lifespan=lifespan)
    app.include_router(router)
    app.add_exception_handler(ReelcraftError, _error)
    if STATIC_DIR.is_dir():
        app.mount("/", SPAStaticFiles(directory=STATIC_DIR, html=True), name="web")
    return app
