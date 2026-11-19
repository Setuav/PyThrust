import math
from pathlib import Path

import numpy as np
import pytest
import setuav_neuralfoil as nf
from setuav_neuralfoil import geometry

from pythrust.battery import FixedVoltageBattery
from pythrust.io import read_apc_geometry
from pythrust.motor import MotorSpec
from pythrust.propeller import AirfoilPolar, BladeElementPropeller, BladeGeometry, BladeSection, BlendedPolar
from pythrust.propeller import apc_airfoil_polars
from pythrust.propeller.polar import NEURALFOIL_ALPHA_DEG, REYNOLDS, StationPolars
from pythrust.propulsion import PropulsionSolver, SystemSpec

DATA = Path(__file__).parent / "data"
RHO = 1.225


def _polar(cl, cd, name="test"):
    """A 3 x 2 table: alpha -0.1, 0, 0.1 rad; Re 1e4, 1e5."""
    return AirfoilPolar(
        name=name, alpha_rad=np.array([-0.1, 0.0, 0.1]), reynolds=np.array([1e4, 1e5]), cl=np.array(cl), cd=np.array(cd)
    )


LINEAR = _polar(cl=[[-0.4, -0.2], [0.2, 0.4], [0.8, 1.0]], cd=[[0.03, 0.02], [0.02, 0.01], [0.04, 0.03]])


@pytest.fixture(scope="module")
def naca4412():
    return AirfoilPolar.from_neuralfoil("NACA 4412", n_crit=9.0)


### Table


def test_table_shape_and_order_are_checked():
    with pytest.raises(ValueError, match="shape"):
        _polar(cl=[[0.0, 0.0]], cd=[[0.0, 0.0]])
    with pytest.raises(ValueError, match="increase"):
        AirfoilPolar("x", np.array([0.1, 0.0]), np.array([1e4, 1e5]), np.zeros((2, 2)), np.zeros((2, 2)))


def test_interpolates_linearly_in_alpha_and_log_reynolds():
    alpha = np.array([0.0, 0.05, 0.0, 0.05])
    reynolds = np.array([1e4, 1e4, 10**4.5, 10**4.5])

    cl, cd = LINEAR.coefficients(alpha, reynolds, np.zeros(4))

    np.testing.assert_allclose(cl, [0.2, 0.5, 0.3, 0.6])
    np.testing.assert_allclose(cd, [0.02, 0.03, 0.015, 0.025])


def test_reynolds_beyond_the_table_uses_its_ends():
    cl, _ = LINEAR.coefficients(np.zeros(2), np.array([1e2, 1e7]), np.zeros(2))

    np.testing.assert_allclose(cl, [0.2, 0.4])


def test_lift_has_the_prandtl_glauert_factor():
    cl0, cd0 = LINEAR.coefficients(0.05, 1e4, 0.0)
    cl, cd = LINEAR.coefficients(0.05, 1e4, 0.6)

    assert cl == pytest.approx(cl0 / 0.8)
    assert cd == pytest.approx(cd0)


def test_angles_wrap_around_a_full_turn():
    a, b = LINEAR.coefficients(np.array([0.05, 0.05 + 2 * np.pi]), 1e4, 0.0)

    assert a[0] == pytest.approx(a[1])


def test_keeps_the_shape_of_a_station_grid():
    cl, cd = LINEAR.coefficients(np.zeros((3, 5)), np.full((3, 5), 1e4), np.zeros((3, 5)))

    assert cl.shape == cd.shape == (3, 5)


### NeuralFoil


def test_matches_neuralfoil_at_the_table_points(naca4412):
    alpha_deg = np.array([-8.0, 0.0, 6.5, 12.0])
    for re in (REYNOLDS[3], REYNOLDS[8]):
        expected = nf.get_aero_from_naca("4412", alpha=alpha_deg, Re=re, n_crit=9.0)

        cl, cd = naca4412.coefficients(np.radians(alpha_deg), re, 0.0)

        np.testing.assert_allclose(cl, expected["CL"], rtol=1e-10)
        np.testing.assert_allclose(cd, expected["CD"], rtol=1e-10)


def test_flat_plate_beyond_neuralfoils_range(naca4412):
    alpha = np.radians([-90.0, 60.0, 150.0])

    cl, cd = naca4412.coefficients(alpha, 1e5, 0.0)

    np.testing.assert_allclose(cl, np.sin(2 * alpha), atol=1e-12)
    np.testing.assert_allclose(cd, 2 * np.sin(alpha) ** 2, atol=1e-12)


def test_default_n_crit_is_7():
    assert AirfoilPolar.from_neuralfoil.__defaults__[0] == 7.0
    assert apc_airfoil_polars() is not None and apc_airfoil_polars()["E63"] is apc_airfoil_polars(7.0)["E63"]


def test_zero_lift_angle():
    """The lowest over the Reynolds numbers; near Re 5e4 the NACA 0012's lift bends about zero angle."""
    symmetric = AirfoilPolar.from_neuralfoil("0012")
    cambered = AirfoilPolar.from_neuralfoil("4412")

    assert symmetric.zero_lift_alpha_rad == pytest.approx(0.0, abs=math.radians(1.0))
    assert cambered.zero_lift_alpha_rad == pytest.approx(math.radians(-4.4), abs=math.radians(0.2))


def test_dat_file_and_coordinates_give_the_naca_polar(tmp_path, naca4412):
    coordinates = geometry.naca("4412")
    path = tmp_path / "naca4412.dat"
    path.write_text("NACA 4412\n" + "\n".join(f"{x:.16f} {y:.16f}" for x, y in coordinates) + "\n")

    from_file = AirfoilPolar.from_neuralfoil(path, n_crit=9.0)
    from_coordinates = AirfoilPolar.from_neuralfoil(coordinates, n_crit=9.0)

    np.testing.assert_allclose(from_file.cl, naca4412.cl, rtol=1e-8)
    np.testing.assert_array_equal(from_coordinates.cl, naca4412.cl)
    assert from_file.name == str(path)


### Mixing


def test_blended_polar_mixes_the_coefficients():
    other = _polar(cl=[[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]], cd=[[0.1, 0.1], [0.1, 0.1], [0.1, 0.1]])
    blend = BlendedPolar(LINEAR, other, 0.25)

    cl, cd = blend.coefficients(0.05, 1e4, 0.0)

    assert cl == pytest.approx(0.75 * 0.5)
    assert cd == pytest.approx(0.75 * 0.03 + 0.25 * 0.1)


def test_station_polars_mix_the_nearest_sections():
    other = _polar(cl=[[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]], cd=[[0.1, 0.1], [0.1, 0.1], [0.1, 0.1]])
    sections = [LINEAR, BlendedPolar(LINEAR, other, 0.5), other]

    stations = StationPolars.interpolate(np.array([0.0, 1.0, 2.0]), sections, np.array([0.0, 0.5, 1.5, 2.0]))

    assert stations.polars == [LINEAR, other]
    np.testing.assert_allclose(stations.weights, [[1.0, 0.0], [0.75, 0.25], [0.25, 0.75], [0.0, 1.0]])
    cl, _ = stations.coefficients(np.full((4, 2), 0.05), np.full((4, 2), 1e4), np.zeros((4, 2)))
    np.testing.assert_allclose(cl[:, 0], [0.5, 0.375, 0.125, 0.0])


### Blade-element propeller


def test_a_blade_takes_one_kind_of_section():
    qprop = BladeSection(0.5, 5.8, -0.3, 1.2, 0.028, 0.05, 0.02, 0.5, 70000.0, -0.7)
    blade = BladeGeometry(2, 0.1, (0.02, 0.1), (0.01, 0.01), (0.3, 0.2), (qprop, LINEAR))

    with pytest.raises(TypeError, match="all BladeSection"):
        BladeElementPropeller(blade)


def test_apc_airfoil_polars_are_cached_per_n_crit():
    polars = apc_airfoil_polars(5.0)

    assert set(polars) == {"E63", "APC12", "CLARK-Y"}
    assert apc_airfoil_polars(5.0)["E63"] is polars["E63"]
    assert apc_airfoil_polars(9.0)["E63"] is not polars["E63"]


def test_apc_geometry_blends_the_airfoils_across_the_transition():
    polars = apc_airfoil_polars(5.0)
    blade = read_apc_geometry(DATA / "10x5E-PERF.PE0", polars)

    assert blade.sections[0] is polars["E63"]
    assert blade.sections[-1] is polars["APC12"]
    middle = [s for s in blade.sections if isinstance(s, BlendedPolar)]
    assert middle and all(0.0 < s.weight < 1.0 for s in middle)


def test_static_coefficients_are_near_the_wind_tunnel_measurement():
    """APC 10x5E geometry with NeuralFoil polars (n_crit 5) against UIUC static data: 2500-6700 RPM."""
    propeller = BladeElementPropeller(read_apc_geometry(DATA / "10x5E-PERF.PE0", apc_airfoil_polars(5.0)))
    lines = (DATA / "apce_10x5_static_pg0819.txt").read_text().split("\n")[1:]
    measured = [tuple(float(value) for value in line.split()) for line in lines if line.strip()]
    diameter = propeller.diameter_m

    for rpm, ct_measured, cp_measured in measured:
        n = rpm / 60.0
        thrust, torque = propeller.thrust_torque(RHO, 0.0, rpm)
        assert thrust / (RHO * n**2 * diameter**4) == pytest.approx(ct_measured, rel=0.08)
        assert 2 * math.pi * torque / (RHO * n**2 * diameter**5) == pytest.approx(cp_measured, rel=0.08)


@pytest.mark.parametrize("airspeed", [0.0, 8.0, 15.0])
def test_solver_finds_an_operating_point(airspeed):
    propeller = BladeElementPropeller(read_apc_geometry(DATA / "10x5E-PERF.PE0", apc_airfoil_polars(5.0)))

    point = PropulsionSolver().solve_operating_point(
        motor=MotorSpec(kv_rpm_per_v=1000.0, resistance_ohm=0.08, no_load_current_a=0.6, current_max_a=40.0),
        battery=FixedVoltageBattery(voltage_v=11.1),
        system=SystemSpec(resistance_ohm=0.02),
        propeller=propeller,
        rho=RHO,
        airspeed_mps=airspeed,
        throttle=0.8,
    )

    assert point.is_feasible
    assert 0.0 < point.propeller_efficiency < 1.0 or airspeed == 0.0
