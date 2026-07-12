"""
orchestrator.py
================
Ties together every ingestion reader built in Phases 1.2-1.5 into one
runnable pipeline, and produces a JSON manifest of what happened - the
"Raw Layer" record of each ingestion run that Phase 2 (validation) and
later phases can reference.

Two entry points:
  - run_csv_ingestion()   -> reads every registered CSV source (auto-generating
                              synthetic master data first if it's missing)
  - run_api_enrichment()  -> derives locations from a given orders DataFrame
                              and fetches Weather/Holiday/Exchange-Rate data
                              for the highest-volume locations (opt-in, since
                              it needs both real order data and network access)

Usage:
    python -m src.ingestion.orchestrator                  # CSV sources only
    python -m src.ingestion.orchestrator --with-api-sample # + a small live API sample
"""

import argparse
from pathlib import Path
from typing import Optional

import pandas as pd

from src.ingestion.api_client import ExchangeRateAPIClient, HolidayAPIClient, WeatherAPIClient
from src.ingestion.csv_reader import CSVIngestionReader
from src.ingestion.location_resolver import extract_order_locations
from src.ingestion.master_data_generator import generate_all_master_data
from src.ingestion.source_registry import get_source, list_sources, resolve_source_files
from src.utils.config import PROJECT_ROOT
from src.utils.helpers import ensure_dir, get_run_id, get_utc_timestamp, write_json
from src.utils.logger import get_logger

logger = get_logger(__name__)

MANIFEST_DIR = PROJECT_ROOT / "logs" / "ingestion_manifests"


def _ensure_master_data_exists(output_dir: Path, **generator_kwargs) -> bool:
    """
    Generates synthetic master data into `output_dir` only if it doesn't
    already contain CSVs. Returns True if generation ran, False if files
    already existed (i.e., generation was skipped).

    Factored out from run_csv_ingestion so it's independently testable
    against a throwaway tmp_path, without touching the real project data.
    """
    output_dir = Path(output_dir)
    existing = list(output_dir.glob("*.csv")) if output_dir.exists() else []
    if existing:
        logger.info(f"Master data already exists ({len(existing)} files) - skipping generation")
        return False

    logger.info(f"No master data found in {output_dir} - generating now")
    generate_all_master_data(output_dir=output_dir, **generator_kwargs)
    return True


def run_csv_ingestion(
    source_names: Optional[list] = None,
    auto_generate_missing_master_data: bool = True,
) -> list:
    """
    Reads every registered CSV-format data source and returns a list of
    IngestionResult objects (one per file actually found on disk).

    Sources with no files present (e.g., Kaggle datasets not yet downloaded)
    are logged and skipped, not treated as fatal - this lets you run the
    orchestrator productively even before every dataset is in place.
    """
    if source_names is None:
        source_names = list_sources()

    all_results = []

    for name in source_names:
        config = get_source(name)
        if config.get("format") != "csv":
            continue  # API sources handled separately by run_api_enrichment

        if name == "generated_master_data" and auto_generate_missing_master_data:
            _ensure_master_data_exists(config["raw_dir"])

        files = resolve_source_files(name)
        if not files:
            logger.warning(
                f"[{name}] No files found in {config['raw_dir']} - skipping. "
                f"See docs/PHASE1_DATASET_ACQUISITION_GUIDE.md if this is a Kaggle source."
            )
            continue

        reader = CSVIngestionReader(name)
        for file_path in files:
            if file_path.name.lower().startswith("description"):
                continue  # data dictionaries, not data - e.g. DescriptionDataCoSupplyChain.csv
            _df, result = reader.read(file_path)
            all_results.append(result)

    return all_results


def run_api_enrichment(
    orders_df: pd.DataFrame,
    top_n_locations: int = 5,
    holiday_year: int = 2018,
    weather_start_date: str = "2018-01-01",
    weather_end_date: str = "2018-01-07",
) -> list:
    """
    Derives the highest-volume order locations from `orders_df` and fetches
    live Weather + Holiday data for them, plus one Exchange Rate snapshot.
    Requires internet access - each call degrades to a "failed" result
    (not an exception) if the network is unavailable, per api_client.py's
    retry/failure design.
    """
    results = []

    locations = extract_order_locations(orders_df)
    top_locations = locations.head(top_n_locations)

    weather_client = WeatherAPIClient()
    holiday_client = HolidayAPIClient()
    fx_client = ExchangeRateAPIClient()

    for _, loc in top_locations.iterrows():
        if pd.notna(loc["latitude"]) and pd.notna(loc["longitude"]):
            _data, result = weather_client.fetch(
                latitude=loc["latitude"], longitude=loc["longitude"],
                start_date=weather_start_date, end_date=weather_end_date,
            )
            results.append(result)

        if loc["country_code"]:
            _data, result = holiday_client.fetch(country_code=loc["country_code"], year=holiday_year)
            results.append(result)
        else:
            logger.warning(f"Skipping holiday lookup for unresolved country: {loc['order_country']}")

    _data, fx_result = fx_client.fetch(base_currency="USD")
    results.append(fx_result)

    return results


def write_manifest(results: list, run_id: Optional[str] = None) -> Path:
    """
    Aggregates a list of IngestionResult objects into a single JSON manifest
    file - the audit trail of what was ingested, when, and whether it
    succeeded. Written to logs/ingestion_manifests/<run_id>.json.
    """
    run_id = run_id or get_run_id("ingestion")
    ensure_dir(MANIFEST_DIR)

    result_dicts = [r.to_dict() for r in results]
    summary = {
        "run_id": run_id,
        "generated_at": get_utc_timestamp(),
        "total_sources_attempted": len(result_dicts),
        "succeeded": sum(1 for r in result_dicts if r["status"] == "success"),
        "failed": sum(1 for r in result_dicts if r["status"] == "failed"),
        "skipped": sum(1 for r in result_dicts if r["status"] == "skipped"),
        "total_rows_ingested": sum(r["row_count"] for r in result_dicts if r["status"] == "success"),
        "results": result_dicts,
    }

    manifest_path = MANIFEST_DIR / f"{run_id}.json"
    write_json(summary, manifest_path)
    logger.info(
        f"Manifest written to {manifest_path} "
        f"({summary['succeeded']} succeeded, {summary['failed']} failed, "
        f"{summary['skipped']} skipped, {summary['total_rows_ingested']:,} total rows)"
    )
    return manifest_path


def run_full_ingestion(with_api_sample: bool = False) -> Path:
    """
    Main orchestrator entry point: runs CSV ingestion for every registered
    source, optionally samples the external APIs against the DataCo order
    data if it's present, and writes one combined manifest.
    """
    run_id = get_run_id("ingestion")
    logger.info(f"=== Starting ingestion run {run_id} ===")

    results = run_csv_ingestion()

    if with_api_sample:
        dataco_files = resolve_source_files("dataco_supply_chain")
        main_file = next((f for f in dataco_files if not f.name.lower().startswith("description")), None)
        if main_file:
            reader = CSVIngestionReader("dataco_supply_chain")
            orders_df, _ = reader.read(main_file)
            if orders_df is not None:
                logger.info("Running a live external API sample against DataCo order locations...")
                results.extend(run_api_enrichment(orders_df))
        else:
            logger.warning("--with-api-sample requested but DataCo order data not found - skipping")

    manifest_path = write_manifest(results, run_id=run_id)
    logger.info(f"=== Ingestion run {run_id} complete ===")
    return manifest_path


def _parse_args():
    parser = argparse.ArgumentParser(description="Run the SupplyChain360 ingestion pipeline")
    parser.add_argument(
        "--with-api-sample", action="store_true",
        help="Also fetch a small live sample from Weather/Holiday/Exchange-Rate APIs "
             "(requires internet access and DataCoSupplyChainDataset.csv to be present)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_full_ingestion(with_api_sample=args.with_api_sample)
