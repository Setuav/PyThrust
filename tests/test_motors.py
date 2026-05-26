from pathlib import Path
import pytest
from pythrust.motors import MotorDatabase


def test_motor_database():
    db = MotorDatabase()
    data_dir = Path(__file__).parent.parent / "datasets" / "brushless-motor"
    
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
