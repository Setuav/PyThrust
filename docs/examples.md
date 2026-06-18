# Examples

PyThrust includes runnable examples that show the main workflows: solving against catalog data, calibrating losses from measurements, and using OpenMDAO for propulsion co-design.

Run examples from the repository root so relative `data/` and `docs/images/` paths resolve correctly.

```bash
PYTHONPATH=. python examples/<example_name>.py
```

---

## Requirements

| Example | Extra dependencies |
|---|---|
| `calibrate_from_datasheet.py` | Core PyThrust dependencies |
| `select_motor.py` | `openmdao` |
| `optimize_and_plot_propulsion.py` | `openmdao`, `matplotlib` |

Install the full example environment:

```bash
pip install -e .[plot,openmdao]
```

---

## Datasheet Calibration

Script:

```bash
PYTHONPATH=. python examples/calibrate_from_datasheet.py
```

This example identifies the lumped system resistance for a motor, propeller, battery, ESC, and wiring setup.

It uses:

| Input | Value or source |
|---|---|
| Motor | Datasheet Kv, resistance, no-load current, and current limit |
| Propeller | `APC_13x6.5E` from `data/propellers/apc_202602` |
| Battery | 4S nominal voltage, `14.8 V` |
| Test table | RPM, thrust in grams, and battery current in amps |

The output reports:

| Metric | Meaning |
|---|---|
| System resistance | Fitted `SystemSpec.resistance_ohm` |
| Thrust RMSE | Propeller-model thrust error against measured thrust |
| Current RMSE | Battery-current prediction error |
| Thrust R2 | Fit quality for the aerodynamic thrust prediction |
| Per-point table | Predicted vs measured thrust/current for each RPM row |

See [Motor Calibration](motor_calibration.md) for the calibration model and equations.

![Calibration results](images/calibration_results.png)

---

## Motor Selection

Script:

```bash
PYTHONPATH=. python examples/select_motor.py
```

This example combines theoretical co-design with real motor database lookup.

Workflow:

1. Load `APC_13x6.5E` propeller data.
2. Use OpenMDAO to find an efficient theoretical motor/propeller/throttle combination for hover.
3. Load the brushless motor database from `data/motors`.
4. Search real motors near the optimized Kv and current requirement.
5. Print the top candidates sorted by winding resistance and weight.

The optimization target is a hover thrust of `4.903 N`, approximately `500 gf`.

Typical output includes:

| Output | Meaning |
|---|---|
| Target Kv | Ideal speed constant from the theoretical optimization |
| Target diameter | Optimized propeller diameter |
| Target hover current | Current at the optimized hover point |
| Minimum hover power | Battery power objective value |
| Top motor matches | Closest catalog motors with Kv, resistance, weight, and current limit |

See [Component Databases](databases.md) for motor catalog format and query helpers.

---

## Propulsion Optimization and Plotting

Script:

```bash
PYTHONPATH=. python examples/optimize_and_plot_propulsion.py
```

This example demonstrates OpenMDAO-based propulsion co-design and a parametric Kv sweep.

It performs three stages:

1. Run the baseline propulsion model.
2. Optimize motor Kv, propeller diameter, and throttle for a fixed hover thrust.
3. Sweep Kv and re-optimize diameter/throttle at each point.

The generated plot is saved to:

```text
docs/images/optimize_and_plot_results.png
```

The plot shows:

| Panel | Shows |
|---|---|
| Power and propeller size vs motor Kv | Hover battery power and optimized propeller diameter |
| Throttle and RPM vs motor Kv | Optimized throttle setting and shaft speed |

![Propulsion co-design optimization](images/optimize_and_plot_results.png)

See [Propulsion Solver](usage.md) for the operating-point solver used inside the OpenMDAO component.
