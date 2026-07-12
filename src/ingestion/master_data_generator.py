"""
master_data_generator.py
=========================
Generates the synthetic master data entities that have no public dataset
equivalent: Warehouses, Suppliers, Courier Partners, Vehicles, and Delivery
Routes. These feed DimWarehouse, DimSupplier, and DimCourier in Phase 5.

Design goals:
  - Deterministic: same seed -> same output, every time (reproducible builds,
    diffable CSVs in git history if you ever choose to commit a snapshot).
  - Referentially consistent: every vehicle's courier_id and every route's
    origin_warehouse_id/courier_id points at a row that actually exists in
    the corresponding table - this mirrors a real master-data system and
    gives Phase 2 (validation) and Phase 5 (warehouse FK loading) something
    real to check.
  - Works with or without Faker: uses the `faker` package for richer
    name/address variety if installed, otherwise falls back to a curated
    static name pool so this still runs in minimal environments.

Usage:
    python -m src.ingestion.master_data_generator
    # or with custom counts/seed:
    python -m src.ingestion.master_data_generator --seed 99 --warehouses 20
"""

import argparse
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from src.ingestion.source_registry import get_source
from src.utils.helpers import ensure_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from faker import Faker
    _HAS_FAKER = True
except ImportError:
    _HAS_FAKER = False


# ---------------------------------------------------------------------------
# Fallback name pools (used when Faker isn't installed)
# ---------------------------------------------------------------------------

_CITIES = [
    # (city, country, latitude, longitude) - approximate city-center coordinates
    ("Los Angeles", "United States", 34.0522, -118.2437),
    ("Chicago", "United States", 41.8781, -87.6298),
    ("Dallas", "United States", 32.7767, -96.7970),
    ("Sao Paulo", "Brazil", -23.5505, -46.6333),
    ("Rio de Janeiro", "Brazil", -22.9068, -43.1729),
    ("Berlin", "Germany", 52.5200, 13.4050),
    ("Hamburg", "Germany", 53.5511, 9.9937),
    ("Paris", "France", 48.8566, 2.3522),
    ("Lyon", "France", 45.7640, 4.8357),
    ("London", "United Kingdom", 51.5074, -0.1278),
    ("Manchester", "United Kingdom", 53.4808, -2.2426),
    ("Toronto", "Canada", 43.6532, -79.3832),
    ("Vancouver", "Canada", 49.2827, -123.1207),
    ("Mexico City", "Mexico", 19.4326, -99.1332),
    ("Guadalajara", "Mexico", 20.6597, -103.3496),
    ("Madrid", "Spain", 40.4168, -3.7038),
    ("Barcelona", "Spain", 41.3851, 2.1734),
    ("Milan", "Italy", 45.4642, 9.1900),
    ("Rome", "Italy", 41.9028, 12.4964),
    ("Sydney", "Australia", -33.8688, 151.2093),
    ("Melbourne", "Australia", -37.8136, 144.9631),
    ("Shanghai", "China", 31.2304, 121.4737),
    ("Shenzhen", "China", 22.5431, 114.0579),
    ("Tokyo", "Japan", 35.6762, 139.6503),
    ("Osaka", "Japan", 34.6937, 135.5023),
    ("Mumbai", "India", 19.0760, 72.8777),
    ("Delhi", "India", 28.7041, 77.1025),
    ("Singapore", "Singapore", 1.3521, 103.8198),
    ("Amsterdam", "Netherlands", 52.3676, 4.9041),
    ("Warsaw", "Poland", 52.2297, 21.0122),
]

_FIRST_NAMES = ["James", "Maria", "Wei", "Priya", "Ahmed", "Sofia", "Liam", "Yuki",
                "Carlos", "Anna", "Chen", "Fatima", "Lucas", "Elena", "Raj", "Nina"]
_LAST_NAMES = ["Smith", "Silva", "Zhang", "Sharma", "Khan", "Rossi", "Muller", "Tanaka",
               "Garcia", "Kowalski", "Wang", "Ahmed", "Costa", "Novak", "Patel", "Ivanov"]

_SUPPLIER_NAME_PREFIXES = ["Global", "Prime", "Apex", "Summit", "Nova", "Meridian", "Union",
                            "Vertex", "Pioneer", "Crestline", "Northgate", "Bluewave"]
_SUPPLIER_NAME_SUFFIXES = ["Trading Co.", "Industries", "Supply Chain", "Distributors",
                            "Manufacturing", "Exports", "Logistics Group", "Wholesale Ltd."]

_COURIER_NAME_PREFIXES = ["Rapid", "SwiftShip", "FreightLine", "TransGlobal", "QuickHaul",
                           "MetroExpress", "SkyCargo", "CoastalFreight"]

_PRODUCT_CATEGORIES = [
    "Electronics", "Home and Kitchen", "Fashion", "Toys and Games", "Sports and Fitness",
    "Books", "Grocery", "Beauty and Personal Care", "Automotive", "Furniture",
]

_VEHICLE_TYPES = ["Van", "Truck", "Cargo Bike", "Cargo Plane", "Container Ship"]
_FUEL_TYPES = ["Diesel", "Electric", "Petrol", "Hybrid"]
_SERVICE_TYPES = ["Express", "Standard", "Economy", "Freight"]
_REGIONS = ["North America", "South America", "Europe", "East Asia", "South Asia",
            "Southeast Asia", "Oceania", "Middle East and Africa"]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def _random_date(rng: random.Random, start_year: int = 2015, end_year: int = 2024) -> date:
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    delta_days = (end - start).days
    return start + timedelta(days=rng.randint(0, delta_days))


def _make_email(name: str, domain: str) -> str:
    return f"{name.lower().replace(' ', '.')}@{domain}"


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def generate_warehouses(n: int, seed: int) -> pd.DataFrame:
    rng = _rng(seed)
    faker = Faker() if _HAS_FAKER else None
    if faker:
        faker.seed_instance(seed)

    rows = []
    cities_sample = rng.sample(_CITIES, min(n, len(_CITIES))) if n <= len(_CITIES) else \
        [rng.choice(_CITIES) for _ in range(n)]

    for i, (city, country, base_lat, base_lon) in enumerate(cities_sample, start=1):
        manager = faker.name() if faker else f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"
        # Small jitter (~a few km) so a warehouse isn't dead-center on the
        # city's exact coordinate, while staying geographically accurate.
        rows.append({
            "id": f"WH-{i:04d}",
            "warehouse_name": f"{city} Fulfillment Center",
            "country": country,
            "city": city,
            "latitude": round(base_lat + rng.uniform(-0.05, 0.05), 4),
            "longitude": round(base_lon + rng.uniform(-0.05, 0.05), 4),
            "warehouse_type": rng.choice(["Fulfillment Center", "Distribution Center", "Cross-Dock Facility"]),
            "capacity_sqft": rng.randint(50_000, 500_000),
            "operational_since": _random_date(rng, 2010, 2022).isoformat(),
            "manager_name": manager,
            "contact_email": _make_email(manager, "supplychain360.com"),
            "timezone": rng.choice(["UTC-8", "UTC-5", "UTC", "UTC+1", "UTC+8", "UTC+9", "UTC+5:30"]),
        })
    return pd.DataFrame(rows)


def generate_suppliers(n: int, seed: int) -> pd.DataFrame:
    rng = _rng(seed)
    faker = Faker() if _HAS_FAKER else None
    if faker:
        faker.seed_instance(seed + 1)

    rows = []
    for i in range(1, n + 1):
        city, country, _lat, _lon = rng.choice(_CITIES)
        name = (
            faker.company() if faker
            else f"{rng.choice(_SUPPLIER_NAME_PREFIXES)} {rng.choice(_SUPPLIER_NAME_SUFFIXES)}"
        )
        rows.append({
            "id": f"SUP-{i:04d}",
            "supplier_name": name,
            "country": country,
            "city": city,
            "contact_email": _make_email(name.split()[0], "suppliermail.com"),
            "phone": f"+{rng.randint(1, 99)}-{rng.randint(100,999)}-{rng.randint(1000000,9999999)}",
            "product_category": rng.choice(_PRODUCT_CATEGORIES),
            "reliability_score": rng.randint(60, 100),
            "avg_lead_time_days": rng.randint(2, 45),
            "contract_start_date": _random_date(rng, 2016, 2023).isoformat(),
            "active_flag": rng.random() > 0.08,  # ~92% active
        })
    return pd.DataFrame(rows)


def generate_courier_partners(n: int, seed: int) -> pd.DataFrame:
    rng = _rng(seed)
    rows = []
    for i in range(1, n + 1):
        name = f"{rng.choice(_COURIER_NAME_PREFIXES)} Logistics"
        coverage = rng.sample(_REGIONS, k=rng.randint(1, 4))
        rows.append({
            "id": f"CUR-{i:04d}",
            "courier_name": name,
            "service_type": rng.choice(_SERVICE_TYPES),
            "coverage_regions": ";".join(coverage),
            "contact_email": _make_email(name.split()[0], "couriernet.com"),
            "avg_delivery_days": round(rng.uniform(1.0, 10.0), 1),
            "cost_per_kg_usd": round(rng.uniform(0.5, 8.0), 2),
            "active_flag": rng.random() > 0.05,  # ~95% active
        })
    return pd.DataFrame(rows)


def generate_vehicles(n: int, courier_ids: list, seed: int) -> pd.DataFrame:
    """Every vehicle's courier_id is guaranteed to reference an existing courier."""
    rng = _rng(seed)
    rows = []
    for i in range(1, n + 1):
        vehicle_type = rng.choice(_VEHICLE_TYPES)
        capacity_kg = {
            "Van": rng.randint(500, 2000),
            "Truck": rng.randint(5000, 25000),
            "Cargo Bike": rng.randint(20, 100),
            "Cargo Plane": rng.randint(20000, 120000),
            "Container Ship": rng.randint(200000, 2000000),
        }[vehicle_type]
        rows.append({
            "id": f"VEH-{i:04d}",
            "courier_id": rng.choice(courier_ids),
            "vehicle_type": vehicle_type,
            "capacity_kg": capacity_kg,
            "registration_number": f"{rng.choice('ABCDEFGH')}{rng.randint(100,999)}-{rng.randint(10,99)}",
            "fuel_type": rng.choice(_FUEL_TYPES),
            "status": rng.choices(["Active", "Maintenance", "Retired"], weights=[85, 10, 5])[0],
            "last_service_date": _random_date(rng, 2023, 2024).isoformat(),
        })
    return pd.DataFrame(rows)


def generate_delivery_routes(n: int, warehouse_ids: list, courier_ids: list, seed: int) -> pd.DataFrame:
    """
    Every route's origin_warehouse_id and courier_id are guaranteed to
    reference existing rows in warehouses.csv / courier_partners.csv.
    """
    rng = _rng(seed)
    rows = []
    for i in range(1, n + 1):
        distance_km = rng.randint(20, 12000)
        rows.append({
            "id": f"RT-{i:04d}",
            "origin_warehouse_id": rng.choice(warehouse_ids),
            "destination_region": rng.choice(_REGIONS),
            "courier_id": rng.choice(courier_ids),
            "distance_km": distance_km,
            "estimated_delivery_days": max(1, round(distance_km / 800) + rng.randint(0, 2)),
            "route_status": rng.choices(["Active", "Inactive"], weights=[90, 10])[0],
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def generate_all_master_data(
    seed: int = 42,
    n_warehouses: int = 15,
    n_suppliers: int = 30,
    n_couriers: int = 8,
    n_vehicles: int = 40,
    n_routes: int = 35,
    output_dir: Optional[Path] = None,
) -> dict:
    """
    Generates all five master data tables with guaranteed referential
    integrity between them, and writes each to CSV.

    Returns a dict of {table_name: DataFrame} for callers that want to
    inspect the data without re-reading it from disk (e.g., tests).
    """
    if output_dir is None:
        output_dir = get_source("generated_master_data")["raw_dir"]
    output_dir = ensure_dir(output_dir)

    warehouses = generate_warehouses(n_warehouses, seed)
    suppliers = generate_suppliers(n_suppliers, seed)
    couriers = generate_courier_partners(n_couriers, seed)
    vehicles = generate_vehicles(n_vehicles, courier_ids=list(couriers["id"]), seed=seed)
    routes = generate_delivery_routes(
        n_routes,
        warehouse_ids=list(warehouses["id"]),
        courier_ids=list(couriers["id"]),
        seed=seed,
    )

    tables = {
        "warehouses": warehouses,
        "suppliers": suppliers,
        "courier_partners": couriers,
        "vehicles": vehicles,
        "delivery_routes": routes,
    }

    for name, df in tables.items():
        out_path = output_dir / f"{name}.csv"
        df.to_csv(out_path, index=False)
        logger.info(f"Generated {len(df):,} rows -> {out_path}")

    logger.info(
        f"Master data generation complete (seed={seed}, faker={'on' if _HAS_FAKER else 'off (fallback names)'})"
    )
    return tables


def _parse_args():
    parser = argparse.ArgumentParser(description="Generate synthetic master data for SupplyChain360")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--warehouses", type=int, default=15)
    parser.add_argument("--suppliers", type=int, default=30)
    parser.add_argument("--couriers", type=int, default=8)
    parser.add_argument("--vehicles", type=int, default=40)
    parser.add_argument("--routes", type=int, default=35)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    generate_all_master_data(
        seed=args.seed,
        n_warehouses=args.warehouses,
        n_suppliers=args.suppliers,
        n_couriers=args.couriers,
        n_vehicles=args.vehicles,
        n_routes=args.routes,
    )
