"""
location_resolver.py
=====================
Derives the reference points the external APIs need (country codes for the
Holiday API, lat/lon for the Weather API) directly from ingested order data,
instead of a hardcoded country list.

The DataCo Supply Chain dataset already includes `Latitude`/`Longitude` per
order plus `Order Country` (and `Order City`) - this module extracts the
distinct combinations so we only call each external API once per unique
location, not once per order row.

Country-name -> ISO 3166-1 alpha-2 code resolution prefers `pycountry` (exact,
exhaustive) when installed, and falls back to a bundled static table (covers
the countries realistically present in a global e-commerce dataset) so this
still works in environments where installing every optional package isn't
possible.

Usage:
    from src.ingestion.location_resolver import extract_order_locations

    locations_df = extract_order_locations(orders_df)
    # columns: order_country, order_city, latitude, longitude, country_code, order_count
"""

from typing import Optional

import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)

try:
    import pycountry
    _HAS_PYCOUNTRY = True
except ImportError:
    _HAS_PYCOUNTRY = False


# Fallback table used when pycountry isn't installed. Covers the countries
# realistically present in a global e-commerce/logistics dataset. Extend as
# needed if a real dataset run logs an "unresolved country" warning.
_FALLBACK_COUNTRY_TO_ISO2 = {
    "united states": "US", "usa": "US", "estados unidos": "US",
    "brazil": "BR", "brasil": "BR",
    "germany": "DE", "alemania": "DE",
    "france": "FR", "francia": "FR",
    "united kingdom": "GB", "reino unido": "GB",
    "canada": "CA",
    "mexico": "MX", "méxico": "MX",
    "spain": "ES", "españa": "ES",
    "italy": "IT", "italia": "IT",
    "australia": "AU",
    "china": "CN",
    "japan": "JP",
    "india": "IN",
    "south korea": "KR", "korea": "KR",
    "netherlands": "NL", "holanda": "NL",
    "belgium": "BE",
    "switzerland": "CH",
    "sweden": "SE",
    "norway": "NO",
    "denmark": "DK",
    "finland": "FI",
    "poland": "PL",
    "austria": "AT",
    "portugal": "PT",
    "ireland": "IE",
    "greece": "GR",
    "turkey": "TR",
    "russia": "RU",
    "argentina": "AR",
    "chile": "CL",
    "colombia": "CO",
    "peru": "PE",
    "venezuela": "VE",
    "ecuador": "EC",
    "uruguay": "UY",
    "paraguay": "PY",
    "bolivia": "BO",
    "guatemala": "GT",
    "honduras": "HN",
    "el salvador": "SV",
    "nicaragua": "NI",
    "costa rica": "CR",
    "panama": "PA",
    "dominican republic": "DO", "republica dominicana": "DO",
    "cuba": "CU",
    "puerto rico": "PR",
    "south africa": "ZA",
    "egypt": "EG",
    "nigeria": "NG",
    "kenya": "KE",
    "morocco": "MA",
    "algeria": "DZ",
    "tunisia": "TN",
    "saudi arabia": "SA",
    "united arab emirates": "AE",
    "israel": "IL",
    "singapore": "SG",
    "malaysia": "MY",
    "indonesia": "ID",
    "philippines": "PH",
    "thailand": "TH",
    "vietnam": "VN",
    "new zealand": "NZ",
    "pakistan": "PK",
    "bangladesh": "BD",
    "sri lanka": "LK",
    "romania": "RO",
    "hungary": "HU",
    "czech republic": "CZ", "czechia": "CZ",
    "slovakia": "SK",
    "bulgaria": "BG",
    "croatia": "HR",
    "serbia": "RS",
    "ukraine": "UA",
}


def resolve_country_code(country_name: Optional[str]) -> Optional[str]:
    """
    Resolves a free-text country name (as it appears in order data) to an
    ISO 3166-1 alpha-2 code (e.g. "United States" -> "US"), needed by the
    Holiday API. Returns None if it can't be resolved - callers should log
    and skip rather than guess.
    """
    if not country_name or not isinstance(country_name, str):
        return None

    name = country_name.strip()
    if not name:
        return None

    if _HAS_PYCOUNTRY:
        try:
            match = pycountry.countries.search_fuzzy(name)
            if match:
                return match[0].alpha_2
        except LookupError:
            pass  # fall through to fallback table

    return _FALLBACK_COUNTRY_TO_ISO2.get(name.lower())


def extract_order_locations(
    df: pd.DataFrame,
    country_col: str = "Order Country",
    city_col: str = "Order City",
    lat_col: str = "Latitude",
    lon_col: str = "Longitude",
) -> pd.DataFrame:
    """
    Extracts distinct (country, city, lat, lon) combinations from an orders
    DataFrame, so external APIs are called once per unique location rather
    than once per order row.

    For each unique (country, city) pair, latitude/longitude is taken as the
    mean of all matching rows. Returns a DataFrame with columns:
        order_country, order_city, latitude, longitude, country_code, order_count
    Rows where the country can't be resolved to an ISO code are still
    included (country_code = None) but logged as a warning.
    """
    missing_cols = [c for c in [country_col, city_col] if c not in df.columns]
    if missing_cols:
        raise KeyError(
            f"extract_order_locations: expected column(s) {missing_cols} not found. "
            f"Available columns: {list(df.columns)}"
        )

    has_coords = lat_col in df.columns and lon_col in df.columns
    group_cols = [country_col, city_col]

    order_counts = df.groupby(group_cols, dropna=False).size().rename("order_count")

    if has_coords:
        coords = df.groupby(group_cols, dropna=False)[[lat_col, lon_col]].mean()
        grouped = coords.join(order_counts).reset_index()
    else:
        grouped = order_counts.reset_index()
        grouped[lat_col] = None
        grouped[lon_col] = None
        logger.warning(
            f"Columns '{lat_col}'/'{lon_col}' not found - latitude/longitude "
            f"will be null. Weather API calls will need a separate geocoding step."
        )

    grouped = grouped.rename(columns={
        country_col: "order_country",
        city_col: "order_city",
        lat_col: "latitude",
        lon_col: "longitude",
    })

    grouped["country_code"] = grouped["order_country"].apply(resolve_country_code)

    unresolved = grouped[grouped["country_code"].isna()]["order_country"].unique()
    if len(unresolved) > 0:
        logger.warning(
            f"Could not resolve ISO country code for: {list(unresolved)}. "
            f"Holiday API calls will be skipped for these; add them to "
            f"_FALLBACK_COUNTRY_TO_ISO2 in location_resolver.py if needed."
        )

    logger.info(
        f"Extracted {len(grouped)} unique locations from {len(df):,} order rows "
        f"({grouped['country_code'].notna().sum()} with resolved country codes)"
    )

    return grouped.sort_values("order_count", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    # Quick manual sanity check with synthetic order-like data
    sample = pd.DataFrame({
        "Order Country": ["United States", "Brazil", "United States", "Germany", "Nowhereland"],
        "Order City": ["Los Angeles", "Sao Paulo", "Los Angeles", "Berlin", "Atlantis"],
        "Latitude": [34.05, -23.55, 34.06, 52.52, 0.0],
        "Longitude": [-118.24, -46.63, -118.25, 13.40, 0.0],
    })
    result = extract_order_locations(sample)
    print(result)
