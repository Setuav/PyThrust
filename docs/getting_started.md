# Getting Started

This guide walks through installing PyThrust and solving a first propulsion operating point.

## Requirements

PyThrust requires Python 3.10 or newer.

Core dependencies:

* `numpy`
* `scipy`

Optional extras:

* `plot` for visualization examples
* `openmdao` for multidisciplinary design optimization workflows
* `dev` for tests
* `docs` for the MkDocs documentation site

## Installation

Clone the repository and install the package in editable mode:

```bash
git clone https://github.com/Setuav/PyThrust.git
cd PyThrust
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

For the full development environment:

```bash
pip install -e .[plot,openmdao,dev,docs]
```

## First Solve

The core workflow is:

1. Load a propeller aerodynamic dataset.
2. Define motor, battery, system, and propeller specifications.
3. Solve the operating point for an airspeed and throttle.

```python
from pathlib import Path

from pythrust.propellers import PropellerDatabase
from pythrust.propulsion import (
    BatterySpec,
    MotorSpec,
    PropellerSpec,
    PropulsionSolver,
    SystemSpec,
)

prop_db = PropellerDatabase()
prop_db.load(Path("data/propellers/apc_202602"), strict=False)
prop_entry = prop_db.get("APC_13x6.5E")

motor = MotorSpec(
    kv_rpm_per_v=860.0,
    resistance_ohm=0.0258,
    no_load_current_a=1.3,
    current_max_a=65.0,
)
battery = BatterySpec(voltage_v=14.8)
system = SystemSpec(resistance_ohm=0.05)
propeller = PropellerSpec(diameter_m=0.3302, blade_count=2)

solver = PropulsionSolver()
point = solver.solve_operating_point(
    motor=motor,
    battery=battery,
    system=system,
    propeller=propeller,
    prop_entry=prop_entry,
    rho=1.225,
    airspeed_mps=15.0,
    throttle=0.7,
)

print(point.rpm)
print(point.thrust_n)
print(point.motor_current_a)
print(point.is_feasible)
```

## Run the Examples

```bash
PYTHONPATH=. python examples/select_motor.py
PYTHONPATH=. python examples/calibrate_from_datasheet.py
PYTHONPATH=. python examples/optimize_and_plot_propulsion.py
```

The plotting and OpenMDAO examples require the optional dependencies shown above.

See [Examples](examples.md) for the purpose, inputs, and outputs of each script.

## Build the Documentation Locally

```bash
pip install -e .[docs]
mkdocs serve
```

Then open the local MkDocs URL printed in the terminal.
