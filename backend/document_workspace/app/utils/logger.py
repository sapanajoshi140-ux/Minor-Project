"""
Centralised logging configuration.
Call setup_logging() once at application startup (in main.py lifespan).
"""

import logging
import sys
from pathlib import Path


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """
    Configure the root logger.

    Args:
        level:    Log level string — "DEBUG", "INFO", "WARNING", "ERROR".
        log_file: Optional file path. If provided, logs go to stdout AND the file.
    """
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s — %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    handlers: list[logging.Handler] = [_stream_handler(formatter)]
    if log_file:
        handlers.append(_file_handler(log_file, formatter))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
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