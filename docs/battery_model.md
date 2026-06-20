# Battery Model

Status: draft design note for issue #3.

PyThrust currently models the battery as a fixed pack voltage with a scalar
discharge efficiency. That is useful for quick propulsion sizing, but it hides
two effects that matter for electric aircraft performance studies:

- The terminal voltage drops with load.
- The usable energy depends on discharge rate and state of charge.

This page defines the planned battery-model direction before implementation.
The target is a lightweight rate-map model inspired by Robert A. McDonald's
`bat-perf` model and the paper "Battery Knockdown Factors for Conceptual
Design".

## Goals

The model should:

- Stay fast enough for sizing sweeps, optimizers, and OpenMDAO workflows.
- Use manufacturer-accessible data such as capacity, voltage limits, current
  limits, discharge curves, and C-rate maps.
- Support point-performance analysis at a specified state of charge.
- Support mission integration by advancing battery state through time.
- Preserve a simple fixed-voltage battery path for examples and low-fidelity
  studies.

The model should not try to replace electrochemical simulation tools. PyThrust
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

The implementation should report infeasible states when requested power exceeds
this limit, when current exceeds the configured limit, or when terminal voltage
falls below cutoff.

## Planned Python API

Use explicit names for the two battery fidelities:

```python
from pythrust.battery import BatteryState, FixedVoltageBattery, RateMapBattery

battery = FixedVoltageBattery(voltage_v=14.8)

state = BatteryState(soc=1.0)
battery = RateMapBattery.from_json(
    "data/batteries/example_liion_cell.json",
    series=4,
    parallel=2,
)
```

`BatterySpec` is too general once multiple battery models exist. The planned
transition is:

```python
BatterySpec = FixedVoltageBattery
```

The alias keeps old examples working during the first implementation pass, but
new code and documentation should use `FixedVoltageBattery`.

The initial common behavior should be small:

```python
voltage = battery.terminal_voltage(current_a=current, state=state)
power = battery.terminal_power(current_a=current, state=state)
next_state = battery.step_power(power_w=power, dt_s=dt, state=state)
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

The first implementation can interpolate `OCV(dod)` and `R(dod)` directly. A
later calibration utility can derive these curves from manufacturer C-rate
discharge maps. Manufacturer discharge curves are usually terminal voltage
under load, so real datasets should document how `OCV(dod)` and `R(dod)` were
derived.

## Solver Integration

The current propulsion solver assumes:

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

For mission simulation, the solver should evaluate each time step with the
current state, compute pack current/power, then advance DOD:

$$
x_{next} = x + \frac{I_{cell}}{Q_{cell}} \Delta t
$$

## Implementation Order

1. Add `pythrust/battery/` with `FixedVoltageBattery`, `RateMapBattery`, and
   `BatteryState`.
2. Add fixture data and unit tests for point states: current, C-rate, voltage,
   power, and infeasible power.
3. Rename internal uses of `BatterySpec` to `FixedVoltageBattery`, leaving a
   compatibility alias.
4. Integrate dynamic pack voltage into `PropulsionSolver`.
5. Add a rate-map battery mission example after solver integration.
6. Update user docs, API reference, and theory docs after the implementation
   stabilizes.

## References

- Robert A. McDonald, "Battery Knockdown Factors for Conceptual Design",
  AIAA Aviation Forum, 2024, DOI: `10.2514/6.2024-3903`.
- `ramcdona/bat-perf`: <https://github.com/ramcdona/bat-perf>
