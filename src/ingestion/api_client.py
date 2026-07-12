"""
api_client.py
=============
REST API ingestion clients for the three external enrichment sources:
Weather (Open-Meteo), Public Holidays (Nager.Date), and Exchange Rates.

All three share the same needs - timeout, retry-on-transient-failure, JSON
parsing, and saving the raw response to the Raw Layer - so they're built on
a common `BaseAPIClient`. Each concrete client only defines its endpoint
shape and how to build request parameters.

None of these APIs require a paid key (Open-Meteo and Nager.Date are fully
free; the exchange-rate API used here has a free public tier), so Phase 0's
`.env.example` API key fields stay optional.

Usage:
    from src.ingestion.api_client import WeatherAPIClient, HolidayAPIClient, ExchangeRateAPIClient

    weather = WeatherAPIClient()
    data, result = weather.fetch(latitude=34.05, longitude=-118.24,
                                  start_date="2018-01-01", end_date="2018-01-07")

    holidays = HolidayAPIClient()
    data, result = holidays.fetch(country_code="US", year=2018)

    fx = ExchangeRateAPIClient()
    data, result = fx.fetch(base_currency="USD")
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from src.ingestion.base import IngestionResult
from src.ingestion.source_registry import get_source
from src.utils.config import PROJECT_ROOT
from src.utils.helpers import get_utc_timestamp, write_json
from src.utils.logger import get_logger

logger = get_logger(__name__)


class APIClientError(Exception):
    """Raised when an API call fails after all retries are exhausted."""


class BaseAPIClient:
    """
    Shared request/retry/save-raw-response logic for all external API
    ingestion clients.

    Subclasses implement `_build_request(**kwargs)` returning (url, params)
    and `source_registry_name` pointing at the matching entry in
    config/data_sources.yaml (for base_url + raw_dir).
    """

    source_registry_name: str = ""
    max_retries: int = 3
    backoff_seconds: float = 1.5
    timeout_seconds: float = 10.0

    def __init__(self):
        self.source_config = get_source(self.source_registry_name)
        self.base_url = self.source_config.get("base_url", "")
        self.raw_dir: Path = self.source_config.get(
            "raw_dir", PROJECT_ROOT / "data" / "raw" / "external_apis"
        )
        self.session = requests.Session()

    def _build_request(self, **kwargs):
        raise NotImplementedError

    def _raw_filename(self, **kwargs) -> str:
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        return f"{self.source_registry_name}_{ts}.json"

    def fetch(self, save_raw: bool = True, **kwargs):
        """
        Executes the API call with retry-on-failure, returns
        (parsed_json_or_None, IngestionResult). Never raises - failures are
        captured in the result so a batch of many location/date calls can
        continue past one bad request.
        """
        started_at = get_utc_timestamp()
        start_perf = time.monotonic()
        url, params = self._build_request(**kwargs)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout_seconds)
                response.raise_for_status()
                data = response.json()

                finished_at = get_utc_timestamp()
                duration = time.monotonic() - start_perf

                raw_path = None
                if save_raw:
                    raw_path = self.raw_dir / self._raw_filename(**kwargs)
                    write_json(data, raw_path)

                result = IngestionResult(
                    source_name=self.source_registry_name,
                    file_path=str(raw_path) if raw_path else None,
                    row_count=self._estimate_row_count(data),
                    column_count=0,
                    columns=[],
                    checksum=None,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_seconds=round(duration, 3),
                    status="success",
                    extra={"url": url, "params": params, "attempt": attempt},
                )
                logger.info(
                    f"[{self.source_registry_name}] Fetched OK "
                    f"(attempt {attempt}/{self.max_retries}, {duration:.2f}s): {params}"
                )
                return data, result

            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(
                    f"[{self.source_registry_name}] Attempt {attempt}/{self.max_retries} "
                    f"failed for params={params}: {e}"
                )
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)  # linear backoff

        finished_at = get_utc_timestamp()
        duration = time.monotonic() - start_perf
        result = IngestionResult(
            source_name=self.source_registry_name,
            file_path=None,
            row_count=0,
            column_count=0,
            columns=[],
            checksum=None,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            status="failed",
            error_message=str(last_error),
            extra={"url": url, "params": params},
        )
        logger.error(
            f"[{self.source_registry_name}] All {self.max_retries} attempts failed "
            f"for params={params}: {last_error}"
        )
        return None, result

    @staticmethod
    def _estimate_row_count(data) -> int:
        """Best-effort row count for logging - APIs return varied JSON shapes."""
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            for key in ("daily", "hourly"):
                if key in data and isinstance(data[key], dict):
                    first_series = next(iter(data[key].values()), [])
                    if isinstance(first_series, list):
                        return len(first_series)
            if "rates" in data and isinstance(data["rates"], dict):
                return len(data["rates"])  # flat currency -> rate mapping
            return 1
        return 0


class WeatherAPIClient(BaseAPIClient):
    """Open-Meteo historical weather client - no API key required."""

    source_registry_name = "weather_api"

    def _build_request(self, latitude: float, longitude: float,
                        start_date: str, end_date: str, **kwargs):
        # Open-Meteo's historical archive lives under /v1/archive, while the
        # base_url in config points at /v1 - this composes the two.
        url = f"{self.base_url}/archive"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
        }
        return url, params

    def _raw_filename(self, latitude: float, longitude: float, start_date: str, **kwargs) -> str:
        return f"weather_{latitude:.2f}_{longitude:.2f}_{start_date}.json"


class HolidayAPIClient(BaseAPIClient):
    """Nager.Date public holiday client - no API key required."""

    source_registry_name = "holiday_api"

    def _build_request(self, country_code: str, year: int, **kwargs):
        url = f"{self.base_url}/PublicHolidays/{year}/{country_code.upper()}"
        return url, {}

    def _raw_filename(self, country_code: str, year: int, **kwargs) -> str:
        return f"holidays_{country_code.upper()}_{year}.json"


class ExchangeRateAPIClient(BaseAPIClient):
    """Exchange Rate API client - free tier, no key required for /latest."""

    source_registry_name = "exchange_rate_api"

    def _build_request(self, base_currency: str = "USD", **kwargs):
        url = f"{self.base_url}/latest/{base_currency.upper()}"
        return url, {}

    def _raw_filename(self, base_currency: str = "USD", **kwargs) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        return f"exchange_rates_{base_currency.upper()}_{date_str}.json"


if __name__ == "__main__":
    # NOTE: this performs a REAL network call and requires internet access.
    # Safe to skip if you're offline - the automated test suite uses mocks
    # and doesn't need network access.
    print("Fetching sample public holidays for the US in 2024 (live network call)...")
    client = HolidayAPIClient()
    data, result = client.fetch(country_code="US", year=2024)
    print(result.to_dict())
    if data:
        print(f"First holiday: {data[0]}")
