import json
import math
from pathlib import Path
import pytest
from pythrust.battery import FixedVoltageBattery
from pythrust.motors import MotorDatabase
from pythrust.propellers import PropellerDatabase
from pythrust.propulsion import PropellerSpec, PropulsionSolver, SystemSpec


def test_motor_database():
    db = MotorDatabase()
    data_dir = Path(__file__).parent.parent / "pythrust" / "data" / "motors"
    
    # Verify load from directory
    assert db.load(data_dir)
    assert db.is_loaded
    assert db.motor_count == 7880

    # Test listing and getting
    motors = db.list_motors()
    assert len(motors) > 0
    motor_id = motors[0]
    
    entry = db.get(motor_id)
    assert entry is not None
    assert entry.id == motor_id
    assert entry.kv > 0

    # Test load_entry individually
    db_single = MotorDatabase()
    single_path = data_dir / f"{motor_id}.json"
    loaded_entry = db_single.load_entry(single_path)
    assert loaded_entry is not None
    assert loaded_entry.id == motor_id
    assert db_single.motor_count == 1
    assert db_single.get(motor_id) is not None

    # Test conversion to MotorSpec
    spec = entry.to_spec()
    assert spec.kv_rpm_per_v == entry.kv
    assert spec.resistance_ohm == entry.resistance
    assert spec.no_load_current_a == entry.io
    assert spec.current_max_a == entry.max_current
    assert spec.no_load_voltage_v == entry.io_voltage

    # Test search filters (Kv and Weight limits)
    results = db.search(
        min_kv=500.0,
        max_kv=600.0,
        min_weight=100.0,
        max_weight=180.0,
        min_max_current=20.0
    )
    
    assert len(results) > 0
    for r in results:
        assert 500.0 <= r.kv <= 600.0
        assert 100.0 <= r.weight_g <= 180.0
        assert r.max_current >= 20.0


def _write_motor(path, **overrides):
    data = {
        "id": "Test_Motor",
        "name": "Test Motor",
        "manufacturer": "Test",
        "kv": 1000.0,
        "resistance": 0.172,
        "io": 0.8,
        "max_current": 25.0,
        "weight_g": 60.0,
        "max_power": 255.0,
        "io_voltage": 10.0,
    }
    data.update(overrides)
    data = {key: value for key, value in data.items() if value is not None}
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize("max_current", [0.0, None])
def test_motor_without_max_current_has_no_limit(tmp_path, max_current):
    entry = MotorDatabase().load_entry(_write_motor(tmp_path / "m.json", max_current=max_current))

    assert entry.max_current == 0.0
    assert not entry.has_current_limit
    assert math.isinf(entry.to_spec().current_max_a)


def test_motor_with_max_current_keeps_limit(tmp_path):
    entry = MotorDatabase().load_entry(_write_motor(tmp_path / "m.json", max_current=25.0))

    assert entry.has_current_limit
    assert entry.to_spec().current_max_a == 25.0


def test_motor_without_max_current_is_not_current_limited(tmp_path):
    prop_db = PropellerDatabase()
    prop_db.load(Path(__file__).parent.parent / "pythrust" / "data" / "propellers" / "apc_202602")
    prop_entry = prop_db.get("APC_10x5E")
    entry = MotorDatabase().load_entry(_write_motor(tmp_path / "m.json", max_current=0.0))

    point = PropulsionSolver().solve_operating_point(
        motor=entry.to_spec(),
        battery=FixedVoltageBattery(voltage_v=14.8),
        system=SystemSpec(),
        propeller=PropellerSpec(diameter_m=prop_entry.diameter_m),
        prop_entry=prop_entry,
        rho=1.225,
        airspeed_mps=0.0,
        throttle=0.5,
    )

    assert point.is_feasible
    assert point.motor_current_a > 0.0


def test_bundled_motors_without_max_current_load():
    db = MotorDatabase()
    db.load(Path(__file__).parent.parent / "pythrust" / "data" / "motors")
    without_limit = [entry for entry in db.search() if not entry.has_current_limit]

    assert without_limit
    assert all(math.isinf(entry.to_spec().current_max_a) for entry in without_limit)
