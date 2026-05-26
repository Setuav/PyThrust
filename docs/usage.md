# Propulsion Solver User & API Guide

This guide describes how to configure, run, and analyze the equilibrium RPM propulsion solver for single operating points and sweeps.

## 1) Problem Statement

For a given throttle setting, flight airspeed, and propeller/motor specification, PyThrust solves for the equilibrium shaft speed (RPM) such that the motor's internal terminal voltage matches the applied throttle voltage:

$$
g(\text{RPM}) = V_{\text{back}}(\text{RPM}) + I(\text{RPM}) R + I(\text{RPM}) R_{\text{system}} - \text{throttle} \times V_{\text{pack}} = 0
$$

Once the root of $g(\text{RPM}) = 0$ is found, the solver evaluates the complete aerodynamic and electrical state (thrust, torque, currents, powers, efficiency).

---

## 2) Solver Configuration (`SolverConfig`)

The numerical behavior of the root finder is controlled by `SolverConfig`:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `rpm_min` | `float` | `100.0` | Lower bound limit for RPM |
| `rpm_max_margin` | `float` | `1.1` | Safety scaling factor applied to calculated max RPM upper bound |
| `eps_rpm` | `float` | `1e-8` | Convergence tolerance for shaft speed (RPM) |
| `eps_v` | `float` | `1e-8` | Convergence tolerance for terminal voltage residuals |
| `max_iter` | `int` | `100` | Maximum iterations permitted for root finder |

---

## 3) Example Usage

Here is a complete example showing how to load a propeller dataset, define specifications, and solve for an operating point:

```python
from pathlib import Path
from pythrust.propellers import PropellerDatabase
from pythrust.propulsion import (
    BatterySpec,
    MotorSpec,
    PropellerSpec,
    SystemSpec,
    PropulsionSolver,
)

# 1. Load propeller aerodynamic dataset
db = PropellerDatabase()
db.load(Path("data/propellers/apc_202602"), strict=False)
prop_entry = db.get("APC_13x6.5E")

# 2. Define component specifications
motor = MotorSpec(
    kv_rpm_per_v=860.0,
    resistance_ohm=0.0258,
    no_load_current_a=1.3,
    current_max_a=65.0,
)

battery = BatterySpec(
    voltage_v=14.8,
    discharge_efficiency=1.0
)

system = SystemSpec(resistance_ohm=0.05)
propeller = PropellerSpec(diameter_m=0.3302, blade_count=2)

# 3. Solve operating point
solver = PropulsionSolver()
point = solver.solve_operating_point(
    motor=motor,
    battery=battery,
    system=system,
    propeller=propeller,
    prop_entry=prop_entry,
    rho=1.225,
    airspeed_mps=15.0,
    throttle=0.7,
)

# 4. View results
print(f"RPM               : {point.rpm:.1f}")
print(f"Thrust            : {point.thrust_n:.2f} N")
print(f"Battery Current   : {point.battery_power_w / battery.voltage_v:.2f} A")
print(f"Is Feasible       : {point.is_feasible}")
```

---

## 4) Feasibility Rules

An operating point is marked as infeasible (`point.is_feasible = False`) if:
- `motor_current_a > current_max_a` (motor current limit exceeded)
- `ct < 0` or `cp < 0` or `advance_ratio < 0` (aerodynamic coefficients out of physical range)
- No valid RPM bracket with a voltage sign change is found.
