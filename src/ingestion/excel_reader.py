"""
excel_reader.py
===============
Config-driven Excel (.xlsx) ingestion reader.

None of SupplyChain360's four core Kaggle sources ship as Excel, but the
blueprint calls for reusable multi-format ingestion, and it's realistic that
a future manual data drop (e.g., a supplier sends an updated master list, or
a one-off business adjustment file) arrives as .xlsx. This reader stays
generic and registry-driven like csv_reader.py, so wiring in a real Excel
source later is a config change, not new code.

Usage:
    from src.ingestion.excel_reader import ExcelIngestionReader

    reader = ExcelIngestionReader("some_future_excel_source")
    df, result = reader.read(file_path, sheet_name=None)  # None = all sheets
"""

from pathlib import Path
from typing import Optional, Union

import pandas as pd

from src.ingestion.base import BaseIngestionReader
from src.ingestion.source_registry import get_source
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ExcelIngestionReader(BaseIngestionReader):
    """
    Excel reader supporting single-sheet or multi-sheet workbooks.

    When `sheet_name=None` (the default), ALL sheets are read and concatenated
    into a single DataFrame with an added `_sheet_name` column, so downstream
    validation/ETL can still tell which sheet each row came from. Pass a
    specific sheet name/index to read just one sheet as a plain DataFrame.
    """

    def __init__(self, source_name: str):
        super().__init__(source_name)
        # Not every Excel source needs to be pre-registered in data_sources.yaml
        # (e.g., a one-off manual file) - fall back to sane defaults if absent.
        try:
            self.source_config = get_source(source_name)
        except Exception:
            logger.warning(
                f"[{source_name}] Not found in data_sources.yaml - using defaults"
            )
            self.source_config = {}

    def _read(
        self,
        file_path: Path,
        sheet_name: Optional[Union[str, int]] = None,
        header: int = 0,
        dtype: Optional[dict] = None,
    ):
        engine = "openpyxl"

        if sheet_name is not None:
            # Single, specific sheet requested
            return pd.read_excel(
                file_path, sheet_name=sheet_name, header=header, dtype=dtype, engine=engine
            )

        # sheet_name=None -> pandas returns {sheet_name: DataFrame, ...}
        all_sheets = pd.read_excel(
            file_path, sheet_name=None, header=header, dtype=dtype, engine=engine
        )

        if len(all_sheets) == 1:
            # Single-sheet workbook - just return the one DataFrame, no need
            # to tag/concatenate.
            only_df = next(iter(all_sheets.values()))
            logger.info(f"[{self.source_name}] Single-sheet workbook detected")
            return only_df

        frames = []
        for name, df in all_sheets.items():
            df = df.copy()
            df["_sheet_name"] = name
            frames.append(df)
        combined = pd.concat(frames, ignore_index=True)
        logger.info(
            f"[{self.source_name}] Combined {len(all_sheets)} sheets "
            f"({', '.join(all_sheets.keys())}) into one DataFrame"
        )
        return combined


if __name__ == "__main__":
    # Quick manual sanity check - builds a throwaway 2-sheet workbook and
    # reads it back, since no real Excel source exists yet.
    import tempfile

    tmp_path = Path(tempfile.mktemp(suffix=".xlsx"))
    with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
        pd.DataFrame({"region": ["North", "South"], "revenue": [1000, 2000]}).to_excel(
            writer, sheet_name="Q1", index=False
        )
        pd.DataFrame({"region": ["North", "South"], "revenue": [1100, 2100]}).to_excel(
            writer, sheet_name="Q2", index=False
        )

    reader = ExcelIngestionReader("smoke_test_excel_source")
    df, result = reader.read(tmp_path)  # sheet_name=None -> combines both sheets
    print(df)
    print(result.to_dict())
    tmp_path.unlink()
