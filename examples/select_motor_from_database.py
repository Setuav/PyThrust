"""Select catalog motors for a hover requirement.

For one catalog propeller and battery voltage, this example solves every
catalog motor at full throttle and in hover, then ranks the motors that pass by
the battery power they draw in hover.

A motor passes when:

- the catalog gives its maximum current,
- its current at full throttle stays within that maximum, and
- its thrust at full throttle is at least ``MIN_THRUST_TO_WEIGHT`` times the
  hover thrust.

The hover thrust includes the motor's own weight, so a heavier motor also has
to lift itself. Catalogs list one frame in several windings (Kv values); the
table shows the best winding of each frame, taking motors of one manufacturer
with the same weight as one frame.

Usage::

    PYTHONPATH=. python examples/select_motor_from_database.py
"""

import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scipy.optimize import brentq

from pythrust import dataset_dir
from pythrust.battery import FixedVoltageBattery
from pythrust.motors import MotorDatabase
from pythrust.propellers import PropellerDatabase
from pythrust.propulsion import PropellerSpec, PropulsionSolver, SystemSpec

PROP_ID = "APC_13x6.5E"
BATTERY = FixedVoltageBattery(voltage_v=14.8)        # 4S LiPo, nominal
SYSTEM = SystemSpec(resistance_ohm=0.03)             # ESC, wiring and battery
AIRFRAME_MASS_PER_MOTOR_G = 400.0                    # everything except the motor, per rotor
MIN_THRUST_TO_WEIGHT = 2.0
RHO = 1.225
GRAVITY = 9.80665
TOP_N = 10

SOLVER = PropulsionSolver()


def solve(motor, propeller, prop_entry, throttle):
    return SOLVER.solve_operating_point(
        motor=motor,
        battery=BATTERY,
        system=SYSTEM,
        propeller=propeller,
        prop_entry=prop_entry,
        rho=RHO,
        airspeed_mps=0.0,
        throttle=throttle,
    )


def hover_point(motor, propeller, prop_entry, thrust_n):
    """Return the feasible operating point that gives ``thrust_n``, or None."""

    def thrust_error(throttle):
        return solve(motor, propeller, prop_entry, throttle).thrust_n - thrust_n

    lowest_throttle = 0.05
    if thrust_error(lowest_throttle) >= 0.0:
        return None
    throttle = brentq(thrust_error, lowest_throttle, 1.0, xtol=1e-5)
    point = solve(motor, propeller, prop_entry, throttle)
    return (throttle, point) if point.is_feasible else None


def evaluate(entry, propeller, prop_entry):
    """Return ``(reason, result)``; ``reason`` is None when the motor passes."""
    if not entry.has_current_limit:
        return "no published max current", None

    motor = entry.to_spec()
    hover_thrust_n = (AIRFRAME_MASS_PER_MOTOR_G + entry.weight_g) * GRAVITY / 1000.0

    full = solve(motor, propeller, prop_entry, 1.0)
    if full.infeasible_reason == "current_limit":
        return "over max current at full throttle", None
    if not full.is_feasible:
        return "no full-throttle operating point", None
    if full.thrust_n < MIN_THRUST_TO_WEIGHT * hover_thrust_n:
        return f"thrust-to-weight below {MIN_THRUST_TO_WEIGHT:g}", None

    hover = hover_point(motor, propeller, prop_entry, hover_thrust_n)
    if hover is None:
        return "no hover operating point", None
    throttle, point = hover
    return None, {
        "entry": entry,
        "hover_thrust_g": hover_thrust_n * 1000.0 / GRAVITY,
        "hover_power_w": point.battery_power_w,
        "hover_throttle": throttle,
        "hover_current_a": point.motor_current_a,
        "full_current_a": full.motor_current_a,
        "thrust_to_weight": full.thrust_n / hover_thrust_n,
    }


def main():
    prop_db = PropellerDatabase()
    prop_db.load(dataset_dir() / "propellers" / "apc_202602", strict=False)
    prop_entry = prop_db.get(PROP_ID)
    if prop_entry is None:
        raise SystemExit(f"Propeller '{PROP_ID}' not found in dataset.")
    propeller = PropellerSpec(diameter_m=prop_entry.diameter_m)

    motor_db = MotorDatabase()
    if not motor_db.load(dataset_dir() / "motors"):
        raise SystemExit("Motor database not found.")

    print(f"Propeller       : {PROP_ID}")
    print(f"Battery         : {BATTERY.voltage_v:.1f} V, system resistance {SYSTEM.resistance_ohm:.3f} ohm")
    print(f"Airframe / motor: {AIRFRAME_MASS_PER_MOTOR_G:.0f} g, plus the motor's own weight")
    print(f"Thrust-to-weight: >= {MIN_THRUST_TO_WEIGHT:g} at full throttle")
    print(f"Motors in catalog: {motor_db.motor_count}")

    rejected = Counter()
    passed = []
    for motor_id in motor_db.list_motors():
        reason, result = evaluate(motor_db.get(motor_id), propeller, prop_entry)
        if reason is None:
            passed.append(result)
        else:
            rejected[reason] += 1

    print(f"\nPassed: {len(passed)}")
    for reason, count in rejected.most_common():
        print(f"Rejected, {reason}: {count}")

    passed.sort(key=lambda r: r["hover_power_w"])
    best_per_frame = {}
    for r in passed:
        best_per_frame.setdefault((r["entry"].manufacturer, r["entry"].weight_g), r)
    ranked = list(best_per_frame.values())

    print(f"\nTop {min(TOP_N, len(ranked))} frames by hover battery power (best winding of each):\n")
    header = (
        f"{'#':>2}  {'Motor':<38}{'Kv':>6}{'Mass':>8}{'Hover':>9}{'Eff.':>8}"
        f"{'Throttle':>10}{'I hover':>9}{'I full/max':>13}{'T/W':>6}"
    )
    units = f"{'':>2}  {'':<38}{'':>6}{'[g]':>8}{'[W]':>9}{'[g/W]':>8}{'[%]':>10}{'[A]':>9}{'[A]':>13}{'':>6}"
    print(header)
    print(units)
    print("-" * len(header))
    for rank, r in enumerate(ranked[:TOP_N], start=1):
        entry = r["entry"]
        name = f"{entry.manufacturer} {entry.name}"[:37]
        print(
            f"{rank:>2}  {name:<38}"
            f"{entry.kv:>6.0f}"
            f"{entry.weight_g:>8.1f}"
            f"{r['hover_power_w']:>9.1f}"
            f"{r['hover_thrust_g'] / r['hover_power_w']:>8.2f}"
            f"{r['hover_throttle'] * 100.0:>10.1f}"
            f"{r['hover_current_a']:>9.2f}"
            f"{r['full_current_a']:>7.1f}/{entry.max_current:<5.0f}"
            f"{r['thrust_to_weight']:>6.2f}"
        )


if __name__ == "__main__":
    main()
