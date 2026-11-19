"""Blade geometry and airfoil section data for blade-element propeller models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Tuple, Union

if TYPE_CHECKING:
    from .polar import AirfoilPolar, BlendedPolar


@dataclass(frozen=True)
class BladeSection:
    """Airfoil section parameters of QPROP's lift and drag model.

    Lift is linear in the angle of attack and clipped to ``[cl_min, cl_max]``:
    ``CL = cl0 + cl_alpha_per_rad * alpha``. Drag is quadratic in lift and
    scales with the Reynolds number:
    ``CD = (cd0 + cd2 * (CL - cl_at_cd0)**2) * (Re / reynolds_ref)**reynolds_exp``,
    with ``cd2 = cd2_upper`` above ``cl_at_cd0`` and ``cd2_lower`` below it.
    """

    cl0: float
    cl_alpha_per_rad: float
    cl_min: float
    cl_max: float
    cd0: float
    cd2_upper: float
    cd2_lower: float
    cl_at_cd0: float
    reynolds_ref: float
    reynolds_exp: float


@dataclass(frozen=True)
class BladeGeometry:
    """Propeller blade described at radial stations from root to tip.

    Units:
    - radius_m: tip radius, m
    - r_m: station radius, m
    - chord_m: chord, m
    - blade_angle_rad: blade angle from the plane of rotation, rad

    ``sections`` gives the airfoil at each station: QPROP's ``BladeSection``
    parameters, or tabulated polars (``AirfoilPolar``, ``BlendedPolar``); a
    blade uses one kind throughout.
    """

    blade_count: int
    radius_m: float
    r_m: Tuple[float, ...]
    chord_m: Tuple[float, ...]
    blade_angle_rad: Tuple[float, ...]
    sections: Tuple[Union[BladeSection, "AirfoilPolar", "BlendedPolar"], ...]

    def __post_init__(self) -> None:
        count = len(self.r_m)
        if count < 2:
            raise ValueError("a blade needs at least two stations")
        if not (len(self.chord_m) == len(self.blade_angle_rad) == len(self.sections) == count):
            raise ValueError("r_m, chord_m, blade_angle_rad and sections must have the same length")
        if any(inner >= outer for inner, outer in zip(self.r_m, self.r_m[1:])):
            raise ValueError("station radii must increase from root to tip")
        if self.radius_m < self.r_m[-1]:
            raise ValueError("the tip radius must not be less than the last station radius")
