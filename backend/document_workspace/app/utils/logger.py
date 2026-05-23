"""
Centralised logging configuration.
Call setup_logging() once at application startup (in main.py lifespan).

Warning: setup_logging() uses basicConfig(force=True), which replaces all
handlers on the root logger each time it is called.  In multi-threaded
startup code this can cause log records emitted between the old and new
handler sets to be dropped.  Call it exactly once, before spawning threads.
"""

import logging
import sys
from pathlib import Path

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """
    Configure the root logger.

    Args:
        level:    Log level string — "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL".
                  Raises ValueError for unrecognised values instead of silently
                  falling back to INFO.
        log_file: Optional file path. If provided, logs go to stdout AND the file.

    Raises:
        ValueError: if `level` is not one of the recognised level strings.
    """
    normalised = level.upper()
    if normalised not in _VALID_LEVELS:
        raise ValueError(
            f"Invalid log level {level!r}. Must be one of: {', '.join(sorted(_VALID_LEVELS))}"
        )

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s — %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    handlers: list[logging.Handler] = [_stream_handler(formatter)]
    if log_file:
        handlers.append(_file_handler(log_file, formatter))

    logging.basicConfig(
        level=getattr(logging, normalised),
        handlers=handlers,
        force=True,
    )

    # Suppress noisy third-party loggers
    for name in ("urllib3", "PIL", "easyocr", "fitz", "multipart"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper — use instead of logging.getLogger() in modules."""
    return logging.getLogger(name)


def _stream_handler(formatter: logging.Formatter) -> logging.StreamHandler:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(formatter)
    return h


def _file_handler(log_file: str, formatter: logging.Formatter) -> logging.FileHandler:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    h = logging.FileHandler(log_file, encoding="utf-8")
    h.setFormatter(formatter)
    return h