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

## Battery, System, and Propeller Specs

| Class | Purpose |
|---|---|
| `BatterySpec` | Pack voltage and discharge efficiency |
| `SystemSpec` | Lumped electrical resistance for battery, ESC, wires, and connectors |
| `PropellerSpec` | Propeller geometry passed to the solver |
| `OperatingPoint` | Solved RPM, thrust, torque, power, current, voltage, efficiency, and feasibility state |

## Propulsion Solver

`PropulsionSolver` solves the coupled electrical and aerodynamic equilibrium for a single operating condition:

```python
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
```

`SolverConfig` controls numerical behavior:

| Field | Default | Description |
|---|---:|---|
| `rpm_min` | `100.0` | Lower RPM bound |
| `rpm_max_margin` | `1.1` | Safety factor on estimated maximum RPM |
| `eps_rpm` | `1e-8` | RPM convergence tolerance |
| `eps_v` | `1e-8` | Voltage residual tolerance |
| `max_iter` | `100` | Maximum root-finder iterations |

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

Inputs include motor parameters, battery voltage, system resistance, propeller diameter, throttle, density, and airspeed. Outputs include RPM, thrust, torque, battery current, battery power, motor current, motor voltage, and feasibility.
