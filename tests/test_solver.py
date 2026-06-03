import math
import pytest
from pythrust.propellers.database import (
    PropellerMetadata,
    PropellerDataPoint,
    PropellerEntry
)
from pythrust.propulsion.models import (
    MotorSpec,
    BatterySpec,
    SystemSpec,
    PropellerSpec,
    OperatingPoint
)
from pythrust.propulsion.solver import PropulsionSolver, SolverConfig


@pytest.fixture
def test_setup():
    motor = MotorSpec(
        kv_rpm_per_v=980.0,
        resistance_ohm=0.06,
        no_load_current_a=1.2,
        current_max_a=30.0,
        torque_constant_kv_ratio=1.0,
        magnetic_lag_tau=0.0001
    )
    battery = BatterySpec(voltage_v=11.1, discharge_efficiency=0.98)
    system = SystemSpec(resistance_ohm=0.015)
    propeller = PropellerSpec(diameter_m=0.254, blade_count=2, pitch_m=0.114)
    
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
        1000.0: [
            PropellerDataPoint(j=0.0, ct=0.11, cp=0.055),
            PropellerDataPoint(j=0.4, ct=0.08, cp=0.04),
            PropellerDataPoint(j=0.8, ct=0.02, cp=0.01)
        ],
        8000.0: [
            PropellerDataPoint(j=0.0, ct=0.12, cp=0.06),
            PropellerDataPoint(j=0.4, ct=0.09, cp=0.045),
            PropellerDataPoint(j=0.8, ct=0.03, cp=0.015)
        ]
    }
    
    prop_entry = PropellerEntry(metadata=meta, data_by_rpm=data)
    
    return motor, battery, system, propeller, prop_entry


def test_solver_zero_throttle(test_setup):
    motor, battery, system, propeller, prop_entry = test_setup
    solver = PropulsionSolver()
    
    op = solver.solve_operating_point(
        motor=motor,
        battery=battery,
        system=system,
        propeller=propeller,
        prop_entry=prop_entry,
        rho=1.225,
        airspeed_mps=0.0,
        throttle=0.0
    )
    
    assert op.rpm == 0.0
    assert op.is_feasible is False
    assert op.infeasible_reason == "throttle<=0"


def test_solver_successful_solve(test_setup):
    motor, battery, system, propeller, prop_entry = test_setup
    solver = PropulsionSolver()
    
    # Use static thrust (airspeed = 0.0) to avoid numeric edge issues on J
    op = solver.solve_operating_point(
        motor=motor,
        battery=battery,
        system=system,
        propeller=propeller,
        prop_entry=prop_entry,
        rho=1.225,
        airspeed_mps=0.0,
        throttle=0.8
    )
    
    # It should successfully converge to a positive RPM and be feasible
    assert op.is_feasible is True
    assert op.rpm > 0.0
    assert op.advance_ratio == 0.0
    assert op.ct > 0.0
    assert op.cp > 0.0
    assert op.thrust_n > 0.0
    assert op.torque_nm > 0.0
    
    # Test backing variables consistency
    # V_applied = 0.8 * 11.1 = 8.88V
    # V_motor + I * R_sys = V_applied
    v_applied = 0.8 * battery.voltage_v
    v_motor = op.motor_voltage_v
    i_sys = op.motor_current_a
    assert math.isclose(v_motor + i_sys * system.resistance_ohm, v_applied, rel_tol=1e-3)


def test_solver_current_limit_exceeded(test_setup):
    motor, battery, system, propeller, prop_entry = test_setup
    # Create a motor with a very low current limit to force current_limit infeasibility
    low_limit_motor = MotorSpec(
        kv_rpm_per_v=motor.kv_rpm_per_v,
        resistance_ohm=motor.resistance_ohm,
        no_load_current_a=motor.no_load_current_a,
        current_max_a=1.0  # Extremely low current limit
    )
    
    solver = PropulsionSolver()
    op = solver.solve_operating_point(
        motor=low_limit_motor,
        battery=battery,
        system=system,
        propeller=propeller,
        prop_entry=prop_entry,
        rho=1.225,
        airspeed_mps=0.0,
        throttle=0.9
    )
    
    assert op.is_feasible is False
    assert op.infeasible_reason == "current_limit"


def test_solver_no_bracket(test_setup):
    motor, battery, system, propeller, prop_entry = test_setup
    # Set high airspeed, so at low RPM the advance ratio is huge (past J_max)
    # causing cp <= 0 and evaluate_state returning inf, or v_motor > v_applied.
    solver = PropulsionSolver()
    op = solver.solve_operating_point(
        motor=motor,
        battery=battery,
        system=system,
        propeller=propeller,
        prop_entry=prop_entry,
        rho=1.225,
        airspeed_mps=100.0,  # Unrealistic high speed
        throttle=0.1         # Very low throttle
    )
    
    assert op.is_feasible is False
    assert op.infeasible_reason == "no_bracket"


def test_estimate_j_max(test_setup):
    _, _, _, _, prop_entry = test_setup
    
    # 1. Standard estimation
    # j_max values from data: 0.8 at 1000.0 RPM, 0.8 at 8000.0 RPM.
    # List of j_maxes is [0.8, 0.8]. Sorted.
    # len is 2. start = 2 // 4 = 0.
    # Should return j_maxes[0] = 0.8
    assert PropulsionSolver._estimate_j_max(prop_entry) == 0.8
    
    # 2. Empty data_by_rpm
    empty_meta = PropellerMetadata("empty", "A", "B", 10.0, 5.0, 2, "csv")
    empty_entry = PropellerEntry(metadata=empty_meta, data_by_rpm={})
    assert PropulsionSolver._estimate_j_max(empty_entry) == 0.6


def test_solver_efficiencies(test_setup):
    motor, battery, system, propeller, prop_entry = test_setup
    # Configure higher rpm_min to prevent rpm_min J from exceeding j_max and returning inf
    solver = PropulsionSolver(SolverConfig(rpm_min=2000.0))

    # 1. Static case (airspeed = 0)
    op_static = solver.solve_operating_point(
        motor=motor,
        battery=battery,
        system=system,
        propeller=propeller,
        prop_entry=prop_entry,
        rho=1.225,
        airspeed_mps=0.0,
        throttle=0.8
    )
    assert op_static.is_feasible is True
    assert op_static.propeller_efficiency == 0.0
    assert op_static.system_efficiency == 0.0
    assert 0.0 < op_static.motor_efficiency <= 1.0

    # 2. Dynamic case (airspeed = 5.0 m/s)
    op_dynamic = solver.solve_operating_point(
        motor=motor,
        battery=battery,
        system=system,
        propeller=propeller,
        prop_entry=prop_entry,
        rho=1.225,
        airspeed_mps=5.0,
        throttle=0.8
    )
    assert op_dynamic.is_feasible is True
    # Efficiencies should be positive and physically reasonable
    assert 0.0 < op_dynamic.propeller_efficiency <= 1.0
    assert 0.0 < op_dynamic.motor_efficiency <= 1.0
    assert 0.0 < op_dynamic.system_efficiency <= 1.0
    
    # System efficiency should be propeller_eff * motor_eff * battery_discharge_eff approximately
    # Since battery discharge efficiency is 0.98 and sys resistance is small:
    # eta_sys = (T * V) / P_battery. eta_motor = P_shaft / P_motor. eta_prop = (T * V) / P_shaft.
    # P_battery = (P_motor + I^2 * R_sys) / eta_batt_discharge.
    # Let's verify mathematically:
    expected_sys = op_dynamic.propeller_efficiency * op_dynamic.motor_efficiency
    # Since there are small electrical line losses (R_sys = 0.015) and battery efficiency (0.98),
    # actual system efficiency will be slightly lower than expected_sys.
    assert op_dynamic.system_efficiency <= expected_sys + 1e-5


def test_solver_invalid_efficiency(test_setup):
    motor, battery, system, propeller, _ = test_setup
    
    # Create custom propeller data where Ct/Cp = 15.0 at J = 0.2
    # With J = 0.2, eta_prop = (Ct/Cp) * J = 15.0 * 0.2 = 3.0 (> 1.0)
    meta = PropellerMetadata(
        id="bad_prop",
        manufacturer="APC",
        model="SF",
        diameter_in=10.0,
        pitch_in=4.7,
        blade_count=2,
        data_csv="bad.csv"
    )
    data = {
        8000.0: [
            PropellerDataPoint(j=0.0, ct=0.12, cp=0.06),
            PropellerDataPoint(j=0.2, ct=0.15, cp=0.01),
            PropellerDataPoint(j=0.8, ct=0.02, cp=0.01)
        ]
    }
    bad_entry = PropellerEntry(metadata=meta, data_by_rpm=data)
    
    solver = PropulsionSolver(SolverConfig(rpm_min=2000.0))
    # Solve at airspeed = 5.0 m/s to land J near 0.2
    op = solver.solve_operating_point(
        motor=motor,
        battery=battery,
        system=system,
        propeller=propeller,
        prop_entry=bad_entry,
        rho=1.225,
        airspeed_mps=5.0,
        throttle=0.8
    )
    
    # The solver should calculate the point but mark it infeasible
    assert op.is_feasible is False
    assert op.infeasible_reason == "invalid_efficiency"


