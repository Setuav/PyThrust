"""Simulate a simple mission with a rate-map battery.

This example couples RateMapBattery to PropulsionSolver. Each segment solves
the propulsion operating point from the current battery state, then advances
state of charge using the solved battery current.

Usage::

    PYTHONPATH=. python examples/rate_map_battery_mission.py
"""

from pathlib import Path

from pythrust.battery import BatteryState, RateMapBattery
from pythrust.propellers import PropellerDatabase
from pythrust.propulsion import MotorSpec, PropellerSpec, PropulsionSolver, SystemSpec


MISSION_SEGMENTS = [
    {"name": "takeoff", "duration_s": 45.0, "throttle": 0.70, "airspeed_mps": 0.0},
    {"name": "climb", "duration_s": 90.0, "throttle": 0.65, "airspeed_mps": 5.0},
    {"name": "cruise", "duration_s": 180.0, "throttle": 0.50, "airspeed_mps": 10.0},
    {"name": "return", "duration_s": 120.0, "throttle": 0.45, "airspeed_mps": 8.0},
]


def load_propeller():
    db = PropellerDatabase()
    db.load(Path("data/propellers/apc_202602"), strict=False)
    prop_entry = db.get("APC_13x6.5E")
    if prop_entry is None:
        raise SystemExit("Propeller 'APC_13x6.5E' not found in dataset.")
    return prop_entry


def main():
    battery_dataset = Path("data/batteries/example_liion_cell.json")
    battery = RateMapBattery.from_json(battery_dataset, series=4, parallel=2)
    state = BatteryState(soc=0.95)

    motor = MotorSpec(
        kv_rpm_per_v=860.0,
        resistance_ohm=0.0258,
        no_load_current_a=1.3,
        current_max_a=65.0,
    )
    system = SystemSpec(resistance_ohm=0.095)
    propeller = PropellerSpec(diameter_m=0.3302)
    prop_entry = load_propeller()
    solver = PropulsionSolver()

    total_energy_wh = 0.0
    total_time_s = 0.0

    print("Rate-map battery mission")
    print(f"Cell dataset : {battery_dataset}")
    print(f"Pack topology: series={battery.series}, parallel={battery.parallel}")
    print(f"Initial state: SoC={state.soc:.3f}, DOD={state.dod:.3f}")
    print()

    header = (
        f"{'Segment':<10}{'t [s]':>7}{'SoC in':>9}{'Throttle':>10}"
        f"{'RPM':>9}{'Thrust [N]':>12}{'Vpack':>9}{'Ipack':>9}"
        f"{'C-rate':>9}{'SoC out':>10}"
    )
    print(header)
    print("-" * len(header))

    for segment in MISSION_SEGMENTS:
        op = solver.solve_operating_point(
            motor=motor,
            battery=battery,
            battery_state=state,
            system=system,
            propeller=propeller,
            prop_entry=prop_entry,
            rho=1.225,
            airspeed_mps=segment["airspeed_mps"],
            throttle=segment["throttle"],
        )

        if not op.is_feasible:
            reason = op.infeasible_reason or "unknown"
            raise SystemExit(f"Mission segment '{segment['name']}' is infeasible: {reason}")

        next_state = battery.step_current(
            state=state,
            current_a=op.battery_current_a,
            dt_s=segment["duration_s"],
        )

        total_energy_wh += op.battery_power_w * segment["duration_s"] / 3600.0
        total_time_s += segment["duration_s"]

        print(
            f"{segment['name']:<10}"
            f"{segment['duration_s']:>7.0f}"
            f"{state.soc:>9.3f}"
            f"{segment['throttle']:>10.2f}"
            f"{op.rpm:>9.0f}"
            f"{op.thrust_n:>12.2f}"
            f"{op.battery_voltage_v:>9.2f}"
            f"{op.battery_current_a:>9.2f}"
            f"{op.battery_c_rate:>9.2f}"
            f"{next_state.soc:>10.3f}"
        )
        state = next_state

    print()
    print(f"Mission time : {total_time_s / 60.0:.1f} min")
    print(f"Energy used  : {total_energy_wh:.1f} Wh")
    print(f"Final state  : SoC={state.soc:.3f}, DOD={state.dod:.3f}")


if __name__ == "__main__":
    main()
