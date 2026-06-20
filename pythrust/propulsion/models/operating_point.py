"""Solved propulsion operating point data structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OperatingPoint:
    """Solved operating point for a given condition."""

    rpm: float
    advance_ratio: float
    ct: float
    cp: float
    thrust_n: float
    torque_nm: float
    shaft_power_w: float
    motor_power_w: float
    battery_power_w: float
    motor_current_a: float
    motor_voltage_v: float
    is_feasible: bool
    infeasible_reason: Optional[str] = None
    propeller_efficiency: float = 0.0
    motor_efficiency: float = 0.0
    system_efficiency: float = 0.0
