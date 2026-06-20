"""Propeller model data structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PropellerSpec:
    """Propeller geometry.

    Units:
    - diameter_m: m
    - pitch_m: m (optional)
    """

    diameter_m: float
    blade_count: int = 2
    pitch_m: Optional[float] = None
