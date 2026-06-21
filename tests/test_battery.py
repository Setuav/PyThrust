import json
import math
from pathlib import Path

import pytest

from pythrust.battery import BatteryState, FixedVoltageBattery, RateMapBattery
from pythrust.propulsion.models import BatterySpec


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def rate_map_battery():
    return RateMapBattery(
        name="Example pack",
        capacity_ah=4.2,
        cutoff_voltage_v=2.5,
        charge_voltage_v=4.2,
        max_current_a=20.0,
        series=4,
        parallel=2,
        dod=[0.0, 0.5, 1.0],
        ocv_v=[4.2, 3.8, 3.2],
        resistance_ohm=[0.02, 0.03, 0.05],
    )


def test_fixed_voltage_battery_replaces_battery_spec():
    battery = FixedVoltageBattery(voltage_v=14.8, discharge_efficiency=0.95)

    assert BatterySpec is FixedVoltageBattery
    assert battery.terminal_voltage(current_a=10.0) == 14.8
    assert math.isclose(battery.terminal_power(current_a=10.0), 14.8 * 10.0 / 0.95)


def test_battery_state_dod_round_trip():
    state = BatteryState.from_dod(0.25)

    assert state.soc == 0.75
    assert state.dod == 0.25


@pytest.mark.parametrize("soc", [math.nan, math.inf, -math.inf])
def test_battery_state_rejects_non_finite_soc(soc):
    with pytest.raises(ValueError, match="soc"):
        BatteryState(soc=soc)


@pytest.mark.parametrize("dod", [math.nan, math.inf, -math.inf])
def test_battery_state_rejects_non_finite_dod(dod):
    with pytest.raises(ValueError, match="dod"):
        BatteryState.from_dod(dod)


def test_rate_map_state_at_current(rate_map_battery):
    state = BatteryState(soc=0.5)
    point = rate_map_battery.state_at_current(state=state, current_a=8.0)

    assert point.is_feasible is True
    assert math.isclose(point.cell_current_a, 4.0)
    assert math.isclose(point.cell_voltage_v, 3.8 - 0.03 * 4.0)
    assert math.isclose(point.terminal_voltage_v, (3.8 - 0.03 * 4.0) * 4)
    assert math.isclose(point.power_w, point.terminal_voltage_v * 8.0)
    assert math.isclose(point.c_rate, 4.0 / 4.2)


def test_rate_map_state_at_power(rate_map_battery):
    state = BatteryState(soc=0.5)
    point = rate_map_battery.state_at_power(state=state, power_w=100.0)

    ocv = 3.8
    resistance = 0.03
    cell_power = 100.0 / (4 * 2)
    expected_cell_current = (ocv - math.sqrt(ocv**2 - 4.0 * resistance * cell_power)) / (
        2.0 * resistance
    )

    assert point.is_feasible is True
    assert math.isclose(point.cell_current_a, expected_cell_current)
    assert math.isclose(point.power_w, 100.0, rel_tol=1e-12)


def test_rate_map_reports_infeasible_power(rate_map_battery):
    state = BatteryState(soc=0.5)
    point = rate_map_battery.state_at_power(state=state, power_w=2000.0)

    assert point.is_feasible is False
    assert point.infeasible_reason == "power_limit"


def test_rate_map_preserves_first_infeasible_reason(rate_map_battery):
    state = BatteryState(soc=0.5)
    point = rate_map_battery.state_at_current(state=state, current_a=1000.0)

    assert point.is_feasible is False
    assert point.cell_current_a > rate_map_battery.max_current_a
    assert point.cell_voltage_v < rate_map_battery.cutoff_voltage_v
    assert point.infeasible_reason == "current_limit"


def test_rate_map_step_current(rate_map_battery):
    state = BatteryState(soc=1.0)
    next_state = rate_map_battery.step_current(state=state, current_a=8.4, dt_s=1800.0)

    assert math.isclose(next_state.dod, 0.5)
    assert math.isclose(next_state.soc, 0.5)


def test_rate_map_loads_from_json(tmp_path):
    path = tmp_path / "battery.json"
    path.write_text(
        json.dumps(
            {
                "name": "JSON pack",
                "source": "test",
                "cell": {
                    "capacity_ah": 4.2,
                    "cutoff_voltage_v": 2.5,
                    "charge_voltage_v": 4.2,
                    "max_current_a": 20.0,
                },
                "curves": {
                    "dod": [0.0, 0.5, 1.0],
                    "ocv_v": [4.2, 3.8, 3.2],
                    "resistance_ohm": [0.02, 0.03, 0.05],
                },
            }
        ),
        encoding="utf-8",
    )

    battery = RateMapBattery.from_json(path, series=4, parallel=2)

    assert battery.name == "JSON pack"
    assert battery.source == "test"
    assert battery.series == 4
    assert battery.parallel == 2


def test_rate_map_loads_example_cell_dataset():
    path = PROJECT_ROOT / "data" / "batteries" / "example_liion_cell.json"

    battery = RateMapBattery.from_json(path, series=4, parallel=2)
    point = battery.state_at_current(state=BatteryState(soc=0.5), current_a=8.4)

    assert battery.name == "Example Li-ion Cell"
    assert battery.series == 4
    assert battery.parallel == 2
    assert battery.capacity_ah == 4.2
    assert point.is_feasible is True
    assert math.isclose(point.cell_current_a, 4.2)
