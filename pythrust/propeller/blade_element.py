"""Blade-element propeller model after QPROP."""

from __future__ import annotations

import math
from dataclasses import fields
from typing import Tuple

import numpy as np

from .bem import solve_stations
from .blade import BladeGeometry, BladeSection

QPROP_MU = 1.78e-5
"""QPROP's default air viscosity, kg/(m s)."""
QPROP_SPEED_OF_SOUND = 340.0
"""QPROP's default speed of sound, m/s."""


class BladeElementPropeller:
    """Propeller model from blade geometry, solved with QPROP's formulation.

    The blade is analysed at ``stations`` points: the midpoints of equal
    intervals from the first to the last station of ``geometry``. Chord, blade
    angle and section parameters there come from a cubic spline through the
    geometry's stations, with zero third derivative in the end intervals.
    Thrust and torque sum each station's load over its interval (Drela, QPROP
    Formulation, section 3.2).

    ``mu`` and ``speed_of_sound`` are the air's viscosity and speed of sound;
    the defaults are QPROP's.
    """

    def __init__(
        self,
        geometry: BladeGeometry,
        mu: float = QPROP_MU,
        speed_of_sound: float = QPROP_SPEED_OF_SOUND,
        stations: int = 25,
    ) -> None:
        if stations < 1:
            raise ValueError("stations must be at least 1")
        self.geometry = geometry
        self.mu = float(mu)
        self.speed_of_sound = float(speed_of_sound)

        r = np.asarray(geometry.r_m, dtype=float)
        edges = np.linspace(r[0], r[-1], stations + 1)
        self._r = 0.5 * (edges[:-1] + edges[1:])
        self._dr = np.diff(edges)
        self._chord = _spline(r, np.asarray(geometry.chord_m, dtype=float), self._r)
        self._beta = _spline(r, np.asarray(geometry.blade_angle_rad, dtype=float), self._r)
        self._sections = _spline_sections(r, geometry.sections, self._r)

    @property
    def diameter_m(self) -> float:
        return 2.0 * self.geometry.radius_m

    @property
    def max_advance_ratio(self) -> float:
        """Advance ratio at which the section at 75% radius has zero lift.

        Thrust is near zero there and the induced velocity small, so this
        estimates the advance ratio of zero thrust without solving the blade.
        """
        radius = self.geometry.radius_m
        r = np.asarray(self.geometry.r_m, dtype=float)
        r75 = min(max(0.75 * radius, r[0]), r[-1])
        beta = float(_spline(r, np.asarray(self.geometry.blade_angle_rad, dtype=float), np.array([r75]))[0])
        section = self._sections[int(np.argmin(np.abs(self._r - r75)))]
        phi = beta + section.cl0 / section.cl_alpha_per_rad
        if phi <= 0.0:
            return 0.0
        if phi >= 0.5 * math.pi:
            return math.inf
        return math.pi * (r75 / radius) * math.tan(phi)

    def thrust_torque(self, rho: float, airspeed_mps: float, rpm: float) -> Tuple[float, float]:
        """Thrust in N and torque in N m; zero at zero RPM, NaN where a station has no solution."""
        omega = float(rpm) * math.pi / 30.0
        if omega <= 0.0:
            return 0.0, 0.0
        s = solve_stations(
            self.geometry.blade_count,
            self.geometry.radius_m,
            self._r,
            self._chord,
            self._beta,
            self._sections,
            airspeed_mps,
            omega,
            rho,
            self.mu,
            self.speed_of_sound,
        )
        if not s.converged.all():
            return math.nan, math.nan
        w = np.hypot(s.axial_velocity, s.tangential_velocity)
        # Gamma * eps = Gamma * cd / cl = W c cd / 2, finite where cl is zero.
        profile = 0.5 * w * self._chord * s.cd
        load = rho * self.geometry.blade_count * self._dr
        thrust = float(np.sum(load * (s.circulation * s.tangential_velocity - profile * s.axial_velocity)))
        torque = float(np.sum(load * (s.circulation * s.axial_velocity + profile * s.tangential_velocity) * self._r))
        return thrust, torque


def _spline(x: np.ndarray, y: np.ndarray, at: np.ndarray) -> np.ndarray:
    """Cubic spline through (x, y) with zero third derivative in the end intervals.

    Two points give the straight line through them.
    """
    n = x.size
    if n == 2 or np.all(y == y[0]):
        return np.interp(at, x, y)
    h = np.diff(x)
    # Unknowns are the second derivatives m at the points.
    matrix = np.zeros((n, n))
    rhs = np.zeros(n)
    for i in range(1, n - 1):
        matrix[i, i - 1] = h[i - 1]
        matrix[i, i] = 2.0 * (h[i - 1] + h[i])
        matrix[i, i + 1] = h[i]
        rhs[i] = 6.0 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])
    matrix[0, 0], matrix[0, 1] = 1.0, -1.0
    matrix[-1, -1], matrix[-1, -2] = 1.0, -1.0
    m = np.linalg.solve(matrix, rhs)
    i = np.clip(np.searchsorted(x, at) - 1, 0, n - 2)
    left, right = x[i + 1] - at, at - x[i]
    return (
        (m[i] * left**3 + m[i + 1] * right**3) / (6.0 * h[i])
        + (y[i] / h[i] - m[i] * h[i] / 6.0) * left
        + (y[i + 1] / h[i] - m[i + 1] * h[i] / 6.0) * right
    )


def _spline_sections(x: np.ndarray, sections, at: np.ndarray) -> list:
    """Section parameters at ``at``, each splined like the chord."""
    columns = {
        f.name: _spline(x, np.array([getattr(s, f.name) for s in sections], dtype=float), at)
        for f in fields(BladeSection)
    }
    return [BladeSection(**{name: float(values[k]) for name, values in columns.items()}) for k in range(at.size)]
