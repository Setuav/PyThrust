import math

from pythrust.battery import FixedVoltageBattery
from pythrust.motor import MotorSpec
from pythrust.propeller import PropellerDataPoint, TablePropeller
from pythrust.propulsion import PropulsionSolver, SystemSpec

RHO = 1.225


def _propeller():
    points = [
        PropellerDataPoint(j=0.0, ct=0.10, cp=0.05),
        PropellerDataPoint(j=0.8, ct=0.02, cp=0.02),
    ]
    return TablePropeller(diameter_m=0.254, data_by_rpm={1000.0: list(points), 9000.0: list(points)})


def test_table_propeller_turns_coefficients_into_thrust_and_torque():
    propeller = _propeller()
    rpm, diameter_m = 6000.0, 0.254
    n = rpm / 60.0

    thrust_n, torque_nm = propeller.thrust_torque(RHO, 0.0, rpm)

    assert math.isclose(thrust_n, 0.10 * RHO * n**2 * diameter_m**4)
    assert math.isclose(torque_nm, 0.05 * RHO * n**2 * diameter_m**5 / (2.0 * math.pi))


def test_table_propeller_diameter_scales_with_unchanged_coefficients():
    base = _propeller()
    scaled = base.scaled(2.0 * base.diameter_m)

    thrust_n, torque_nm = base.thrust_torque(RHO, 0.0, 6000.0)
    scaled_thrust_n, scaled_torque_nm = scaled.thrust_torque(RHO, 0.0, 6000.0)

    assert math.isclose(scaled_thrust_n, 2.0**4 * thrust_n)
    assert math.isclose(scaled_torque_nm, 2.0**5 * torque_nm)


def test_table_propeller_has_no_torque_past_its_data():
    propeller = _propeller()
    airspeed_mps = 1.0 * (6000.0 / 60.0) * propeller.diameter_m  # J = 1.0, past the table's 0.8

    assert propeller.thrust_torque(RHO, airspeed_mps, 6000.0) == (0.0, 0.0)


class _ConstantCoefficientPropeller:
    """A propeller model that is not a table: fixed thrust and power coefficients."""

    diameter_m = 0.254
    max_advance_ratio = 0.8

    def thrust_torque(self, rho, airspeed_mps, rpm):
        n = rpm / 60.0
        return (
            0.10 * rho * n**2 * self.diameter_m**4,
            0.05 * rho * n**2 * self.diameter_m**5 / (2.0 * math.pi),
        )


def test_solver_accepts_any_propeller_model():
    point = PropulsionSolver().solve_operating_point(
        motor=MotorSpec(kv_rpm_per_v=980.0, resistance_ohm=0.06, no_load_current_a=1.2, current_max_a=30.0),
        battery=FixedVoltageBattery(voltage_v=11.1),
        system=SystemSpec(resistance_ohm=0.015),
        propeller=_ConstantCoefficientPropeller(),
        rho=RHO,
        airspeed_mps=0.0,
        throttle=0.7,
    )

    assert point.is_feasible
    assert math.isclose(point.ct, 0.10)
    assert math.isclose(point.cp, 0.05)
    assert math.isclose(point.shaft_power_w, point.torque_nm * point.rpm * math.pi / 30.0)
