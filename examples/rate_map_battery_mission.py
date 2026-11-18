"""Simulate a simple mission with a rate-map battery.

This example couples RateMapBattery to PropulsionSolver. Each segment solves
the propulsion operating point from the current battery state, then integrates
state of charge using the solved battery current.

Usage::

    PYTHONPATH=. python examples/rate_map_battery_mission.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pythrust import dataset_dir
from pythrust.battery import BatteryState, RateMapBattery
from pythrust.motors import MotorDatabase
from pythrust.propeller import PropellerDatabase, TablePropeller
from pythrust.propulsion import PropulsionSolver, SystemSpec


MISSION_SEGMENTS = [
    {"name": "takeoff", "duration_s": 45.0, "throttle": 0.70, "airspeed_mps": 0.0},
    {"name": "climb", "duration_s": 90.0, "throttle": 0.65, "airspeed_mps": 5.0},
    {"name": "cruise", "duration_s": 180.0, "throttle": 0.50, "airspeed_mps": 10.0},
    {"name": "return", "duration_s": 120.0, "throttle": 0.45, "airspeed_mps": 8.0},
]


def load_propeller():
    db = PropellerDatabase()
    db.load(dataset_dir() / "propellers" / "apc_202602", strict=False)
    prop_entry = db.get("APC_13x6.5E")
    if prop_entry is None:
        raise SystemExit("Propeller 'APC_13x6.5E' not found in dataset.")
    return TablePropeller(prop_entry)


def load_motor():
    db = MotorDatabase()
    db.load(dataset_dir() / "motors")
    motor_entry = db.get("SunnySky_X2820_KV860_V3_3-4S")
    if motor_entry is None:
        raise SystemExit("Motor 'SunnySky_X2820_KV860_V3_3-4S' not found in dataset.")
    return motor_entry.to_spec()


def main():
    battery_dataset = dataset_dir() / "batteries" / "example_liion_cell.json"
    battery = RateMapBattery.from_json(battery_dataset, series=4, parallel=2)
    state = BatteryState(soc=0.95)

    motor = load_motor()
    system = SystemSpec(resistance_ohm=0.015)  # ESC and wiring; the battery model has its own resistance
    propeller = load_propeller()
    solver = PropulsionSolver()

    total_energy_wh = 0.0
    total_time_s = 0.0

    print("Rate-map battery mission")
    print(f"Pack: {battery.name}, {battery.series}S{battery.parallel}P")
    print(f"Initial SoC: {state.soc * 100.0:.1f}%")
    print()

    header = f"{'Segment':<10}{'min':>6}{'thr':>7}{'T [g]':>8}{'SoC':>17}{'I [A]':>9}{'V [V]':>9}"
    print(header)
    print("-" * len(header))

    for segment in MISSION_SEGMENTS:
        op = solver.solve_operating_point(
            motor=motor,
            battery=battery,
            battery_state=state,
            system=system,
            propeller=propeller,
            rho=1.225,
            airspeed_mps=segment["airspeed_mps"],
            throttle=segment["throttle"],
        )

        if not op.is_feasible:
            reason = op.infeasible_reason or "unknown"
            raise SystemExit(f"Mission segment '{segment['name']}' is infeasible: {reason}")

        battery_result = battery.integrate_current(
            state=state,
            current_a=op.battery_current_a,
            dt_s=segment["duration_s"],
        )
        next_state = battery_result.final_state

        total_energy_wh += battery_result.delivered_energy_wh
        total_time_s += segment["duration_s"]

        print(
            f"{segment['name']:<10}"
            f"{segment['duration_s'] / 60.0:>6.1f}"
            f"{segment['throttle'] * 100.0:>6.0f}%"
            f"{op.thrust_n * 1000.0 / 9.80665:>8.0f}"
            f"{state.soc * 100.0:>7.1f}% -> {next_state.soc * 100.0:>5.1f}%"
            f"{op.battery_current_a:>9.2f}"
            f"{op.battery_voltage_v:>9.2f}"
        )
        state = next_state

    print()
    print(f"Summary: {total_time_s / 60.0:.1f} min, {total_energy_wh:.1f} Wh, final SoC {state.soc * 100.0:.1f}%")


if __name__ == "__main__":
    main()
