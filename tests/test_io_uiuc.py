import math
from pathlib import Path

import pytest

from pythrust.battery import FixedVoltageBattery
from pythrust.io import read_uiuc_geometry, read_uiuc_performance
from pythrust.motor import MotorSpec
from pythrust.propeller import BladeElementPropeller, BladeGeometry, BladeSection
from pythrust.propulsion import PropulsionSolver, SystemSpec

DATA = Path(__file__).parent / "data"
RHO = 1.225
DIAMETER = 10 * 0.0254

# The example section of the QPROP user guide; UIUC files give no airfoil data.
SECTION = BladeSection(
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

GEOMETRY = "r/R    c/R     beta\n0.15   0.130   32.76\n0.60   0.174   15.97\n1.00   0.041   8.99\n"


def _write(tmp_path, text, newline="\n"):
    path = tmp_path / "prop_geom.txt"
    path.write_bytes(text.replace("\n", newline).encode())
    return path


def test_reads_geometry_in_si_units():
    blade = read_uiuc_geometry(DATA / "apce_10x5_geom.txt", DIAMETER, SECTION)

    radius = 0.5 * DIAMETER
    assert isinstance(blade, BladeGeometry)
    assert blade.blade_count == 2
    assert blade.radius_m == pytest.approx(radius)
    assert len(blade.r_m) == 18
    assert (blade.r_m[0], blade.chord_m[0], blade.blade_angle_rad[0]) == pytest.approx(
        (0.15 * radius, 0.130 * radius, math.radians(32.76))
    )
    assert (blade.r_m[-1], blade.chord_m[-1], blade.blade_angle_rad[-1]) == pytest.approx(
        (radius, 0.041 * radius, math.radians(8.99))
    )
    assert blade.sections == (SECTION,) * 18


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_reads_either_line_ending(tmp_path, newline):
    blade = read_uiuc_geometry(_write(tmp_path, GEOMETRY + "\n", newline), 0.2, SECTION, blade_count=3)

    assert blade.blade_count == 3
    assert blade.r_m == pytest.approx([0.015, 0.06, 0.1])


@pytest.mark.parametrize(
    "text, message",
    [
        (GEOMETRY.replace("0.174", "abc"), r"prop_geom\.txt:3: 'abc' is not a number"),
        (GEOMETRY.replace("   15.97", ""), r"prop_geom\.txt:3: expected 'r/R c/R beta', got 2 values"),
        (GEOMETRY.replace("0.60", "0.10"), r"prop_geom\.txt: station radii must increase"),
        ("r/R    c/R     beta\n0.15   0.130   32.76\n", r"prop_geom\.txt: a blade needs at least two stations"),
    ],
)
def test_rejects_a_malformed_file(tmp_path, text, message):
    with pytest.raises(ValueError, match=message):
        read_uiuc_geometry(_write(tmp_path, text), 0.2, SECTION)


@pytest.mark.parametrize("diameter", [0.0, -0.2, math.nan])
def test_rejects_a_non_positive_diameter(tmp_path, diameter):
    with pytest.raises(ValueError, match="diameter_m must be positive"):
        read_uiuc_geometry(_write(tmp_path, GEOMETRY), diameter, SECTION)


def test_static_thrust_is_near_the_wind_tunnel_measurement():
    """With a generic section the model is a rough estimate: within 20 % of the measured CT."""
    propeller = BladeElementPropeller(read_uiuc_geometry(DATA / "apce_10x5_geom.txt", DIAMETER, SECTION))
    lines = (DATA / "apce_10x5_static_pg0819.txt").read_text().split("\n")[1:]
    measured = [tuple(float(value) for value in line.split()) for line in lines if line.strip()]

    for rpm, ct_measured, _ in measured:
        n = rpm / 60.0
        thrust, _ = propeller.thrust_torque(RHO, 0.0, rpm)
        assert thrust / (RHO * n**2 * DIAMETER**4) == pytest.approx(ct_measured, rel=0.20)


def test_solver_runs_with_a_uiuc_propeller():
    propeller = BladeElementPropeller(read_uiuc_geometry(DATA / "apce_10x5_geom.txt", DIAMETER, SECTION))

    point = PropulsionSolver().solve_operating_point(
        motor=MotorSpec(kv_rpm_per_v=1000.0, resistance_ohm=0.08, no_load_current_a=0.6, current_max_a=40.0),
        battery=FixedVoltageBattery(voltage_v=11.1),
        system=SystemSpec(resistance_ohm=0.02),
        propeller=propeller,
        rho=RHO,
        airspeed_mps=8.0,
        throttle=0.8,
    )

    assert point.is_feasible
    assert 0.0 < point.propeller_efficiency < 1.0


STATIC = DATA / "apce_10x5_static_pg0819.txt"
FORWARD = DATA / "apce_10x5_kt0823_6005.txt"


def test_performance_bands_start_at_the_static_point():
    table = read_uiuc_performance(DIAMETER, STATIC, [FORWARD])

    assert table.diameter_m == DIAMETER
    assert table.rpm_levels == [6005.0]
    points = table.data_by_rpm[6005.0]
    # Static: 5869 RPM CT 0.0977 CP 0.0373, 6146 RPM CT 0.0983 CP 0.0374.
    assert (points[0].j, points[0].ct, points[0].cp) == pytest.approx(
        (0.0, 0.0977 + (6005 - 5869) / (6146 - 5869) * 0.0006, 0.0373 + (6005 - 5869) / (6146 - 5869) * 0.0001)
    )
    assert (points[1].j, points[1].ct, points[1].cp) == (0.093, 0.0942, 0.0385)
    assert (points[-1].j, points[-1].ct, points[-1].cp) == (0.484, 0.0338, 0.0249)
    assert len(points) == 18


def test_performance_from_static_data_only():
    table = read_uiuc_performance(DIAMETER, STATIC)

    assert len(table.rpm_levels) == 16
    assert table.get_coefficients(2508.0, 0.0) == pytest.approx((0.0914, 0.0374))


def test_performance_needs_the_rpm_in_a_forward_file_name(tmp_path):
    path = tmp_path / "apce_10x5_forward.txt"
    path.write_text(FORWARD.read_text())

    with pytest.raises(ValueError, match="does not end in the test RPM"):
        read_uiuc_performance(DIAMETER, forward=[path])


def test_performance_rejects_a_malformed_row(tmp_path):
    path = tmp_path / "apce_10x5_kt0823_6005.txt"
    path.write_text("J CT CP eta\n0.1 0.09 0.04\n")

    with pytest.raises(ValueError, match="apce_10x5_kt0823_6005.txt:2: expected 4 numbers"):
        read_uiuc_performance(DIAMETER, forward=[path])


def test_performance_needs_some_data():
    with pytest.raises(ValueError, match="no measurements"):
        read_uiuc_performance(DIAMETER)
