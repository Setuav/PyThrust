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

## Propellers: QPROP Files

A QPROP propeller file describes the blade itself: chord and blade angle at
radial stations, and the airfoil's lift and drag parameters. The format is
defined in the [QPROP user guide](https://web.mit.edu/drela/Public/web/qprop/qprop_doc.txt).
`pythrust.io.read_qprop_propeller` reads one into a `BladeGeometry` in SI units:

```python
from pythrust.io import read_qprop_propeller

blade = read_qprop_propeller("prop.txt")
print(blade.blade_count, blade.radius_m)
print(blade.r_m, blade.chord_m, blade.blade_angle_rad)
print(blade.sections[0].cl_alpha_per_rad)
```

The file holds, in order:

| Line | Content |
|---|---|
| 1 | Name |
| 2 | `Nblades [R]`; without `R`, the last station's radius is the tip radius |
| 3 | `CL0 CL_a` |
| 4 | `CLmin CLmax` |
| 5 | `CD0 CD2u CD2l CLCD0` |
| 6 | `REref REexp` |
| 7 | `Rfac Cfac Bfac` |
| 8 | `Radd Cadd Badd` |
| 9 on | `r chord beta`, one station per line from root to tip |

Radii and chords become `value * fac + add` in metres, and the blade angle
`beta * Bfac + Badd` in degrees, converted to radians. A station line may
append its own `CL0 CL_a CLmin CLmax CD0 CD2u CD2l CLCD0 REref REexp`; values it
leaves out take those of lines 3 to 6. Lines starting with `#` and blank lines
are skipped, and text after `!` is ignored.

`CL_a` is read per radian. The QPROP guide does not state its unit; its example
value of 5.8 is a lift slope per radian.

The tip radius `R` on line 2 is scaled like the station radii, as the QPROP
guide states. QPROP 1.22 itself applies `Rfac` and `Radd` only to the stations
and uses `R` as written, so a file that gives `R` with `Rfac` other than 1 or
`Radd` other than 0 gives different tip losses in QPROP and in PyThrust.
Without `R`, or with the radii in metres, the two agree. `R` must not be less
than the last station's radius.

## Motors: QPROP Files

A QPROP motor file gives a name, the motor type, then one parameter per line.
`pythrust.io.read_qprop_motor` reads one into a `MotorSpec`:

```python
from pythrust.io import read_qprop_motor

motor = read_qprop_motor("motor.txt", current_max_a=40.0)
```

| Type | Parameters, one per line | `MotorSpec` fields |
|---|---|---|
| 1 | `R Io Kv` | first-order model |
| 2 | `R0 Io0 Kv Kq tau Io1 Io2 R2`; at least the first three | second-order model |

Kv and Kq are in rpm/V. `torque_constant_kv_ratio` is `Kq / Kv`, and a zero
`Kq` means `Kq = Kv`. `Io1` (A s) and `Io2` (A s^2) multiply the shaft speed in
rad/s and its square, and `R2` (ohm/A^2) the current squared. Type 2
parameters left out are zero.

QPROP files carry no current limit; `current_max_a` sets it and defaults to
infinity. QPROP reads only the first number on each line, so a line with
more than one number raises `ValueError` rather than shifting the
parameters. Motor types other than 1 and 2 are rejected.

With the same propeller and motor files, `PropulsionSolver` and a
`BladeElementPropeller` give the RPM, thrust, torque and current that QPROP
1.22 gives at a set voltage, to the digits QPROP prints.

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
