"""
test_ingestion_excel.py
========================
Tests for src/ingestion/excel_reader.py.

Run with:
    pytest tests/test_ingestion_excel.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from src.ingestion.excel_reader import ExcelIngestionReader


@pytest.fixture
def single_sheet_xlsx(tmp_path):
    path = tmp_path / "single.xlsx"
    df = pd.DataFrame({"product": ["Widget", "Gadget"], "price": [9.99, 19.99]})
    df.to_excel(path, sheet_name="Products", index=False, engine="openpyxl")
    return path


@pytest.fixture
def multi_sheet_xlsx(tmp_path):
    path = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame({"region": ["North", "South"], "revenue": [1000, 2000]}).to_excel(
            writer, sheet_name="Q1", index=False
        )
        pd.DataFrame({"region": ["North", "South"], "revenue": [1100, 2100]}).to_excel(
            writer, sheet_name="Q2", index=False
        )
        pd.DataFrame({"region": ["East"], "revenue": [500]}).to_excel(
            writer, sheet_name="Q3", index=False
        )
    return path


def test_single_sheet_workbook_returns_plain_dataframe(single_sheet_xlsx):
    reader = ExcelIngestionReader("test_source_not_registered")
    df, result = reader.read(single_sheet_xlsx)
    assert result.status == "success"
    assert len(df) == 2
    assert "_sheet_name" not in df.columns  # single sheet - no tagging needed
    assert list(df["product"]) == ["Widget", "Gadget"]


def test_multi_sheet_workbook_combines_with_sheet_tag(multi_sheet_xlsx):
    reader = ExcelIngestionReader("test_source_not_registered")
    df, result = reader.read(multi_sheet_xlsx)
    assert result.status == "success"
    assert "_sheet_name" in df.columns
    assert set(df["_sheet_name"].unique()) == {"Q1", "Q2", "Q3"}
    assert len(df) == 5  # 2 + 2 + 1 rows across three sheets
    assert result.row_count == 5


def test_specific_sheet_name_returns_only_that_sheet(multi_sheet_xlsx):
    reader = ExcelIngestionReader("test_source_not_registered")
    df, result = reader.read(multi_sheet_xlsx, sheet_name="Q2")
    assert len(df) == 2
    assert list(df["revenue"]) == [1100, 2100]
    assert "_sheet_name" not in df.columns


def test_missing_excel_file_returns_skipped():
    reader = ExcelIngestionReader("test_source_not_registered")
    df, result = reader.read(Path("/tmp/does_not_exist_xyz.xlsx"))
    assert df is None
    assert result.status == "skipped"


def test_unregistered_source_name_does_not_raise(single_sheet_xlsx):
    # Excel reader should work even for a source not in data_sources.yaml
    # (e.g., an ad-hoc manual file), just with a logged warning.
    reader = ExcelIngestionReader("totally_made_up_source_name")
    df, result = reader.read(single_sheet_xlsx)
    assert result.status == "success"
