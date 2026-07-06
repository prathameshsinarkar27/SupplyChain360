"""
config.py
=========
Centralized configuration loader for SupplyChain360.

Usage:
    from src.utils.config import get_config
    cfg = get_config()
    print(cfg["database"]["port"])
    print(cfg["_env"]["DB_PASSWORD"])
"""

import os
import functools
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Project root = two levels up from this file (src/utils/config.py -> project root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
ENV_PATH = PROJECT_ROOT / ".env"


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or is invalid."""


def _load_yaml_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise ConfigError(
            f"Config file not found at {config_path}. "
            f"Did you rename config.yaml or move it out of the config/ folder?"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"Failed to parse {config_path}: {e}") from e
    return data


def _load_env(env_path: Path) -> dict:
    """
    Loads .env into os.environ (if present) and returns a plain dict snapshot
    of the environment variables we care about. Falls back gracefully if
    .env does not exist yet (e.g., fresh clone before setup).
    """
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
    else:
        # Not fatal in Phase 0 - later phases (DB, APIs) will need a real .env
        pass

    keys = [
        "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
        "PGADMIN_EMAIL", "PGADMIN_PASSWORD",
        "EXCHANGE_RATE_API_KEY", "HOLIDAY_API_KEY", "FUEL_PRICE_API_KEY", "PRODUCT_INFO_API_KEY",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION", "S3_BUCKET_NAME",
        "AIRFLOW_UID", "AIRFLOW__CORE__EXECUTOR",
        "APP_ENV", "LOG_LEVEL",
    ]
    return {k: os.getenv(k) for k in keys}


def _resolve_paths(cfg: dict) -> dict:
    """Convert relative paths in config['paths'] to absolute Path objects
    anchored at PROJECT_ROOT, and ensure they exist."""
    resolved = {}
    for key, rel_path in cfg.get("paths", {}).items():
        abs_path = (PROJECT_ROOT / rel_path).resolve()
        abs_path.mkdir(parents=True, exist_ok=True)
        resolved[key] = abs_path
    cfg["_resolved_paths"] = resolved
    return cfg


@functools.lru_cache(maxsize=1)
def get_config() -> dict:
    """
    Loads and caches the full configuration (YAML + env).
    Cached with lru_cache so repeated calls are cheap; call
    get_config.cache_clear() in tests if you need a fresh reload.
    """
    cfg = _load_yaml_config(CONFIG_PATH)
    cfg["_env"] = _load_env(ENV_PATH)
    cfg["_project_root"] = PROJECT_ROOT
    cfg = _resolve_paths(cfg)
    return cfg


if __name__ == "__main__":
    # Quick manual sanity check: `python -m src.utils.config`
    config = get_config()
    print(f"Project: {config['project']['name']} v{config['project']['version']}")
    print(f"Phase:   {config['project']['phase']}")
    print(f"Root:    {config['_project_root']}")
    print(f"DB port: {config['database']['port']}")
