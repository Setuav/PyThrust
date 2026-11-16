"""Propulsion units sharing one battery network."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from scipy.optimize import brentq

from pythrust.battery import FixedVoltageBattery
from pythrust.battery.network import BatteryNetwork, NetworkPoint, NetworkState
from pythrust.propellers.database import PropellerEntry

from .models import MotorSpec, OperatingPoint, PropellerSpec, SystemSpec
from .solver import PropulsionSolver

_SAG_SEARCH_FRACTIONS = (0.98, 0.95, 0.9, 0.8, 0.65, 0.5, 0.35, 0.2)
"""Bus voltages, as fractions of the open-circuit voltage, searched for the root."""
_UNSOLVED = ("no_bracket", "no_convergence")
_BOUNDARY_TOLERANCE = 1e-6
"""Relative width to which the voltage where a unit loses its operating point is bisected."""


@dataclass(frozen=True)
class PropulsionUnit:
    """Motor, propeller and speed controller driven from a battery network."""

    motor: MotorSpec
    propeller: PropellerSpec
    prop_entry: PropellerEntry
    system: SystemSpec = SystemSpec()


@dataclass(frozen=True)
class BusOperatingPoint:
    """Operating point of every unit on a bus and of the network feeding it.

    An infeasible point need not balance the network: when a unit has no
    operating point, or the network cannot supply the units' current at any
    voltage they run at, ``voltage_v`` is the voltage the search stopped at and
    ``network`` is the network at the units' current there.
    """

    voltage_v: float
    current_a: float
    units: tuple[OperatingPoint, ...]
    network: NetworkPoint
    is_feasible: bool
    infeasible_reason: Optional[str] = None

    @property
    def power_w(self) -> float:
        """Electrical power drawn from the network."""
        return self.voltage_v * self.current_a

    @property
    def thrust_n(self) -> float:
        """Thrust summed over the units."""
        return sum(unit.thrust_n for unit in self.units)


class BusSolver:
    """Solve units that share one battery network at their own throttles.

    The units see the network's terminal voltage, which sags with their total
    current. The bus voltage is the root of ``V - (Voc - R * sum(I_k(V)))``, where
    ``I_k(V)`` is the battery-side current of unit ``k`` supplied at ``V`` and
    ``Voc`` and ``R`` are the network's open-circuit voltage and resistance.
    """

    def __init__(self, solver: Optional[PropulsionSolver] = None) -> None:
        self.solver = solver or PropulsionSolver()

    def solve(
        self,
        network: BatteryNetwork,
        state: NetworkState,
        units: Sequence[PropulsionUnit],
        throttles: Sequence[float],
        rho: float,
        airspeed_mps: float,
    ) -> BusOperatingPoint:
        if not units:
            raise ValueError("a bus needs at least one propulsion unit")
        if len(throttles) != len(units):
            raise ValueError(f"got {len(throttles)} throttles for {len(units)} units")
        ocv_v, resistance_ohm = network.thevenin(state)

        def unit_points(voltage_v: float) -> tuple[OperatingPoint, ...]:
            battery = FixedVoltageBattery(voltage_v=voltage_v)
            return tuple(
                self.solver.solve_operating_point(
                    motor=unit.motor,
                    battery=battery,
                    system=unit.system,
                    propeller=unit.propeller,
                    prop_entry=unit.prop_entry,
                    rho=rho,
                    airspeed_mps=airspeed_mps,
                    throttle=throttle,
                )
                for unit, throttle in zip(units, throttles)
            )

        def residual(points: tuple[OperatingPoint, ...], voltage_v: float) -> float:
            current_a = sum(point.battery_current_a for point in points)
            return voltage_v - (ocv_v - resistance_ohm * current_a)

        # The residual rises with the voltage, so the bus voltage lies between the
        # open-circuit voltage and the first lower voltage where the residual turns
        # negative. The search steps down from the open-circuit voltage, because the
        # units lose their operating point as the voltage falls.
        upper_v = ocv_v
        upper_points = unit_points(upper_v)
        if _unsolved(upper_points) or residual(upper_points, upper_v) <= 0.0:
            return _bus_point(network, state, upper_v, upper_points)
        lower_v: Optional[float] = None
        for fraction in _SAG_SEARCH_FRACTIONS:
            candidate_v = fraction * ocv_v
            points = unit_points(candidate_v)
            if _unsolved(points):
                candidate_v = _lowest_solved_voltage(unit_points, candidate_v, upper_v)
                points = unit_points(candidate_v)
                if residual(points, candidate_v) > 0.0:
                    return _bus_point(network, state, candidate_v, points, overloaded=True)
                lower_v = candidate_v
                break
            if residual(points, candidate_v) < 0.0:
                lower_v = candidate_v
                break
            upper_v, upper_points = candidate_v, points
        if lower_v is None:
            return _bus_point(network, state, upper_v, upper_points, overloaded=True)
        voltage_v = float(
            brentq(
                lambda v: residual(unit_points(v), v),
                lower_v,
                upper_v,
                xtol=1e-9,
                rtol=1e-12,
            )
        )
        return _bus_point(network, state, voltage_v, unit_points(voltage_v))


def _unsolved(points: Sequence[OperatingPoint]) -> bool:
    """Whether a unit has no operating point at the voltage it was solved for."""
    return any(point.infeasible_reason in _UNSOLVED for point in points)


def _lowest_solved_voltage(
    unit_points: Callable[[float], tuple[OperatingPoint, ...]],
    unsolved_v: float,
    solved_v: float,
) -> float:
    """Bisect for the lowest voltage above ``unsolved_v`` at which every unit has an operating point."""
    while solved_v - unsolved_v > _BOUNDARY_TOLERANCE * solved_v:
        middle_v = 0.5 * (unsolved_v + solved_v)
        if _unsolved(unit_points(middle_v)):
            unsolved_v = middle_v
        else:
            solved_v = middle_v
    return solved_v


def _bus_point(
    network: BatteryNetwork,
    state: NetworkState,
    voltage_v: float,
    points: tuple[OperatingPoint, ...],
    *,
    overloaded: bool = False,
) -> BusOperatingPoint:
    current_a = sum(point.battery_current_a for point in points)
    network_point = network.state_at_current(state, current_a)
    reason = "bus_overload" if overloaded else None
    if reason is None:
        reason = next(
            (
                f"unit_{index}_{point.infeasible_reason}"
                for index, point in enumerate(points)
                if not point.is_feasible and point.infeasible_reason != "throttle<=0"
            ),
            None,
        )
    if reason is None and not network_point.is_feasible:
        reason = f"network_{network_point.infeasible_reason}"
    return BusOperatingPoint(
        voltage_v=float(voltage_v),
        current_a=float(current_a),
        units=points,
        network=network_point,
        is_feasible=reason is None,
        infeasible_reason=reason,
    )
