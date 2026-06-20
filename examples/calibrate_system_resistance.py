"""Calibrate system resistance from a manufacturer thrust/current table.

This example demonstrates how to use PropulsionCalibrator to identify the
system resistance parameter so PyThrust's fixed-voltage propulsion model
matches the manufacturer's performance data.

Usage::

    PYTHONPATH=. python examples/calibrate_system_resistance.py
"""

import math
from pathlib import Path

from pythrust.battery import FixedVoltageBattery
from pythrust.propellers import PropellerDatabase
from pythrust.propulsion import (
    MotorSpec,
    PropellerSpec,
    SystemSpec,
)
from pythrust.propulsion.autotune import ManufacturerTestPoint, PropulsionCalibrator

# 1. Motor parameters taken directly from the manufacturer datasheet.
motor = MotorSpec(
    kv_rpm_per_v=860.0,        # RPM/V
    resistance_ohm=0.0258,     # Ohm, terminal resistance
    no_load_current_a=1.3,     # A, idle current at rated voltage
    current_max_a=65.0,        # A, continuous current limit
)

# 2. Fixed-voltage battery, initial system resistance, and propeller geometry.
battery = FixedVoltageBattery(voltage_v=14.8)   # 4S LiPo at nominal voltage
system = SystemSpec(resistance_ohm=0.05)        # initial guess, fitted below
propeller = PropellerSpec(diameter_m=0.3302)    # 13-inch propeller

# 3. Load propeller aerodynamic data.
db = PropellerDatabase()
db.load(Path("data/propellers/apc_202602"), strict=False)
prop_entry = db.get("APC_13x6.5E")
if prop_entry is None:
    raise SystemExit("Propeller 'APC_13x6.5E' not found in dataset.")

# 4. Manufacturer test table: RPM, thrust in grams, and battery current in amps.
RAW_TABLE = [
    {"rpm": 3897, "thrust_g": 500, "current_a": 3.9},
    {"rpm": 4804, "thrust_g": 750, "current_a": 6.7},
    {"rpm": 5421, "thrust_g": 1000, "current_a": 10.2},
    {"rpm": 6071, "thrust_g": 1250, "current_a": 13.9},
    {"rpm": 6564, "thrust_g": 1500, "current_a": 18.1},
    {"rpm": 7077, "thrust_g": 1750, "current_a": 22.6},
    {"rpm": 7560, "thrust_g": 2000, "current_a": 27.6},
    {"rpm": 8016, "thrust_g": 2250, "current_a": 33.5},
    {"rpm": 8346, "thrust_g": 2500, "current_a": 40.1},
    {"rpm": 8695, "thrust_g": 2750, "current_a": 47.5},
    {"rpm": 9230, "thrust_g": 3350, "current_a": 63.2},
]
points = [
    ManufacturerTestPoint(
        rpm=row["rpm"],
        thrust_g=row["thrust_g"],
        current_a=row["current_a"],
    )
    for row in RAW_TABLE
]

# 5. Calibrate the lumped system resistance.
calibrator = PropulsionCalibrator()
result = calibrator.calibrate(
    points, motor, battery, system, propeller, prop_entry, rho=1.225
)

print("--- Calibration Result --------------------------------------")
print(f"  System resistance : {result.system_resistance_ohm:.5f} ohm")
print(f"  Thrust RMSE       : {result.rmse_thrust_g:.1f} g")
print(f"  Current RMSE      : {result.rmse_current_a:.2f} A")
print(f"  R^2 (thrust)      : {result.r_squared_thrust:.4f}")
print(f"  Converged         : {result.converged}")
print(f"  Points used       : {result.n_points}")
for w in result.warnings:
    print(f"  WARNING: {w}")
print()

# 6. Validate by comparing predictions against the table at each RPM.
system_calibrated = result.to_system_spec()
kt = 60.0 / (2.0 * math.pi * motor.kv_rpm_per_v)

header = f"{'RPM':>6}  {'Thrust Pred':>12}  {'Thrust Meas':>12}  {'Thrust Err':>11}  {'Current Pred':>13}  {'Current Meas':>13}  {'Current Err':>11}"
print(header)
print("-" * len(header))
for pt in points:
    n = pt.rpm / 60.0
    ct, cp = prop_entry.get_coefficients(pt.rpm, 0.0)
    torque_nm = cp * 1.225 * (n ** 2) * (propeller.diameter_m ** 5) / (2.0 * math.pi)
    i_motor = torque_nm / kt + motor.no_load_current_a
    v_back = pt.rpm / motor.kv_rpm_per_v
    v_m = v_back + i_motor * motor.resistance_ohm
    
    thrust_pred_g = ct * 1.225 * (n ** 2) * (propeller.diameter_m ** 4) * 1000.0 / 9.80665
    current_pred_a = (v_m * i_motor + (i_motor ** 2) * system_calibrated.resistance_ohm) / battery.voltage_v
    
    t_err = thrust_pred_g - pt.thrust_g
    c_err = current_pred_a - pt.current_a
    
    print(
        f"{pt.rpm:>6.0f}  "
        f"{thrust_pred_g:>10.0f} g  "
        f"{pt.thrust_g:>10.0f} g  "
        f"{t_err:>+9.1f} g  "
        f"{current_pred_a:>11.2f} A  "
        f"{pt.current_a:>11.2f} A  "
        f"{c_err:>+9.2f} A"
    )
