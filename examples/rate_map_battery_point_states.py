"""Evaluate rate-map battery point states.

This example loads a cell-level rate-map dataset, applies a 4S2P pack topology,
and evaluates the same battery state under current, C-rate, voltage, power,
load-resistance, and internal-loss requests.

Usage::

    PYTHONPATH=. python examples/rate_map_battery_point_states.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pythrust.battery import BatteryState, RateMapBattery


def print_point(label, point):
    """Print one compact battery point-state row."""
    status = "OK" if point.is_feasible else f"NO ({point.infeasible_reason})"
    print(
        f"{label:<18}"
        f"{point.terminal_voltage_v:>10.2f}"
        f"{point.current_a:>10.2f}"
        f"{point.power_w:>11.2f}"
        f"{point.c_rate:>9.2f}"
        f"{point.efficiency:>9.3f}"
        f"  {status}"
    )


def main():
    dataset = Path("data/batteries/example_liion_cell.json")
    battery = RateMapBattery.from_json(dataset, series=4, parallel=2)
    state = BatteryState(soc=0.60)

    print("Rate-map battery point states")
    print(f"Cell dataset : {dataset}")
    print(f"Pack topology: {battery.series}S{battery.parallel}P")
    print(f"State        : SoC={state.soc:.2f}, DOD={state.dod:.2f}")
    print()
    print(f"{'Case':<18}{'Vpack':>10}{'Ipack':>10}{'Ppack':>11}{'C-rate':>9}{'eta':>9}  Status")
    print("-" * 79)

    print_point("current 12 A", battery.state_at_current(state=state, current_a=12.0))
    print_point("1.5 C", battery.state_at_c_rate(state=state, c_rate=1.5))
    print_point("voltage 14 V", battery.state_at_voltage(state=state, voltage_v=14.0))
    print_point("power 180 W", battery.state_at_power(state=state, power_w=180.0))
    print_point("load 1.5 ohm", battery.state_at_load_resistance(state=state, resistance_ohm=1.5))
    print_point("loss 8 W", battery.state_at_power_loss(state=state, power_loss_w=8.0))
    print_point("too much power", battery.state_at_power(state=state, power_w=3000.0))

    next_state = battery.step_current(state=state, current_a=12.0, dt_s=60.0)
    print()
    print(f"After 60 s at 12 A: SoC={next_state.soc:.3f}, DOD={next_state.dod:.3f}")


if __name__ == "__main__":
    main()
