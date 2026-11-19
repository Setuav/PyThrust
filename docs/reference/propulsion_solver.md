# Propulsion Solver

`PropulsionSolver` finds the shaft RPM at which the motor's electrical model
and the propeller's aerodynamic load agree, for a motor, propeller, battery,
throttle and airspeed. `BusSolver` does the same for several propulsion units
sharing one battery network.

## Symbols

| Symbol | Meaning |
|---|---|
| $\text{RPM}$ | Propeller shaft speed being solved |
| $n$ | Shaft speed in revolutions per second |
| $T$ | Thrust |
| $Q$ | Propeller shaft torque |
| $I$ | Motor winding current |
| $I_0$ | No-load current |
| $R_m$ | Motor winding resistance |
| $R_{\text{system}}$ | Lumped system resistance |
| $V_{\text{back}}$ | Motor back-EMF voltage |
| $V_m$ | Motor terminal voltage |
| $V_{\text{pack}}$ | Battery pack voltage |
| $x$ | Battery depth of discharge |
| $V_{\text{applied}}$ | Average voltage the throttle applies to the motor |

## System Resistance and Power Chain

The voltage drops across ESC MOSFETs, battery internal resistance, cables, and connectors are modeled as a lumped transmission system resistance ($R_{\text{system}}$):

$$
V_m = \text{throttle} \times V_{\text{pack}} - I R_{\text{system}}
$$

The overall electrical power drawn from the battery pack is:

$$
P_{\text{battery}} = \frac{V_m I + I^2 R_{\text{system}}}{\eta_{\text{discharge}}}
$$

For `RateMapBattery`, the equivalent-circuit terminal voltage already captures
the cell-level voltage sag from the battery curves. `R_system` should still be
used for wiring, ESC, connector, or other losses outside the battery model.

## Equilibrium RPM

The throttle command defines the average voltage available from the battery:

$$
V_{\text{applied}} =
\text{throttle} \cdot V_{\text{pack}}
$$

For `FixedVoltageBattery`, `V_pack` is the configured pack voltage. For
`RateMapBattery`, `V_pack` is evaluated from the current battery state and the
current implied by the candidate RPM:

!!! note "Rate-map batteries are state dependent"
    A `RateMapBattery` solve needs a `BatteryState` because terminal voltage depends on both depth of discharge and current.

$$
V_{\text{pack}} = V_{\text{pack}}(x, I)
$$

The solver searches for the RPM where the motor voltage demand plus system voltage drop equals the applied voltage:

$$
g(\text{RPM}) =
V_m(\text{RPM})
+ I(\text{RPM}) R_{\text{system}}
- V_{\text{applied}}
$$

The equilibrium point is:

$$
g(\text{RPM}) = 0
$$

PyThrust solves this scalar root-finding problem with Brent's method through `scipy.optimize.root_scalar`.

## RPM Bracket

Before solving, PyThrust builds a search interval:

| Bound | How it is chosen |
|---|---|
| Lower RPM | At least `SolverConfig.rpm_min`; raised if airspeed and propeller `J` range require a higher RPM |
| Upper RPM | Estimated from `motor.kv_rpm_per_v * battery.terminal_voltage(0 A) * throttle`, then expanded by `rpm_max_margin` |

If the residual does not change sign inside the bracket, the point is returned as infeasible with reason `no_bracket`.

Where the propeller model gives NaN, the residual has no value. If it has none
at the lower bound, as past the end of a table, the solver raises the lower
bound to the lowest RPM where it has one. Negative thrust or torque counts as
a value, so a blade-element propeller needs no such search.

## API

### Solving an Operating Point

`PropulsionSolver` solves the coupled electrical and aerodynamic equilibrium for a single operating condition:

```python
point = solver.solve_operating_point(
    motor=motor,
    battery=battery,
    battery_state=state,  # required for RateMapBattery
    system=system,
    propeller=propeller,
    rho=1.225,
    airspeed_mps=15.0,
    throttle=0.7,
)
```

`battery_state` may be omitted for `FixedVoltageBattery`. It is required for
dynamic battery models such as `RateMapBattery`.

| Class | Purpose |
|---|---|
| `SystemSpec` | Lumped resistance of the ESC, wires and connectors, and the ESC's optional motor-side current limit |
| `OperatingPoint` | Solved RPM, thrust, torque, motor/battery current, voltage, efficiency, and feasibility state |

### Solver Configuration

The numerical behavior of the root finder is controlled by `SolverConfig`:

| Parameter | Type | Default | Description |
|---|---|---:|---|
| `rpm_min` | `float` | `100.0` | Lower bound limit for RPM |
| `rpm_max_margin` | `float` | `1.1` | Safety scaling factor applied to the upper RPM estimate |
| `eps_rpm` | `float` | `1e-8` | Convergence tolerance for shaft speed |
| `eps_v` | `float` | `1e-8` | Voltage residual tolerance |
| `max_iter` | `int` | `100` | Maximum root-finder iterations |

### Result Fields

`solve_operating_point(...)` returns an `OperatingPoint`:

| Field | Meaning |
|---|---|
| `rpm` | Solved shaft speed |
| `advance_ratio` | Propeller advance ratio at the solved point |
| `ct`, `cp` | Thrust and power coefficients at the solved point |
| `thrust_n` | Thrust force |
| `torque_nm` | Propeller shaft torque |
| `shaft_power_w` | Mechanical shaft power |
| `motor_power_w` | Electrical power at motor terminals |
| `battery_power_w` | Battery-side power including system losses |
| `battery_voltage_v` | Battery terminal pack voltage at the solved point |
| `battery_current_a` | Battery DC current draw at the solved point |
| `battery_c_rate` | Cell C-rate for rate-map batteries, or `0.0` for fixed-voltage batteries |
| `battery_efficiency` | Discharge efficiency from the active battery model |
| `motor_current_a` | Motor winding current |
| `motor_voltage_v` | Motor terminal voltage |
| `propeller_efficiency` | Propulsive efficiency based on thrust power |
| `motor_efficiency` | Shaft power divided by motor electrical power |
| `system_efficiency` | Thrust power divided by battery power |
| `is_feasible` | Whether the point passed feasibility checks |
| `infeasible_reason` | Reason string when `is_feasible` is false |

### Feasibility Rules

An operating point is marked as infeasible when one of these checks fails:

| Reason | Meaning |
|---|---|
| `throttle<=0` | No positive throttle command |
| `no_bracket` | The RPM search interval does not contain a valid voltage-balance root |
| `no_convergence` | The root finder did not converge |
| `current_limit` | `motor_current_a` exceeds `current_max_a` |
| `esc_current_limit` | `motor_current_a` exceeds the `SystemSpec`'s `max_current_a` |
| `battery_current_limit` | Rate-map battery current exceeds the configured cell current limit |
| `battery_voltage_cutoff` | Rate-map battery terminal cell voltage falls below cutoff |
| `battery_voltage_limit` | Rate-map battery terminal cell voltage exceeds the configured charge voltage |
| `battery_state_limit` | Rate-map battery state is outside the valid range |
| `invalid_coefficients` | Propeller coefficient lookup produced non-physical values |
| `invalid_efficiency` | Computed efficiency is outside the physically expected range |

## Bus Solver

`BusSolver` solves several propulsion units that share one `BatteryNetwork`,
each at its own throttle. A `PropulsionUnit` holds a motor, its propeller and
its `SystemSpec`. The bus voltage sags with the units' total current:

```python
from pythrust.propulsion import BusSolver, PropulsionUnit

bus = BusSolver().solve(
    network,
    network.full_state(),
    units=[left_unit, right_unit],
    throttles=[0.7, 0.7],
    rho=1.225,
    airspeed_mps=15.0,
)
bus.voltage_v, bus.current_a, bus.thrust_n, bus.units, bus.network.packs
```

A unit at zero throttle draws no current. The point is infeasible when a unit
exceeds its motor or ESC current limit, a pack leaves its operating limits, a unit
has no operating point (its reason is prefixed with `unit_<index>_`), or the
network cannot supply the units' current at any voltage they run at
(`bus_overload`). An infeasible point need not balance the network.
