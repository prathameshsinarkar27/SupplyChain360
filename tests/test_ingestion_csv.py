"""
test_ingestion_csv.py
======================
Tests for src/ingestion/{base, csv_reader, source_registry}.py.

Uses pytest's tmp_path fixture to create throwaway CSVs so the repo itself
never needs sample data files committed to it.

Run with:
    pytest tests/test_ingestion_csv.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from src.ingestion.base import BaseIngestionReader, IngestionResult
from src.ingestion.csv_reader import CSVIngestionReader
from src.ingestion.source_registry import (
    get_source,
    list_sources,
    resolve_source_files,
    SourceNotFoundError,
)


# --------------------------------------------------------------------------
# source_registry tests
# --------------------------------------------------------------------------

def test_list_sources_includes_expected_entries():
    sources = list_sources()
    assert "dataco_supply_chain" in sources
    assert "retail_inventory" in sources
    assert "amazon_products" in sources
    assert "amazon_reviews" in sources
    assert "generated_master_data" in sources


def test_get_source_returns_resolved_raw_dir():
    source = get_source("dataco_supply_chain")
    assert source["encoding"] == "latin-1"
    assert isinstance(source["raw_dir"], Path)
    assert source["raw_dir"].is_absolute()


def test_get_source_unknown_raises():
    with pytest.raises(SourceNotFoundError):
        get_source("not_a_real_source")


def test_resolve_source_files_skips_missing(tmp_path, monkeypatch):
    # generated_master_data expects files that don't exist yet (Phase 1.5 will create them)
    files = resolve_source_files("generated_master_data")
    assert files == []  # none exist yet - should not raise


# --------------------------------------------------------------------------
# CSVIngestionReader tests
# --------------------------------------------------------------------------

@pytest.fixture
def utf8_csv(tmp_path):
    content = "order_id,customer_name,amount\n1,Alice,100.50\n2,Bob,75.25\n"
    path = tmp_path / "sample_utf8.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def latin1_csv(tmp_path):
    # Mirrors the real DataCo file's encoding quirk (accented characters)
    content = "order_id,customer_fname,city\n1,Jos\xe9,S\xe3o Paulo\n2,M\xfcller,M\xfcnchen\n"
    path = tmp_path / "sample_latin1.csv"
    path.write_bytes(content.encode("latin-1"))
    return path


@pytest.fixture
def malformed_row_csv(tmp_path):
    content = (
        "name,category,price\n"
        '"Widget",tools,9.99\n'
        "BROKEN,ROW,WITH,EXTRA,FIELDS\n"
        '"Gadget",electronics,19.99\n'
    )
    path = tmp_path / "sample_malformed.csv"
    path.write_text(content, encoding="utf-8")
    return path


def _reader_for(tmp_source_name="dataco_supply_chain"):
    return CSVIngestionReader(tmp_source_name)


def test_csv_reader_reads_utf8_file(utf8_csv):
    reader = _reader_for("amazon_products")  # utf-8 source
    df, result = reader.read(utf8_csv)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert result.status == "success"
    assert result.row_count == 2
    assert result.column_count == 3
    assert result.checksum is not None


def test_csv_reader_handles_latin1_encoding(latin1_csv):
    reader = _reader_for("dataco_supply_chain")  # latin-1 source per config
    df, result = reader.read(latin1_csv)
    assert result.status == "success"
    assert df.iloc[0]["customer_fname"] == "Jos\xe9"
    assert df.iloc[1]["city"] == "M\xfcnchen"


def test_csv_reader_skips_malformed_rows_without_failing(malformed_row_csv):
    reader = _reader_for("amazon_products")
    df, result = reader.read(malformed_row_csv)
    assert result.status == "success"
    assert len(df) == 2  # the 3-column-violating row is dropped, not fatal
    assert list(df["name"]) == ["Widget", "Gadget"]


def test_csv_reader_missing_file_returns_skipped_result():
    reader = _reader_for("dataco_supply_chain")
    df, result = reader.read(Path("/tmp/definitely_does_not_exist_12345.csv"))
    assert df is None
    assert result.status == "skipped"
    assert result.row_count == 0


def test_csv_reader_chunking(tmp_path):
    # 10 data rows, chunked into groups of 3 -> 4 chunks (3,3,3,1)
    rows = ["id,value"] + [f"{i},{i*10}" for i in range(10)]
    path = tmp_path / "chunked.csv"
    path.write_text("\n".join(rows), encoding="utf-8")

    reader = _reader_for("amazon_products")
    chunks, result = reader.read(path, chunksize=3)
    assert isinstance(chunks, list)
    assert len(chunks) == 4
    assert result.row_count == 10
    assert sum(len(c) for c in chunks) == 10


def test_ingestion_result_to_dict_roundtrip():
    result = IngestionResult(
        source_name="test",
        file_path="x.csv",
        row_count=5,
        column_count=2,
        columns=["a", "b"],
        checksum="abc123",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z",
        duration_seconds=1.0,
        status="success",
    )
    d = result.to_dict()
    assert d["row_count"] == 5
    assert d["status"] == "success"
