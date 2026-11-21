import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Literal

from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy.orm import Session

from reelcraft.core.errors import ReelcraftError
from reelcraft.storage import settings
from reelcraft.storage.db import session_scope

Task = Literal["text", "vision"]
# Seconds before each retry of a 5xx; "overloaded" came in bursts of tens of seconds when tested
RETRY_WAITS = (5, 15, 45)

# pydantic-ai prints an observability banner on first run; it would land in CLI output
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")


class QuotaExceeded(ReelcraftError):
    """Provider said 429: retrying right away only burns more quota."""


class ProviderUnavailable(ReelcraftError):
    """5xx (overloaded, internal error): transient, worth retrying after a pause."""


def build(session: Session, spec: str) -> Model:
    """`provider:model` from Settings to a pydantic-ai model with its credentials."""
    provider, _, name = spec.partition(":")
    if not name:
        raise ReelcraftError(f"Model '{spec}' harus berformat provider:model")
    if provider == "google":
        key = settings.get(session, "gemini_api_key")
        if not key:
            raise ReelcraftError("Gemini API key belum diatur. Isi di Settings.")
        return GoogleModel(name, provider=GoogleProvider(api_key=key))
    if provider == "openai":
        base_url = settings.get(session, "openai_base_url")
        key = settings.get(session, "openai_api_key")
        if not key and not base_url:
            raise ReelcraftError("OpenAI API key belum diatur. Isi di Settings.")
        # Local servers (Ollama, LM Studio) ignore the key but the client requires one
        return OpenAIChatModel(name, provider=OpenAIProvider(base_url=base_url, api_key=key or "-"))
    raise ReelcraftError(f"Provider '{provider}' tidak dikenal. Pilihan: google, openai")


def model_for(task: Task) -> Model:
    with session_scope() as s:
        spec = settings.get(s, f"{task}_model")
        assert spec is not None  # both have defaults
        return build(s, spec)


def error_kind(status: int) -> type[ReelcraftError]:
    if status == 429:
        return QuotaExceeded
    return ProviderUnavailable if status >= 500 else ReelcraftError


@contextmanager
def ai_errors() -> Iterator[None]:
    """Provider failures as one readable line instead of an SDK traceback."""
    try:
        yield
    except ModelHTTPError as e:
        body = e.body if isinstance(e.body, dict) else {}
        detail = (body.get("error") or {}).get("message") if body else None
        message = f"AI menolak permintaan ({e.status_code}): {detail or e.message}"
        raise error_kind(e.status_code)(message) from e
    except UnexpectedModelBehavior as e:
        raise ReelcraftError(f"Jawaban AI tidak sesuai format: {e}") from e


def retrying[T](call: Callable[[], T]) -> T:
    """`call()`, retried after a pause while the provider is overloaded (5xx); other errors
    (bad key, quota, bad output) are raised right away since retrying won't help."""
    for wait in RETRY_WAITS:
        try:
            return call()
        except ProviderUnavailable:
            time.sleep(wait)
    return call()
