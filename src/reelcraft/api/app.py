from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from reelcraft import __version__
from reelcraft.api import projects
from reelcraft.core.errors import NotFound, ReelcraftError
from reelcraft.storage.db import get_engine

# The web build lands here (see web/vite.config.ts) and ships inside the wheel
STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(prefix="/api/v1")
router.include_router(projects.router)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
def get_version() -> dict[str, str]:
    return {"version": __version__}


def _error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=404 if isinstance(exc, NotFound) else 400)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_engine()  # fail at startup, not on the first request, if the DB can't be migrated
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Reelcraft", version=__version__, lifespan=lifespan)
    app.include_router(router)
    app.add_exception_handler(ReelcraftError, _error)
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
    return app
