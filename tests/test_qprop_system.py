"""PyThrust's solver against QPROP 1.22 for the same propeller and motor files."""

from pathlib import Path

import pytest

from pythrust.battery import FixedVoltageBattery
from pythrust.io import read_qprop_motor, read_qprop_propeller
from pythrust.propeller import BladeElementPropeller
from pythrust.propulsion import PropulsionSolver, SystemSpec

DATA = Path(__file__).parent / "data"

# QPROP 1.22 run with a set voltage, as `qprop prop motor V 0 Volt`:
# (airspeed m/s, volts, rpm, thrust N, torque N m, current A). QPROP prints
# rpm, thrust and torque to 4 significant digits and the current to 6.
QPROP_POINTS = [
    (0, 11.1, 6528.0, 6.405, 0.1021, 12.0704),
    (8, 11.1, 6845.0, 4.666, 0.09875, 11.7198),
    (15, 14.8, 8391.0, 4.463, 0.116, 13.7187),
]


@pytest.mark.parametrize("airspeed, volts, rpm, thrust, torque, current", QPROP_POINTS)
def test_operating_point_matches_qprop(airspeed, volts, rpm, thrust, torque, current):
    point = PropulsionSolver().solve_operating_point(
        motor=read_qprop_motor(DATA / "qprop_motor.txt"),
        battery=FixedVoltageBattery(voltage_v=volts),
        system=SystemSpec(),
        propeller=BladeElementPropeller(read_qprop_propeller(DATA / "qprop_10x5.txt")),
        rho=1.225,
        airspeed_mps=airspeed,
        throttle=1.0,
    )

    assert point.is_feasible
    assert point.rpm == pytest.approx(rpm, rel=1e-4)
    assert point.thrust_n == pytest.approx(thrust, rel=6e-4)
    assert point.torque_nm == pytest.approx(torque, rel=6e-4)
    assert point.motor_current_a == pytest.approx(current, rel=1e-5)
