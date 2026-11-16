"""Electrical system model data structures."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional


@dataclass(frozen=True)
class SystemSpec:
    """Speed controller and wiring between the battery and one motor.

    Units:
    - resistance_ohm: ohm, in series with the motor
    - max_current_a: A, continuous motor-side current limit of the speed
      controller; ``None`` for no controller limit
    """

    resistance_ohm: float = 0.0
    max_current_a: Optional[float] = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.resistance_ohm) or self.resistance_ohm < 0.0:
            raise ValueError("resistance_ohm must be finite and non-negative")
        if self.max_current_a is not None and not (
            math.isfinite(self.max_current_a) and self.max_current_a > 0.0
        ):
            raise ValueError("max_current_a must be finite and positive")
