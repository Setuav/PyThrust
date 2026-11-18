"""Propeller models: thrust and torque at an operating condition."""

from __future__ import annotations

import math
from typing import Optional, Protocol

from .database import PropellerEntry


class PropellerModel(Protocol):
    """What the propulsion solver needs from a propeller."""

    @property
    def diameter_m(self) -> float:
        """Propeller diameter in metres."""
        ...

    @property
    def max_advance_ratio(self) -> float:
        """Advance ratio up to which the model is expected to give thrust.

        The solver starts its RPM search at this advance ratio.
        """
        ...

    def thrust_torque(self, rho: float, airspeed_mps: float, rpm: float) -> tuple[float, float]:
        """Return thrust in N and shaft torque in N m.

        ``rho`` is the air density in kg/m^3. A model returns zero torque where
        it has no data; the solver treats that condition as having no solution.
        """
        ...


class TablePropeller:
    """Propeller model interpolating a table of thrust and power coefficients.

    ``diameter_m`` defaults to the diameter of the tabulated propeller. Another
    diameter scales the propeller with its coefficients unchanged: a
    geometrically similar propeller, without the Reynolds number effects of the
    size change.
    """

    def __init__(self, entry: PropellerEntry, diameter_m: Optional[float] = None) -> None:
        self.entry = entry
        self.diameter_m = entry.diameter_m if diameter_m is None else float(diameter_m)

    @property
    def max_advance_ratio(self) -> float:
        """Lower quartile of the largest advance ratio of each RPM band; 0.6 without data."""
        j_maxes = sorted(points[-1].j for points in self.entry.data_by_rpm.values() if points)
        if not j_maxes:
            return 0.6
        return j_maxes[len(j_maxes) // 4]

    def thrust_torque(self, rho: float, airspeed_mps: float, rpm: float) -> tuple[float, float]:
        n = max(rpm / 60.0, 1e-6)
        j = airspeed_mps / (n * self.diameter_m) if self.diameter_m > 0 else 0.0
        ct, cp = self.entry.get_coefficients(rpm, j)
        thrust_n = ct * rho * (n**2) * (self.diameter_m**4)
        torque_nm = cp * rho * (n**2) * (self.diameter_m**5) / (2.0 * math.pi)
        return thrust_n, torque_nm
