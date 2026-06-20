"""Battery model data structures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatterySpec:
    """Battery pack parameters.

    Units:
    - voltage_v: V
    - discharge_efficiency: 0-1
    """

    voltage_v: float
    discharge_efficiency: float = 1.0
