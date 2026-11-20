from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
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


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    """4 s at 10 fps: 2 s red then 2 s blue, so exactly one cut at 2.0 s."""
    path = tmp_path_factory.mktemp("media") / "sample.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), 10, (320, 240))
    for color in ((0, 0, 255), (255, 0, 0)):  # BGR
        frame = np.full((240, 320, 3), color, dtype=np.uint8)
        for _ in range(20):
            writer.write(frame)
    writer.release()
    return path
