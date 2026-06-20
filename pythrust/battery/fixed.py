"""Fixed-voltage battery model."""

from __future__ import annotations

from dataclasses import dataclass

from .state import BatteryState


@dataclass(frozen=True)
class FixedVoltageBattery:
    """Battery model with constant pack voltage.

    This is the historical PyThrust battery model under a more explicit name.
    """

    voltage_v: float
    discharge_efficiency: float = 1.0

    def terminal_voltage(
        self,
        current_a: float = 0.0,
        state: BatteryState | None = None,
    ) -> float:
        """Return pack voltage for the requested current and state."""
        return self.voltage_v

    def terminal_power(
        self,
        current_a: float,
        state: BatteryState | None = None,
    ) -> float:
        """Return battery-side power draw using the fixed-voltage efficiency."""
        return self.voltage_v * current_a / max(1e-12, self.discharge_efficiency)
