"""Propulsion units sharing one battery network."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from scipy.optimize import brentq

from pythrust.battery import FixedVoltageBattery
from pythrust.battery.network import BatteryNetwork, NetworkPoint, NetworkState
from pythrust.propellers.database import PropellerEntry

from .models import MotorSpec, OperatingPoint, PropellerSpec, SystemSpec
from .solver import PropulsionSolver

_SAG_SEARCH_FRACTIONS = (0.98, 0.95, 0.9, 0.8, 0.65, 0.5, 0.35, 0.2)
"""Bus voltages, as fractions of the open-circuit voltage, searched for the root."""
_UNSOLVED = ("no_bracket", "no_convergence")


@dataclass(frozen=True)
class PropulsionUnit:
    """Motor, propeller and speed controller driven from a battery network."""

    motor: MotorSpec
    propeller: PropellerSpec
    prop_entry: PropellerEntry
    system: SystemSpec = SystemSpec()


@dataclass(frozen=True)
class BusOperatingPoint:
    """Operating point of every unit on a bus and of the network feeding it."""

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

        # The residual rises with the voltage, so the solution lies between the
        # open-circuit voltage and the first lower voltage where it turns negative.
        # The search steps down rather than starting near zero volts, where the
        # units have no operating point.
        upper_v = ocv_v
        if residual(unit_points(upper_v), upper_v) <= 0.0:
            voltage_v = upper_v
        else:
            lower_v: Optional[float] = None
            for fraction in _SAG_SEARCH_FRACTIONS:
                candidate_v = fraction * ocv_v
                points = unit_points(candidate_v)
                if any(point.infeasible_reason in _UNSOLVED for point in points):
                    break
                if residual(points, candidate_v) < 0.0:
                    lower_v = candidate_v
                    break
                upper_v = candidate_v
            if lower_v is None:
                raise ValueError(
                    "the battery network cannot hold the units' load: no bus voltage "
                    f"between {upper_v:.3g} V and its sag limit balances the current"
                )
            voltage_v = float(
                brentq(
                    lambda v: residual(unit_points(v), v),
                    lower_v,
                    upper_v,
                    xtol=1e-9,
                    rtol=1e-12,
                )
            )
        points = unit_points(voltage_v)
        current_a = sum(point.battery_current_a for point in points)
        network_point = network.state_at_current(state, current_a)
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
