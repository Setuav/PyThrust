"""Battery packs wired in series strings connected in parallel."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Sequence

import numpy as np
from scipy.integrate import solve_ivp

from .rate_map import RateMapBattery
from .state import BatteryPoint, BatteryState

_VOLTAGE_MATCH_TOLERANCE = 0.01


@dataclass(frozen=True)
class NetworkState:
    """State of charge of every pack of a network, in ``BatteryNetwork.packs`` order."""

    packs: tuple[BatteryState, ...]

    @classmethod
    def uniform(cls, pack_count: int, soc: float = 1.0) -> "NetworkState":
        """Return a state with every one of ``pack_count`` packs at ``soc``."""
        return cls(tuple(BatteryState(soc=soc) for _ in range(pack_count)))


@dataclass(frozen=True)
class NetworkPoint:
    """Electrical state of a network at its terminals and in every pack."""

    terminal_voltage_v: float
    current_a: float
    power_w: float
    ocv_v: float
    resistance_ohm: float
    packs: tuple[BatteryPoint, ...]
    is_feasible: bool
    infeasible_reason: Optional[str] = None


@dataclass(frozen=True)
class NetworkIntegrationResult:
    """Constant-power discharge history of a network."""

    final_state: NetworkState
    time_s: tuple[float, ...]
    pack_soc: tuple[tuple[float, ...], ...]
    """State-of-charge history of each pack, in ``BatteryNetwork.packs`` order."""
    voltage_v: tuple[float, ...]
    current_a: tuple[float, ...]
    delivered_energy_wh: float
    stop_reason: str


@dataclass(frozen=True)
class BatteryNetwork:
    """Battery packs wired as parallel strings of series-connected packs.

    ``strings[i]`` lists the packs connected in series in string ``i``; all strings
    share the network terminals. Every pack is a rate-map battery whose open-circuit
    voltage and resistance follow its own state of charge, so at any instant the
    network is a Thevenin source and the strings share the load current according to
    their open-circuit voltages and resistances.
    """

    strings: tuple[tuple[RateMapBattery, ...], ...]

    def __post_init__(self) -> None:
        strings = tuple(tuple(string) for string in self.strings)
        if not strings or any(not string for string in strings):
            raise ValueError("a battery network needs at least one pack in every string")
        windows = [
            (
                sum(pack.charge_voltage_v * pack.series for pack in string),
                sum(pack.cutoff_voltage_v * pack.series for pack in string),
            )
            for string in strings
        ]
        charge_v, cutoff_v = windows[0]
        for other_charge_v, other_cutoff_v in windows[1:]:
            if not (
                math.isclose(other_charge_v, charge_v, rel_tol=_VOLTAGE_MATCH_TOLERANCE)
                and math.isclose(other_cutoff_v, cutoff_v, rel_tol=_VOLTAGE_MATCH_TOLERANCE)
            ):
                raise ValueError(
                    "parallel strings need matching charge and cut-off voltages, got "
                    f"{charge_v:g}-{cutoff_v:g} V and {other_charge_v:g}-{other_cutoff_v:g} V"
                )
        object.__setattr__(self, "strings", strings)

    @classmethod
    def single(cls, pack: RateMapBattery) -> "BatteryNetwork":
        """Return a network of one pack."""
        return cls(((pack,),))

    @classmethod
    def parallel(cls, *packs: RateMapBattery) -> "BatteryNetwork":
        """Return a network of ``packs`` connected in parallel."""
        return cls(tuple((pack,) for pack in packs))

    @classmethod
    def series(cls, *packs: RateMapBattery) -> "BatteryNetwork":
        """Return a network of ``packs`` connected in series."""
        return cls((tuple(packs),))

    @property
    def packs(self) -> tuple[RateMapBattery, ...]:
        """Every pack, string by string."""
        return tuple(pack for string in self.strings for pack in string)

    def full_state(self) -> NetworkState:
        """Return the state with every pack fully charged."""
        return NetworkState.uniform(len(self.packs))

    def thevenin(self, state: NetworkState) -> tuple[float, float]:
        """Return the network open-circuit voltage and resistance at ``state``."""
        string_ocv, string_resistance = self._string_sources(state)
        conductance = sum(1.0 / resistance for resistance in string_resistance)
        ocv_v = sum(ocv / resistance for ocv, resistance in zip(string_ocv, string_resistance)) / conductance
        return ocv_v, 1.0 / conductance

    def state_at_current(self, state: NetworkState, current_a: float) -> NetworkPoint:
        """Evaluate the network for a terminal current."""
        ocv_v, resistance_ohm = self.thevenin(state)
        voltage_v = ocv_v - resistance_ohm * current_a
        return self._point(state, voltage_v, current_a, ocv_v, resistance_ohm)

    def state_at_power(self, state: NetworkState, power_w: float) -> NetworkPoint:
        """Evaluate the network for a terminal power draw."""
        ocv_v, resistance_ohm = self.thevenin(state)
        discriminant = ocv_v**2 - 4.0 * resistance_ohm * power_w
        if discriminant < 0.0:
            return NetworkPoint(
                terminal_voltage_v=0.0,
                current_a=0.0,
                power_w=0.0,
                ocv_v=ocv_v,
                resistance_ohm=resistance_ohm,
                packs=(),
                is_feasible=False,
                infeasible_reason="power_limit",
            )
        current_a = (ocv_v - math.sqrt(discriminant)) / (2.0 * resistance_ohm)
        return self._point(state, ocv_v - resistance_ohm * current_a, current_a, ocv_v, resistance_ohm)

    def integrate_power_to_soc(
        self,
        state: NetworkState,
        power_w: float,
        final_soc: float,
        *,
        max_step_s: float = 60.0,
    ) -> NetworkIntegrationResult:
        """Discharge at constant terminal power until a pack reaches ``final_soc``.

        Each pack drains with its own share of the current. The discharge ends
        earlier when any pack reaches its cut-off voltage or current limit, or the
        network can no longer deliver the power.
        """
        packs = self.packs
        self._validate_state(state)
        if not math.isfinite(power_w) or power_w <= 0.0:
            raise ValueError("power_w must be finite and positive")
        if not 0.0 <= final_soc < min(pack_state.soc for pack_state in state.packs):
            raise ValueError("final_soc must be non-negative and below every pack's state of charge")
        if max_step_s <= 0.0:
            raise ValueError("max_step_s must be positive")

        def network_state(values: np.ndarray) -> NetworkState:
            return NetworkState(tuple(BatteryState(soc=float(min(1.0, max(0.0, v)))) for v in values))

        def rhs(_time_s: float, values: np.ndarray) -> list[float]:
            point = self.state_at_power(network_state(values), power_w)
            if not point.is_feasible and not point.packs:
                return [0.0] * len(packs)
            return [
                -pack_point.cell_current_a / pack.capacity_as
                for pack, pack_point in zip(packs, point.packs)
            ]

        def depleted(_time_s: float, values: np.ndarray) -> float:
            return float(min(values) - final_soc)

        def infeasible(_time_s: float, values: np.ndarray) -> float:
            return _feasibility_margin(self.state_at_power(network_state(values), power_w), packs)

        depleted.terminal = True  # type: ignore[attr-defined]
        depleted.direction = -1  # type: ignore[attr-defined]
        infeasible.terminal = True  # type: ignore[attr-defined]
        infeasible.direction = -1  # type: ignore[attr-defined]

        start = np.array([pack_state.soc for pack_state in state.packs])
        if _feasibility_margin(self.state_at_power(state, power_w), packs) <= 0.0:
            return self._integration_result(np.array([0.0]), start[:, None], power_w, "infeasible_start")

        reference_current_a = power_w / max(self.thevenin(state)[0], 1e-9)
        horizon_s = 10.0 * sum(pack.capacity_as for pack in packs) / max(reference_current_a, 1e-9)
        solution = solve_ivp(
            rhs,
            (0.0, horizon_s),
            start,
            max_step=max_step_s,
            events=(depleted, infeasible),
            rtol=1e-8,
            atol=1e-10,
        )
        if solution.t_events[0].size:
            reason = "final_soc"
        elif solution.t_events[1].size:
            reason = _stop_reason(self.state_at_power(network_state(solution.y[:, -1]), power_w))
        else:
            reason = "time_horizon"
        return self._integration_result(solution.t, solution.y, power_w, reason)

    def _string_sources(self, state: NetworkState) -> tuple[list[float], list[float]]:
        self._validate_state(state)
        pack_states = iter(state.packs)
        string_ocv: list[float] = []
        string_resistance: list[float] = []
        for string in self.strings:
            ocv_v = 0.0
            resistance_ohm = 0.0
            for pack in string:
                dod = next(pack_states).dod
                ocv_v += pack.ocv(dod) * pack.series
                resistance_ohm += pack.resistance(dod) * pack.series / pack.parallel
            string_ocv.append(ocv_v)
            string_resistance.append(resistance_ohm)
        return string_ocv, string_resistance

    def _point(
        self,
        state: NetworkState,
        voltage_v: float,
        current_a: float,
        ocv_v: float,
        resistance_ohm: float,
    ) -> NetworkPoint:
        string_ocv, string_resistance = self._string_sources(state)
        pack_states = iter(state.packs)
        pack_points: list[BatteryPoint] = []
        for string, string_ocv_v, string_resistance_ohm in zip(self.strings, string_ocv, string_resistance):
            string_current_a = (string_ocv_v - voltage_v) / string_resistance_ohm
            pack_points.extend(
                pack.state_at_current(next(pack_states), string_current_a) for pack in string
            )
        reason = next(
            (
                f"pack_{index}_{point.infeasible_reason}"
                for index, point in enumerate(pack_points)
                if not point.is_feasible
            ),
            None,
        )
        return NetworkPoint(
            terminal_voltage_v=float(voltage_v),
            current_a=float(current_a),
            power_w=float(voltage_v * current_a),
            ocv_v=float(ocv_v),
            resistance_ohm=float(resistance_ohm),
            packs=tuple(pack_points),
            is_feasible=reason is None,
            infeasible_reason=reason,
        )

    def _validate_state(self, state: NetworkState) -> None:
        if len(state.packs) != len(self.packs):
            raise ValueError(
                f"network state has {len(state.packs)} packs, the network has {len(self.packs)}"
            )

    def _integration_result(
        self,
        time_s: Sequence[float],
        soc: np.ndarray,
        power_w: float,
        stop_reason: str,
    ) -> NetworkIntegrationResult:
        voltages: list[float] = []
        currents: list[float] = []
        for column in range(soc.shape[1]):
            point = self.state_at_power(
                NetworkState(tuple(BatteryState(soc=float(min(1.0, max(0.0, v)))) for v in soc[:, column])),
                power_w,
            )
            voltages.append(point.terminal_voltage_v)
            currents.append(point.current_a)
        times = tuple(float(t) for t in time_s)
        return NetworkIntegrationResult(
            final_state=NetworkState(
                tuple(BatteryState(soc=float(min(1.0, max(0.0, v)))) for v in soc[:, -1])
            ),
            time_s=times,
            pack_soc=tuple(tuple(float(v) for v in row) for row in soc),
            voltage_v=tuple(voltages),
            current_a=tuple(currents),
            delivered_energy_wh=power_w * times[-1] / 3600.0,
            stop_reason=stop_reason,
        )


def _feasibility_margin(point: NetworkPoint, packs: Sequence[RateMapBattery]) -> float:
    """Smallest relative headroom to a pack's cut-off voltage or current limit."""
    if not point.packs:
        return -1.0
    margins: list[float] = []
    for pack, pack_point in zip(packs, point.packs):
        margins.append((pack_point.cell_voltage_v - pack.cutoff_voltage_v) / pack.cutoff_voltage_v)
        margins.append((pack.max_current_a - pack_point.cell_current_a) / pack.max_current_a)
    return min(margins)


def _stop_reason(point: NetworkPoint) -> str:
    return point.infeasible_reason or "infeasible"
