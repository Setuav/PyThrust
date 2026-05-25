"""Unit and integration tests for PropulsionCalibrator.

Run from the project root::

    pytest tests/test_autotune.py -v
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from pythrust.propellers.database import PropellerDatabase
from pythrust.propulsion import (
    BatterySpec,
    MotorSpec,
    PropellerSpec,
    SystemSpec,
    PropulsionSolver,
)
from pythrust.propulsion.autotune import (
    CalibrationResult,
    ManufacturerTestPoint,
    PropulsionCalibrator,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DATASET_DIR = Path(__file__).parent.parent / "datasets" / "propellers" / "apc_202602"
_PROP_ID = "APC_13x6.5E"


@pytest.fixture(scope="module")
def prop_entry():
    db = PropellerDatabase()
    if not db.load(_DATASET_DIR, strict=False):
        pytest.skip(f"Propeller dataset not found at {_DATASET_DIR}")
    entry = db.get(_PROP_ID)
    if entry is None:
        pytest.skip(f"{_PROP_ID} not found in dataset")
    return entry


@pytest.fixture(scope="module")
def base_motor():
    return MotorSpec(
        kv_rpm_per_v=860.0,
        resistance_ohm=0.0258,
        no_load_current_a=1.3,
        current_max_a=65.0,
    )


@pytest.fixture(scope="module")
def base_battery():
    return BatterySpec(voltage_v=14.8)


@pytest.fixture(scope="module")
def base_propeller():
    return PropellerSpec(diameter_m=0.3302)  # 13-inch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_synthetic_table(
    motor: MotorSpec,
    battery: BatterySpec,
    system: SystemSpec,
    propeller: PropellerSpec,
    prop_entry,
    throttles=(0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
    rho: float = 1.225,
) -> list[ManufacturerTestPoint]:
    """Generate a synthetic table from the forward model."""
    solver = PropulsionSolver()
    points = []
    for t in throttles:
        op = solver.solve_operating_point(
            motor=motor,
            battery=battery,
            system=system,
            propeller=propeller,
            prop_entry=prop_entry,
            rho=rho,
            airspeed_mps=0.0,
            throttle=t,
        )
        if op.is_feasible:
            # battery DC current = battery power / battery voltage
            current_a = op.battery_power_w / battery.voltage_v
            points.append(
                ManufacturerTestPoint(
                    rpm=op.rpm,
                    thrust_g=op.thrust_n * 1000.0 / 9.80665,
                    current_a=current_a,
                )
            )
    return points


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Calibrator must recover the true system resistance from synthetic data."""

    @pytest.mark.parametrize("true_r_sys", [0.01, 0.03, 0.05, 0.08])
    def test_recover_system_resistance(
        self, true_r_sys, base_motor, base_battery, base_propeller, prop_entry
    ):
        system_true = SystemSpec(resistance_ohm=true_r_sys)
        table = _make_synthetic_table(
            base_motor, base_battery, system_true, base_propeller, prop_entry
        )
        assert len(table) >= 3, "Need >= 3 feasible points"

        cal = PropulsionCalibrator()
        result = cal.calibrate(
            table,
            base_motor,
            base_battery,
            SystemSpec(resistance_ohm=0.04),  # starting guess
            base_propeller,
            prop_entry,
        )

        assert result.converged, "Optimizer did not converge"
        assert abs(result.system_resistance_ohm - true_r_sys) < 0.001, (
            f"true R={true_r_sys}, recovered R={result.system_resistance_ohm:.5f}"
        )
        assert result.r_squared_thrust > 0.99
        assert result.rmse_thrust_g < 2.0


class TestDataQuality:
    """Edge cases and data quality handling."""

    def test_warns_on_few_points(
        self, base_motor, base_battery, base_propeller, prop_entry
    ):
        table = [ManufacturerTestPoint(rpm=4000.0, thrust_g=500.0, current_a=4.0)]

        cal = PropulsionCalibrator()
        result = cal.calibrate(
            table, base_motor, base_battery, SystemSpec(resistance_ohm=0.05),
            base_propeller, prop_entry,
        )
        assert any("valid point" in w.lower() or "fewer" in w.lower()
                   for w in result.warnings), (
            f"Expected a 'few points' warning; got: {result.warnings}"
        )

    def test_empty_table(
        self, base_motor, base_battery, base_propeller, prop_entry
    ):
        cal = PropulsionCalibrator()
        result = cal.calibrate(
            [], base_motor, base_battery, SystemSpec(resistance_ohm=0.05),
            base_propeller, prop_entry,
        )
        assert not result.converged
        assert result.n_points == 0
        assert math.isnan(result.rmse_thrust_g)

    def test_invalid_rows_are_dropped(
        self, base_motor, base_battery, base_propeller, prop_entry
    ):
        system_true = SystemSpec(resistance_ohm=0.05)
        good = _make_synthetic_table(
            base_motor, base_battery, system_true, base_propeller, prop_entry
        )
        bad = [
            ManufacturerTestPoint(rpm=-100.0, thrust_g=500.0, current_a=4.0),  # negative rpm
            ManufacturerTestPoint(rpm=4000.0, thrust_g=-10.0, current_a=4.0),  # negative thrust
            ManufacturerTestPoint(rpm=4000.0, thrust_g=500.0, current_a=-1.0),  # negative current
        ]
        table = bad + good

        cal = PropulsionCalibrator()
        result = cal.calibrate(
            table, base_motor, base_battery, SystemSpec(resistance_ohm=0.05),
            base_propeller, prop_entry,
        )
        assert result.n_points == len(good)
        assert result.converged
        assert any("dropped" in w.lower() for w in result.warnings)


class TestCSVLoader:
    """CSV loading."""

    def test_load_valid_csv(self, tmp_path):
        csv_file = tmp_path / "table.csv"
        csv_file.write_text(
            "rpm,thrust_g,current_a\n"
            "3000,182.0,3.2\n"
            "6000,680.0,13.1\n"
            "9000,1720.0,44.5\n"
        )
        points = PropulsionCalibrator.load_csv(csv_file)
        assert len(points) == 3
        assert points[0].rpm == pytest.approx(3000.0)
        assert points[0].thrust_g == pytest.approx(182.0)
        assert points[0].current_a == pytest.approx(3.2)

    def test_load_missing_required_column(self, tmp_path):
        csv_file = tmp_path / "table_missing.csv"
        csv_file.write_text(
            "rpm,thrust_g\n"
            "3000,182.0\n"
        )
        points = PropulsionCalibrator.load_csv(csv_file)
        assert len(points) == 0

    def test_load_skips_bad_rows(self, tmp_path):
        csv_file = tmp_path / "table_bad.csv"
        csv_file.write_text(
            "rpm,thrust_g,current_a\n"
            "3000,182.0,3.2\n"
            "bad,row,here\n"
            "9000,1720.0,44.5\n"
        )
        points = PropulsionCalibrator.load_csv(csv_file)
        assert len(points) == 2


class TestToSystemSpec:
    def test_to_system_spec(self):
        result = CalibrationResult(
            system_resistance_ohm=0.052,
            rmse_thrust_g=4.2,
            rmse_current_a=0.18,
            r_squared_thrust=0.998,
            n_points=8,
            converged=True,
            warnings=[],
        )
        spec = result.to_system_spec()
        assert isinstance(spec, SystemSpec)
        assert spec.resistance_ohm == pytest.approx(0.052)


class TestSecondOrderMotor:
    def test_no_load_current_exponent(self):
        motor = MotorSpec(
            kv_rpm_per_v=860.0,
            resistance_ohm=0.025,
            no_load_current_a=1.3,
            current_max_a=65.0,
            no_load_voltage_v=10.0,
            iron_loss_exponent=1.5,
        )
        assert motor.get_no_load_current(8600.0) == pytest.approx(1.3)
        assert motor.get_no_load_current(17200.0) == pytest.approx(1.3 * (2.0 ** 1.5))
        assert motor.get_no_load_current(0.0) == pytest.approx(1.3)

    def test_no_load_current_quadratic(self):
        motor = MotorSpec(
            kv_rpm_per_v=800.0,
            resistance_ohm=0.03,
            no_load_current_a=1.0,
            current_max_a=50.0,
            no_load_current_linear=0.02,
            no_load_current_quadratic=0.005,
        )
        omega = 1000.0 * math.pi / 30.0
        expected = 1.0 + 0.02 * omega + 0.005 * (omega ** 2)
        assert motor.get_no_load_current(1000.0) == pytest.approx(expected)

    def test_winding_resistance_quadratic(self):
        motor = MotorSpec(
            kv_rpm_per_v=800.0,
            resistance_ohm=0.03,
            no_load_current_a=1.0,
            current_max_a=50.0,
            resistance_quadratic=0.001,
        )
        assert motor.get_winding_resistance(10.0) == pytest.approx(0.13)
        assert motor.get_winding_resistance(0.0) == pytest.approx(0.03)

    def test_solver_with_second_order_parameters(self, prop_entry):
        motor = MotorSpec(
            kv_rpm_per_v=860.0,
            resistance_ohm=0.0258,
            no_load_current_a=1.3,
            current_max_a=65.0,
            torque_constant_kv_ratio=1.02,
            magnetic_lag_tau=1e-5,
            no_load_current_linear=0.001,
            resistance_quadratic=1e-5,
        )
        battery = BatterySpec(voltage_v=14.8)
        system = SystemSpec(resistance_ohm=0.05)
        propeller = PropellerSpec(diameter_m=0.3302)
        solver = PropulsionSolver()

        op = solver.solve_operating_point(
            motor=motor,
            battery=battery,
            system=system,
            propeller=propeller,
            prop_entry=prop_entry,
            rho=1.225,
            airspeed_mps=0.0,
            throttle=0.7,
        )
        assert op.is_feasible
        assert op.rpm > 3000.0
        assert op.motor_current_a > 1.0
        assert op.motor_voltage_v > 0.0
