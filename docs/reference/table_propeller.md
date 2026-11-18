# Tabulated Propeller

`TablePropeller` holds $C_t(J, \text{RPM})$ and $C_p(J, \text{RPM})$, for example
read from an APC performance file. It interpolates linearly in $J$ within each
RPM band, then linearly between the two bands around the RPM.

## API

`TablePropeller` is the model for tabulated coefficients. It holds a diameter
and, for each RPM band, a list of `PropellerDataPoint(j, ct, cp)` sorted by
advance ratio. `pythrust.io.read_apc` builds one from an APC performance file:

```python
from pythrust.io import read_apc

propeller = read_apc("PER3_13x65E.dat")
thrust_n, torque_nm = propeller.thrust_torque(rho=1.225, airspeed_mps=10.0, rpm=6000.0)
ct, cp = propeller.get_coefficients(rpm=6000.0, advance_ratio=0.3)
```

| Member | Description |
|---|---|
| `TablePropeller(diameter_m, data_by_rpm)` | Build a table from your own data |
| `scaled(diameter_m)` | The propeller at another diameter with its coefficients unchanged: a geometrically similar propeller, without the Reynolds number effects of the size change |
| `get_coefficients(rpm, advance_ratio)` | Interpolated `Ct` and `Cp`; zero past a band's largest advance ratio |
| `rpm_levels` | Sorted RPM bands |

## APC Performance Files

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
