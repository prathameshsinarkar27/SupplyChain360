"""
logger.py
=========
Centralized logging setup for SupplyChain360.

Every module in the project should obtain its logger via:

    from src.utils.logger import get_logger
    logger = get_logger(__name__)

    logger.info("Ingestion started")
    logger.warning("Missing values found in column X")
    logger.error("Failed to connect to database")

Features:
  - Console handler (colored level names if colorlog-friendly terminal)
  - Rotating file handler -> logs/supplychain360.log
  - Configuration driven by config/config.yaml (level, format, rotation size)
  - Safe to call get_logger() multiple times (handlers are not duplicated)
"""

import logging
import logging.handlers
from pathlib import Path

from src.utils.config import get_config

_CONFIGURED_LOGGERS = set()


def _build_handlers(log_cfg: dict, logs_dir: Path):
    handlers = []
    log_format = log_cfg.get("format", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    date_format = log_cfg.get("date_format", "%Y-%m-%d %H:%M:%S")
    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

    if log_cfg.get("log_to_console", True):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    if log_cfg.get("log_to_file", True):
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file_path = logs_dir / log_cfg.get("log_file_name", "supplychain360.log")
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_file_path),
            maxBytes=int(log_cfg.get("max_bytes", 5 * 1024 * 1024)),
            backupCount=int(log_cfg.get("backup_count", 5)),
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    return handlers


def get_logger(name: str = "supplychain360") -> logging.Logger:
    """
    Returns a configured logger. Safe to call repeatedly across modules -
    handlers are attached only once per logger name.
    """
    logger = logging.getLogger(name)

    if name in _CONFIGURED_LOGGERS:
        return logger

    config = get_config()
    log_cfg = config.get("logging", {})
    logs_dir = config["_resolved_paths"].get("logs", Path("logs"))

    level_name = log_cfg.get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    for handler in _build_handlers(log_cfg, logs_dir):
        logger.addHandler(handler)

    # Prevent double logging if root logger also has handlers attached
    logger.propagate = False

    _CONFIGURED_LOGGERS.add(name)
    return logger


if __name__ == "__main__":
    # Quick manual sanity check: `python -m src.utils.logger`
    log = get_logger("supplychain360.test")
    log.debug("This is a DEBUG message (may not show if level=INFO)")
    log.info("This is an INFO message")
    log.warning("This is a WARNING message")
    log.error("This is an ERROR message")
    log.critical("This is a CRITICAL message")
    print("Check logs/supplychain360.log for the file output.")
