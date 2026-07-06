"""
helpers.py
==========
Generic, reusable utility functions shared across all phases of SupplyChain360.

"""

import os
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

from src.utils.logger import get_logger

logger = get_logger(__name__)


def ensure_dir(path: Union[str, Path]) -> Path:
    """Create a directory (and parents) if it doesn't exist. Returns the Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_utc_timestamp() -> str:
    """Returns current UTC time as an ISO-8601 string, e.g. 2026-07-06T10:15:30Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_run_id(prefix: str = "run") -> str:
    """
    Generates a unique, sortable run identifier for pipeline executions,
    e.g. run_20260706_101530
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}"


def file_checksum(file_path: Union[str, Path], algorithm: str = "sha256") -> str:
    """
    Computes a checksum of a file's contents. Useful for detecting whether a
    source file has changed between ingestion runs (idempotency checks).
    """
    file_path = Path(file_path)
    hash_func = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def read_json(file_path: Union[str, Path]) -> Any:
    """Reads and parses a JSON file, raising a clear error if it fails."""
    file_path = Path(file_path)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to read JSON file {file_path}: {e}")
        raise


def write_json(data: Any, file_path: Union[str, Path], indent: int = 2) -> None:
    """Writes a Python object to a JSON file, creating parent dirs if needed."""
    file_path = Path(file_path)
    ensure_dir(file_path.parent)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, default=str)
    logger.debug(f"Wrote JSON file: {file_path}")


def bytes_to_human_readable(num_bytes: float) -> str:
    """Converts a byte count into a human-readable string, e.g. '3.4 MB'."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def list_files_with_extension(directory: Union[str, Path], extension: str) -> list:
    """
    Lists all files in a directory (non-recursive) matching a given extension.
    Example: list_files_with_extension("data/raw", ".csv")
    """
    directory = Path(directory)
    if not directory.exists():
        logger.warning(f"Directory does not exist: {directory}")
        return []
    ext = extension if extension.startswith(".") else f".{extension}"
    return sorted([str(f) for f in directory.glob(f"*{ext}")])


def safe_env_bool(value: str, default: bool = False) -> bool:
    """Parses a string environment variable into a boolean safely."""
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    # Quick manual sanity check: `python -m src.utils.helpers`
    print("UTC timestamp:", get_utc_timestamp())
    print("Run ID:", get_run_id("ingestion"))
    print("Human readable (1536 bytes):", bytes_to_human_readable(1536))
