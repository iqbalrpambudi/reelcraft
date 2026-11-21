import os
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from reelcraft.ai.tts import _wav
from reelcraft.core.config import get_settings
from reelcraft.media.transcribe import Word
from reelcraft.storage.db import get_engine


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch) -> Iterator[None]:
    """Every test gets its own empty, migrated database; never the user's ~/.reelcraft."""
    # Behind a symlink on purpose: data dirs often are (macOS /var), and paths must still match
    (tmp_path / "real").mkdir()
    (tmp_path / "data").symlink_to(tmp_path / "real")
    monkeypatch.setenv("REELCRAFT_DATA_DIR", str(tmp_path / "data"))
    # Never pick up the developer's real keys: no REELCRAFT_* env, no .env from the repo
    for name in [n for n in os.environ if n.startswith("REELCRAFT_") and n != "REELCRAFT_DATA_DIR"]:
        monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
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


def _describe_every_image(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    images = sum(
        isinstance(c, BinaryContent)
        for part in messages[-1].parts
        for c in (getattr(part, "content", None) or [])
        if not isinstance(getattr(part, "content", None), str)
    )
    scenes = [
        {"image": i, "description": f"Gambar {i}", "tags": ["uji"]} for i in range(1, images + 1)
    ]
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"scenes": scenes})])


@pytest.fixture(autouse=True)
def offline_vision(monkeypatch) -> None:
    """Pipeline runs in tests never reach a real AI provider; tests may override this."""
    from reelcraft.pipeline.steps import tag

    monkeypatch.setattr(tag, "model_for", lambda task: FunctionModel(_describe_every_image))


FAKE_SCRIPT = {"title": "Judul uji", "segments": ["Tahukah kamu warna ini?", "Ini scene kedua."]}


@pytest.fixture(autouse=True)
def offline_script_and_voice(monkeypatch) -> None:
    """Script, TTS and Whisper offline: 1 s of silence, heard as the script's words."""
    from reelcraft.pipeline.steps import script, voice

    monkeypatch.setattr(script, "model_for", lambda task: TestModel(custom_output_args=FAKE_SCRIPT))
    monkeypatch.setattr(voice, "synthesize", lambda text: _wav(b"\0\0" * 24_000))

    def heard(audio, model, report) -> list[Word]:
        words = ["halo", "semua", "ini", "scene", "kedua"]
        return [Word(w, i * 0.2, i * 0.2 + 0.15) for i, w in enumerate(words)]

    monkeypatch.setattr(voice, "transcribe", heard)
