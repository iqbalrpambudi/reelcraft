from alembic import context
from sqlalchemy import create_engine

from reelcraft.core.config import get_settings
from reelcraft.storage import models  # noqa: F401  registers tables on Base.metadata
from reelcraft.storage.db import Base, UTCDateTime


def render_item(type_, obj, autogen_context):
    # UTCDateTime is plain DATETIME in the database; keep migrations free of app imports
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime()"
    return False


url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url

with create_engine(url).connect() as connection:
    # render_as_batch: SQLite can't ALTER most columns, so Alembic rebuilds the table instead
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()
