"""Centralized logging configuration.

One call to `configure_logging()` at app/CLI startup; everything else uses
`logging.getLogger(__name__)` and inherits the format + level.
"""

import logging
import sys

_CONFIGURED = False

_FMT = "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s : %(message)s"
_DATEFMT = "%H:%M:%S"


def configure_logging(level: str | int = "INFO") -> None:
    """Idempotent — safe to call from multiple entrypoints."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    if isinstance(level, str):
        level = level.upper()

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))

    root = logging.getLogger()
    # Remove uvicorn's default handlers so we don't double-print.
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn writes its own loggers — let them propagate to the root handler.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    # Calm down noisy libraries.
    for noisy in ("httpx", "httpcore", "hpack", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
