# Data Files

PyThrust ships no motor or propeller catalogs. You supply the data for the
components you analyze: propeller tables from the manufacturer's files, motor
constants from a datasheet or a test.

## Propellers: APC Performance Files

APC publishes a performance file for each of its propellers at
<https://www.apcprop.com/technical-information/performance-data/>. The files
are named `PER3_<size>.dat`, for example `PER3_13x65E.dat` for the 13x6.5E.

`pythrust.io.read_apc` reads one file into a `TablePropeller`:

```python
from pythrust.io import read_apc

propeller = read_apc("PER3_13x65E.dat")
print(propeller.diameter_m)   # 0.3302
print(propeller.rpm_levels)   # [1000.0, 2000.0, ..., 18000.0]
```

The reader takes from the file:

| Item | Use |
|---|---|
| Size in the first line, such as `13x6.5E` | Diameter in inches, converted to metres |
| `PROP RPM = ...` headers | One table band per RPM |
| `J`, `Ct` and `Cp` columns | Advance ratio and the thrust and power coefficients |

Rows with a negative `Ct` or `Cp`, where the propeller windmills, are left
out: each RPM band ends at the last advance ratio with positive thrust and
power. A file without a size in its first line, or without data rows, raises
`ValueError`.

APC computes these tables with its own blade-element software; they are not
wind-tunnel measurements.

## Motors: Datasheet Values

Write the motor constants into a `MotorSpec`:

```python
from pythrust.motor import MotorSpec

motor = MotorSpec(
    kv_rpm_per_v=860.0,       # Kv
    resistance_ohm=0.0258,    # winding resistance Rm
    no_load_current_a=1.3,    # no-load current Io
    current_max_a=65.0,       # maximum continuous current
)
```

Datasheets give the no-load current at a stated voltage, usually 10 V. The
first-order model treats it as constant. For a motor without a published
current limit, pass `current_max_a=math.inf`; the solver then never reports
`current_limit`.

## Batteries: Cell Datasets

`RateMapBattery.from_json(...)` reads a cell dataset. The format is described
in [Battery Model](battery_model.md); `pythrust.dataset_dir()` holds the example
cell `batteries/example_liion_cell.json`.
