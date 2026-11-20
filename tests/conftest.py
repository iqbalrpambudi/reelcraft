from collections.abc import Iterator

import pytest

from reelcraft.core.config import get_settings
from reelcraft.storage.db import get_engine


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch) -> Iterator[None]:
    """Every test gets its own empty, migrated database; never the user's ~/.reelcraft."""
    monkeypatch.setenv("REELCRAFT_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    get_engine().dispose()
    get_settings.cache_clear()
    get_engine.cache_clear()
