"""Rate-map battery model."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
from scipy.integrate import solve_ivp

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

    def state_at_power_loss(self, state: BatteryState, power_loss_w: float) -> BatteryPoint:
        """Evaluate battery point state for a specified pack internal power loss."""
        if not math.isfinite(power_loss_w) or power_loss_w < 0.0:
            raise ValueError("power_loss_w must be finite and non-negative")

        dod = state.dod
        resistance_ohm = self.resistance(dod)
        cell_power_loss_w = power_loss_w / (self.series * self.parallel)
        cell_current_a = math.sqrt(cell_power_loss_w / resistance_ohm) if cell_power_loss_w > 0.0 else 0.0
        return self.state_at_current(state=state, current_a=cell_current_a * self.parallel)

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
        return self._integrate_with_point_function(
            state=state,
            dt_s=dt_s,
            max_step_s=max_step_s,
            point_function=lambda current_state: self.state_at_current(current_state, current_a),
        )

    def integrate_c_rate(
        self,
        state: BatteryState,
        c_rate: float,
        dt_s: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate battery state under constant cell C-rate."""
        if not math.isfinite(c_rate) or c_rate < 0.0:
            raise ValueError("c_rate must be finite and non-negative")
        return self.integrate_current(
            state=state,
            current_a=c_rate * self.rated_current_a * self.parallel,
            dt_s=dt_s,
            max_step_s=max_step_s,
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
        return self._integrate_with_point_function(
            state=state,
            dt_s=dt_s,
            max_step_s=max_step_s,
            point_function=lambda current_state: self.state_at_power(current_state, power_w),
        )

    def integrate_voltage(
        self,
        state: BatteryState,
        voltage_v: float,
        dt_s: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate battery state under constant pack terminal voltage."""
        self._validate_integration_inputs(voltage_v, dt_s, max_step_s, "voltage_v")
        return self._integrate_with_point_function(
            state=state,
            dt_s=dt_s,
            max_step_s=max_step_s,
            point_function=lambda current_state: self.state_at_voltage(current_state, voltage_v),
        )

    def integrate_load_resistance(
        self,
        state: BatteryState,
        resistance_ohm: float,
        dt_s: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate battery state under constant pack load resistance."""
        if not math.isfinite(resistance_ohm) or resistance_ohm <= 0.0:
            raise ValueError("resistance_ohm must be finite and positive")
        self._validate_integration_inputs(0.0, dt_s, max_step_s, "load")
        return self._integrate_with_point_function(
            state=state,
            dt_s=dt_s,
            max_step_s=max_step_s,
            point_function=lambda current_state: self.state_at_load_resistance(current_state, resistance_ohm),
        )

    def integrate_power_loss(
        self,
        state: BatteryState,
        power_loss_w: float,
        dt_s: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate battery state under constant pack internal power loss."""
        self._validate_integration_inputs(power_loss_w, dt_s, max_step_s, "power_loss_w")
        return self._integrate_with_point_function(
            state=state,
            dt_s=dt_s,
            max_step_s=max_step_s,
            point_function=lambda current_state: self.state_at_power_loss(current_state, power_loss_w),
        )

    def integrate_current_to_dod(
        self,
        state: BatteryState,
        current_a: float,
        dod_final: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate constant current until a target DOD is reached."""
        self._validate_integration_inputs(current_a, 0.0, max_step_s, "current_a")
        return self._integrate_to_dod(
            state=state,
            dod_final=dod_final,
            max_step_s=max_step_s,
            point_function=lambda current_state: self.state_at_current(current_state, current_a),
        )

    def integrate_c_rate_to_dod(
        self,
        state: BatteryState,
        c_rate: float,
        dod_final: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate constant cell C-rate until a target DOD is reached."""
        if not math.isfinite(c_rate) or c_rate < 0.0:
            raise ValueError("c_rate must be finite and non-negative")
        return self.integrate_current_to_dod(
            state=state,
            current_a=c_rate * self.rated_current_a * self.parallel,
            dod_final=dod_final,
            max_step_s=max_step_s,
        )

    def integrate_power_to_dod(
        self,
        state: BatteryState,
        power_w: float,
        dod_final: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate constant pack power until a target DOD is reached."""
        self._validate_integration_inputs(power_w, 0.0, max_step_s, "power_w")
        return self._integrate_to_dod(
            state=state,
            dod_final=dod_final,
            max_step_s=max_step_s,
            point_function=lambda current_state: self.state_at_power(current_state, power_w),
        )

    def integrate_voltage_to_dod(
        self,
        state: BatteryState,
        voltage_v: float,
        dod_final: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate constant pack terminal voltage until a target DOD is reached."""
        self._validate_integration_inputs(voltage_v, 0.0, max_step_s, "voltage_v")
        return self._integrate_to_dod(
            state=state,
            dod_final=dod_final,
            max_step_s=max_step_s,
            point_function=lambda current_state: self.state_at_voltage(current_state, voltage_v),
        )

    def integrate_load_resistance_to_dod(
        self,
        state: BatteryState,
        resistance_ohm: float,
        dod_final: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate constant pack load resistance until a target DOD is reached."""
        if not math.isfinite(resistance_ohm) or resistance_ohm <= 0.0:
            raise ValueError("resistance_ohm must be finite and positive")
        self._validate_integration_inputs(0.0, 0.0, max_step_s, "load")
        return self._integrate_to_dod(
            state=state,
            dod_final=dod_final,
            max_step_s=max_step_s,
            point_function=lambda current_state: self.state_at_load_resistance(current_state, resistance_ohm),
        )

    def integrate_power_loss_to_dod(
        self,
        state: BatteryState,
        power_loss_w: float,
        dod_final: float,
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate constant pack internal power loss until a target DOD is reached."""
        self._validate_integration_inputs(power_loss_w, 0.0, max_step_s, "power_loss_w")
        return self._integrate_to_dod(
            state=state,
            dod_final=dod_final,
            max_step_s=max_step_s,
            point_function=lambda current_state: self.state_at_power_loss(current_state, power_loss_w),
        )

    def dod_at_voltage_power(self, voltage_v: float, power_w: float) -> float:
        """Solve DOD where constant-voltage and requested-power states coincide."""
        self._validate_integration_inputs(voltage_v, 0.0, 1.0, "voltage_v")
        self._validate_integration_inputs(power_w, 0.0, 1.0, "power_w")
        return self._solve_dod(
            lambda dod: self.state_at_voltage(BatteryState.from_dod(dod), voltage_v).power_w - power_w
        )

    def dod_at_power_voltage(self, power_w: float, voltage_v: float) -> float:
        """Solve DOD where constant-power and requested-voltage states coincide."""
        self._validate_integration_inputs(power_w, 0.0, 1.0, "power_w")
        self._validate_integration_inputs(voltage_v, 0.0, 1.0, "voltage_v")
        return self._solve_dod(
            lambda dod: self.state_at_power(BatteryState.from_dod(dod), power_w).terminal_voltage_v - voltage_v
        )

    def integrate_power_profile(
        self,
        state: BatteryState,
        power_w: Sequence[float],
        durations_s: Sequence[float],
        *,
        max_step_s: float = 1.0,
    ) -> BatteryIntegrationResult:
        """Integrate consecutive constant-power segments into one time history."""
        if len(power_w) != len(durations_s):
            raise ValueError("power_w and durations_s must have the same length")
        if len(power_w) == 0:
            point = self.state_at_power(state=state, power_w=0.0)
            return self._integration_result(
                final_state=state,
                histories=self._initial_integration_histories(state, point),
                delivered_energy_wh=0.0,
                consumed_charge_ah=0.0,
                is_feasible=True,
                stop_reason="duration_complete",
            )
        if not math.isfinite(max_step_s) or max_step_s <= 0.0:
            raise ValueError("max_step_s must be finite and positive")

        histories: dict[str, list[float]] | None = None
        current_state = state
        elapsed_s = 0.0
        delivered_energy_wh = 0.0
        consumed_charge_ah = 0.0

        for power, duration_s in zip(power_w, durations_s):
            result = self.integrate_power(
                state=current_state,
                power_w=power,
                dt_s=duration_s,
                max_step_s=max_step_s,
            )
            if histories is None:
                histories = {name: list(values) for name, values in self._histories_from_result(result).items()}
            else:
                self._extend_profile_histories(histories, result, elapsed_s)

            elapsed_s = histories["time_s"][-1]
            delivered_energy_wh += result.delivered_energy_wh
            consumed_charge_ah += result.consumed_charge_ah
            current_state = result.final_state
            if not result.is_feasible:
                return self._integration_result(
                    final_state=current_state,
                    histories=histories,
                    delivered_energy_wh=delivered_energy_wh,
                    consumed_charge_ah=consumed_charge_ah,
                    is_feasible=False,
                    stop_reason=result.stop_reason,
                )

        if histories is None:
            raise RuntimeError("integration profile did not produce histories")
        return self._integration_result(
            final_state=current_state,
            histories=histories,
            delivered_energy_wh=delivered_energy_wh,
            consumed_charge_ah=consumed_charge_ah,
            is_feasible=True,
            stop_reason="duration_complete",
        )

    def energy_knockdown_dod(
        self,
        dod_initial: float,
        dod_final: float,
        *,
        samples: int = 1001,
    ) -> float:
        """Return reversible energy fraction available over a DOD interval."""
        self._validate_dod_interval(dod_initial, dod_final)
        if samples < 2:
            raise ValueError("samples must be at least 2")

        total_energy_wh = self._reversible_energy_wh(0.0, 1.0, samples=samples)
        interval_energy_wh = self._reversible_energy_wh(dod_initial, dod_final, samples=samples)
        return interval_energy_wh / total_energy_wh

    def energy_knockdown_c_rate(
        self,
        c_rate: float,
        *,
        max_step_s: float = 1.0,
    ) -> float:
        """Return usable-energy fraction at C-rate relative to reversible energy."""
        if not math.isfinite(c_rate) or c_rate < 0.0:
            raise ValueError("c_rate must be finite and non-negative")
        if not math.isfinite(max_step_s) or max_step_s <= 0.0:
            raise ValueError("max_step_s must be finite and positive")
        if c_rate == 0.0:
            return 1.0

        energy_wh = self._usable_energy_at_c_rate(c_rate, max_step_s=max_step_s)
        reversible_energy_wh = self._reversible_energy_wh(0.0, 1.0, samples=1001)
        return energy_wh / reversible_energy_wh

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
        clipped = min(1.0, max(0.0, float(dod)))
        if math.isclose(clipped, 0.0, rel_tol=0.0, abs_tol=1e-12):
            return 0.0
        if math.isclose(clipped, 1.0, rel_tol=0.0, abs_tol=1e-12):
            return 1.0
        return clipped

    def _reversible_energy_wh(self, dod_initial: float, dod_final: float, *, samples: int) -> float:
        dod_values = np.linspace(dod_initial, dod_final, samples)
        ocv_values = np.array([self.ocv(float(dod)) for dod in dod_values])
        cell_energy_wh = float(np.trapezoid(ocv_values, dod_values)) * self.capacity_ah
        return cell_energy_wh * self.series * self.parallel

    def _usable_energy_at_c_rate(self, c_rate: float, *, max_step_s: float) -> float:
        current_a = c_rate * self.rated_current_a * self.parallel
        duration_s = self.capacity_as / (self.rated_current_a * c_rate) if c_rate > 0.0 else 0.0
        result = self.integrate_current(
            state=BatteryState(soc=1.0),
            current_a=current_a,
            dt_s=duration_s,
            max_step_s=max_step_s,
        )
        return result.delivered_energy_wh

    def _integrate_with_point_function(
        self,
        state: BatteryState,
        dt_s: float,
        max_step_s: float,
        point_function: Callable[[BatteryState], BatteryPoint],
    ) -> BatteryIntegrationResult:
        initial_point = point_function(state)
        histories = self._initial_integration_histories(state, initial_point)

        if not initial_point.is_feasible:
            return self._integration_result(
                final_state=state,
                histories=histories,
                delivered_energy_wh=0.0,
                consumed_charge_ah=0.0,
                is_feasible=False,
                stop_reason=initial_point.infeasible_reason or "infeasible_state",
            )
        if dt_s == 0.0:
            return self._integration_result(
                final_state=state,
                histories=histories,
                delivered_energy_wh=0.0,
                consumed_charge_ah=0.0,
                is_feasible=True,
                stop_reason="duration_complete",
            )
        if initial_point.current_a == 0.0:
            self._append_integration_sample(histories, dt_s, state, initial_point)
            return self._integration_result(
                final_state=state,
                histories=histories,
                delivered_energy_wh=0.0,
                consumed_charge_ah=0.0,
                is_feasible=True,
                stop_reason="duration_complete",
            )

        def rhs(_time_s: float, values: np.ndarray) -> list[float]:
            state_at_t = BatteryState.from_dod(self._clip_dod(float(values[0])))
            point = point_function(state_at_t)
            return [
                point.cell_current_a / self.capacity_as,
                point.power_w / 3600.0,
                point.current_a / 3600.0,
            ]

        events = self._time_integration_events(point_function)
        solution = solve_ivp(
            rhs,
            (0.0, dt_s),
            [state.dod, 0.0, 0.0],
            events=events,
            max_step=max_step_s,
            rtol=1e-9,
            atol=1e-11,
        )
        if not solution.success:
            raise RuntimeError(solution.message)

        histories = {
            "time_s": [],
            "dod": [],
            "voltage_v": [],
            "current_a": [],
            "c_rate": [],
            "power_w": [],
            "efficiency": [],
        }
        for time_s, dod in zip(solution.t, solution.y[0]):
            sample_state = BatteryState.from_dod(self._clip_dod(float(dod)))
            sample_point = point_function(sample_state)
            self._append_integration_sample(histories, float(time_s), sample_state, sample_point)

        final_state = BatteryState.from_dod(self._clip_dod(float(solution.y[0, -1])))
        final_point = point_function(final_state)
        stop_reason = "duration_complete"
        is_feasible = True
        if solution.t[-1] < dt_s - 1e-9:
            stop_reason = self._stop_reason(final_state, final_point)
            is_feasible = False

        return self._integration_result(
            final_state=final_state,
            histories=histories,
            delivered_energy_wh=float(solution.y[1, -1]),
            consumed_charge_ah=float(solution.y[2, -1]),
            is_feasible=is_feasible,
            stop_reason=stop_reason,
        )

    def _integrate_to_dod(
        self,
        state: BatteryState,
        dod_final: float,
        max_step_s: float,
        point_function: Callable[[BatteryState], BatteryPoint],
    ) -> BatteryIntegrationResult:
        if not math.isfinite(dod_final) or dod_final < 0.0 or dod_final > 1.0:
            raise ValueError("dod_final must be finite and between 0 and 1")
        if dod_final <= state.dod:
            raise ValueError("dod_final must be greater than the initial DOD")

        initial_point = point_function(state)
        histories = self._initial_integration_histories(state, initial_point)

        if not initial_point.is_feasible:
            return self._integration_result(
                final_state=state,
                histories=histories,
                delivered_energy_wh=0.0,
                consumed_charge_ah=0.0,
                is_feasible=False,
                stop_reason=initial_point.infeasible_reason or "infeasible_state",
            )
        if initial_point.current_a <= 0.0:
            return self._integration_result(
                final_state=state,
                histories=histories,
                delivered_energy_wh=0.0,
                consumed_charge_ah=0.0,
                is_feasible=False,
                stop_reason="zero_discharge_current",
            )

        max_dod_step = max_step_s * initial_point.cell_current_a / self.capacity_as

        def rhs(dod: float, _values: np.ndarray) -> list[float]:
            state_at_dod = BatteryState.from_dod(self._clip_dod(dod))
            point = point_function(state_at_dod)
            if point.cell_current_a <= 0.0:
                return [0.0, 0.0, 0.0]
            return [
                self.capacity_as / point.cell_current_a,
                point.terminal_voltage_v * self.capacity_ah * self.parallel,
                self.capacity_ah * self.parallel,
            ]

        events = self._dod_integration_events(point_function)
        solution = solve_ivp(
            rhs,
            (state.dod, dod_final),
            [0.0, 0.0, 0.0],
            events=events,
            max_step=min(max_dod_step, dod_final - state.dod),
            rtol=1e-9,
            atol=1e-11,
        )
        if not solution.success:
            raise RuntimeError(solution.message)

        histories = {
            "time_s": [],
            "dod": [],
            "voltage_v": [],
            "current_a": [],
            "c_rate": [],
            "power_w": [],
            "efficiency": [],
        }
        for dod, time_s in zip(solution.t, solution.y[0]):
            sample_state = BatteryState.from_dod(self._clip_dod(float(dod)))
            sample_point = point_function(sample_state)
            self._append_integration_sample(histories, float(time_s), sample_state, sample_point)

        final_state = BatteryState.from_dod(self._clip_dod(float(solution.t[-1])))
        final_point = point_function(final_state)
        stop_reason = "dod_target"
        is_feasible = True
        if solution.t[-1] < dod_final - 1e-10:
            stop_reason = self._stop_reason(final_state, final_point)
            is_feasible = False

        return self._integration_result(
            final_state=final_state,
            histories=histories,
            delivered_energy_wh=float(solution.y[1, -1]),
            consumed_charge_ah=float(solution.y[2, -1]),
            is_feasible=is_feasible,
            stop_reason=stop_reason,
        )

    def _solve_dod(self, residual: Callable[[float], float]) -> float:
        low = 0.0
        high = 1.0
        low_value = residual(low)
        high_value = residual(high)
        if not math.isfinite(low_value) or not math.isfinite(high_value):
            raise ValueError("DOD solve residual must be finite at interval bounds")
        if low_value == 0.0:
            return low
        if high_value == 0.0:
            return high
        if low_value * high_value > 0.0:
            raise ValueError("voltage and power do not bracket a DOD solution")

        for _ in range(80):
            mid = 0.5 * (low + high)
            mid_value = residual(mid)
            if mid_value == 0.0:
                return mid
            if low_value * mid_value <= 0.0:
                high = mid
            else:
                low = mid
                low_value = mid_value

        return 0.5 * (low + high)

    def _time_integration_events(
        self,
        point_function: Callable[[BatteryState], BatteryPoint],
    ) -> list[Callable[[float, np.ndarray], float]]:
        def event(_time_s: float, values: np.ndarray) -> float:
            dod = float(values[0])
            state = BatteryState.from_dod(self._clip_dod(dod))
            point = point_function(state)
            return self._feasibility_margin(dod, point)

        event.terminal = True  # type: ignore[attr-defined]
        event.direction = -1  # type: ignore[attr-defined]
        return [event]

    def _dod_integration_events(
        self,
        point_function: Callable[[BatteryState], BatteryPoint],
    ) -> list[Callable[[float, np.ndarray], float]]:
        def event(dod: float, _values: np.ndarray) -> float:
            state = BatteryState.from_dod(self._clip_dod(dod))
            point = point_function(state)
            return self._feasibility_margin(dod, point)

        event.terminal = True  # type: ignore[attr-defined]
        event.direction = -1  # type: ignore[attr-defined]
        return [event]

    def _feasibility_margin(self, dod: float, point: BatteryPoint) -> float:
        return min(
            self.max_current_a - point.cell_current_a,
            point.cell_voltage_v - self.cutoff_voltage_v,
            self.charge_voltage_v - point.cell_voltage_v,
            1.0 - dod,
        )

    def _stop_reason(self, state: BatteryState, point: BatteryPoint) -> str:
        if not point.is_feasible:
            return point.infeasible_reason or "infeasible_state"

        margins = {
            "current_limit": self.max_current_a - point.cell_current_a,
            "voltage_cutoff": point.cell_voltage_v - self.cutoff_voltage_v,
            "voltage_limit": self.charge_voltage_v - point.cell_voltage_v,
            "dod_limit": 1.0 - state.dod,
        }
        return min(margins, key=lambda name: margins[name])

    @staticmethod
    def _validate_integration_inputs(load: float, dt_s: float, max_step_s: float, load_name: str) -> None:
        if not math.isfinite(load) or load < 0.0:
            raise ValueError(f"{load_name} must be finite and non-negative")
        if not math.isfinite(dt_s) or dt_s < 0.0:
            raise ValueError("dt_s must be finite and non-negative")
        if not math.isfinite(max_step_s) or max_step_s <= 0.0:
            raise ValueError("max_step_s must be finite and positive")

    @staticmethod
    def _validate_dod_interval(dod_initial: float, dod_final: float) -> None:
        if not math.isfinite(dod_initial) or not math.isfinite(dod_final):
            raise ValueError("dod values must be finite")
        if dod_initial < 0.0 or dod_initial > 1.0 or dod_final < 0.0 or dod_final > 1.0:
            raise ValueError("dod values must be between 0 and 1")
        if dod_final <= dod_initial:
            raise ValueError("dod_final must be greater than dod_initial")

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

    @staticmethod
    def _histories_from_result(result: BatteryIntegrationResult) -> dict[str, Sequence[float]]:
        return {
            "time_s": result.time_s,
            "dod": result.dod,
            "voltage_v": result.voltage_v,
            "current_a": result.current_a,
            "c_rate": result.c_rate,
            "power_w": result.power_w,
            "efficiency": result.efficiency,
        }

    @staticmethod
    def _extend_profile_histories(
        histories: dict[str, list[float]],
        result: BatteryIntegrationResult,
        time_offset_s: float,
    ) -> None:
        histories["time_s"].extend(time_offset_s + value for value in result.time_s[1:])
        histories["dod"].extend(result.dod[1:])
        histories["voltage_v"].extend(result.voltage_v[1:])
        histories["current_a"].extend(result.current_a[1:])
        histories["c_rate"].extend(result.c_rate[1:])
        histories["power_w"].extend(result.power_w[1:])
        histories["efficiency"].extend(result.efficiency[1:])
