import math
from pythrust.propeller.table import (
    PropellerDataPoint,
    TablePropeller,
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


def test_table_propeller_properties():
    data = {
        1000.0: [PropellerDataPoint(j=0.0, ct=0.1, cp=0.05)],
        2000.0: [PropellerDataPoint(j=0.0, ct=0.12, cp=0.06)]
    }
    
    entry = TablePropeller(diameter_m=0.254, data_by_rpm=data)
    
    assert entry.diameter_m == 0.254
    assert entry.rpm_levels == [1000.0, 2000.0]


def test_table_propeller_get_coefficients():
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
    
    entry = TablePropeller(diameter_m=0.254, data_by_rpm=data)
    
    # 1. Test empty data
    empty_entry = TablePropeller(diameter_m=0.254, data_by_rpm={})
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
