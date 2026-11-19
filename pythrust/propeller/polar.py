"""Airfoil sections from tabulated lift and drag polars, computed with NeuralFoil."""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
from numpy.typing import ArrayLike

AirfoilShape = Union[str, PathLike, np.ndarray]
"""A NACA 4- or 5-digit designation, the path of a .dat file, or (N, 2) coordinates."""

NEURALFOIL_ALPHA_DEG = np.arange(-20.0, 25.0 + 1e-9, 0.5)
"""Angles of attack evaluated with NeuralFoil, deg; its confidence falls quickly outside them."""
FLAT_PLATE_ALPHA_DEG = np.concatenate([np.arange(-180.0, -35.0 + 1e-9, 5.0), np.arange(40.0, 180.0 + 1e-9, 5.0)])
"""Angles of attack given flat-plate values, deg; the table interpolates linearly in between."""
REYNOLDS = np.logspace(4.0, 6.0, 13)
"""Reynolds numbers of the table; outside them the nearest is used."""


@dataclass(frozen=True, eq=False)
class AirfoilPolar:
    """Lift and drag of an airfoil section, tabulated over angle of attack and Reynolds number.

    ``cl`` and ``cd`` have shape ``(len(alpha_rad), len(reynolds))``. Coefficients between the
    table's points are interpolated linearly in the angle of attack and in ``log(Re)``.
    ``alpha_rad`` is measured from the chord line, from the leading edge to the trailing edge.
    """

    name: str
    alpha_rad: np.ndarray
    reynolds: np.ndarray
    cl: np.ndarray
    cd: np.ndarray

    def __post_init__(self) -> None:
        shape = (len(self.alpha_rad), len(self.reynolds))
        if np.shape(self.cl) != shape or np.shape(self.cd) != shape:
            raise ValueError(f"cl and cd must have shape {shape}")
        if np.any(np.diff(self.alpha_rad) <= 0) or np.any(np.diff(self.reynolds) <= 0):
            raise ValueError("alpha_rad and reynolds must increase")
        # Lookup arrays: both coefficients interpolated together, Reynolds number on a log scale.
        object.__setattr__(self, "_table", np.stack([self.cl, self.cd], axis=-1))
        object.__setattr__(self, "_log_reynolds", np.log(self.reynolds))

    @classmethod
    def from_neuralfoil(
        cls,
        airfoil: AirfoilShape,
        n_crit: float = 7.0,
        name: Optional[str] = None,
        model_size: str = "xlarge",
    ) -> "AirfoilPolar":
        """Tabulate an airfoil's polars with NeuralFoil (``setuav-neuralfoil``).

        NeuralFoil gives the coefficients from -20 to 25 degrees, at Reynolds numbers from 1e4
        to 1e6. Beyond -35 and 40 degrees the section is taken as a flat plate,
        ``CL = sin(2 alpha)`` and ``CD = 2 sin(alpha)^2``; in between the table interpolates.

        ``n_crit`` is the transition amplification factor: 9 for a quiet wind tunnel, lower
        for a turbulent free stream. The default, 7, fits UIUC's measurements of 75 APC
        propellers best, with 5 nearly as well. ``model_size`` selects NeuralFoil's network.
        """
        import setuav_neuralfoil as nf

        alpha_deg, re = np.meshgrid(NEURALFOIL_ALPHA_DEG, REYNOLDS, indexing="ij")
        aero = nf.get_aero_from_coordinates(
            _coordinates(airfoil), alpha=alpha_deg.ravel(), Re=re.ravel(), n_crit=n_crit, model_size=model_size
        )
        shape = alpha_deg.shape

        plate = np.radians(FLAT_PLATE_ALPHA_DEG)
        alpha = np.concatenate([plate[plate < 0], np.radians(NEURALFOIL_ALPHA_DEG), plate[plate > 0]])
        n_low = int(np.sum(plate < 0))
        cl = np.empty((alpha.size, REYNOLDS.size))
        cd = np.empty_like(cl)
        cl[:] = np.sin(2.0 * alpha)[:, None]
        cd[:] = (2.0 * np.sin(alpha) ** 2)[:, None]
        rows = slice(n_low, n_low + NEURALFOIL_ALPHA_DEG.size)
        cl[rows] = np.reshape(aero["CL"], shape)
        cd[rows] = np.reshape(aero["CD"], shape)

        if name is None:
            name = str(airfoil) if isinstance(airfoil, (str, PathLike)) else "airfoil"
        return cls(name=name, alpha_rad=alpha, reynolds=REYNOLDS.copy(), cl=cl, cd=cd)

    @property
    def zero_lift_alpha_rad(self) -> float:
        """The lowest angle of zero lift over the table's Reynolds numbers, between -20 and 25 degrees.

        At each Reynolds number it takes the zero crossing of rising lift nearest zero angle, past
        any wiggle of the lift curve at negative angles.
        """
        inside = (self.alpha_rad >= np.radians(-20.0)) & (self.alpha_rad <= np.radians(25.0))
        alpha = self.alpha_rad[inside]
        angles = []
        for cl in self.cl[inside].T:
            rising = np.nonzero((cl[:-1] <= 0.0) & (cl[1:] > 0.0))[0]
            crossings = alpha[rising] - cl[rising] * (alpha[rising + 1] - alpha[rising]) / (cl[rising + 1] - cl[rising])
            if crossings.size:
                angles.append(crossings[np.argmin(np.abs(crossings))])
        if not angles:
            raise ValueError(f"{self.name}: lift does not cross zero between -20 and 25 degrees")
        return float(min(angles))

    def coefficients(self, alpha_rad: ArrayLike, reynolds: ArrayLike, mach: ArrayLike) -> Tuple[np.ndarray, np.ndarray]:
        """Lift and drag coefficients; the lift includes the Prandtl-Glauert factor ``1/sqrt(1 - M^2)``."""
        alpha = np.mod(np.asarray(alpha_rad, dtype=float) + np.pi, 2.0 * np.pi) - np.pi
        log_re = np.log(np.clip(np.asarray(reynolds, dtype=float), self.reynolds[0], self.reynolds[-1]))
        both = _bilinear(self.alpha_rad, self._log_reynolds, self._table, alpha, log_re)
        return both[..., 0] / np.sqrt(1.0 - np.asarray(mach, dtype=float) ** 2), both[..., 1]


@dataclass(frozen=True)
class BlendedPolar:
    """A section between two airfoils: their coefficients mixed, ``weight`` of ``second``."""

    first: AirfoilPolar
    second: AirfoilPolar
    weight: float

    @property
    def zero_lift_alpha_rad(self) -> float:
        return min(self.first.zero_lift_alpha_rad, self.second.zero_lift_alpha_rad)

    def coefficients(self, alpha_rad: ArrayLike, reynolds: ArrayLike, mach: ArrayLike) -> Tuple[np.ndarray, np.ndarray]:
        cl1, cd1 = self.first.coefficients(alpha_rad, reynolds, mach)
        cl2, cd2 = self.second.coefficients(alpha_rad, reynolds, mach)
        w = self.weight
        return (1.0 - w) * cl1 + w * cl2, (1.0 - w) * cd1 + w * cd2


PolarSection = Union[AirfoilPolar, BlendedPolar]


class StationPolars:
    """The sections of a blade's analysis stations, each a weighted mix of a few polars.

    ``weights[k, j]`` is the share of ``polars[j]`` at station ``k``; each row sums to one.
    """

    def __init__(self, polars: Sequence[AirfoilPolar], weights: np.ndarray) -> None:
        self.polars = list(polars)
        self.weights = np.asarray(weights, dtype=float)

    @classmethod
    def interpolate(cls, r: np.ndarray, sections: Sequence[PolarSection], at: np.ndarray) -> "StationPolars":
        """Sections at radii ``at``, mixed linearly between the sections given at radii ``r``."""
        polars: List[AirfoilPolar] = []
        for section in sections:
            for polar, _ in _components(section):
                if not any(polar is known for known in polars):
                    polars.append(polar)

        weights = np.zeros((len(at), len(polars)))
        i = np.clip(np.searchsorted(r, at) - 1, 0, len(r) - 2)
        t = np.clip((at - r[i]) / (r[i + 1] - r[i]), 0.0, 1.0)
        for k in range(len(at)):
            for section, share in ((sections[i[k]], 1.0 - t[k]), (sections[i[k] + 1], t[k])):
                for polar, part in _components(section):
                    j = next(j for j, known in enumerate(polars) if known is polar)
                    weights[k, j] += share * part
        return cls(polars, weights)

    def __getitem__(self, k: int) -> "StationPolars":
        return StationPolars(self.polars, self.weights[k : k + 1])

    @property
    def zero_lift_alpha_rad(self) -> float:
        """The lowest zero-lift angle among the polars a station uses; for a single station."""
        return min(p.zero_lift_alpha_rad for p, w in zip(self.polars, self.weights[0]) if w > 0.0)

    def coefficients(self, alpha_rad: ArrayLike, reynolds: ArrayLike, mach: ArrayLike) -> Tuple[np.ndarray, np.ndarray]:
        """Lift and drag coefficients; the first axis of the arrays runs over the stations."""
        alpha, reynolds, mach = np.broadcast_arrays(
            np.asarray(alpha_rad, dtype=float), np.asarray(reynolds, dtype=float), np.asarray(mach, dtype=float)
        )
        cl = np.zeros(alpha.shape)
        cd = np.zeros(alpha.shape)
        for j, polar in enumerate(self.polars):
            rows = self.weights[:, j] > 0.0
            if not rows.any():
                continue
            share = self.weights[rows, j].reshape((-1,) + (1,) * (alpha.ndim - 1))
            cl_j, cd_j = polar.coefficients(alpha[rows], reynolds[rows], mach[rows])
            cl[rows] += share * cl_j
            cd[rows] += share * cd_j
        return cl, cd


def _components(section: PolarSection):
    if isinstance(section, BlendedPolar):
        return ((section.first, 1.0 - section.weight), (section.second, section.weight))
    return ((section, 1.0),)


def _coordinates(airfoil: AirfoilShape) -> np.ndarray:
    from setuav_neuralfoil import geometry

    if isinstance(airfoil, np.ndarray):
        return airfoil
    if isinstance(airfoil, str):
        designation = airfoil.lower().replace("naca", "").replace(" ", "").replace("-", "")
        if designation.isdigit() and len(designation) in (4, 5):
            return geometry.naca(airfoil)
    return geometry.read_dat(airfoil)


def _bilinear(x: np.ndarray, y: np.ndarray, table: np.ndarray, at_x: np.ndarray, at_y: np.ndarray) -> np.ndarray:
    """Interpolate ``table[i, j, ...]`` given at ``(x[i], y[j])``; ``at_x`` within ``x``, ``at_y`` within ``y``.

    The result has the shape of ``at_x`` and ``at_y`` broadcast, followed by the table's trailing axes.
    """
    at_x, at_y = np.broadcast_arrays(at_x, at_y)
    i = np.minimum(np.maximum(np.searchsorted(x, at_x) - 1, 0), x.size - 2)
    j = np.minimum(np.maximum(np.searchsorted(y, at_y) - 1, 0), y.size - 2)
    extra = (...,) + (None,) * (table.ndim - 2)
    tx = ((at_x - x[i]) / (x[i + 1] - x[i]))[extra]
    ty = ((at_y - y[j]) / (y[j + 1] - y[j]))[extra]
    low = table[i, j] + tx * (table[i + 1, j] - table[i, j])
    high = table[i, j + 1] + tx * (table[i + 1, j + 1] - table[i, j + 1])
    return low + ty * (high - low)
