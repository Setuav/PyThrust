import math

import pytest

from pythrust.battery import BatteryNetwork, BatteryState, RateMapBattery
from pythrust.propellers.database import PropellerDataPoint, PropellerEntry, PropellerMetadata
from pythrust.propulsion import BusSolver, PropulsionSolver, PropulsionUnit
from pythrust.propulsion.models import MotorSpec, PropellerSpec, SystemSpec


@pytest.fixture
def unit():
    motor = MotorSpec(
        kv_rpm_per_v=980.0,
        resistance_ohm=0.06,
        no_load_current_a=1.2,
        current_max_a=30.0,
        torque_constant_kv_ratio=1.0,
        magnetic_lag_tau=0.0001,
    )
    meta = PropellerMetadata(
        id="apc_10x4.7",
        manufacturer="APC",
        model="SF",
        diameter_in=10.0,
        pitch_in=4.7,
        blade_count=2,
        data_csv="apc_10x4.7.csv",
    )
    data = {
        1000.0: [
            PropellerDataPoint(j=0.0, ct=0.11, cp=0.055),
            PropellerDataPoint(j=0.4, ct=0.08, cp=0.04),
            PropellerDataPoint(j=0.8, ct=0.02, cp=0.01),
        ],
        8000.0: [
            PropellerDataPoint(j=0.0, ct=0.12, cp=0.06),
            PropellerDataPoint(j=0.4, ct=0.09, cp=0.045),
            PropellerDataPoint(j=0.8, ct=0.03, cp=0.015),
        ],
    }
    return PropulsionUnit(
        motor=motor,
        propeller=PropellerSpec(diameter_m=0.254, blade_count=2, pitch_m=0.114),
        prop_entry=PropellerEntry(metadata=meta, data_by_rpm=data),
        system=SystemSpec(resistance_ohm=0.015),
    )


@pytest.fixture
def pack():
    return RateMapBattery(
        name="3S pack",
        capacity_ah=4.2,
        cutoff_voltage_v=3.0,
        charge_voltage_v=4.2,
        max_current_a=60.0,
        series=3,
        parallel=1,
        dod=[0.0, 1.0],
        ocv_v=[4.1, 3.5],
        resistance_ohm=[0.02, 0.03],
    )


def test_single_unit_bus_matches_the_unit_solver(unit, pack):
    network = BatteryNetwork.single(pack)
    state = network.full_state()

    bus = BusSolver().solve(network, state, [unit], [0.7], rho=1.225, airspeed_mps=10.0)
    direct = PropulsionSolver().solve_operating_point(
        motor=unit.motor,
        battery=pack,
        system=unit.system,
        propeller=unit.propeller,
        prop_entry=unit.prop_entry,
        rho=1.225,
        airspeed_mps=10.0,
        throttle=0.7,
        battery_state=BatteryState(soc=1.0),
    )

    assert bus.is_feasible
    assert math.isclose(bus.units[0].rpm, direct.rpm, rel_tol=1e-6)
    assert math.isclose(bus.thrust_n, direct.thrust_n, rel_tol=1e-6)
    assert math.isclose(bus.voltage_v, direct.battery_voltage_v, rel_tol=1e-6)
    assert math.isclose(bus.current_a, direct.battery_current_a, rel_tol=1e-6)


def test_units_on_one_bus_share_its_sag(unit, pack):
    network = BatteryNetwork.single(pack)
    state = network.full_state()
    solver = BusSolver()

    one = solver.solve(network, state, [unit], [0.8], rho=1.225, airspeed_mps=10.0)
    two = solver.solve(network, state, [unit, unit], [0.8, 0.8], rho=1.225, airspeed_mps=10.0)

    ocv_v, resistance_ohm = network.thevenin(state)
    assert math.isclose(two.voltage_v, ocv_v - resistance_ohm * two.current_a, rel_tol=1e-9)
    assert two.voltage_v < one.voltage_v
    assert two.units[0].rpm < one.units[0].rpm
    assert math.isclose(two.current_a, 2.0 * two.units[0].battery_current_a, rel_tol=1e-9)


def test_idle_units_draw_nothing_and_stay_feasible(unit, pack):
    network = BatteryNetwork.single(pack)
    bus = BusSolver().solve(
        network, network.full_state(), [unit, unit], [0.6, 0.0], rho=1.225, airspeed_mps=8.0
    )

    assert bus.is_feasible
    assert bus.units[1].battery_current_a == 0.0
    assert math.isclose(bus.current_a, bus.units[0].battery_current_a)


def test_speed_controller_limit_marks_the_unit_infeasible(unit, pack):
    limited = PropulsionUnit(
        motor=unit.motor,
        propeller=unit.propeller,
        prop_entry=unit.prop_entry,
        system=SystemSpec(resistance_ohm=0.015, max_current_a=1.0),
    )
    network = BatteryNetwork.single(pack)
    bus = BusSolver().solve(network, network.full_state(), [limited], [0.9], rho=1.225, airspeed_mps=5.0)

    assert not bus.is_feasible
    assert bus.infeasible_reason == "unit_0_esc_current_limit"


def test_bus_needs_a_throttle_per_unit(unit, pack):
    network = BatteryNetwork.single(pack)
    with pytest.raises(ValueError, match="2 throttles for 1 units"):
        BusSolver().solve(network, network.full_state(), [unit], [0.5, 0.5], rho=1.225, airspeed_mps=5.0)


def _pack_with_cell_resistance(resistance_ohm):
    return RateMapBattery(
        name="3S pack",
        capacity_ah=4.2,
        cutoff_voltage_v=3.0,
        charge_voltage_v=4.2,
        max_current_a=60.0,
        series=3,
        parallel=1,
        dod=[0.0, 1.0],
        ocv_v=[4.1, 3.5],
        resistance_ohm=[resistance_ohm, resistance_ohm],
    )


def test_windmilling_unit_gives_an_infeasible_point(unit, pack):
    network = BatteryNetwork.single(pack)
    bus = BusSolver().solve(network, network.full_state(), [unit], [0.05], rho=1.225, airspeed_mps=20.0)

    assert not bus.is_feasible
    assert bus.infeasible_reason == "unit_0_no_bracket"
    assert bus.voltage_v == network.thevenin(network.full_state())[0]


def test_network_that_cannot_hold_the_load_gives_an_infeasible_point(unit):
    network = BatteryNetwork.single(_pack_with_cell_resistance(5.0))
    bus = BusSolver().solve(network, network.full_state(), [unit], [1.0], rho=1.225, airspeed_mps=0.0)

    assert not bus.is_feasible
    assert bus.infeasible_reason == "bus_overload"


def test_bus_balances_above_the_voltage_where_a_unit_stops(unit):
    # At this throttle and airspeed the unit has no operating point a little below
    # the bus voltage, so the sag search reaches a voltage where the unit stops
    # before the residual turns negative.
    network = BatteryNetwork.single(_pack_with_cell_resistance(0.6))
    state = network.full_state()
    bus = BusSolver().solve(network, state, [unit], [0.32], rho=1.225, airspeed_mps=10.0)

    ocv_v, resistance_ohm = network.thevenin(state)
    assert bus.units[0].infeasible_reason not in ("no_bracket", "no_convergence")
    assert math.isclose(bus.voltage_v, ocv_v - resistance_ohm * bus.current_a, rel_tol=1e-9)
