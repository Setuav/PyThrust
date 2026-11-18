"""Simulate a simple mission with a rate-map battery.

This example couples RateMapBattery to PropulsionSolver. Each segment solves
the propulsion operating point from the current battery state, then integrates
state of charge using the solved battery current.

Usage::

    PYTHONPATH=. python examples/rate_map_battery_mission.py [PER3_13x65E.dat]

The argument is an APC performance file, from
https://www.apcprop.com/technical-information/performance-data/. Without it
the example uses the APC 13x6.5E file kept with the tests.
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pythrust import dataset_dir
from pythrust.battery import BatteryState, RateMapBattery
from pythrust.io import read_apc
from pythrust.motor import MotorSpec
from pythrust.propulsion import PropulsionSolver, SystemSpec


MISSION_SEGMENTS = [
    {"name": "takeoff", "duration_s": 45.0, "throttle": 0.70, "airspeed_mps": 0.0},
    {"name": "climb", "duration_s": 90.0, "throttle": 0.65, "airspeed_mps": 5.0},
    {"name": "cruise", "duration_s": 180.0, "throttle": 0.50, "airspeed_mps": 10.0},
    {"name": "return", "duration_s": 120.0, "throttle": 0.45, "airspeed_mps": 8.0},
]


DEFAULT_APC_FILE = PROJECT_ROOT / "tests" / "data" / "PER3_13x65E.dat"

# SunnySky X2820 KV860 V3, from the manufacturer's datasheet.
MOTOR = MotorSpec(kv_rpm_per_v=860.0, resistance_ohm=0.0258, no_load_current_a=1.3, current_max_a=65.0)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("apc_file", nargs="?", type=Path, default=DEFAULT_APC_FILE, help="APC PER3_*.dat file")
    args = parser.parse_args()

    battery_dataset = dataset_dir() / "batteries" / "example_liion_cell.json"
    battery = RateMapBattery.from_json(battery_dataset, series=4, parallel=2)
    state = BatteryState(soc=0.95)

    motor = MOTOR
    system = SystemSpec(resistance_ohm=0.015)  # ESC and wiring; the battery model has its own resistance
    propeller = read_apc(args.apc_file)
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
