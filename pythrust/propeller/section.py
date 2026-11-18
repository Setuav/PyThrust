"""Airfoil section lift and drag of QPROP's blade-element model."""

from __future__ import annotations

from typing import Tuple

import numpy as np
from numpy.typing import ArrayLike

from .blade import BladeSection


def section_coefficients(
    section: BladeSection,
    alpha_rad: ArrayLike,
    reynolds: ArrayLike,
    mach: ArrayLike,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return the lift and drag coefficients of a section.

    Lift is linear in the angle of attack with the Prandtl-Glauert factor:
    ``CL = (cl0 + cl_alpha_per_rad * alpha) / sqrt(1 - M^2)``. Where that lift
    passes ``cl_max`` or ``cl_min``, the section is stalled and the lift is
    ``cl_max * cos(alpha - cl0 / cl_alpha_per_rad)`` (``cl_min`` below), which
    falls off past the stall.

    Drag is ``(cd0 + cd2 * (CL - cl_at_cd0)^2) * (Re / reynolds_ref)^reynolds_exp``,
    with ``cd2_upper`` where ``CL > cl_at_cd0`` and ``cd2_lower`` elsewhere. A
    stalled section adds ``2 * sin(alpha - alpha_cd0)^2``, where
    ``alpha_cd0 = (cl_at_cd0 - cl0) / cl_alpha_per_rad``; this term does not
    scale with the Reynolds number.

    This reproduces QPROP 1.22 for angles of attack within +-85 degrees and
    Mach numbers up to 0.56, where it was checked against QPROP's output. The
    stalled lift and the unscaled stall drag are not in the QPROP user guide;
    they were measured from QPROP's output. The Mach number must be below 1.
    """
    alpha = np.asarray(alpha_rad, dtype=float)
    reynolds = np.asarray(reynolds, dtype=float)
    mach = np.asarray(mach, dtype=float)

    cl_linear = (section.cl0 + section.cl_alpha_per_rad * alpha) / np.sqrt(1.0 - mach**2)
    stall_lift = np.cos(alpha - section.cl0 / section.cl_alpha_per_rad)
    above = cl_linear > section.cl_max
    below = cl_linear < section.cl_min
    cl = np.where(above, section.cl_max * stall_lift, np.where(below, section.cl_min * stall_lift, cl_linear))

    cd2 = np.where(cl > section.cl_at_cd0, section.cd2_upper, section.cd2_lower)
    cd = (section.cd0 + cd2 * (cl - section.cl_at_cd0) ** 2) * (reynolds / section.reynolds_ref) ** section.reynolds_exp
    alpha_cd0 = (section.cl_at_cd0 - section.cl0) / section.cl_alpha_per_rad
    cd = cd + np.where(above | below, 2.0 * np.sin(alpha - alpha_cd0) ** 2, 0.0)
    return cl, cd
