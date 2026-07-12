"""
source_registry.py
===================
Thin accessor layer over config/data_sources.yaml so ingestion code never
hardcodes dataset paths, file names, or encodings.

Usage:
    from src.ingestion.source_registry import get_source, list_sources

    src = get_source("dataco_supply_chain")
    print(src["raw_dir"], src["encoding"])
"""

from pathlib import Path
from typing import Any, Optional

import yaml

from src.utils.config import PROJECT_ROOT
from src.utils.logger import get_logger

logger = get_logger(__name__)

DATA_SOURCES_PATH = PROJECT_ROOT / "config" / "data_sources.yaml"


class SourceNotFoundError(Exception):
    """Raised when a requested data source name isn't in the registry."""


def _load_registry() -> dict:
    if not DATA_SOURCES_PATH.exists():
        raise FileNotFoundError(
            f"Data source registry not found at {DATA_SOURCES_PATH}. "
            f"Was config/data_sources.yaml moved or renamed?"
        )
    with open(DATA_SOURCES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("sources", {})


def list_sources() -> list:
    """Returns all registered source names."""
    return sorted(_load_registry().keys())


def get_source(name: str) -> dict:
    """
    Returns the config dict for a single named source, with `raw_dir`
    resolved to an absolute Path for convenience.
    """
    registry = _load_registry()
    if name not in registry:
        available = ", ".join(sorted(registry.keys()))
        raise SourceNotFoundError(
            f"Unknown data source '{name}'. Available sources: {available}"
        )
    source = dict(registry[name])  # shallow copy so callers can't mutate the cache
    if "raw_dir" in source:
        source["raw_dir"] = (PROJECT_ROOT / source["raw_dir"]).resolve()
    return source


def resolve_source_files(name: str) -> list:
    """
    Returns a list of absolute file Paths that actually exist on disk for a
    given source, based on its `expected_files` entries. Skips comment-only
    entries and logs a warning for any expected file that's missing.
    """
    source = get_source(name)
    raw_dir: Path = source["raw_dir"]
    expected = source.get("expected_files", []) or []

    found = []
    for filename in expected:
        file_path = raw_dir / filename
        if file_path.exists():
            found.append(file_path)
        else:
            logger.warning(f"[{name}] Expected file not found: {file_path}")
    return found


if __name__ == "__main__":
    # Quick manual sanity check: `python -m src.ingestion.source_registry`
    for name in list_sources():
        src = get_source(name)
        print(f"- {name}: {src.get('description', '(no description)')}")
