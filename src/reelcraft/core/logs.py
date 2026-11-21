"""One log for the CLI and the server: JSON lines in <data dir>/logs/reelcraft.log, read back by
`reelcraft logs`. structlog and plain `logging` loggers both end up there."""

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog

from reelcraft.core.config import get_settings

FILE_BYTES, FILE_COUNT = 5_000_000, 3  # rotated: at most ~20 MB on disk


def _drop_none(_logger: object, _name: str, event: dict) -> dict:
    return {k: v for k, v in event.items() if v is not None}


_SHARED = [
    structlog.contextvars.merge_contextvars,
    _drop_none,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]
_handlers: list[logging.Handler] = []


def log_file() -> Path:
    return get_settings().data_dir / "logs" / "reelcraft.log"


def _handler(handler: logging.Handler, renderer: structlog.typing.Processor) -> logging.Handler:
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=_SHARED,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                renderer,
            ],
        )
    )
    return handler


def setup(console: bool = False) -> None:
    """File logging always; console output too for `serve`. Safe to call again."""
    root = logging.getLogger()
    for h in _handlers:
        root.removeHandler(h)
        h.close()
    _handlers.clear()
    path = log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    rotating = logging.handlers.RotatingFileHandler(
        path, maxBytes=FILE_BYTES, backupCount=FILE_COUNT, encoding="utf-8"
    )
    _handlers.append(_handler(rotating, structlog.processors.JSONRenderer(ensure_ascii=False)))
    if console:
        _handlers.append(
            _handler(logging.StreamHandler(sys.stderr), structlog.dev.ConsoleRenderer(colors=False))
        )
    for h in _handlers:
        root.addHandler(h)
    root.setLevel(logging.INFO)
    # Every page polls the queue: request lines would bury what matters
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    for noisy in ("httpx", "httpx2", "httpcore", "google_genai", "faster_whisper", "alembic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[*_SHARED, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
