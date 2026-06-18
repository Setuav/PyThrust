# Component Databases

PyThrust uses a directory-based database design to manage catalog assets for propellers and brushless motors.

---

## 1) Propeller Database (`data/propellers/`)

Each propeller dataset consists of a JSON metadata file and a corresponding CSV performance table.

### JSON Metadata format (`*.json`)
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

### CSV Performance format (`*.csv`)
Required columns:
- `rpm` (RPM band)
- `advance_ratio` (Advance ratio, $J$)
- `thrust_coeff` (Thrust coefficient, $C_t$)
- `power_coeff` (Power coefficient, $C_p$)

*Example data row:*
```csv
rpm,speed_mps,advance_ratio,efficiency,thrust_coeff,power_coeff,power_w,torque_nm,thrust_n,thrust_per_power_n_w,mach,reynolds,figure_of_merit
1000,0.00,0.0000,0.0000,0.0889,0.0376,0.822,0.008,0.354,0.430,0.05,16634,0.5624
```

---

## 2) Brushless Motor Database (`data/motors/`)

The motor database is a directory of individual JSON files representing brushless motors.

### Motor Spec format (`*.json`)
```json
{
  "id": "SunnySky_X2826_KV550",
  "name": "X2826 KV550 3-4S",
  "manufacturer": "SunnySky",
  "kv": 550.0,
  "resistance": 0.045,
  "io": 1.2,
  "max_current": 48.0,
  "weight_g": 180.0,
  "max_power": 850.0,
  "io_voltage": 10.0
}
```

---

## 3) Code Examples

### Loading Propeller Database
```python
from pathlib import Path
from pythrust.propellers import PropellerDatabase

db = PropellerDatabase()
db.load(Path("data/propellers/apc_202602"))

# Get propeller by ID
prop_entry = db.get("APC_13x6.5E")
```

### Loading Motor Database
```python
from pathlib import Path
from pythrust.motors import MotorDatabase

db = MotorDatabase()
db.load(Path("data/motors"))

# Get motor by ID
motor_entry = db.get("SunnySky_X2826_KV550")
```
