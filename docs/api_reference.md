# API Reference

This page summarizes the main public classes and helpers. For implementation details, see the source modules under `pythrust/`.

## Propulsion Models

`MotorSpec` defines brushless motor electrical parameters:

| Field | Unit | Description |
|---|---:|---|
| `kv_rpm_per_v` | RPM/V | Motor speed constant |
| `resistance_ohm` | ohm | Winding resistance |
| `no_load_current_a` | A | Datasheet no-load current |
| `current_max_a` | A | Maximum continuous or configured current limit |
| `torque_constant_kv_ratio` | - | Optional second-order motor model ratio |
| `magnetic_lag_tau` | s | Optional magnetic lag time constant |
| `iron_loss_exponent` | - | Optional no-load current speed scaling exponent |

Use `get_no_load_current(rpm)` and `get_winding_resistance(current_a)` when evaluating speed-dependent or current-dependent motor behavior.

## Battery Models

PyThrust exposes battery models from `pythrust.battery`:

| Class | Purpose |
|---|---|
| `FixedVoltageBattery` | Historical fixed pack-voltage model with scalar discharge efficiency |
| `RateMapBattery` | Equivalent-circuit model using cell OCV and resistance curves |
| `BatteryState` | State of charge/depth of discharge passed to dynamic battery models |
| `BatteryPoint` | Evaluated terminal voltage, current, power, C-rate, efficiency, and feasibility |

`BatterySpec` remains available from `pythrust.propulsion` as a compatibility
alias for `FixedVoltageBattery`. New code should import `FixedVoltageBattery`
or `RateMapBattery` directly.

`RateMapBattery.from_json(path, series=..., parallel=...)` loads one cell
dataset and applies the requested pack topology at runtime.

Main `RateMapBattery` point-state helpers:

| Method | Description |
|---|---|
| `state_at_current(state, current_a)` | Evaluate voltage, power, C-rate, efficiency, and feasibility at pack current |
| `state_at_c_rate(state, c_rate)` | Evaluate the state at cell C-rate |
| `state_at_voltage(state, voltage_v)` | Evaluate current required to hold pack terminal voltage |
| `state_at_power(state, power_w)` | Evaluate current and voltage at pack terminal power |
| `state_at_load_resistance(state, resistance_ohm)` | Evaluate a resistive load |
| `state_at_power_loss(state, power_loss_w)` | Evaluate a requested pack internal loss power |

Main `RateMapBattery` integration helpers:

| Method | Description |
|---|---|
| `integrate_current(...)` | Integrate over time at constant pack current |
| `integrate_c_rate(...)` | Integrate over time at constant cell C-rate |
| `integrate_power(...)` | Integrate over time at constant pack terminal power |
| `integrate_voltage(...)` | Integrate over time at constant pack terminal voltage |
| `integrate_load_resistance(...)` | Integrate over time at constant pack load resistance |
| `integrate_power_loss(...)` | Integrate over time at constant pack internal loss power |
| `integrate_current_to_dod(...)` | Integrate constant current until target DOD |
| `integrate_c_rate_to_dod(...)` | Integrate constant C-rate until target DOD |
| `integrate_power_to_dod(...)` | Integrate constant power until target DOD |
| `integrate_voltage_to_dod(...)` | Integrate constant voltage until target DOD |
| `integrate_load_resistance_to_dod(...)` | Integrate constant load resistance until target DOD |
| `integrate_power_loss_to_dod(...)` | Integrate constant internal loss power until target DOD |
| `integrate_power_profile(...)` | Integrate consecutive constant-power mission segments |

`BatteryIntegrationResult` reports final state, sampled histories, delivered
energy, consumed charge, feasibility, and stop reason.

## System and Propeller Specs

| Class | Purpose |
|---|---|
| `SystemSpec` | Lumped electrical resistance for battery, ESC, wires, and connectors |
| `PropellerSpec` | Propeller geometry passed to the solver |
| `OperatingPoint` | Solved RPM, thrust, torque, motor/battery current, voltage, efficiency, and feasibility state |

## Propulsion Solver

`PropulsionSolver` solves the coupled electrical and aerodynamic equilibrium for a single operating condition:

```python
point = solver.solve_operating_point(
    motor=motor,
    battery=battery,
    battery_state=state,  # required for RateMapBattery
    system=system,
    propeller=propeller,
    prop_entry=prop_entry,
    rho=1.225,
    airspeed_mps=15.0,
    throttle=0.7,
)
```

`battery_state` may be omitted for `FixedVoltageBattery`. It is required for
dynamic battery models such as `RateMapBattery`.

`SolverConfig` controls numerical behavior:

| Field | Default | Description |
|---|---:|---|
| `rpm_min` | `100.0` | Lower RPM bound |
| `rpm_max_margin` | `1.1` | Safety factor on estimated maximum RPM |
| `eps_rpm` | `1e-8` | RPM convergence tolerance |
| `eps_v` | `1e-8` | Voltage residual tolerance |
| `max_iter` | `100` | Maximum root-finder iterations |

`OperatingPoint` includes propulsion outputs such as `rpm`, `thrust_n`,
`torque_nm`, `motor_current_a`, and `motor_voltage_v`, plus battery outputs:

| Field | Description |
|---|---|
| `battery_power_w` | Battery-side power draw |
| `battery_voltage_v` | Battery terminal pack voltage |
| `battery_current_a` | Battery DC current draw |
| `battery_c_rate` | Cell C-rate for rate-map batteries, or `0.0` for fixed-voltage batteries |
| `battery_efficiency` | Battery model discharge efficiency at the solved point |

## Propeller Database

`PropellerDatabase` loads JSON metadata and CSV performance tables:

```python
from pathlib import Path
from pythrust.propellers import PropellerDatabase

db = PropellerDatabase()
db.load(Path("data/propellers/apc_202602"), strict=False)
entry = db.get("APC_13x6.5E")
ct, cp = entry.get_coefficients(rpm=5000.0, advance_ratio=0.4)
```

Main helpers:

| Method | Description |
|---|---|
| `load(data_dir, strict=False)` | Load every propeller JSON file in a directory |
| `load_entry(json_path, data_dir=None, strict=False)` | Load one propeller entry |
| `list_propellers()` | Return sorted propeller IDs |
| `get(prop_id)` | Return a `PropellerEntry` by ID |
| `find_by_size(diameter_in, pitch_in, blade_count=2, tolerance=0.5)` | Find the closest size match |
| `get_interpolated_coefficients(...)` | Fetch `Ct` and `Cp` through a size lookup |

## Motor Database

`MotorDatabase` loads brushless motor JSON files and converts catalog entries into solver specs:

```python
from pathlib import Path
from pythrust.motors import MotorDatabase

db = MotorDatabase()
db.load(Path("data/motors"))
motor_entry = db.get("SunnySky_X2826_KV550")
motor = motor_entry.to_spec()
```

Main helpers:

| Method | Description |
|---|---|
| `load(data_dir)` | Recursively load motor JSON files |
| `load_entry(json_path)` | Load one motor JSON file |
| `list_motors()` | Return sorted motor IDs |
| `get(motor_id)` | Return a `MotorEntry` by ID |
| `search(...)` | Filter by Kv, current, and weight constraints |

## Calibration

`PropulsionCalibrator` fits `SystemSpec.resistance_ohm` against manufacturer or thrust-stand data:

```python
from pythrust.propulsion import PropulsionCalibrator

calibrator = PropulsionCalibrator(system_bounds=(0.0, 1.0))
points = calibrator.load_csv("table.csv")
result = calibrator.calibrate(
    points,
    motor,
    battery,
    system,
    propeller,
    prop_entry,
)
system = result.to_system_spec()
```

`CalibrationResult` reports fitted resistance, thrust/current RMSE values, thrust `R^2`, convergence status, and quality warnings.

## OpenMDAO

`pythrust.openmdao.PropulsionComponent` wraps `PropulsionSolver` as an `ExplicitComponent` for optimization models.

Inputs include motor parameters, fixed battery voltage, system resistance, propeller diameter, throttle, density, and airspeed. Outputs include RPM, thrust, torque, battery current, battery power, motor current, motor voltage, and feasibility.
