"""Battery state and point-result data structures."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional


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
