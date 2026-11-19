import math
from dataclasses import replace
from pathlib import Path

import pytest

from pythrust.io import read_apc, read_apc_geometry
from pythrust.propeller import BladeElementPropeller, BladeGeometry, BladeSection

APC_FILE = Path(__file__).parent / "data" / "PER3_13x65E.dat"
GEOMETRY_FILE = Path(__file__).parent / "data" / "10x5E-PERF.PE0"
INCH = 0.0254

E63 = BladeSection(
    cl0=0.50,
    cl_alpha_per_rad=5.8,
    cl_min=-0.3,
    cl_max=1.2,
    cd0=0.028,
    cd2_upper=0.050,
    cd2_lower=0.020,
    cl_at_cd0=0.5,
    reynolds_ref=70000.0,
    reynolds_exp=-0.7,
)
APC12 = replace(E63, cl0=0.30, cd0=0.010)


def test_read_apc_file():
    propeller = read_apc(APC_FILE)

    assert propeller.diameter_m == pytest.approx(13.0 * 0.0254)
    assert propeller.rpm_levels == [1000.0 * k for k in range(1, 19)]
    first = propeller.data_by_rpm[1000.0][0]
    assert (first.j, first.ct, first.cp) == (0.0, 0.0889, 0.0376)


def test_read_apc_keeps_only_positive_coefficients_sorted_by_advance_ratio():
    propeller = read_apc(APC_FILE)

    for points in propeller.data_by_rpm.values():
        advance_ratios = [point.j for point in points]
        assert advance_ratios == sorted(set(advance_ratios))
        assert all(point.ct >= 0.0 and point.cp >= 0.0 for point in points)


def _apc_text(model_line, rows):
    lines = [f"   {model_line}", "", "   PROP RPM =   5000", "", "   V  J  Pe  Ct  Cp ..."]
    lines += ["   " + "  ".join(str(value) for value in row) for row in rows]
    return "\r\n".join(lines) + "\r\n"


def _row(j, ct, cp):
    return [0.0, j, 0.0, ct, cp] + [0.0] * 10


def test_read_apc_drops_windmilling_rows(tmp_path):
    path = tmp_path / "PER3_10x5.dat"
    path.write_text(_apc_text("10x5   (10x5.dat)", [_row(0.0, 0.1, 0.05), _row(0.5, 0.02, 0.01), _row(0.7, -0.01, -0.002)]))

    propeller = read_apc(path)

    assert propeller.diameter_m == pytest.approx(0.254)
    assert [point.j for point in propeller.data_by_rpm[5000.0]] == [0.0, 0.5]


def test_read_apc_rejects_a_file_without_a_size(tmp_path):
    path = tmp_path / "bad.dat"
    path.write_text(_apc_text("not a propeller", [_row(0.0, 0.1, 0.05)]))

    with pytest.raises(ValueError, match="no propeller size"):
        read_apc(path)


def test_read_apc_rejects_a_file_without_data(tmp_path):
    path = tmp_path / "empty.dat"
    path.write_text(_apc_text("10x5   (10x5.dat)", []))

    with pytest.raises(ValueError, match="no performance data"):
        read_apc(path)


def test_read_apc_geometry_in_si_units():
    blade = read_apc_geometry(GEOMETRY_FILE, E63)

    assert isinstance(blade, BladeGeometry)
    assert blade.blade_count == 2
    assert blade.radius_m == pytest.approx(5.0 * INCH)
    assert len(blade.r_m) == 41  # the 53 stations from the hub transition at 0.95 in
    assert (blade.r_m[0], blade.chord_m[0], blade.blade_angle_rad[0]) == pytest.approx(
        (0.95 * INCH, 0.7898 * INCH, math.radians(36.9991))
    )
    assert (blade.r_m[-1], blade.chord_m[-1], blade.blade_angle_rad[-1]) == pytest.approx(
        (5.0 * INCH, 0.0163 * INCH, math.radians(9.0475))
    )
    assert blade.sections == (E63,) * 41


def test_read_apc_geometry_blends_the_two_airfoils_across_the_transition():
    """AIRFOIL1 E63 at 0.95 in, AIRFOIL2 APC12 from 3.66 in."""
    blade = read_apc_geometry(GEOMETRY_FILE, {"E63": E63, "APC12": APC12})

    r_in = [r / INCH for r in blade.r_m]
    for r, section in zip(r_in, blade.sections):
        weight = min(max((r - 0.95) / (3.66 - 0.95), 0.0), 1.0)
        assert section.cl0 == pytest.approx(0.50 + (0.30 - 0.50) * weight)
        assert section.cd0 == pytest.approx(0.028 + (0.010 - 0.028) * weight)
        assert section.cl_alpha_per_rad == pytest.approx(5.8)
    assert blade.sections[0] == E63
    assert blade.sections[-1] == APC12


def test_read_apc_geometry_names_a_missing_airfoil():
    with pytest.raises(KeyError, match="no section for airfoil 'APC12'"):
        read_apc_geometry(GEOMETRY_FILE, {"E63": E63})


@pytest.mark.parametrize(
    "edit, message",
    [
        (lambda text: text.replace(" BLADES:", " BLADE:"), "no BLADES line"),
        (lambda text: text.replace(" RADIUS:", " RADIUS ").replace(" HUBTRA:", " HUBTRA "), "no RADIUS, HUBTRA line"),
        (lambda text: text.replace(" AIRFOIL2:", " AIRFOIL :"), "expected AIRFOIL1 and AIRFOIL2 lines"),
        (lambda text: text.replace("HUBTRA:  0.95", "HUBTRA:  4.99"), "a blade needs at least two stations"),
    ],
)
def test_read_apc_geometry_rejects_a_malformed_file(tmp_path, edit, message):
    path = tmp_path / "prop.PE0"
    path.write_text(edit(GEOMETRY_FILE.read_text()))

    with pytest.raises(ValueError, match=f"prop.PE0: {message}"):
        read_apc_geometry(path, {"E63": E63, "APC12": APC12})


def test_apc_geometry_gives_a_working_propeller_model():
    propeller = BladeElementPropeller(read_apc_geometry(GEOMETRY_FILE, E63))
    thrust, torque = propeller.thrust_torque(1.225, 0.0, 6000.0)

    assert propeller.diameter_m == pytest.approx(10.0 * INCH)
    assert thrust > 0.0 and torque > 0.0


def test_read_apc_geometry_tip_radius_is_at_least_the_last_station(tmp_path):
    """RADIUS is rounded to two decimals: 13x8E gives 6.47 in, its last station 6.475 in."""
    path = tmp_path / "prop.PE0"
    path.write_text(GEOMETRY_FILE.read_text().replace(" RADIUS:  5.00", " RADIUS:  4.99"))

    blade = read_apc_geometry(path, E63)

    assert blade.radius_m == pytest.approx(5.0 * INCH)
