# Propeller Database

This module loads propeller datasets stored as JSON metadata + CSV data tables.
Any dataset can be used as long as required fields exist.

## Data format

### JSON metadata

Each propeller has a metadata file that points to a CSV file.

```json
{
  "id": "PROP_13x6.5E",
  "manufacturer": "Example",
  "model": "13x6.5E",
  "diameter_in": 13.0,
  "pitch_in": 6.5,
  "blade_count": 2,
  "data_csv": "PROP_13x6.5E.csv"
}
```

### CSV data

Required columns:
- `rpm`
- `advance_ratio`
- `thrust_coeff`
- `power_coeff`

Optional columns are ignored by the loader (e.g. `speed_mps`, `efficiency`, `mach`, `reynolds`).

Example:

```
rpm,speed_mps,advance_ratio,efficiency,thrust_coeff,power_coeff,power_w,torque_nm,thrust_n,thrust_per_power_n_w,mach,reynolds,figure_of_merit
1000,0.00,0.0000,0.0000,0.0889,0.0376,0.822,0.008,0.354,0.430,0.05,16634,0.5624
```

## Loading data

```python
from pathlib import Path
from pythrust.propellers import PropellerDatabase

# Load a dataset directory
_db = PropellerDatabase()
_db.load(Path("datasets/propellers/example_dataset"))

# Load a single entry
_entry = _db.load_entry(Path("datasets/propellers/example_dataset/PROP_13x6.5E.json"))
```

## Interpolation behavior

- **RPM band interpolation:** linear between the nearest RPM levels.
- **J interpolation:** linear between the nearest J points.
- **J beyond data range:** returns `Ct = 0`, `Cp = 0` (no extrapolation).

## Validation modes

`load(..., strict=True)` enforces:
- required columns exist
- numeric values are finite
- `rpm > 0`, `J >= 0`, `Ct >= 0`, `Cp >= 0`
- no duplicate `(rpm, J)`
- each RPM band has at least 2 points

`strict=False` (default) skips invalid rows and continues loading.
