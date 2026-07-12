"""
test_orchestrator.py
=====================
Tests for src/ingestion/orchestrator.py.

Run with:
    pytest tests/test_orchestrator.py -v
"""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.ingestion.base import IngestionResult
from src.ingestion.orchestrator import (
    _ensure_master_data_exists,
    run_api_enrichment,
    run_csv_ingestion,
    write_manifest,
)


def test_ensure_master_data_generates_into_empty_dir(tmp_path):
    generated = _ensure_master_data_exists(
        tmp_path, seed=1, n_warehouses=3, n_suppliers=3, n_couriers=2, n_vehicles=5, n_routes=5
    )
    assert generated is True
    assert len(list(tmp_path.glob("*.csv"))) == 5


def test_ensure_master_data_skips_when_files_already_exist(tmp_path):
    _ensure_master_data_exists(tmp_path, seed=1, n_warehouses=3, n_suppliers=3,
                                n_couriers=2, n_vehicles=5, n_routes=5)
    generated_again = _ensure_master_data_exists(tmp_path, seed=999, n_warehouses=99)
    assert generated_again is False

    warehouses = pd.read_csv(tmp_path / "warehouses.csv")
    assert len(warehouses) == 3  # unchanged from the first call


def test_run_csv_ingestion_reads_generated_master_data():
    # generated_master_data is a real, committed source in this project -
    # this is an integration test against the actual registry/files.
    results = run_csv_ingestion(source_names=["generated_master_data"])
    assert len(results) == 5
    assert all(r.status == "success" for r in results)
    total_rows = sum(r.row_count for r in results)
    assert total_rows > 0


def test_run_csv_ingestion_skips_missing_sources_gracefully():
    results = run_csv_ingestion(source_names=["dataco_supply_chain"])
    assert results == []  # no files present -> no results, no crash


def test_write_manifest_aggregates_mixed_statuses(tmp_path, monkeypatch):
    import src.ingestion.orchestrator as orch
    monkeypatch.setattr(orch, "MANIFEST_DIR", tmp_path)

    results = [
        IngestionResult(source_name="a", file_path="a.csv", row_count=100, column_count=3,
                         columns=["x", "y", "z"], checksum="abc", started_at="t1", finished_at="t2",
                         duration_seconds=0.1, status="success"),
        IngestionResult(source_name="b", file_path="b.csv", row_count=0, column_count=0, columns=[],
                         checksum=None, started_at="t1", finished_at="t2", duration_seconds=0.1,
                         status="failed", error_message="boom"),
        IngestionResult(source_name="c", file_path=None, row_count=0, column_count=0, columns=[],
                         checksum=None, started_at="t1", finished_at="t2", duration_seconds=0.0,
                         status="skipped"),
    ]
    manifest_path = write_manifest(results, run_id="test_mixed")

    with open(manifest_path) as f:
        manifest = json.load(f)

    assert manifest["succeeded"] == 1
    assert manifest["failed"] == 1
    assert manifest["skipped"] == 1
    assert manifest["total_rows_ingested"] == 100
    assert len(manifest["results"]) == 3


def test_write_manifest_empty_results_list(tmp_path, monkeypatch):
    import src.ingestion.orchestrator as orch
    monkeypatch.setattr(orch, "MANIFEST_DIR", tmp_path)

    manifest_path = write_manifest([], run_id="test_empty")
    with open(manifest_path) as f:
        manifest = json.load(f)
    assert manifest["total_sources_attempted"] == 0
    assert manifest["total_rows_ingested"] == 0


def test_run_api_enrichment_calls_weather_holiday_and_fx():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"daily": {"time": ["2018-01-01"], "temperature_2m_max": [20.0]}}
    mock_resp.raise_for_status.return_value = None

    orders_df = pd.DataFrame({
        "Order Country": ["United States", "United States", "Brazil"],
        "Order City": ["Los Angeles", "Los Angeles", "Sao Paulo"],
        "Latitude": [34.05, 34.05, -23.55],
        "Longitude": [-118.24, -118.24, -46.63],
    })

    with patch("requests.Session.get", return_value=mock_resp) as mock_get:
        results = run_api_enrichment(orders_df, top_n_locations=2, holiday_year=2018)
        assert len(results) == 5  # 2 locations x (weather + holiday) + 1 exchange rate
        assert all(r.status == "success" for r in results)
        assert mock_get.call_count == 5


def test_run_api_enrichment_skips_holiday_for_unresolved_country():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"daily": {"time": ["2018-01-01"], "temperature_2m_max": [20.0]}}
    mock_resp.raise_for_status.return_value = None

    orders_df = pd.DataFrame({
        "Order Country": ["Nowhereland"],
        "Order City": ["Atlantis"],
        "Latitude": [0.0],
        "Longitude": [0.0],
    })

    with patch("requests.Session.get", return_value=mock_resp):
        results = run_api_enrichment(orders_df, top_n_locations=1, holiday_year=2018)
        assert len(results) == 2  # 1 weather + 1 fx, no holiday (unresolved country)
