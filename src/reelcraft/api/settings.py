from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from reelcraft.api.deps import get_session
from reelcraft.services import settings
from reelcraft.services.settings import AICheck, SettingOut

router = APIRouter(prefix="/settings", tags=["settings"])
Db = Annotated[Session, Depends(get_session)]


@router.get("")
def list_settings(db: Db) -> list[SettingOut]:
    return settings.list_all(db)


@router.patch("")
def update_settings(values: dict[str, str | None], db: Db) -> list[SettingOut]:
    return settings.update(db, values)


@router.post("/check-ai")
def check_ai() -> list[AICheck]:
    return settings.check_ai()
