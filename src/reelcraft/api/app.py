from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from reelcraft import __version__

# The web build lands here (see web/vite.config.ts) and ships inside the wheel
STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
def get_version() -> dict[str, str]:
    return {"version": __version__}


def create_app() -> FastAPI:
    app = FastAPI(title="Reelcraft", version=__version__)
    app.include_router(router)
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
    return app
