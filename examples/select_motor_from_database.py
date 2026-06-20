"""Select commercially available brushless motors from the database.

This example first solves for an efficient theoretical hover design, then uses
the motor database to find real motors near the optimized Kv and current.

Usage::

    PYTHONPATH=. python examples/select_motor_from_database.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import openmdao.api as om

from pythrust.motors import MotorDatabase
from pythrust.openmdao import PropulsionComponent
from pythrust.propellers import PropellerDatabase


def main():
    # 1. Load propeller aerodynamic data.
    db = PropellerDatabase()
    db.load(Path("data/propellers/apc_202602"), strict=False)
    prop_entry = db.get("APC_13x6.5E")
    if prop_entry is None:
        print("Error: Propeller 'APC_13x6.5E' not found.")
        sys.exit(1)

    # 2. Run co-design optimization to find the ideal theoretical motor.
    print("=== Running Theoretical Optimization ===")
    prob = om.Problem()
    model = prob.model
    model.add_subsystem("prop", PropulsionComponent(prop_entry=prop_entry), promotes=["*"])

    model.add_design_var("kv_rpm_per_v", lower=500.0, upper=1500.0, ref=1000.0)
    model.add_design_var("diameter_m", lower=0.254, upper=0.381, ref=0.3)
    model.add_design_var("throttle", lower=0.2, upper=0.9, ref=0.5)

    model.add_constraint("thrust_n", equals=4.903, ref=5.0)
    model.add_constraint("motor_current_a", upper=25.0, ref=25.0)
    model.add_objective("battery_power_w", ref=100.0)

    prob.driver = om.ScipyOptimizeDriver(optimizer="SLSQP")
    prob.driver.options["disp"] = False
    prob.setup()

    prob.set_val("kv_rpm_per_v", 860.0)
    prob.set_val("resistance_ohm", 0.0258)
    prob.set_val("no_load_current_a", 1.3)
    prob.set_val("current_max_a", 65.0)
    prob.set_val("voltage_v", 14.8)
    prob.set_val("resistance_system_ohm", 0.095)
    prob.set_val("diameter_m", 0.3302)
    prob.set_val("throttle", 0.5)
    prob.set_val("rho", 1.225)
    prob.set_val("airspeed_mps", 0.0)

    prob.run_driver()

    opt_kv = float(prob.get_val("kv_rpm_per_v")[0])
    opt_dia = float(prob.get_val("diameter_m")[0]) * 39.3701
    opt_power = float(prob.get_val("battery_power_w")[0])
    opt_current = float(prob.get_val("motor_current_a")[0])

    print("\nIdeal Theoretical Design:")
    print(f"  Target Kv           : {opt_kv:.1f} RPM/V")
    print(f"  Target Diameter     : {opt_dia:.2f} inches")
    print(f"  Target Hover Current: {opt_current:.2f} A")
    print(f"  Min Hover Power     : {opt_power:.2f} W")

    # 3. Load motor database and find catalog candidates near the optimum.
    motors_db_path = Path(__file__).resolve().parent.parent / "data" / "motors"
    db_motors = MotorDatabase()
    if not db_motors.load(motors_db_path):
        print(f"\nError: Motor database not found at {motors_db_path}")
        sys.exit(1)

    print(f"\n=== Loading Motor Database ({motors_db_path.name}) ===")
    print(f"Loaded {db_motors.motor_count} unique reference motors.")

    min_kv = opt_kv * 0.85
    max_kv = opt_kv * 1.15
    min_max_current = opt_current * 1.5

    results = db_motors.search(
        min_kv=min_kv,
        max_kv=max_kv,
        min_max_current=min_max_current,
        min_weight=30.0,
        max_weight=180.0,
    )

    candidates = []
    for entry in results:
        kv_err = abs(entry.kv - opt_kv) / opt_kv
        candidates.append(
            {
                "name": entry.name,
                "manufacturer": entry.manufacturer,
                "kv": entry.kv,
                "resistance": entry.resistance,
                "max_current": entry.max_current,
                "weight_g": entry.weight_g,
                "kv_error_pct": kv_err * 100.0,
            }
        )

    candidates.sort(key=lambda x: (x["resistance"], x["weight_g"]))

    print(f"\n=== Top 5 Real-World Motor Matches (Ideal Kv ~ {opt_kv:.0f}) ===")
    if not candidates:
        print("No matching real motors found with specified criteria.")
    else:
        for idx, c in enumerate(candidates[:5]):
            print(f"\n{idx + 1}. {c['manufacturer']} {c['name']}")
            print(f"   Kv          : {c['kv']:.0f} RPM/V (Diff: {c['kv_error_pct']:.1f}%)")
            res_mohm = c["resistance"] * 1000.0 if c["resistance"] else float("inf")
            print(f"   Resistance  : {res_mohm:.1f} mOhm")
            print(f"   Weight      : {c['weight_g']:.1f} g")
            print(f"   Max Current : {c['max_current']:.1f} A")


if __name__ == "__main__":
    main()
