"""
test_api_client.py
===================
Tests for src/ingestion/api_client.py.

All HTTP calls are mocked via unittest.mock - these tests run fully offline
and never hit the real Weather/Holiday/Exchange-Rate APIs. Live network
verification is a separate manual step (see the Phase 1.4 implementation
guide).

Run with:
    pytest tests/test_api_client.py -v
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.ingestion.api_client import ExchangeRateAPIClient, HolidayAPIClient, WeatherAPIClient


def _mock_response(json_data):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


def test_weather_api_success_and_row_count():
    mock_resp = _mock_response({
        "daily": {"time": ["2018-01-01", "2018-01-02"], "temperature_2m_max": [15.2, 16.1]}
    })
    with patch("requests.Session.get", return_value=mock_resp) as mock_get:
        client = WeatherAPIClient()
        data, result = client.fetch(
            latitude=34.05, longitude=-118.24,
            start_date="2018-01-01", end_date="2018-01-02", save_raw=False,
        )
        assert result.status == "success"
        assert result.row_count == 2
        assert mock_get.call_count == 1
        assert "archive" in mock_get.call_args[0][0]


def test_holiday_api_success_list_shaped_json():
    mock_resp = _mock_response([{"date": "2018-01-01", "localName": "New Year"}])
    with patch("requests.Session.get", return_value=mock_resp):
        client = HolidayAPIClient()
        data, result = client.fetch(country_code="us", year=2018, save_raw=False)
        assert result.status == "success"
        assert result.row_count == 1
        assert data[0]["localName"] == "New Year"


def test_holiday_api_uppercases_country_code_in_url():
    mock_resp = _mock_response([])
    with patch("requests.Session.get", return_value=mock_resp) as mock_get:
        client = HolidayAPIClient()
        client.fetch(country_code="us", year=2018, save_raw=False)
        called_url = mock_get.call_args[0][0]
        assert "/US" in called_url


def test_exchange_rate_api_success_flat_rates_dict():
    mock_resp = _mock_response({"base": "USD", "rates": {"EUR": 0.91, "BRL": 5.4}})
    with patch("requests.Session.get", return_value=mock_resp):
        client = ExchangeRateAPIClient()
        data, result = client.fetch(base_currency="usd", save_raw=False)
        assert result.status == "success"
        assert result.row_count == 2


def test_retry_then_succeed():
    call_count = {"n": 0}

    def flaky_get(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise requests.exceptions.ConnectionError("simulated network blip")
        return _mock_response([{"date": "2019-01-01", "localName": "New Year"}])

    with patch("requests.Session.get", side_effect=flaky_get):
        client = HolidayAPIClient()
        client.backoff_seconds = 0.01
        data, result = client.fetch(country_code="US", year=2019, save_raw=False)
        assert result.status == "success"
        assert result.extra["attempt"] == 2


def test_all_retries_exhausted_returns_failed_result_without_raising():
    with patch("requests.Session.get", side_effect=requests.exceptions.Timeout("always times out")):
        client = HolidayAPIClient()
        client.max_retries = 2
        client.backoff_seconds = 0.01
        data, result = client.fetch(country_code="US", year=2020, save_raw=False)
        assert data is None
        assert result.status == "failed"
        assert "always times out" in result.error_message


def test_http_error_status_triggers_failed_result():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error")
    with patch("requests.Session.get", return_value=mock_resp):
        client = HolidayAPIClient()
        client.max_retries = 1
        data, result = client.fetch(country_code="ZZ", year=2018, save_raw=False)
        assert data is None
        assert result.status == "failed"


def test_save_raw_writes_json_file(tmp_path):
    mock_resp = _mock_response([{"date": "2018-01-01", "localName": "New Year"}])
    with patch("requests.Session.get", return_value=mock_resp):
        client = HolidayAPIClient()
        client.raw_dir = tmp_path  # redirect output to a throwaway test dir
        data, result = client.fetch(country_code="US", year=2018, save_raw=True)
        assert result.status == "success"
        assert result.file_path is not None
        written_files = list(tmp_path.glob("*.json"))
        assert len(written_files) == 1
        assert "US" in written_files[0].name
