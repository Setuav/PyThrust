# Battery Model

PyThrust supports a fixed-voltage battery model and a lightweight rate-map
battery model. The fixed-voltage path is useful for quick propulsion sizing,
but it hides two effects that matter for electric aircraft performance studies:

- The terminal voltage drops with load.
- The usable energy depends on discharge rate and state of charge.

This page defines the rate-map model now implemented in PyThrust. The model is
inspired by Robert A. McDonald's
`bat-perf` model and the paper "Battery Knockdown Factors for Conceptual
Design".

!!! abstract "Model scope"
    PyThrust uses a compact equivalent-circuit battery model for sizing and optimization. It is intended to capture voltage sag and usable energy trends without introducing electrochemical simulation inputs.

## Goals

The model is intended to:

- Stay fast enough for sizing sweeps, optimizers, and OpenMDAO workflows.
- Use manufacturer-accessible data such as capacity, voltage limits, current
  limits, discharge curves, and C-rate maps.
- Support point-performance analysis at a specified state of charge.
- Support mission integration by advancing battery state through time.
- Preserve a simple fixed-voltage battery path for examples and low-fidelity
  studies.

The model does not try to replace electrochemical simulation tools. PyThrust
does not need electrode-level parameters, diffusion constants, thermal cell
models, or PyBaMM-style electrochemistry for this feature.

## Core Equations

The paper treats battery state with two governing equations: conservation of
charge and an algebraic terminal-voltage equation.

Depth of discharge is:

$$
x = 1 - z
$$

where $z$ is state of charge. With discharge current $I$ taken as positive,
charge conservation is:

$$
\frac{dx}{dt} = \frac{I}{Q}
$$

where $Q$ is rated cell capacity in ampere-seconds.

The static equivalent circuit is an open-circuit voltage source in series with
an internal resistance:

$$
V(x, I) = OCV(x) - R(x)I
$$

where:

- $V$ is terminal cell voltage.
- $OCV(x)$ is open-circuit cell voltage as a function of depth of discharge.
- $R(x)$ is effective cell resistance as a function of depth of discharge.
- $I$ is cell current, positive during discharge.

For a pack with cells in series and parallel:

$$
V_{pack} = N_s V_{cell}
$$

$$
I_{cell} = \frac{I_{pack}}{N_p}
$$

$$
Q_{pack} = N_p Q_{cell}
$$

## bat-perf Mapping

The `bat-perf` MATLAB model uses the same core variables:

| PyThrust concept | bat-perf name | Meaning |
|---|---|---|
| `dod` | `dod` | Depth of discharge, from 0 to 1 |
| `capacity_as` | `Qmax` | Cell capacity in ampere-seconds |
| `rated_current_a` | `irated` | 1C current |
| `ocv(dod)` | `OCVfun(dod)` | Open-circuit cell voltage |
| `resistance(dod)` | `Rssfun(dod)` | Steady-state internal resistance |
| `cutoff_voltage_v` | `Vcutoff` | Minimum terminal cell voltage |
| `charge_voltage_v` | `Vcharge` | Maximum terminal cell voltage |

The most important point-state functions are:

| Mode | bat-perf function | Equation |
|---|---|---|
| Specified current | `cellStateI` | $V = OCV - RI$ |
| Specified C-rate | `cellStateC` | $I = C Q_{Ah}$, then $V = OCV - RI$ |
| Specified voltage | `cellStateV` | $I = (OCV - V) / R$ |
| Specified power | `cellStateP` | solve $P = I(OCV - RI)$ |
| Specified load resistance | `cellStateR` | $I = OCV / (R + R_{load})$ |
| Specified internal loss | `cellStatePloss` | solve $P_{loss} = I^2R$ |

For specified power, the current is obtained from the quadratic:

$$
RI^2 - OCV I + P = 0
$$

using the lower-current discharge root:

$$
I = \frac{OCV - \sqrt{OCV^2 - 4RP}}{2R}
$$

The maximum deliverable power at a given DOD occurs when the discriminant is
zero:

$$
P_{max}(x) = \frac{OCV(x)^2}{4R(x)}
$$

The implementation reports infeasible states when requested power exceeds this
limit, when current exceeds the configured limit, or when terminal voltage falls
below cutoff.

## Integration Modes

`RateMapBattery` can integrate battery state through time or to a target depth
of discharge. All integration methods return `BatteryIntegrationResult`, which
contains the final state, sampled histories, delivered energy, consumed charge,
feasibility, and stop reason.

| PyThrust method | bat-perf analogue | Load held constant |
|---|---|---|
| `integrate_current(...)` | `cellIntIt` | Pack current |
| `integrate_c_rate(...)` | `cellIntCt` | Cell C-rate |
| `integrate_power(...)` | `cellIntPt` | Pack terminal power |
| `integrate_voltage(...)` | `cellIntVt` | Pack terminal voltage |
| `integrate_load_resistance(...)` | `cellIntRt` | Pack load resistance |
| `integrate_power_loss(...)` | `cellIntPlosst` | Pack internal loss power |

The target-DOD variants stop at a requested final DOD instead of a requested
duration:

| PyThrust method | bat-perf analogue |
|---|---|
| `integrate_current_to_dod(...)` | `cellIntIdod` |
| `integrate_c_rate_to_dod(...)` | `cellIntCdod` |
| `integrate_power_to_dod(...)` | `cellIntPdod` |
| `integrate_voltage_to_dod(...)` | `cellIntVdod` |
| `integrate_load_resistance_to_dod(...)` | `cellIntRdod` |
| `integrate_power_loss_to_dod(...)` | `cellIntPlossdod` |

Additional helpers cover inverse and segmented calculations:

| Method | Purpose |
|---|---|
| `dod_at_voltage_power(...)` | Find the DOD where a requested voltage and power coincide |
| `dod_at_power_voltage(...)` | Equivalent solve from the constant-power state equation |
| `integrate_power_profile(...)` | Integrate consecutive constant-power mission segments |

!!! note "Numerical method"
    Time and target-DOD integrations use SciPy's adaptive `solve_ivp`
    integrator with `max_step_s` as the maximum time step for time-domain
    solves. Stop events detect current limits, voltage limits, cutoff voltage,
    and DOD exhaustion. This is closer to the `ode45` workflow used by
    `bat-perf` than fixed-step Coulomb counting.

Example:

```python
from pythrust.battery import BatteryState, RateMapBattery

battery = RateMapBattery.from_json(
    "data/batteries/example_liion_cell.json",
    series=4,
    parallel=2,
)
state = BatteryState(soc=1.0)

result = battery.integrate_power(
    state=state,
    power_w=180.0,
    dt_s=300.0,
    max_step_s=1.0,
)

print(result.delivered_energy_wh)
print(result.final_state.dod)
print(result.stop_reason)
```

## Python API

Use explicit names for the two battery fidelities:

=== "Fixed voltage"

    ```python
    from pythrust.battery import FixedVoltageBattery

    battery = FixedVoltageBattery(voltage_v=14.8)
    ```

=== "Rate map"

    ```python
    from pythrust.battery import BatteryState, RateMapBattery

    state = BatteryState(soc=1.0)
    battery = RateMapBattery.from_json(
        "data/batteries/example_liion_cell.json",
        series=4,
        parallel=2,
    )
    ```

!!! tip "Choosing a battery model"
    Use `FixedVoltageBattery` for early propulsion sizing and simple examples. Use `RateMapBattery` when load-dependent voltage, C-rate limits, or state of charge affect the result.

`BatterySpec` is too general once multiple battery models exist. It remains as
a compatibility alias:

```python
BatterySpec = FixedVoltageBattery
```

The alias keeps old code working during the transition, but new code and
documentation should use `FixedVoltageBattery`.

The common battery behavior is intentionally small:

```python
voltage = battery.terminal_voltage(current_a=current, state=state)
power = battery.terminal_power(current_a=current, state=state)
```

`RateMapBattery` also supports state advancement and endurance integration:

```python
next_state = battery.step_power(power_w=power, dt_s=dt, state=state)
result = battery.integrate_power(state=state, power_w=power, dt_s=dt)
```

For the fixed-voltage model, `terminal_voltage` returns the configured voltage.
For the rate-map model, it evaluates the cell/pack equivalent circuit.

## Dataset Shape

The JSON dataset describes one cell. Pack topology is passed when loading the
dataset:

```json
{
  "name": "Example Li-ion Cell",
  "source": "Synthetic example data for PyThrust tests and examples",
  "cell": {
    "capacity_ah": 4.2,
    "cutoff_voltage_v": 2.5,
    "charge_voltage_v": 4.2,
    "max_current_a": 20.0
  },
  "curves": {
    "dod": [0.0, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0],
    "ocv_v": [4.20, 4.08, 3.98, 3.83, 3.70, 3.48, 3.20],
    "resistance_ohm": [0.020, 0.021, 0.022, 0.026, 0.031, 0.039, 0.055]
  }
}
```

```python
battery = RateMapBattery.from_json(cell_path, series=4, parallel=2)
```

The current implementation interpolates `OCV(dod)` and `R(dod)` directly.
Manufacturer discharge curves are usually terminal voltage under load, so real
datasets should document how `OCV(dod)` and `R(dod)` were derived.

## Solver Integration

The propulsion solver starts from the PWM voltage relation:

$$
V_{applied} = throttle \times V_{pack}
$$

For a rate-map battery, `V_pack` depends on current and state:

$$
V_{applied} = throttle \times V_{pack}(x, I)
$$

The root equation therefore becomes:

$$
F(RPM) =
V_{back}(RPM)
+ I(RPM)R_{motor}
+ I(RPM)R_{system}
- throttle \times V_{pack}(x, I(RPM))
$$

This keeps the propeller/motor equilibrium as a one-dimensional root solve
because current remains a function of RPM through the propeller torque demand.

For mission simulation, evaluate each segment with the current state, compute
pack current/power, then advance DOD:

$$
x_{next} = x + \frac{I_{cell}}{Q_{cell}} \Delta t
$$

## Implementation Status

The implementation includes:

- `pythrust.battery.FixedVoltageBattery`
- `pythrust.battery.RateMapBattery`
- `pythrust.battery.BatteryState` and `BatteryPoint`
- JSON cell datasets with explicit series and parallel counts at load time
- Solver integration through `solve_operating_point(..., battery_state=...)`
- `OperatingPoint` battery outputs for voltage, current, C-rate, and efficiency
- SciPy-based integration for current, C-rate, power, voltage, resistance, and
  internal power-loss modes
- Target-DOD integration, energy knockdown helpers, and power-profile
  integration
- A runnable rate-map mission example

## References

- Robert A. McDonald, "Battery Knockdown Factors for Conceptual Design",
  AIAA Aviation Forum, 2024, DOI: `10.2514/6.2024-3903`.
- `ramcdona/bat-perf`: <https://github.com/ramcdona/bat-perf>
