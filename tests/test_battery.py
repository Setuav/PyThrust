import json
import math
from pathlib import Path

import pytest

from pythrust.battery import (
    BatteryIntegrationResult,
    BatteryState,
    FixedVoltageBattery,
    RateMapBattery,
)
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


def test_battery_integration_result_normalizes_histories():
    final_state = BatteryState(soc=0.9)
    result = BatteryIntegrationResult(
        final_state=final_state,
        time_s=[0, 10],
        dod=[0.0, 0.1],
        voltage_v=[16.0, 15.8],
        current_a=[8.0, 8.0],
        c_rate=[1.0, 1.0],
        power_w=[128.0, 126.4],
        efficiency=[0.95, 0.94],
        delivered_energy_wh=0.35,
        consumed_charge_ah=0.022,
        is_feasible=True,
        stop_reason="duration_complete",
    )

    assert result.final_state is final_state
    assert result.time_s == (0.0, 10.0)
    assert result.dod == (0.0, 0.1)
    assert result.stop_reason == "duration_complete"


def test_battery_integration_result_rejects_mismatched_histories():
    with pytest.raises(ValueError, match="same length"):
        BatteryIntegrationResult(
            final_state=BatteryState(soc=0.9),
            time_s=[0.0, 10.0],
            dod=[0.0],
            voltage_v=[16.0, 15.8],
            current_a=[8.0, 8.0],
            c_rate=[1.0, 1.0],
            power_w=[128.0, 126.4],
            efficiency=[0.95, 0.94],
            delivered_energy_wh=0.35,
            consumed_charge_ah=0.022,
            is_feasible=True,
            stop_reason="duration_complete",
        )


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


def test_rate_map_integrates_constant_current(rate_map_battery):
    result = rate_map_battery.integrate_current(
        state=BatteryState(soc=1.0),
        current_a=8.4,
        dt_s=1800.0,
        max_step_s=60.0,
    )

    expected_energy_wh = ((16.464 + 14.696) / 2.0) * 8.4 * 0.5

    assert result.is_feasible is True
    assert result.stop_reason == "duration_complete"
    assert math.isclose(result.final_state.dod, 0.5)
    assert math.isclose(result.consumed_charge_ah, 4.2)
    assert math.isclose(result.delivered_energy_wh, expected_energy_wh)
    assert result.time_s[0] == 0.0
    assert result.time_s[-1] == 1800.0
    assert result.dod[-1] == result.final_state.dod


def test_rate_map_integrates_zero_current_without_changing_state(rate_map_battery):
    result = rate_map_battery.integrate_current(
        state=BatteryState(soc=0.8),
        current_a=0.0,
        dt_s=120.0,
    )

    assert result.is_feasible is True
    assert result.stop_reason == "duration_complete"
    assert result.time_s == (0.0, 120.0)
    assert all(math.isclose(dod, 0.2) for dod in result.dod)
    assert result.consumed_charge_ah == 0.0
    assert result.delivered_energy_wh == 0.0


def test_rate_map_integrates_zero_duration_without_extra_sample(rate_map_battery):
    result = rate_map_battery.integrate_current(
        state=BatteryState(soc=0.8),
        current_a=8.0,
        dt_s=0.0,
    )

    assert result.is_feasible is True
    assert result.stop_reason == "duration_complete"
    assert result.time_s == (0.0,)
    assert math.isclose(result.dod[0], 0.2)


def test_rate_map_integrates_current_until_voltage_cutoff(rate_map_battery):
    result = rate_map_battery.integrate_current(
        state=BatteryState(soc=1.0),
        current_a=36.0,
        dt_s=1200.0,
        max_step_s=60.0,
    )

    assert result.is_feasible is False
    assert result.stop_reason == "voltage_cutoff"
    assert result.time_s[-1] < 1200.0
    assert math.isclose(result.voltage_v[-1] / rate_map_battery.series, rate_map_battery.cutoff_voltage_v)
    assert result.final_state.dod < 1.0


def test_rate_map_integrates_current_until_dod_limit(rate_map_battery):
    result = rate_map_battery.integrate_current(
        state=BatteryState(soc=1.0),
        current_a=1.0,
        dt_s=40000.0,
        max_step_s=5000.0,
    )

    assert result.is_feasible is False
    assert result.stop_reason == "dod_limit"
    assert result.final_state.dod == 1.0
    assert math.isclose(result.time_s[-1], 30240.0)
    assert math.isclose(result.consumed_charge_ah, 8.4)


def test_rate_map_integrates_current_reports_initial_infeasible_state(rate_map_battery):
    result = rate_map_battery.integrate_current(
        state=BatteryState(soc=0.5),
        current_a=1000.0,
        dt_s=60.0,
    )

    assert result.is_feasible is False
    assert result.stop_reason == "current_limit"
    assert result.time_s == (0.0,)
    assert result.consumed_charge_ah == 0.0
    assert result.delivered_energy_wh == 0.0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"current_a": -1.0}, "current_a"),
        ({"current_a": math.nan}, "current_a"),
        ({"dt_s": -1.0}, "dt_s"),
        ({"dt_s": math.inf}, "dt_s"),
        ({"max_step_s": 0.0}, "max_step_s"),
        ({"max_step_s": math.nan}, "max_step_s"),
    ],
)
def test_rate_map_integrate_current_rejects_invalid_inputs(rate_map_battery, kwargs, message):
    params = {
        "state": BatteryState(soc=1.0),
        "current_a": 1.0,
        "dt_s": 10.0,
        "max_step_s": 1.0,
    }
    params.update(kwargs)

    with pytest.raises(ValueError, match=message):
        rate_map_battery.integrate_current(**params)


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
