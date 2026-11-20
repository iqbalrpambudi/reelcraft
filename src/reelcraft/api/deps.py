from collections.abc import Iterator

from sqlalchemy.orm import Session

from reelcraft.storage.db import session_scope


def get_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session
