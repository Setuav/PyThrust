import math
import pytest
from pythrust.propulsion.models import (
    MotorSpec,
    BatterySpec,
    SystemSpec,
    PropellerSpec,
    OperatingPoint
)


def test_motor_spec_no_load_current():
    # 1. Base case: rpm <= 0
    motor = MotorSpec(
        kv_rpm_per_v=980.0,
        resistance_ohm=0.06,
        no_load_current_a=1.2,
        current_max_a=30.0
    )
    assert motor.get_no_load_current(-10.0) == 1.2
    assert motor.get_no_load_current(0.0) == 1.2

    # 2. Power-law iron loss (iron_loss_exponent > 0)
    # rpm_0 = kv_rpm_per_v * no_load_voltage_v = 980.0 * 10.0 = 9800.0
    # rpm = 4900.0 -> (4900.0 / 9800.0)^1.5 = 0.5^1.5 approx 0.35355
    # no_load_current = 1.2 * 0.35355 = 0.42426
    motor_iron = MotorSpec(
        kv_rpm_per_v=980.0,
        resistance_ohm=0.06,
        no_load_current_a=1.2,
        current_max_a=30.0,
        no_load_voltage_v=10.0,
        iron_loss_exponent=1.5
    )
    expected_rpm_0 = 980.0 * 10.0
    expected_current = 1.2 * (4900.0 / expected_rpm_0) ** 1.5
    assert math.isclose(motor_iron.get_no_load_current(4900.0), expected_current)

    # 3. Drela's quadratic speed model (iron_loss_exponent = 0.0)
    # omega = rpm * pi / 30 = 3000 * pi / 30 = 100 * pi
    # Io = Io0 + Io1 * omega + Io2 * omega^2
    motor_drela = MotorSpec(
        kv_rpm_per_v=980.0,
        resistance_ohm=0.06,
        no_load_current_a=1.2,
        current_max_a=30.0,
        no_load_current_linear=0.001,
        no_load_current_quadratic=0.00002
    )
    omega = 3000.0 * (math.pi / 30.0)
    expected_drela = 1.2 + 0.001 * omega + 0.00002 * (omega ** 2)
    assert math.isclose(motor_drela.get_no_load_current(3000.0), expected_drela)


def test_motor_spec_winding_resistance():
    # 1. Base case: resistance_quadratic <= 0
    motor = MotorSpec(
        kv_rpm_per_v=980.0,
        resistance_ohm=0.06,
        no_load_current_a=1.2,
        current_max_a=30.0
    )
    assert motor.get_winding_resistance(10.0) == 0.06
    assert motor.get_winding_resistance(-5.0) == 0.06

    # 2. Quadratic resistance (resistance_quadratic > 0)
    # R = R_base + R_quad * I^2 = 0.06 + 0.002 * 10^2 = 0.06 + 0.2 = 0.26
    motor_quad = MotorSpec(
        kv_rpm_per_v=980.0,
        resistance_ohm=0.06,
        no_load_current_a=1.2,
        current_max_a=30.0,
        resistance_quadratic=0.002
    )
    assert math.isclose(motor_quad.get_winding_resistance(10.0), 0.26)


def test_other_specs():
    battery = BatterySpec(voltage_v=11.1, discharge_efficiency=0.98)
    assert battery.voltage_v == 11.1
    assert battery.discharge_efficiency == 0.98

    system = SystemSpec(resistance_ohm=0.015)
    assert system.resistance_ohm == 0.015

    propeller = PropellerSpec(diameter_m=0.254, blade_count=3, pitch_m=0.114)
    assert propeller.diameter_m == 0.254
    assert propeller.blade_count == 3
    assert propeller.pitch_m == 0.114


def test_operating_point():
    op = OperatingPoint(
        rpm=8000.0,
        advance_ratio=0.4,
        ct=0.08,
        cp=0.04,
        thrust_n=15.0,
        torque_nm=0.3,
        shaft_power_w=250.0,
        motor_power_w=300.0,
        battery_power_w=310.0,
        motor_current_a=25.0,
        motor_voltage_v=12.0,
        is_feasible=True,
        propeller_efficiency=0.65,
        motor_efficiency=0.83,
        system_efficiency=0.5395
    )
    assert op.rpm == 8000.0
    assert op.is_feasible is True
    assert op.infeasible_reason is None
    assert op.propeller_efficiency == 0.65
    assert op.motor_efficiency == 0.83
    assert op.system_efficiency == 0.5395

    # Test default values
    op_default = OperatingPoint(
        rpm=8000.0,
        advance_ratio=0.4,
        ct=0.08,
        cp=0.04,
        thrust_n=15.0,
        torque_nm=0.3,
        shaft_power_w=250.0,
        motor_power_w=300.0,
        battery_power_w=310.0,
        motor_current_a=25.0,
        motor_voltage_v=12.0,
        is_feasible=True
    )
    assert op_default.propeller_efficiency == 0.0
    assert op_default.motor_efficiency == 0.0
    assert op_default.system_efficiency == 0.0

