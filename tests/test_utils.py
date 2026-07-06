"""
test_utils.py
=============
Basic verification tests for core modules: config, logger, helpers.

Run with:
    pytest tests/test_utils.py -v
"""

import os
import time
from pathlib import Path

import pytest

from src.utils.config import get_config, PROJECT_ROOT
from src.utils.logger import get_logger
from src.utils import helpers


# --------------------------------------------------------------------------
# Config tests
# --------------------------------------------------------------------------

def test_config_loads_successfully():
    cfg = get_config()
    assert cfg["project"]["name"] == "SupplyChain360"
    assert "database" in cfg
    assert "logging" in cfg


def test_config_resolves_paths():
    cfg = get_config()
    resolved = cfg["_resolved_paths"]
    assert resolved["data_raw"].exists()
    assert resolved["logs"].exists()


def test_config_env_keys_present_even_if_empty():
    cfg = get_config()
    env = cfg["_env"]
    # Keys should exist in the dict even if the .env file hasn't been created yet
    assert "DB_HOST" in env
    assert "DB_PASSWORD" in env


# --------------------------------------------------------------------------
# Logger tests
# --------------------------------------------------------------------------

def test_logger_writes_to_file():
    logger = get_logger("supplychain360.test_logger")
    marker = f"TEST_LOG_MARKER_{int(time.time())}"
    logger.info(marker)

    cfg = get_config()
    log_file = cfg["_resolved_paths"]["logs"] / cfg["logging"]["log_file_name"]

    # Give the file handler a moment to flush
    for handler in logger.handlers:
        handler.flush()

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert marker in content


def test_logger_does_not_duplicate_handlers():
    logger1 = get_logger("supplychain360.dup_test")
    handler_count_1 = len(logger1.handlers)
    logger2 = get_logger("supplychain360.dup_test")
    handler_count_2 = len(logger2.handlers)
    assert handler_count_1 == handler_count_2
    assert logger1 is logger2


# --------------------------------------------------------------------------
# Helpers tests
# --------------------------------------------------------------------------

def test_ensure_dir_creates_directory(tmp_path):
    target = tmp_path / "nested" / "dir"
    result = helpers.ensure_dir(target)
    assert result.exists()
    assert result.is_dir()


def test_get_utc_timestamp_format():
    ts = helpers.get_utc_timestamp()
    assert ts.endswith("Z")
    assert "T" in ts


def test_get_run_id_prefix():
    run_id = helpers.get_run_id("ingestion")
    assert run_id.startswith("ingestion_")


def test_read_write_json_roundtrip(tmp_path):
    data = {"a": 1, "b": [1, 2, 3], "c": "hello"}
    file_path = tmp_path / "sample.json"
    helpers.write_json(data, file_path)
    loaded = helpers.read_json(file_path)
    assert loaded == data


def test_bytes_to_human_readable():
    assert helpers.bytes_to_human_readable(500) == "500.0 B"
    assert "KB" in helpers.bytes_to_human_readable(2048)


def test_safe_env_bool():
    assert helpers.safe_env_bool("true") is True
    assert helpers.safe_env_bool("0") is False
    assert helpers.safe_env_bool(None, default=True) is True


def test_list_files_with_extension_on_missing_dir():
    result = helpers.list_files_with_extension("nonexistent_dir_xyz", ".csv")
    assert result == []
