import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from reelcraft.api.deps import get_session
from reelcraft.pipeline import runner
from reelcraft.services import media, pipeline
from reelcraft.services.media import MediaOut, SceneOut
from reelcraft.services.pipeline import StepRunOut
from reelcraft.storage.db import session_scope
from reelcraft.storage.files import project_file

router = APIRouter(prefix="/projects/{project_id}", tags=["pipeline"])
Db = Annotated[Session, Depends(get_session)]
EVENT_POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 15


class MediaIn(BaseModel):
    source: str  # URL, or a path on the machine running the server


class RunIn(BaseModel):
    start: str | None = None  # default: first step not done
    end: str | None = None


@router.get("/media")
def list_media(project_id: str, db: Db) -> list[MediaOut]:
    return media.list_for(db, project_id)


@router.post("/media", status_code=201)
def add_media(project_id: str, data: MediaIn, db: Db) -> MediaOut:
    return media.add(db, project_id, data.source)


@router.post("/media/upload", status_code=201)
def upload_media(project_id: str, file: UploadFile, db: Db) -> MediaOut:
    return media.upload(db, project_id, file.filename or "upload.mp4", file.file)


@router.delete("/media/{media_id}", status_code=204)
def remove_media(project_id: str, media_id: str, db: Db) -> None:
    media.remove(db, project_id, media_id)


@router.get("/scenes")
def list_scenes(project_id: str, db: Db) -> list[SceneOut]:
    return media.scenes_for(db, project_id)


@router.get("/steps")
def list_steps(project_id: str, db: Db) -> list[StepRunOut]:
    return pipeline.status(db, project_id)


@router.post("/run", status_code=202)
def run_pipeline(project_id: str, data: RunIn) -> list[StepRunOut]:
    """Queue the run for the server worker; follow it via /events."""
    runner.claim(project_id, data.start, data.end, queue=True)
    with session_scope() as s:
        return pipeline.status(s, project_id)


@router.post("/cancel", status_code=204)
def cancel_pipeline(project_id: str) -> None:
    runner.request_cancel(project_id)


@router.get(
    "/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def pipeline_events(project_id: str, request: Request) -> StreamingResponse:
    """Server-sent events: the step list whenever it changes (works for CLI runs too)."""

    def snapshot() -> str:
        with session_scope() as s:
            return json.dumps([r.model_dump(mode="json") for r in pipeline.status(s, project_id)])

    first = await asyncio.to_thread(snapshot)  # 404 before the stream starts, not inside it

    async def stream() -> AsyncIterator[str]:
        last, idle = first, 0.0
        yield f"data: {first}\n\n"
        while not await request.is_disconnected():
            await asyncio.sleep(EVENT_POLL_SECONDS)
            current = await asyncio.to_thread(snapshot)
            idle += EVENT_POLL_SECONDS
            if current != last:
                last, idle = current, 0.0
                yield f"data: {current}\n\n"
            elif idle >= HEARTBEAT_SECONDS:
                idle = 0.0
                yield ": keep-alive\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/files/{path:path}", response_class=FileResponse)
def project_file_response(project_id: str, path: str) -> FileResponse:
    """Thumbnails, media and renders of the project (path relative to its dir)."""
    file = project_file(project_id, path)
    if not file:
        raise HTTPException(404, "File tidak ditemukan")
    return FileResponse(file)
