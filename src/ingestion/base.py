"""
base.py
=======
Common interface every ingestion reader (CSV, Excel, JSON, API) implements.
Keeping a shared base class means the Phase 1.6 orchestrator can loop over
readers polymorphically without caring what format each source is in.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.utils.helpers import file_checksum, get_utc_timestamp
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    """
    Standardized result object every reader returns, regardless of source
    format. This is what gets logged to the ingestion manifest in Phase 1.6.
    """
    source_name: str
    file_path: Optional[str]
    row_count: int
    column_count: int
    columns: list
    checksum: Optional[str]
    started_at: str
    finished_at: str
    duration_seconds: float
    status: str  # "success" | "failed" | "skipped"
    error_message: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "file_path": self.file_path,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "columns": self.columns,
            "checksum": self.checksum,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "error_message": self.error_message,
            "extra": self.extra,
        }


class BaseIngestionReader(ABC):
    """
    Abstract base for all ingestion readers.

    Subclasses implement `_read()` to return a pandas DataFrame (or an
    iterator of DataFrame chunks for very large files). The public `read()`
    method wraps `_read()` with timing, checksum computation, and consistent
    error handling/logging, so subclasses stay focused on format-specific
    parsing only.
    """

    def __init__(self, source_name: str):
        self.source_name = source_name

    @abstractmethod
    def _read(self, file_path: Path, **kwargs) -> Any:
        """Format-specific read logic. Must be implemented by subclasses."""
        raise NotImplementedError

    def read(self, file_path: Path, compute_checksum: bool = True, **kwargs):
        """
        Reads a single file and returns (dataframe_or_iterator, IngestionResult).
        Never raises on a bad file - failures are captured in the result's
        status/error_message so a batch run can continue past one bad source.
        """
        started_at = get_utc_timestamp()
        start_perf = datetime.now()
        file_path = Path(file_path)

        if not file_path.exists():
            result = IngestionResult(
                source_name=self.source_name,
                file_path=str(file_path),
                row_count=0,
                column_count=0,
                columns=[],
                checksum=None,
                started_at=started_at,
                finished_at=get_utc_timestamp(),
                duration_seconds=0.0,
                status="skipped",
                error_message="File does not exist",
            )
            logger.warning(f"[{self.source_name}] Skipped - file not found: {file_path}")
            return None, result

        try:
            checksum = file_checksum(file_path) if compute_checksum else None
            data = self._read(file_path, **kwargs)

            # Support both a plain DataFrame and a list-of-chunks return type
            if isinstance(data, list):
                row_count = sum(len(chunk) for chunk in data)
                columns = list(data[0].columns) if data else []
            else:
                row_count = len(data)
                columns = list(data.columns)

            finished_at = get_utc_timestamp()
            duration = (datetime.now() - start_perf).total_seconds()

            result = IngestionResult(
                source_name=self.source_name,
                file_path=str(file_path),
                row_count=row_count,
                column_count=len(columns),
                columns=columns,
                checksum=checksum,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=round(duration, 3),
                status="success",
            )
            logger.info(
                f"[{self.source_name}] Read {row_count:,} rows / {len(columns)} cols "
                f"from {file_path.name} in {duration:.2f}s"
            )
            return data, result

        except Exception as e:
            finished_at = get_utc_timestamp()
            duration = (datetime.now() - start_perf).total_seconds()
            result = IngestionResult(
                source_name=self.source_name,
                file_path=str(file_path),
                row_count=0,
                column_count=0,
                columns=[],
                checksum=None,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=round(duration, 3),
                status="failed",
                error_message=str(e),
            )
            logger.error(f"[{self.source_name}] FAILED reading {file_path.name}: {e}")
            return None, result
