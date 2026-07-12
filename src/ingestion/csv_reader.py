"""
csv_reader.py
=============
Config-driven CSV ingestion reader.

Handles the real-world messiness this project's sources actually have:
  - Non-UTF-8 encodings (DataCo ships as latin-1)
  - Large files that shouldn't be loaded fully into memory at once (chunking)
  - Bad/malformed rows that shouldn't kill an entire ingestion run

Usage:
    from src.ingestion.csv_reader import CSVIngestionReader
    from src.ingestion.source_registry import resolve_source_files

    reader = CSVIngestionReader("dataco_supply_chain")
    files = resolve_source_files("dataco_supply_chain")
    df, result = reader.read(files[0])
"""

from pathlib import Path
from typing import Optional

import pandas as pd

from src.ingestion.base import BaseIngestionReader
from src.ingestion.source_registry import get_source
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CSVIngestionReader(BaseIngestionReader):
    """
    CSV reader that pulls its encoding/delimiter defaults from
    config/data_sources.yaml, but allows per-call overrides.
    """

    def __init__(self, source_name: str):
        super().__init__(source_name)
        self.source_config = get_source(source_name)

    def _read(
        self,
        file_path: Path,
        encoding: Optional[str] = None,
        delimiter: str = ",",
        chunksize: Optional[int] = None,
        on_bad_lines: str = "warn",
        dtype: Optional[dict] = None,
    ):
        """
        Reads a CSV file into a DataFrame, or a list of DataFrame chunks if
        `chunksize` is provided (useful for very large files in later phases
        once PySpark isn't yet in the loop).

        `on_bad_lines="warn"` logs malformed rows instead of crashing the
        whole ingestion run on one corrupt line - common with scraped
        datasets like the Amazon Products CSVs.
        """
        resolved_encoding = encoding or self.source_config.get("encoding", "utf-8")

        read_kwargs = dict(
            filepath_or_buffer=file_path,
            encoding=resolved_encoding,
            delimiter=delimiter,
            dtype=dtype,
            on_bad_lines=on_bad_lines,
            engine="python",  # required for on_bad_lines="warn" support
        )

        if chunksize:
            chunks = []
            for chunk in pd.read_csv(chunksize=chunksize, **read_kwargs):
                chunks.append(chunk)
            logger.info(
                f"[{self.source_name}] Read {file_path.name} in "
                f"{len(chunks)} chunk(s) of up to {chunksize:,} rows"
            )
            return chunks

        return pd.read_csv(**read_kwargs)


if __name__ == "__main__":
    # Quick manual sanity check with a tiny inline sample - does not require
    # any real dataset to be downloaded yet.
    import tempfile

    sample_csv = "order_id,customer_name,amount\n1,Alice,100.50\n2,Bob,75.25\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(sample_csv)
        tmp_path = Path(f.name)

    # Bypass the registry for this standalone smoke test
    reader = CSVIngestionReader.__new__(CSVIngestionReader)
    reader.source_name = "smoke_test"
    reader.source_config = {"encoding": "utf-8"}
    df, result = reader.read(tmp_path)
    print(df)
    print(result.to_dict())
    tmp_path.unlink()
