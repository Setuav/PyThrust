import math

import pytest

from pythrust.battery import BatteryNetwork, BatteryState, NetworkState, RateMapBattery


def _pack(*, series: int = 4, parallel: int = 1, ocv_end: float = 3.4) -> RateMapBattery:
    return RateMapBattery(
        name="test cell",
        capacity_ah=3.0,
        cutoff_voltage_v=3.0,
        charge_voltage_v=4.2,
        max_current_a=30.0,
        series=series,
        parallel=parallel,
        dod=[0.0, 0.5, 1.0],
        ocv_v=[4.15, 3.75, ocv_end],
        resistance_ohm=[0.02, 0.025, 0.04],
    )


def test_parallel_packs_match_one_pack_with_their_combined_parallel_count():
    network = BatteryNetwork.parallel(_pack(parallel=1), _pack(parallel=2))
    combined = _pack(parallel=3)
    state = NetworkState.uniform(2, soc=0.7)
    single_state = BatteryState(soc=0.7)

    ocv_v, resistance_ohm = network.thevenin(state)
    assert math.isclose(ocv_v, combined.ocv(0.3) * 4)
    assert math.isclose(resistance_ohm, combined.resistance(0.3) * 4 / 3)

    point = network.state_at_power(state, 400.0)
    reference = combined.state_at_power(single_state, 400.0)
    assert math.isclose(point.terminal_voltage_v, reference.terminal_voltage_v)
    assert math.isclose(point.current_a, reference.current_a)
    # The packs share the current by their parallel counts.
    assert math.isclose(point.packs[1].current_a, 2.0 * point.packs[0].current_a)

    network_run = network.integrate_power_to_soc(state, 400.0, 0.2)
    reference_run = combined.integrate_power_to_dod(single_state, 400.0, 0.8)
    assert network_run.stop_reason == "final_soc"
    assert math.isclose(network_run.time_s[-1], reference_run.time_s[-1], rel_tol=1e-4)
    assert all(math.isclose(pack.soc, 0.2, abs_tol=1e-6) for pack in network_run.final_state.packs)


def test_series_packs_add_voltage_and_resistance():
    network = BatteryNetwork.series(_pack(series=4), _pack(series=4))
    combined = _pack(series=8)
    state = network.full_state()

    ocv_v, resistance_ohm = network.thevenin(state)
    assert math.isclose(ocv_v, combined.ocv(0.0) * 8)
    assert math.isclose(resistance_ohm, combined.resistance(0.0) * 8)
    point = network.state_at_current(state, 20.0)
    assert [pack.current_a for pack in point.packs] == pytest.approx([20.0, 20.0])


def test_unequal_parallel_packs_share_current_and_balance_at_rest():
    network = BatteryNetwork.parallel(_pack(), _pack())
    state = NetworkState((BatteryState(soc=0.9), BatteryState(soc=0.5)))

    loaded = network.state_at_current(state, 30.0)
    assert math.isclose(sum(pack.current_a for pack in loaded.packs), 30.0)
    assert loaded.packs[0].current_a > loaded.packs[1].current_a

    # At rest the fuller pack charges the emptier one.
    resting = network.state_at_current(state, 0.0)
    assert resting.packs[0].current_a > 0.0
    assert math.isclose(resting.packs[1].current_a, -resting.packs[0].current_a)


def test_unequal_parallel_packs_stop_when_the_first_reaches_the_final_soc():
    network = BatteryNetwork.parallel(_pack(), _pack())
    state = NetworkState((BatteryState(soc=1.0), BatteryState(soc=0.6)))

    run = network.integrate_power_to_soc(state, 300.0, 0.2)

    assert run.stop_reason == "final_soc"
    socs = [pack.soc for pack in run.final_state.packs]
    assert math.isclose(min(socs), 0.2, abs_tol=1e-6)
    assert len(run.pack_soc) == 2
    assert run.delivered_energy_wh > 0.0


def test_network_rejects_mismatched_parallel_strings_and_states():
    with pytest.raises(ValueError, match="matching charge and cut-off voltages"):
        BatteryNetwork.parallel(_pack(series=4), _pack(series=6))
    network = BatteryNetwork.single(_pack())
    with pytest.raises(ValueError, match="network state has 2 packs"):
        network.thevenin(NetworkState.uniform(2))
    with pytest.raises(ValueError, match="final_soc"):
        network.integrate_power_to_soc(NetworkState.uniform(1, soc=0.3), 100.0, 0.5)


def test_power_beyond_the_network_is_infeasible():
    network = BatteryNetwork.single(_pack())
    state = network.full_state()
    ocv_v, resistance_ohm = network.thevenin(state)

    point = network.state_at_power(state, ocv_v**2 / (4.0 * resistance_ohm) * 1.01)
    assert not point.is_feasible
    assert point.infeasible_reason == "power_limit"
    run = network.integrate_power_to_soc(state, 2000.0, 0.2)
    assert run.stop_reason == "infeasible_start"
