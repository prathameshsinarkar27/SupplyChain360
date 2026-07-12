"""
test_master_data_generator.py
===============================
Tests for src/ingestion/master_data_generator.py.

Run with:
    pytest tests/test_master_data_generator.py -v
"""

import pandas as pd
import pytest

from src.ingestion.master_data_generator import generate_all_master_data


@pytest.fixture(scope="module")
def generated_tables(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("master_data")
    return generate_all_master_data(
        seed=42, n_warehouses=15, n_suppliers=30, n_couriers=8,
        n_vehicles=40, n_routes=35, output_dir=out_dir,
    )


def test_all_five_tables_generated_with_correct_row_counts(generated_tables):
    assert len(generated_tables["warehouses"]) == 15
    assert len(generated_tables["suppliers"]) == 30
    assert len(generated_tables["courier_partners"]) == 8
    assert len(generated_tables["vehicles"]) == 40
    assert len(generated_tables["delivery_routes"]) == 35


def test_all_id_columns_are_unique(generated_tables):
    for name, df in generated_tables.items():
        assert df["id"].is_unique, f"{name} has duplicate IDs"


def test_vehicles_reference_only_real_couriers(generated_tables):
    courier_ids = set(generated_tables["courier_partners"]["id"])
    vehicle_courier_refs = set(generated_tables["vehicles"]["courier_id"])
    assert vehicle_courier_refs.issubset(courier_ids)


def test_routes_reference_only_real_couriers_and_warehouses(generated_tables):
    courier_ids = set(generated_tables["courier_partners"]["id"])
    warehouse_ids = set(generated_tables["warehouses"]["id"])
    routes = generated_tables["delivery_routes"]
    assert set(routes["courier_id"]).issubset(courier_ids)
    assert set(routes["origin_warehouse_id"]).issubset(warehouse_ids)


def test_warehouse_coordinates_are_geographically_plausible(generated_tables):
    # Regression test for a real bug caught during development: coordinates
    # were originally fully random and didn't match the assigned city.
    wh = generated_tables["warehouses"]
    for _, row in wh.iterrows():
        assert -90 <= row["latitude"] <= 90
        assert -180 <= row["longitude"] <= 180
        if row["city"] == "Melbourne":
            assert -39 < row["latitude"] < -36
            assert 143 < row["longitude"] < 146
        if row["city"] == "Los Angeles":
            assert 33 < row["latitude"] < 35
            assert -119 < row["longitude"] < -117


def test_same_seed_produces_identical_output(tmp_path_factory):
    dir1 = tmp_path_factory.mktemp("run1")
    dir2 = tmp_path_factory.mktemp("run2")
    tables1 = generate_all_master_data(seed=7, n_warehouses=5, n_suppliers=5,
                                        n_couriers=3, n_vehicles=5, n_routes=5, output_dir=dir1)
    tables2 = generate_all_master_data(seed=7, n_warehouses=5, n_suppliers=5,
                                        n_couriers=3, n_vehicles=5, n_routes=5, output_dir=dir2)
    pd.testing.assert_frame_equal(tables1["warehouses"], tables2["warehouses"])
    pd.testing.assert_frame_equal(tables1["vehicles"], tables2["vehicles"])


def test_different_seeds_produce_different_output(tmp_path_factory):
    dir1 = tmp_path_factory.mktemp("seedA")
    dir2 = tmp_path_factory.mktemp("seedB")
    tables1 = generate_all_master_data(seed=1, n_warehouses=5, n_suppliers=5,
                                        n_couriers=3, n_vehicles=5, n_routes=5, output_dir=dir1)
    tables2 = generate_all_master_data(seed=2, n_warehouses=5, n_suppliers=5,
                                        n_couriers=3, n_vehicles=5, n_routes=5, output_dir=dir2)
    assert not tables1["warehouses"]["manager_name"].equals(tables2["warehouses"]["manager_name"])


def test_csv_files_written_to_disk(tmp_path):
    generate_all_master_data(seed=1, n_warehouses=3, n_suppliers=3, n_couriers=2,
                              n_vehicles=5, n_routes=5, output_dir=tmp_path)
    expected_files = [
        "warehouses.csv", "suppliers.csv", "courier_partners.csv",
        "vehicles.csv", "delivery_routes.csv",
    ]
    for filename in expected_files:
        assert (tmp_path / filename).exists()


def test_supplier_reliability_score_within_valid_range(generated_tables):
    scores = generated_tables["suppliers"]["reliability_score"]
    assert scores.min() >= 60
    assert scores.max() <= 100


def test_vehicle_capacity_matches_vehicle_type_scale(generated_tables):
    vehicles = generated_tables["vehicles"]
    ships = vehicles[vehicles["vehicle_type"] == "Container Ship"]
    bikes = vehicles[vehicles["vehicle_type"] == "Cargo Bike"]
    if len(ships) and len(bikes):
        assert ships["capacity_kg"].min() > bikes["capacity_kg"].max()
