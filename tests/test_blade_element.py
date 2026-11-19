import json
from pathlib import Path

import numpy as np
import pytest

from pythrust.battery import FixedVoltageBattery
from pythrust.io import read_qprop_propeller
from pythrust.motor import MotorSpec
from pythrust.propeller import BladeElementPropeller, BladeGeometry, BladeSection
from pythrust.propeller.blade_element import _spline
from pythrust.propulsion import PropulsionSolver, SystemSpec

DATA = Path(__file__).parent / "data"
RHO = 1.225

# QPROP 1.22 thrust (N) and torque (N m), printed to 4 significant digits:
# (airspeed m/s, rpm, thrust, torque).
QPROP_10X5 = [
    (0, 4000, 2.385, 0.04068),
    (0, 8000, 9.675, 0.1509),
    (5, 8000, 8.18, 0.1463),
    (12, 8000, 5.188, 0.1208),
    (20, 9000, 2.79, 0.09304),
    (30, 9000, -3.565, -0.05523),
]
QPROP_LINEAR = {
    "A": [(0, 6000, 4.706, 0.09617), (10, 6000, 3.548, 0.0925), (20, 9000, 5.915, 0.173), (0, 14000, 26.1, 0.4904)],
    "B": [(0, 5000, 7.183, 0.1902), (15, 7000, 10.1, 0.3197), (30, 6000, -2.643, -0.0696)],
}
FOUR_DIGITS = 6e-4


@pytest.fixture(scope="module")
def propeller_10x5():
    return BladeElementPropeller(read_qprop_propeller(DATA / "qprop_10x5.txt"))


def _linear_blade(prop):
    """The station-test blades: three stations on a straight chord and blade angle."""
    t = np.array([0.0, 0.5, 1.0])
    return BladeGeometry(
        blade_count=prop["blade_count"],
        radius_m=prop["radius_m"],
        r_m=tuple(prop["root_m"] + t * (prop["tip_m"] - prop["root_m"])),
        chord_m=tuple(prop["chord_m"][0] + t * (prop["chord_m"][1] - prop["chord_m"][0])),
        blade_angle_rad=tuple(np.radians(prop["blade_angle_deg"][0] + t * (prop["blade_angle_deg"][1] - prop["blade_angle_deg"][0]))),
        sections=(BladeSection(*prop["section"]),) * 3,
    )


@pytest.mark.parametrize("airspeed, rpm, thrust, torque", QPROP_10X5)
def test_matches_qprop_on_a_curved_blade(propeller_10x5, airspeed, rpm, thrust, torque):
    t, q = propeller_10x5.thrust_torque(RHO, airspeed, rpm)

    assert t == pytest.approx(thrust, rel=FOUR_DIGITS)
    assert q == pytest.approx(torque, rel=FOUR_DIGITS)


@pytest.mark.parametrize("name", sorted(QPROP_LINEAR))
def test_matches_qprop_on_straight_blades(name):
    props = json.loads((DATA / "qprop_stations.json").read_text())["props"]
    propeller = BladeElementPropeller(_linear_blade(props[name]))

    for airspeed, rpm, thrust, torque in QPROP_LINEAR[name]:
        t, q = propeller.thrust_torque(RHO, airspeed, rpm)
        assert t == pytest.approx(thrust, rel=FOUR_DIGITS)
        assert q == pytest.approx(torque, rel=FOUR_DIGITS)


def test_spline_has_zero_third_derivative_in_the_end_intervals():
    x = np.array([0.0, 1.0, 2.5, 4.0, 5.0])
    at = np.linspace(0.0, 5.0, 41)

    # Any quadratic satisfies the end conditions, so the spline reproduces it.
    assert _spline(x, 3.0 - 2.0 * x + 0.5 * x**2, at) == pytest.approx(3.0 - 2.0 * at + 0.5 * at**2)
    assert _spline(x[:2], np.array([1.0, 3.0]), np.array([0.25])) == pytest.approx([1.5])


def test_analysis_stations_are_midpoints_from_root_to_last_station(propeller_10x5):
    r = np.asarray(propeller_10x5.geometry.r_m)
    edges = np.linspace(r[0], r[-1], 26)

    assert propeller_10x5._r == pytest.approx(0.5 * (edges[:-1] + edges[1:]))


def test_diameter_and_no_load_at_rest(propeller_10x5):
    assert propeller_10x5.diameter_m == pytest.approx(2.0 * 4.9 * 0.0254)
    assert propeller_10x5.thrust_torque(RHO, 10.0, 0.0) == (0.0, 0.0)


def test_max_advance_ratio_is_near_zero_thrust(propeller_10x5):
    rpm = 8000.0
    j = propeller_10x5.max_advance_ratio
    airspeed = j * (rpm / 60.0) * propeller_10x5.diameter_m

    static_thrust, _ = propeller_10x5.thrust_torque(RHO, 0.0, rpm)
    thrust, _ = propeller_10x5.thrust_torque(RHO, airspeed, rpm)

    assert 0.3 < j < 1.5
    assert abs(thrust) < 0.1 * static_thrust


def test_solver_finds_an_operating_point(propeller_10x5):
    point = PropulsionSolver().solve_operating_point(
        motor=MotorSpec(kv_rpm_per_v=1000.0, resistance_ohm=0.08, no_load_current_a=0.8, current_max_a=40.0),
        battery=FixedVoltageBattery(voltage_v=11.1),
        system=SystemSpec(resistance_ohm=0.02),
        propeller=propeller_10x5,
        rho=RHO,
        airspeed_mps=8.0,
        throttle=0.8,
    )

    thrust, torque = propeller_10x5.thrust_torque(RHO, 8.0, point.rpm)
    assert point.is_feasible
    assert point.thrust_n == pytest.approx(thrust)
    assert point.torque_nm == pytest.approx(torque)
    assert 0.0 < point.propeller_efficiency < 1.0


@pytest.mark.parametrize("airspeed", [0.0, 8.0, 15.0])
def test_solver_needs_few_propeller_evaluations(propeller_10x5, airspeed):
    """Negative thrust near the search's start is a result, not a gap to scan past."""
    calls = []

    class Counted:
        diameter_m = propeller_10x5.diameter_m
        max_advance_ratio = propeller_10x5.max_advance_ratio

        def thrust_torque(self, rho, airspeed_mps, rpm):
            calls.append(rpm)
            return propeller_10x5.thrust_torque(rho, airspeed_mps, rpm)

    point = PropulsionSolver().solve_operating_point(
        motor=MotorSpec(kv_rpm_per_v=1000.0, resistance_ohm=0.08, no_load_current_a=0.6, current_max_a=40.0),
        battery=FixedVoltageBattery(voltage_v=11.1),
        system=SystemSpec(resistance_ohm=0.02),
        propeller=Counted(),
        rho=RHO,
        airspeed_mps=airspeed,
        throttle=0.8,
    )

    assert point.is_feasible
    assert len(calls) <= 20
