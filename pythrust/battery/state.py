"""Battery state and point-result data structures."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Sequence


@dataclass(frozen=True)
class BatteryState:
    """Battery state for mission or point-performance analysis."""

    soc: float = 1.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.soc) or self.soc < 0.0 or self.soc > 1.0:
            raise ValueError("soc must be between 0 and 1")

    @classmethod
    def from_dod(cls, dod: float) -> "BatteryState":
        """Build a battery state from depth of discharge."""
        if not math.isfinite(dod) or dod < 0.0 or dod > 1.0:
            raise ValueError("dod must be between 0 and 1")
        return cls(soc=1.0 - dod)

    @property
    def dod(self) -> float:
        """Depth of discharge, from 0 full to 1 empty."""
        return 1.0 - self.soc


@dataclass(frozen=True)
class BatteryPoint:
    """Battery point-state result."""

    terminal_voltage_v: float
    current_a: float
    power_w: float
    cell_voltage_v: float
    cell_current_a: float
    c_rate: float
    efficiency: float
    ocv_v: float
    resistance_ohm: float
    is_feasible: bool
    infeasible_reason: Optional[str] = None


@dataclass(frozen=True)
class BatteryIntegrationResult:
    """Battery integration time-history and summary result."""

    final_state: BatteryState
    time_s: Sequence[float]
    dod: Sequence[float]
    voltage_v: Sequence[float]
    current_a: Sequence[float]
    c_rate: Sequence[float]
    power_w: Sequence[float]
    efficiency: Sequence[float]
    delivered_energy_wh: float
    consumed_charge_ah: float
    is_feasible: bool
    stop_reason: str

    def __post_init__(self) -> None:
        histories = {
            "time_s": _as_float_tuple(self.time_s),
            "dod": _as_float_tuple(self.dod),
            "voltage_v": _as_float_tuple(self.voltage_v),
            "current_a": _as_float_tuple(self.current_a),
            "c_rate": _as_float_tuple(self.c_rate),
            "power_w": _as_float_tuple(self.power_w),
            "efficiency": _as_float_tuple(self.efficiency),
        }
        lengths = {len(values) for values in histories.values()}
        if len(lengths) != 1:
            raise ValueError("integration histories must have the same length")
        if not histories["time_s"]:
            raise ValueError("integration histories must contain at least one sample")
        if not math.isfinite(self.delivered_energy_wh):
            raise ValueError("delivered_energy_wh must be finite")
        if not math.isfinite(self.consumed_charge_ah):
            raise ValueError("consumed_charge_ah must be finite")
        if not self.stop_reason:
            raise ValueError("stop_reason must not be empty")

        for name, values in histories.items():
            object.__setattr__(self, name, values)


def _as_float_tuple(values: Sequence[float]) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in result):
        raise ValueError("integration histories must contain finite values")
    return result
