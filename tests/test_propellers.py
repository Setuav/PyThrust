import json
import math
import pytest
from pathlib import Path
from pythrust.propellers.database import (
    PropellerDatabase,
    PropellerMetadata,
    PropellerDataPoint,
    PropellerEntry,
    _find_bracketing_indices,
    _find_insert_index
)


def test_find_insert_index():
    values = [0.1, 0.2, 0.4, 0.8]
    assert _find_insert_index(values, 0.0) == 1
    assert _find_insert_index(values, 0.15) == 1
    assert _find_insert_index(values, 0.3) == 2
    assert _find_insert_index(values, 0.5) == 3
    assert _find_insert_index(values, 1.0) == 3


def test_find_bracketing_indices():
    values = [1000.0, 2000.0, 3000.0]
    assert _find_bracketing_indices(values, 500.0) == (0, 0)
    assert _find_bracketing_indices(values, 3500.0) == (2, 2)
    assert _find_bracketing_indices(values, 1500.0) == (0, 1)
    assert _find_bracketing_indices(values, 2000.0) == (0, 1)


def test_propeller_entry_properties():
    meta = PropellerMetadata(
        id="apc_10x4.7",
        manufacturer="APC",
        model="SF",
        diameter_in=10.0,
        pitch_in=4.7,
        blade_count=2,
        data_csv="apc_10x4.7.csv"
    )
    
    data = {
        1000.0: [PropellerDataPoint(j=0.0, ct=0.1, cp=0.05)],
        2000.0: [PropellerDataPoint(j=0.0, ct=0.12, cp=0.06)]
    }
    
    entry = PropellerEntry(metadata=meta, data_by_rpm=data)
    
    assert math.isclose(entry.diameter_m, 10.0 * 0.0254)
    assert math.isclose(entry.pitch_m, 4.7 * 0.0254)
    assert entry.rpm_levels == [1000.0, 2000.0]


def test_propeller_entry_get_coefficients():
    meta = PropellerMetadata(
        id="apc_10x4.7",
        manufacturer="APC",
        model="SF",
        diameter_in=10.0,
        pitch_in=4.7,
        blade_count=2,
        data_csv="apc_10x4.7.csv"
    )
    
    # RPM band 1: 1000.0, J range: 0.0 -> 0.4 -> 0.8
    # RPM band 2: 2000.0, J range: 0.0 -> 0.4 -> 0.8
    data = {
        1000.0: [
            PropellerDataPoint(j=0.0, ct=0.1, cp=0.05),
            PropellerDataPoint(j=0.4, ct=0.08, cp=0.04),
            PropellerDataPoint(j=0.8, ct=0.02, cp=0.01)
        ],
        2000.0: [
            PropellerDataPoint(j=0.0, ct=0.12, cp=0.06),
            PropellerDataPoint(j=0.4, ct=0.10, cp=0.05),
            PropellerDataPoint(j=0.8, ct=0.04, cp=0.02)
        ]
    }
    
    entry = PropellerEntry(metadata=meta, data_by_rpm=data)
    
    # 1. Test empty data
    empty_entry = PropellerEntry(metadata=meta, data_by_rpm={})
    assert empty_entry.get_coefficients(1000.0, 0.2) == (0.0, 0.0)

    # 2. Test clamping on J (low J)
    ct, cp = entry.get_coefficients(1000.0, -0.1)
    assert ct == 0.1 and cp == 0.05

    # 3. Test clamping on J (high J - no extrapolation)
    ct, cp = entry.get_coefficients(1000.0, 0.9)
    assert ct == 0.0 and cp == 0.0

    # 4. Test exact RPM and J interpolation
    # J = 0.2, RPM = 1000.0 -> midway between J=0.0 and J=0.4
    # expected Ct = 0.1 - 0.5 * (0.1 - 0.08) = 0.09
    # expected Cp = 0.05 - 0.5 * (0.05 - 0.04) = 0.045
    ct, cp = entry.get_coefficients(1000.0, 0.2)
    assert math.isclose(ct, 0.09)
    assert math.isclose(cp, 0.045)

    # 5. Test RPM interpolation (blend)
    # J = 0.4, RPM = 1500.0 -> midway between 1000.0 and 2000.0
    # RPM 1000 Ct=0.08, RPM 2000 Ct=0.10 -> expected = 0.09
    # RPM 1000 Cp=0.04, RPM 2000 Cp=0.05 -> expected = 0.045
    ct, cp = entry.get_coefficients(1500.0, 0.4)
    assert math.isclose(ct, 0.09)
    assert math.isclose(cp, 0.045)

    # 6. Test RPM clamping (above max RPM level)
    # RPM = 3000.0 -> clamp to 2000.0. J = 0.4 -> expected Ct=0.10, Cp=0.05
    ct, cp = entry.get_coefficients(3000.0, 0.4)
    assert math.isclose(ct, 0.10)
    assert math.isclose(cp, 0.05)


def test_propeller_database_load(tmp_path):
    # Create mock JSON and CSV file in tmp_path
    prop_id = "test_prop"
    json_content = {
        "id": prop_id,
        "manufacturer": "APC",
        "model": "Thin Electric",
        "diameter_in": 12.0,
        "pitch_in": 6.0,
        "blade_count": 2,
        "data_csv": "test_prop_data.csv"
    }
    
    csv_content = (
        "rpm,advance_ratio,thrust_coeff,power_coeff\n"
        "1000,0.0,0.1,0.05\n"
        "1000,0.5,0.05,0.02\n"
        "2000,0.0,0.11,0.06\n"
        "2000,0.5,0.06,0.03\n"
    )
    
    json_file = tmp_path / f"{prop_id}.json"
    csv_file = tmp_path / "test_prop_data.csv"
    
    json_file.write_text(json.dumps(json_content))
    csv_file.write_text(csv_content)
    
    db = PropellerDatabase()
    assert not db.is_loaded
    
    # Test load
    success = db.load(tmp_path)
    assert success
    assert db.is_loaded
    assert db.propeller_count == 1
    assert db.list_propellers() == [prop_id]
    
    entry = db.get(prop_id)
    assert entry is not None
    assert entry.metadata.id == prop_id
    
    # Test find_by_size
    found = db.find_by_size(12.1, 5.9, blade_count=2, tolerance=0.5)
    assert found is not None
    assert found.metadata.id == prop_id
    
    # Test not found by blade_count
    assert db.find_by_size(12.1, 5.9, blade_count=3) is None
    
    # Test get_interpolated_coefficients
    ct, cp, ok = db.get_interpolated_coefficients(12.0, 6.0, 2, 1500.0, 0.25)
    assert ok
    # RPM 1000 J 0.25 -> 0.1 - 0.5 * 0.05 = 0.075
    # RPM 2000 J 0.25 -> 0.11 - 0.5 * 0.05 = 0.085
    # RPM 1500 J 0.25 -> 0.08
    assert math.isclose(ct, 0.08)


def test_propeller_database_strict_validation(tmp_path):
    # 1. Invalid columns CSV
    prop_id = "bad_cols"
    json_content = {
        "id": prop_id,
        "manufacturer": "APC",
        "model": "EP",
        "diameter_in": 10.0,
        "pitch_in": 5.0,
        "blade_count": 2,
        "data_csv": "bad_cols.csv"
    }
    bad_csv = "rpm,wrong_column,thrust_coeff,power_coeff\n1000,0.1,0.1,0.05\n"
    (tmp_path / f"{prop_id}.json").write_text(json.dumps(json_content))
    (tmp_path / "bad_cols.csv").write_text(bad_csv)
    
    db = PropellerDatabase()
    
    # Non-strict should just skip
    db.load(tmp_path, strict=False)
    assert db.propeller_count == 0
    
    # Strict should raise ValueError
    with pytest.raises(ValueError, match="Missing required columns"):
        db.load(tmp_path, strict=True)
