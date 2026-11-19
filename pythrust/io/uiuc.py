"""Readers for the UIUC Propeller Database.

The database, https://m-selig.ae.illinois.edu/props/propDB.html, gives blade
geometry and wind-tunnel measurements of small propellers.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Union

from pythrust.propeller.blade import BladeGeometry, BladeSection


def read_uiuc_geometry(
    path: Union[str, Path],
    diameter_m: float,
    section: BladeSection,
    blade_count: int = 2,
) -> BladeGeometry:
    """Read a UIUC geometry file (``*_geom.txt``) into a blade geometry in SI units.

    The file has a header line ``r/R c/R beta`` and one line per station from
    root to tip: the radius and the chord as fractions of the tip radius, and
    the blade angle in degrees. It gives neither the diameter, the blade count
    nor the airfoil, so they are arguments; ``section`` applies to every station.

    Raises ``ValueError`` naming the line of a malformed file.
    """
    path = Path(path)
    if not (math.isfinite(diameter_m) and diameter_m > 0.0):
        raise ValueError(f"diameter_m must be positive, got {diameter_m}")
    radius_m = 0.5 * diameter_m

    rows = []
    for number, raw in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
        tokens = raw.split()
        if not tokens:
            continue
        if not rows and not _is_number(tokens[0]):
            continue  # the header line
        if len(tokens) != 3:
            raise ValueError(f"{path.name}:{number}: expected 'r/R c/R beta', got {len(tokens)} values")
        values = []
        for token in tokens:
            if not _is_number(token):
                raise ValueError(f"{path.name}:{number}: {token!r} is not a number")
            values.append(float(token))
        rows.append(values)

    try:
        return BladeGeometry(
            blade_count=blade_count,
            radius_m=radius_m,
            r_m=tuple(r * radius_m for r, _, _ in rows),
            chord_m=tuple(c * radius_m for _, c, _ in rows),
            blade_angle_rad=tuple(math.radians(beta) for _, _, beta in rows),
            sections=(section,) * len(rows),
        )
    except ValueError as error:
        raise ValueError(f"{path.name}: {error}") from error


def _is_number(token: str) -> bool:
    try:
        return math.isfinite(float(token))
    except ValueError:
        return False
