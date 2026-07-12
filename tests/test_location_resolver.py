"""
test_location_resolver.py
==========================
Tests for src/ingestion/location_resolver.py.

Run with:
    pytest tests/test_location_resolver.py -v
"""

import pandas as pd
import pytest

from src.ingestion.location_resolver import extract_order_locations, resolve_country_code


def test_resolve_country_code_known_countries():
    assert resolve_country_code("United States") == "US"
    assert resolve_country_code("Brazil") == "BR"
    assert resolve_country_code("Germany") == "DE"


def test_resolve_country_code_unknown_returns_none():
    assert resolve_country_code("Nowhereland") is None


def test_resolve_country_code_handles_none_and_empty():
    assert resolve_country_code(None) is None
    assert resolve_country_code("") is None
    assert resolve_country_code("   ") is None


def test_extract_order_locations_deduplicates_and_averages_coords():
    df = pd.DataFrame({
        "Order Country": ["United States", "United States", "Brazil"],
        "Order City": ["Los Angeles", "Los Angeles", "Sao Paulo"],
        "Latitude": [34.05, 34.07, -23.55],
        "Longitude": [-118.24, -118.26, -46.63],
    })
    result = extract_order_locations(df)

    assert len(result) == 2  # 2 unique (country, city) pairs, not 3 rows
    la_row = result[result["order_city"] == "Los Angeles"].iloc[0]
    assert la_row["order_count"] == 2
    assert round(la_row["latitude"], 2) == 34.06  # mean of 34.05 and 34.07
    assert la_row["country_code"] == "US"


def test_extract_order_locations_sorted_by_order_count_desc():
    df = pd.DataFrame({
        "Order Country": ["Brazil", "United States", "United States", "United States"],
        "Order City": ["Sao Paulo", "LA", "LA", "LA"],
        "Latitude": [-23.55, 34.05, 34.05, 34.05],
        "Longitude": [-46.63, -118.24, -118.24, -118.24],
    })
    result = extract_order_locations(df)
    assert result.iloc[0]["order_city"] == "LA"  # 3 orders, should be first
    assert result.iloc[0]["order_count"] == 3


def test_extract_order_locations_flags_unresolved_country():
    df = pd.DataFrame({
        "Order Country": ["Nowhereland"],
        "Order City": ["Atlantis"],
        "Latitude": [0.0],
        "Longitude": [0.0],
    })
    result = extract_order_locations(df)
    assert result.iloc[0]["country_code"] is None


def test_extract_order_locations_missing_required_column_raises():
    df = pd.DataFrame({"City": ["LA"]})  # missing both country and city columns
    with pytest.raises(KeyError):
        extract_order_locations(df, country_col="Order Country", city_col="Order City")


def test_extract_order_locations_missing_coords_columns_returns_null_coords():
    df = pd.DataFrame({
        "Order Country": ["United States"],
        "Order City": ["Los Angeles"],
        # no Latitude/Longitude columns at all
    })
    result = extract_order_locations(df)
    assert result.iloc[0]["latitude"] is None
    assert result.iloc[0]["longitude"] is None
