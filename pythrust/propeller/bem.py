"""Blade-element/vortex solution at blade stations, after QPROP's formulation.

The equations follow Mark Drela's "QPROP Formulation" (MIT, 2006), section
2.2, with no externally induced velocity: the flow at a station is
parametrized by an angle ``psi``, and the station is solved where the
circulation from the vortex relation equals the circulation from the
section's lift.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Sequence

import numpy as np
from numpy.typing import ArrayLike

from .blade import BladeSection
from .section import section_coefficients

_GRID_POINTS = 400
"""Samples of psi per station used to bracket the root."""
_BISECTIONS = 80
_EDGE = 1e-9
"""Fraction of the psi range kept clear of its ends, where Wa or Wt is zero."""


@dataclass(frozen=True)
class StationSolution:
    """Flow at each blade station. Every field is an array over the stations.

    Units: velocities m/s, angles rad, circulation m^2/s.
    ``converged`` is False where no root was bracketed; the other fields are
    NaN there.
    """

    psi: np.ndarray
    axial_velocity: np.ndarray
    tangential_velocity: np.ndarray
    axial_induced: np.ndarray
    tangential_induced: np.ndarray
    alpha: np.ndarray
    cl: np.ndarray
    cd: np.ndarray
    reynolds: np.ndarray
    mach: np.ndarray
    circulation: np.ndarray
    converged: np.ndarray


def solve_stations(
    blade_count: int,
    radius_m: float,
    r_m: ArrayLike,
    chord_m: ArrayLike,
    blade_angle_rad: ArrayLike,
    sections: Sequence[BladeSection],
    airspeed_mps: float,
    omega_rad_s: float,
    rho: float,
    mu: float,
    speed_of_sound: float,
) -> StationSolution:
    """Solve the flow at each station of a blade.

    With ``Ua = V`` and ``Ut = omega r``, the velocities seen by the blade are
    ``Wa = (Ua + U sin psi) / 2`` and ``Wt = (Ut + U cos psi) / 2``, where
    ``U = sqrt(Ua^2 + Ut^2)``. The vortex relation gives the circulation
    ``Gamma = vt (4 pi r / B) F sqrt(1 + (4 lw R / (pi B r))^2)`` from the
    tangential induced velocity ``vt = Ut - Wt``, the local wake advance ratio
    ``lw = (r / R) Wa / Wt`` and Prandtl's tip factor
    ``F = (2 / pi) arccos(exp(-(B / 2)(1 - r / R) / lw))``. The station is solved
    where ``Gamma = W c CL / 2``.

    Where several roots exist, the one nearest the uninduced flow is taken.
    """
    r = np.asarray(r_m, dtype=float)
    chord = np.asarray(chord_m, dtype=float)
    beta = np.asarray(blade_angle_rad, dtype=float)
    section = _stack(sections)
    blades = float(blade_count)

    ua = np.full_like(r, float(airspeed_mps))
    ut = float(omega_rad_s) * r
    u = np.hypot(ua, ut)
    psi_free = np.arctan2(ua, ut)
    # Wa > 0 and Wt > 0 between these limits.
    psi_low = -np.arcsin(np.clip(ua / u, -1.0, 1.0))
    psi_high = np.arccos(np.clip(-ut / u, -1.0, 1.0))
    span = psi_high - psi_low
    psi_low = psi_low + _EDGE * span
    psi_high = psi_high - _EDGE * span

    @np.errstate(divide="ignore", invalid="ignore", over="ignore")
    def flow(psi, rr, cc, bb, sec, uaa, utt, uu):
        wa = 0.5 * (uaa + uu * np.sin(psi))
        wt = 0.5 * (utt + uu * np.cos(psi))
        w = np.hypot(wa, wt)
        alpha = bb - np.arctan2(wa, wt)
        reynolds = rho * w * cc / mu
        mach = w / speed_of_sound
        cl, cd = section_coefficients(sec, alpha, reynolds, mach)
        wake_ratio = (rr / radius_m) * wa / wt
        tip = 0.5 * blades * (1.0 - rr / radius_m) / wake_ratio
        prandtl = (2.0 / np.pi) * np.arccos(np.exp(-tip))
        vt = utt - wt
        gamma = vt * (4.0 * np.pi * rr / blades) * prandtl * np.sqrt(
            1.0 + (4.0 * wake_ratio * radius_m / (np.pi * blades * rr)) ** 2
        )
        residual = gamma - 0.5 * w * cc * cl
        return residual, wa, wt, alpha, cl, cd, reynolds, mach, gamma

    column = lambda a: a[:, None]  # noqa: E731
    grid = psi_low[:, None] + span[:, None] * (1.0 - 2.0 * _EDGE) * np.linspace(0.0, 1.0, _GRID_POINTS)[None, :]
    residual = flow(
        grid, column(r), column(chord), column(beta), _columns(section), column(ua), column(ut), column(u)
    )[0]
    change = np.signbit(residual[:, :-1]) != np.signbit(residual[:, 1:])
    change &= np.isfinite(residual[:, :-1]) & np.isfinite(residual[:, 1:])
    midpoints = 0.5 * (grid[:, :-1] + grid[:, 1:])
    distance = np.where(change, np.abs(midpoints - psi_free[:, None]), np.inf)
    pick = np.argmin(distance, axis=1)
    rows = np.arange(r.size)
    converged = np.isfinite(distance[rows, pick])

    lower = grid[rows, pick]
    upper = grid[rows, pick + 1]
    f_lower = residual[rows, pick]
    for _ in range(_BISECTIONS):
        middle = 0.5 * (lower + upper)
        f_middle = flow(middle, r, chord, beta, section, ua, ut, u)[0]
        same = np.signbit(f_middle) == np.signbit(f_lower)
        lower = np.where(same, middle, lower)
        f_lower = np.where(same, f_middle, f_lower)
        upper = np.where(same, upper, middle)
    psi = np.where(converged, 0.5 * (lower + upper), np.nan)

    _, wa, wt, alpha, cl, cd, reynolds, mach, gamma = flow(psi, r, chord, beta, section, ua, ut, u)
    return StationSolution(
        psi=psi,
        axial_velocity=wa,
        tangential_velocity=wt,
        axial_induced=wa - ua,
        tangential_induced=ut - wt,
        alpha=alpha,
        cl=cl,
        cd=cd,
        reynolds=reynolds,
        mach=mach,
        circulation=gamma,
        converged=converged,
    )


def _stack(sections: Sequence[BladeSection]) -> BladeSection:
    """One BladeSection whose fields are arrays over the stations."""
    return BladeSection(
        **{f.name: np.array([getattr(s, f.name) for s in sections], dtype=float) for f in fields(BladeSection)}
    )


def _columns(section: BladeSection) -> BladeSection:
    """The stacked section with its arrays as columns, to broadcast over a grid."""
    return BladeSection(**{f.name: getattr(section, f.name)[:, None] for f in fields(BladeSection)})
