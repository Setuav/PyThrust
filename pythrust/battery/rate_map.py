"""Rate-map battery model."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Sequence

import numpy as np

from .state import BatteryIntegrationResult, BatteryPoint, BatteryState


@dataclass(frozen=True)
class RateMapBattery:
    """Equivalent-circuit battery model driven by OCV and resistance curves."""

    name: str
    capacity_ah: float
    cutoff_voltage_v: float
    charge_voltage_v: float
    max_current_a: float
    series: int
    parallel: int
    dod: Sequence[float]
    ocv_v: Sequence[float]
    resistance_ohm: Sequence[float]
    source: str | None = None

    def __post_init__(self) -> None:
        dod = tuple(float(v) for v in self.dod)
        ocv_v = tuple(float(v) for v in self.ocv_v)
        resistance_ohm = tuple(float(v) for v in self.resistance_ohm)

        if len(dod) < 2:
            raise ValueError("dod must contain at least two points")
        if not (len(dod) == len(ocv_v) == len(resistance_ohm)):
            raise ValueError("dod, ocv_v, and resistance_ohm must have the same length")
        if any(v < 0.0 or v > 1.0 for v in dod):
            raise ValueError("dod values must be between 0 and 1")
        if any(b <= a for a, b in zip(dod, dod[1:])):
            raise ValueError("dod values must be strictly increasing")
        if any(v <= 0.0 for v in resistance_ohm):
            raise ValueError("resistance_ohm values must be positive")
        if self.capacity_ah <= 0.0:
            raise ValueError("capacity_ah must be positive")
        if self.max_current_a <= 0.0:
            raise ValueError("max_current_a must be positive")
        if self.series <= 0 or self.parallel <= 0:
            raise ValueError("series and parallel counts must be positive")

        object.__setattr__(self, "dod", dod)
        object.__setattr__(self, "ocv_v", ocv_v)
        object.__setattr__(self, "resistance_ohm", resistance_ohm)

    @classmethod
    def from_json(
        cls,
        path: str | Path,
        *,
        series: int = 1,
        parallel: int = 1,
    ) -> "RateMapBattery":
        """Load a cell dataset and apply pack series/parallel topology."""
        with Path(path).open("r", encoding="utf-8") as f:
            data = json.load(f)

        cell = data["cell"]
        curves = data["curves"]
        return cls(
            name=data.get("name", "Rate-map cell"),
            source=data.get("source"),
            capacity_ah=cell["capacity_ah"],
            cutoff_voltage_v=cell["cutoff_voltage_v"],
            charge_voltage_v=cell["charge_voltage_v"],
            max_current_a=cell["max_current_a"],
            series=series,
            parallel=parallel,
            dod=curves["dod"],
            ocv_v=curves["ocv_v"],
            resistance_ohm=curves["resistance_ohm"],
        )

    @property
    def capacity_as(self) -> float:
        """Cell capacity in ampere-seconds."""
        return self.capacity_ah * 3600.0

    @property
    def rated_current_a(self) -> float:
        """Cell 1C current in amps."""
        return self.capacity_ah

    def ocv(self, dod: float) -> float:
        """Interpolate open-circuit cell voltage at depth of discharge."""
        return float(np.interp(self._clip_dod(dod), self.dod, self.ocv_v))

    def resistance(self, dod: float) -> float:
        """Interpolate cell resistance at depth of discharge."""
        return float(np.interp(self._clip_dod(dod), self.dod, self.resistance_ohm))

    def terminal_voltage(self, current_a: float, state: BatteryState) -> float:
        """Return pack terminal voltage at pack current and battery state."""
        return self.state_at_current(state=state, current_a=current_a).terminal_voltage_v

    def terminal_power(self, current_a: float, state: BatteryState) -> float:
        """Return pack terminal power at pack current and battery state."""
        return self.state_at_current(state=state, current_a=current_a).power_w

    def state_at_current(self, state: BatteryState, current_a: float) -> BatteryPoint:
        """Evaluate battery point state for a specified pack current."""
        cell_current_a = current_a / self.parallel
        dod = state.dod
        ocv_v = self.ocv(dod)
        resistance_ohm = self.resistance(dod)
        cell_voltage_v = ocv_v - resistance_ohm * cell_current_a
        return self._point_from_cell_state(
            state=state,
            cell_current_a=cell_current_a,
            cell_voltage_v=cell_voltage_v,
            ocv_v=ocv_v,
            resistance_ohm=resistance_ohm,
        )

    def state_at_c_rate(self, state: BatteryState, c_rate: float) -> BatteryPoint:
        """Evaluate battery point state for a specified cell C-rate."""
        return self.state_at_current(
            state=state,
            current_a=c_rate * self.rated_current_a * self.parallel,
        )

    def state_at_voltage(self, state: BatteryState, voltage_v: float) -> BatteryPoint:
        """Evaluate battery point state for a specified pack voltage."""
        cell_voltage_v = voltage_v / self.series
        dod = state.dod
        ocv_v = self.ocv(dod)
        resistance_ohm = self.resistance(dod)
        cell_current_a = (ocv_v - cell_voltage_v) / resistance_ohm
        return self._point_from_cell_state(
            state=state,
            cell_current_a=cell_current_a,
            cell_voltage_v=cell_voltage_v,
            ocv_v=ocv_v,
            resistance_ohm=resistance_ohm,
        )

    def state_at_power(self, state: BatteryState, power_w: float) -> BatteryPoint:
        """Evaluate battery point state for a specified pack power draw."""
        dod = state.dod
        ocv_v = self.ocv(dod)
        resistance_ohm = self.resistance(dod)
        cell_power_w = power_w / (self.series * self.parallel)
        discriminant = ocv_v**2 - 4.0 * resistance_ohm * cell_power_w

        if discriminant < 0.0:
            return BatteryPoint(
                terminal_voltage_v=0.0,
                current_a=0.0,
                power_w=0.0,
                cell_voltage_v=0.0,
                cell_current_a=0.0,
                c_rate=0.0,
                efficiency=0.0,
                ocv_v=ocv_v,
                resistance_ohm=resistance_ohm,
                is_feasible=False,
                infeasible_reason="power_limit",
            )

        cell_current_a = (ocv_v - math.sqrt(discriminant)) / (2.0 * resistance_ohm)
        cell_voltage_v = ocv_v - resistance_ohm * cell_current_a
        return self._point_from_cell_state(
            state=state,
            cell_current_a=cell_current_a,
            cell_voltage_v=cell_voltage_v,
            ocv_v=ocv_v,
            resistance_ohm=resistance_ohm,
        )

    def state_at_load_resistance(self, state: BatteryState, resistance_ohm: float) -> BatteryPoint:
        """Evaluate battery point state for a specified pack load resistance."""
        if resistance_ohm <= 0.0:
            raise ValueError("load resistance must be positive")

        dod = state.dod
        ocv_v = self.ocv(dod)
        cell_internal_ohm = self.resistance(dod)
        cell_load_ohm = resistance_ohm * self.parallel / self.series
        cell_current_a = ocv_v / (cell_internal_ohm + cell_load_ohm)
        cell_voltage_v = ocv_v - cell_internal_ohm * cell_current_a
        return self._point_from_cell_state(
            state=state,
            cell_current_a=cell_current_a,
            cell_voltage_v=cell_voltage_v,
            ocv_v=ocv_v,
            resistance_ohm=cell_internal_ohm,
        )

    def step_current(self, state: BatteryState, current_a: float, dt_s: float) -> BatteryState:
        """Advance state using constant pack current over a time step."""
        if dt_s < 0.0:
            raise ValueError("dt_s must be non-negative")
        cell_current_a = current_a / self.parallel
        dod_next = state.dod + cell_current_a * dt_s / self.capacity_as
        return BatteryState.from_dod(min(1.0, max(0.0, dod_next)))

    def step_power(self, state: BatteryState, power_w: float, dt_s: float) -> BatteryState:
        """Advance state using constant pack power over a time step."""
        point = self.state_at_power(state=state, power_w=power_w)
        if not point.is_feasible:
            raise ValueError(point.infeasible_reason or "infeasible battery power")
        return self.step_current(state=state, current_a=point.current_a, dt_s=dt_s)

    def integrate_current(
        self,
        state: BatteryState,
        current_a: float,
        dt_s: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate battery state under constant pack current."""
        self._validate_integration_inputs(current_a, dt_s, max_step_s, "current_a")

        elapsed_s = 0.0
        current_state = state
        current_point = self.state_at_current(state=current_state, current_a=current_a)
        histories = self._initial_integration_histories(current_state, current_point)
        delivered_energy_wh = 0.0
        consumed_charge_ah = 0.0

        if not current_point.is_feasible:
            return self._integration_result(
                final_state=current_state,
                histories=histories,
                delivered_energy_wh=delivered_energy_wh,
                consumed_charge_ah=consumed_charge_ah,
                is_feasible=False,
                stop_reason=current_point.infeasible_reason or "infeasible_state",
            )
        if dt_s == 0.0:
            return self._integration_result(
                final_state=current_state,
                histories=histories,
                delivered_energy_wh=delivered_energy_wh,
                consumed_charge_ah=consumed_charge_ah,
                is_feasible=True,
                stop_reason="duration_complete",
            )
        if current_a == 0.0:
            self._append_integration_sample(histories, dt_s, current_state, current_point)
            return self._integration_result(
                final_state=current_state,
                histories=histories,
                delivered_energy_wh=delivered_energy_wh,
                consumed_charge_ah=consumed_charge_ah,
                is_feasible=True,
                stop_reason="duration_complete",
            )

        while elapsed_s < dt_s:
            step_s = min(max_step_s, dt_s - elapsed_s)
            time_to_dod_limit_s = self._time_to_dod_limit(current_state, current_a)
            reaches_dod_limit = time_to_dod_limit_s <= step_s
            if reaches_dod_limit:
                step_s = time_to_dod_limit_s
            if step_s <= 0.0:
                return self._integration_result(
                    final_state=current_state,
                    histories=histories,
                    delivered_energy_wh=delivered_energy_wh,
                    consumed_charge_ah=consumed_charge_ah,
                    is_feasible=False,
                    stop_reason="dod_limit",
                )

            next_state = self._advance_state_for_current(current_state, current_a, step_s)
            next_point = self.state_at_current(state=next_state, current_a=current_a)

            if not next_point.is_feasible:
                reason = next_point.infeasible_reason or "infeasible_state"
                step_s, next_state, next_point = self._find_current_integration_boundary(
                    current_state,
                    current_a,
                    step_s,
                )
                delivered_energy_wh += self._trapezoid(current_point.power_w, next_point.power_w, step_s) / 3600.0
                consumed_charge_ah += self._trapezoid(current_point.current_a, next_point.current_a, step_s) / 3600.0
                elapsed_s += step_s
                self._append_integration_sample(histories, elapsed_s, next_state, next_point)
                return self._integration_result(
                    final_state=next_state,
                    histories=histories,
                    delivered_energy_wh=delivered_energy_wh,
                    consumed_charge_ah=consumed_charge_ah,
                    is_feasible=False,
                    stop_reason=reason,
                )

            delivered_energy_wh += self._trapezoid(current_point.power_w, next_point.power_w, step_s) / 3600.0
            consumed_charge_ah += self._trapezoid(current_point.current_a, next_point.current_a, step_s) / 3600.0
            elapsed_s += step_s
            self._append_integration_sample(histories, elapsed_s, next_state, next_point)
            current_state = next_state
            current_point = next_point

            if reaches_dod_limit and elapsed_s < dt_s:
                return self._integration_result(
                    final_state=current_state,
                    histories=histories,
                    delivered_energy_wh=delivered_energy_wh,
                    consumed_charge_ah=consumed_charge_ah,
                    is_feasible=False,
                    stop_reason="dod_limit",
                )

        return self._integration_result(
            final_state=current_state,
            histories=histories,
            delivered_energy_wh=delivered_energy_wh,
            consumed_charge_ah=consumed_charge_ah,
            is_feasible=True,
            stop_reason="duration_complete",
        )

    def integrate_power(
        self,
        state: BatteryState,
        power_w: float,
        dt_s: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate battery state under constant pack power draw."""
        self._validate_integration_inputs(power_w, dt_s, max_step_s, "power_w")

        elapsed_s = 0.0
        current_state = state
        current_point = self.state_at_power(state=current_state, power_w=power_w)
        histories = self._initial_integration_histories(current_state, current_point)
        delivered_energy_wh = 0.0
        consumed_charge_ah = 0.0

        if not current_point.is_feasible:
            return self._integration_result(
                final_state=current_state,
                histories=histories,
                delivered_energy_wh=delivered_energy_wh,
                consumed_charge_ah=consumed_charge_ah,
                is_feasible=False,
                stop_reason=current_point.infeasible_reason or "infeasible_state",
            )
        if dt_s == 0.0:
            return self._integration_result(
                final_state=current_state,
                histories=histories,
                delivered_energy_wh=delivered_energy_wh,
                consumed_charge_ah=consumed_charge_ah,
                is_feasible=True,
                stop_reason="duration_complete",
            )
        if power_w == 0.0:
            self._append_integration_sample(histories, dt_s, current_state, current_point)
            return self._integration_result(
                final_state=current_state,
                histories=histories,
                delivered_energy_wh=delivered_energy_wh,
                consumed_charge_ah=consumed_charge_ah,
                is_feasible=True,
                stop_reason="duration_complete",
            )

        while elapsed_s < dt_s:
            step_s = min(max_step_s, dt_s - elapsed_s)
            time_to_dod_limit_s = self._time_to_dod_limit(current_state, current_point.current_a)
            reaches_dod_limit = time_to_dod_limit_s <= step_s
            if reaches_dod_limit:
                step_s = time_to_dod_limit_s
            if step_s <= 0.0:
                return self._integration_result(
                    final_state=current_state,
                    histories=histories,
                    delivered_energy_wh=delivered_energy_wh,
                    consumed_charge_ah=consumed_charge_ah,
                    is_feasible=False,
                    stop_reason="dod_limit",
                )

            next_state = self._advance_state_for_current(current_state, current_point.current_a, step_s)
            next_point = self.state_at_power(state=next_state, power_w=power_w)

            if not next_point.is_feasible:
                reason = next_point.infeasible_reason or "infeasible_state"
                step_s, next_state, next_point = self._find_power_integration_boundary(
                    current_state,
                    current_point.current_a,
                    power_w,
                    step_s,
                )
                delivered_energy_wh += self._trapezoid(current_point.power_w, next_point.power_w, step_s) / 3600.0
                consumed_charge_ah += self._trapezoid(current_point.current_a, next_point.current_a, step_s) / 3600.0
                elapsed_s += step_s
                self._append_integration_sample(histories, elapsed_s, next_state, next_point)
                return self._integration_result(
                    final_state=next_state,
                    histories=histories,
                    delivered_energy_wh=delivered_energy_wh,
                    consumed_charge_ah=consumed_charge_ah,
                    is_feasible=False,
                    stop_reason=reason,
                )

            delivered_energy_wh += self._trapezoid(current_point.power_w, next_point.power_w, step_s) / 3600.0
            consumed_charge_ah += self._trapezoid(current_point.current_a, next_point.current_a, step_s) / 3600.0
            elapsed_s += step_s
            self._append_integration_sample(histories, elapsed_s, next_state, next_point)
            current_state = next_state
            current_point = next_point

            if reaches_dod_limit and elapsed_s < dt_s:
                return self._integration_result(
                    final_state=current_state,
                    histories=histories,
                    delivered_energy_wh=delivered_energy_wh,
                    consumed_charge_ah=consumed_charge_ah,
                    is_feasible=False,
                    stop_reason="dod_limit",
                )

        return self._integration_result(
            final_state=current_state,
            histories=histories,
            delivered_energy_wh=delivered_energy_wh,
            consumed_charge_ah=consumed_charge_ah,
            is_feasible=True,
            stop_reason="duration_complete",
        )

    def _point_from_cell_state(
        self,
        state: BatteryState,
        cell_current_a: float,
        cell_voltage_v: float,
        ocv_v: float,
        resistance_ohm: float,
    ) -> BatteryPoint:
        pack_current_a = cell_current_a * self.parallel
        pack_voltage_v = cell_voltage_v * self.series
        c_rate = cell_current_a / self.rated_current_a
        efficiency = cell_voltage_v / ocv_v if ocv_v > 0.0 else 0.0
        reason = None

        if cell_current_a > self.max_current_a:
            reason = "current_limit"
        if reason is None and cell_voltage_v < self.cutoff_voltage_v:
            reason = "voltage_cutoff"
        if reason is None and cell_voltage_v > self.charge_voltage_v:
            reason = "voltage_limit"
        if reason is None and (state.dod < 0.0 or state.dod > 1.0):
            reason = "state_limit"

        return BatteryPoint(
            terminal_voltage_v=float(pack_voltage_v),
            current_a=float(pack_current_a),
            power_w=float(pack_voltage_v * pack_current_a),
            cell_voltage_v=float(cell_voltage_v),
            cell_current_a=float(cell_current_a),
            c_rate=float(c_rate),
            efficiency=float(efficiency),
            ocv_v=float(ocv_v),
            resistance_ohm=float(resistance_ohm),
            is_feasible=reason is None,
            infeasible_reason=reason,
        )

    @staticmethod
    def _clip_dod(dod: float) -> float:
        return min(1.0, max(0.0, float(dod)))

    @staticmethod
    def _trapezoid(left: float, right: float, width: float) -> float:
        return 0.5 * (left + right) * width

    @staticmethod
    def _validate_integration_inputs(load: float, dt_s: float, max_step_s: float, load_name: str) -> None:
        if not math.isfinite(load) or load < 0.0:
            raise ValueError(f"{load_name} must be finite and non-negative")
        if not math.isfinite(dt_s) or dt_s < 0.0:
            raise ValueError("dt_s must be finite and non-negative")
        if not math.isfinite(max_step_s) or max_step_s <= 0.0:
            raise ValueError("max_step_s must be finite and positive")

    def _advance_state_for_current(self, state: BatteryState, current_a: float, dt_s: float) -> BatteryState:
        cell_current_a = current_a / self.parallel
        dod_next = state.dod + cell_current_a * dt_s / self.capacity_as
        return BatteryState.from_dod(self._clip_dod(dod_next))

    def _time_to_dod_limit(self, state: BatteryState, current_a: float) -> float:
        cell_current_a = current_a / self.parallel
        if cell_current_a <= 0.0:
            return math.inf
        return max(0.0, (1.0 - state.dod) * self.capacity_as / cell_current_a)

    def _find_current_integration_boundary(
        self,
        state: BatteryState,
        current_a: float,
        step_s: float,
    ) -> tuple[float, BatteryState, BatteryPoint]:
        low_s = 0.0
        high_s = step_s
        boundary_state = state
        boundary_point = self.state_at_current(state=state, current_a=current_a)

        for _ in range(40):
            mid_s = 0.5 * (low_s + high_s)
            mid_state = self._advance_state_for_current(state, current_a, mid_s)
            mid_point = self.state_at_current(state=mid_state, current_a=current_a)
            if mid_point.is_feasible:
                low_s = mid_s
                boundary_state = mid_state
                boundary_point = mid_point
            else:
                high_s = mid_s

        return low_s, boundary_state, boundary_point

    def _find_power_integration_boundary(
        self,
        state: BatteryState,
        current_a: float,
        power_w: float,
        step_s: float,
    ) -> tuple[float, BatteryState, BatteryPoint]:
        low_s = 0.0
        high_s = step_s
        boundary_state = state
        boundary_point = self.state_at_power(state=state, power_w=power_w)

        for _ in range(40):
            mid_s = 0.5 * (low_s + high_s)
            mid_state = self._advance_state_for_current(state, current_a, mid_s)
            mid_point = self.state_at_power(state=mid_state, power_w=power_w)
            if mid_point.is_feasible:
                low_s = mid_s
                boundary_state = mid_state
                boundary_point = mid_point
            else:
                high_s = mid_s

        return low_s, boundary_state, boundary_point

    @staticmethod
    def _initial_integration_histories(state: BatteryState, point: BatteryPoint) -> dict[str, list[float]]:
        return {
            "time_s": [0.0],
            "dod": [state.dod],
            "voltage_v": [point.terminal_voltage_v],
            "current_a": [point.current_a],
            "c_rate": [point.c_rate],
            "power_w": [point.power_w],
            "efficiency": [point.efficiency],
        }

    @staticmethod
    def _append_integration_sample(
        histories: dict[str, list[float]],
        time_s: float,
        state: BatteryState,
        point: BatteryPoint,
    ) -> None:
        histories["time_s"].append(time_s)
        histories["dod"].append(state.dod)
        histories["voltage_v"].append(point.terminal_voltage_v)
        histories["current_a"].append(point.current_a)
        histories["c_rate"].append(point.c_rate)
        histories["power_w"].append(point.power_w)
        histories["efficiency"].append(point.efficiency)

    @staticmethod
    def _integration_result(
        final_state: BatteryState,
        histories: dict[str, list[float]],
        delivered_energy_wh: float,
        consumed_charge_ah: float,
        is_feasible: bool,
        stop_reason: str,
    ) -> BatteryIntegrationResult:
        return BatteryIntegrationResult(
            final_state=final_state,
            time_s=histories["time_s"],
            dod=histories["dod"],
            voltage_v=histories["voltage_v"],
            current_a=histories["current_a"],
            c_rate=histories["c_rate"],
            power_w=histories["power_w"],
            efficiency=histories["efficiency"],
            delivered_energy_wh=delivered_energy_wh,
            consumed_charge_ah=consumed_charge_ah,
            is_feasible=is_feasible,
            stop_reason=stop_reason,
        )
