"""Electrical system model data structures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemSpec:
    """System transmission/line electrical parameters.

    Units:
    - resistance_ohm: ohm
    """

    resistance_ohm: float = 0.0
