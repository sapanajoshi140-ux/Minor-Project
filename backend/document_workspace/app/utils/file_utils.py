"""
File utility helpers — validation, safe naming, size checks, deletion.
"""

import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".png", ".jpg", ".jpeg"}


def validate_extension(filename: str) -> bool:
    """Return True if the file extension is supported."""
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def generate_safe_filename(original_filename: str) -> str:
    """
    Generate a UUID-based filename that preserves the original extension.
    Prevents path traversal and naming collisions.
    """
    ext = Path(original_filename).suffix.lower()
    return f"{uuid.uuid4()}{ext}"


def ensure_directory(path: str | Path) -> Path:
    """Create the directory (and parents) if it does not exist."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


class FileDeleteError(OSError):
    """Raised when a file exists but cannot be deleted."""


def safe_delete_file(file_path: str | Path) -> bool:
    """
    Delete a file safely.

    Returns:
        True  — file existed and was deleted successfully.
        False — file did not exist (no-op); logged as a warning.

    Raises:
        FileDeleteError — file exists but could not be deleted (permission
                          error, I/O error, etc.).  Callers that previously
                          relied on the False-on-error behaviour should catch
                          this exception explicitly.
    """
    p = Path(file_path)
    if not p.exists():
        logger.warning(f"File not found, skipping delete: {p}")
        return False
    try:
        p.unlink()
        logger.info(f"Deleted: {p}")
        return True
    except Exception as exc:
        logger.error(f"Error deleting {file_path}: {exc}")
        raise FileDeleteError(f"Could not delete {file_path}: {exc}") from exc


def get_file_size_mb(file_path: str | Path) -> float:
    """Return file size in megabytes."""
    try:
        return round(Path(file_path).stat().st_size / (1024 * 1024), 4)
    except Exception as exc:
        logger.error(f"Cannot get file size for {file_path}: {exc}")
        return 0.0


def get_extension(filename: str) -> str:
    """
    Return the lowercase extension without the leading dot, e.g. 'pdf'.

    Note: for multi-part suffixes such as 'archive.tar.gz' only the last
    component ('gz') is returned, because Path.suffix only captures the
    final dot segment.  If your use-case requires full suffix awareness,
    use Path(filename).suffixes instead.
    """
    return Path(filename).suffix.lstrip(".").lower()