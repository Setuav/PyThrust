# Examples

PyThrust includes runnable examples that show the main workflows: solving
propulsion models, inspecting rate-map battery behavior, and selecting catalog
motors. They load the bundled datasets through
`pythrust.dataset_dir()`.

```bash
PYTHONPATH=. python examples/<example_name>.py
```

## Requirements

| Example | Extra dependencies |
|---|---|
| `rate_map_battery_point_states.py` | Core PyThrust dependencies |
| `rate_map_battery_mission.py` | Core PyThrust dependencies |
| `select_motor_from_database.py` | Core PyThrust dependencies |

Install PyThrust from the repository root:

```bash
pip install -e .
```

## Rate-Map Battery Point States

Script:

```bash
PYTHONPATH=. python examples/rate_map_battery_point_states.py
```

This example loads `data/batteries/example_liion_cell.json`, applies a `4S2P`
pack topology, and evaluates the same state of charge under several requests.

It demonstrates:

| Query | Meaning |
|---|---|
| `state_at_current` | Terminal voltage and power at a requested pack current |
| `state_at_c_rate` | Current/voltage behavior at a requested cell C-rate |
| `state_at_voltage` | Current required to hold a requested pack voltage |
| `state_at_power` | Current and voltage for a requested pack power |
| `state_at_load_resistance` | Battery behavior under a resistive load |
| `state_at_power_loss` | Battery behavior for a requested internal loss power |
| Infeasible power | How the model reports a power limit |

This example is intentionally independent from the propulsion solver. It
validates the battery model surface before mission or solver integration.

## Rate-Map Battery Mission

Script:

```bash
PYTHONPATH=. python examples/rate_map_battery_mission.py
```

This example couples `RateMapBattery` to `PropulsionSolver` over a short
segment schedule with the `SunnySky_X2820_KV860_V3_3-4S` catalog motor and the
`APC_13x6.5E` propeller. Each segment solves the propulsion operating point
using the current battery state, reports thrust, pack current and voltage, then
integrates state of charge from the solved battery current.

It demonstrates:

| Step | Meaning |
|---|---|
| Load cell data | Use `data/batteries/example_liion_cell.json` with explicit series and parallel counts |
| Solve segment | Pass `battery_state` into `solve_operating_point(...)` |
| Read outputs | Inspect `battery_voltage_v` and `battery_current_a` on `OperatingPoint` |
| Advance state | Use `integrate_current(...)` to update SoC and delivered energy for the next segment |

![Rate-map battery mission simulation](images/rate_map_battery_mission.png)

## Motor Selection

Script:

```bash
PYTHONPATH=. python examples/select_motor_from_database.py
```

This example picks catalog motors for a hover requirement with one catalog
propeller, `APC_13x6.5E`, on a `14.8 V` battery.

For every motor in the catalog it solves the full-throttle and hover operating
points. A motor passes when:

| Rule | Meaning |
|---|---|
| Published current limit | Motors whose catalog entry has no maximum current are skipped |
| Current at full throttle | The full-throttle motor current stays within the motor's maximum current |
| Thrust-to-weight | Full-throttle thrust is at least `2` times the hover thrust |

The hover thrust is `400 g` of airframe per rotor plus the motor's own weight,
so a heavier motor also has to lift itself. Passing motors are ranked by the
battery power they draw in hover. Catalogs list one frame in several windings,
so the table shows the best winding of each frame, taking motors of one
manufacturer with the same weight as one frame.

The output reports how many motors each rule rejected and, for the best frames,
hover power, hover efficiency in g/W, hover throttle and current, the
full-throttle current against the motor's limit, and the thrust-to-weight
ratio.

See [Component Databases](databases.md) for motor catalog format and query
helpers.
