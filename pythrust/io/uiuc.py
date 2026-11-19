"""Readers for the UIUC Propeller Database.

The database, https://m-selig.ae.illinois.edu/props/propDB.html, gives blade
geometry and wind-tunnel measurements of small propellers.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

import numpy as np

from pythrust.propeller.blade import BladeGeometry, BladeSection
from pythrust.propeller.table import PropellerDataPoint, TablePropeller

_RPM_IN_NAME = re.compile(r"_(\d+(?:\.\d+)?)$")


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


def read_uiuc_performance(
    diameter_m: float,
    static: Optional[Union[str, Path]] = None,
    forward: Sequence[Union[str, Path]] = (),
) -> TablePropeller:
    """Build a ``TablePropeller`` from UIUC wind-tunnel measurements.

    ``static`` is a static test file (``*_static_*.txt``: ``RPM CT CP``), and
    ``forward`` are forward-flight files (``J CT CP eta``), each measured at the
    RPM that ends its name, such as ``apce_10x5_kt0823_6005.txt``. Each forward
    file becomes an RPM band; the static file adds its thrust and power
    coefficients, interpolated at that RPM, as the band's point at zero advance
    ratio. Without forward files, each static RPM is a band with that one point.

    Raises ``ValueError`` naming the line of a malformed file, or a forward file
    whose name does not end in its RPM.
    """
    if not (math.isfinite(diameter_m) and diameter_m > 0.0):
        raise ValueError(f"diameter_m must be positive, got {diameter_m}")
    static_rows = _uiuc_rows(Path(static), 3) if static is not None else []
    static_rows.sort()

    data_by_rpm: Dict[float, List[PropellerDataPoint]] = {}
    if not forward:
        for rpm, ct, cp in static_rows:
            data_by_rpm[rpm] = [PropellerDataPoint(j=0.0, ct=ct, cp=cp)]
    for path in map(Path, forward):
        match = _RPM_IN_NAME.search(path.stem)
        if match is None:
            raise ValueError(f"{path.name}: the file name does not end in the test RPM")
        rpm = float(match.group(1))
        points = []
        if static_rows:
            rpms, cts, cps = np.array(static_rows).T
            points.append(PropellerDataPoint(j=0.0, ct=float(np.interp(rpm, rpms, cts)), cp=float(np.interp(rpm, rpms, cps))))
        for j, ct, cp, _ in sorted(_uiuc_rows(path, 4)):
            if not points or j > points[-1].j:  # J increasing, one point each
                points.append(PropellerDataPoint(j=j, ct=ct, cp=cp))
        data_by_rpm[rpm] = points
    if not data_by_rpm:
        raise ValueError("no measurements: give a static file, forward files, or both")
    return TablePropeller(diameter_m, data_by_rpm)


def _uiuc_rows(path: Path, columns: int) -> List[List[float]]:
    """Numeric rows of a UIUC data file, after its header line."""
    rows = []
    for number, raw in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
        tokens = raw.split()
        if not tokens or (not rows and not _is_number(tokens[0])):
            continue
        if len(tokens) != columns or not all(_is_number(t) for t in tokens):
            raise ValueError(f"{path.name}:{number}: expected {columns} numbers")
        rows.append([float(t) for t in tokens])
    return rows
