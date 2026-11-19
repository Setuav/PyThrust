"""Readers for APC propeller files: performance (``PER3_*.dat``) and geometry (``*-PERF.PE0``)."""

from __future__ import annotations

import math
import re
from pathlib import Path
from dataclasses import fields
from typing import Dict, List, Mapping, Union

from pythrust.propeller.blade import BladeGeometry, BladeSection
from pythrust.propeller.polar import AirfoilPolar, BlendedPolar
from pythrust.propeller.table import PropellerDataPoint, TablePropeller

_RPM_RE = re.compile(r"PROP RPM\s*=\s*(\d+(?:\.\d+)?)")
_MODEL_RE = re.compile(r"(?P<diam>\d+(?:\.\d+)?)x\d+(?:\.\d+)?")
_COLUMN_COUNT = 15
"""Columns of an APC data row: V, J, Pe, Ct, Cp, then power, torque, thrust and the rest."""
_J, _CT, _CP = 1, 3, 4
_INCH_TO_M = 0.0254

_GEOMETRY_COLUMN_COUNT = 14
"""Columns of a PE0 station row: station, chord, three pitches, sweep, rake,
thickness ratio, twist, max thickness, cross-section, zhigh, cgy, cgz."""
_STATION, _CHORD, _TWIST = 0, 1, 8
_GEOMETRY_VALUE_RE = re.compile(r"^\s*(RADIUS|HUBTRA|BLADES):\s*(\S+)", re.MULTILINE)
_AIRFOIL_RE = re.compile(r"^\s*AIRFOIL([12]):\s*([-+.\d]+)\s*,\s*(\S+)", re.MULTILINE)


def read_apc(path: Union[str, Path]) -> TablePropeller:
    """Read an APC ``PER3_*.dat`` performance file.

    The file gives thrust and power coefficients against advance ratio at a
    series of RPM values. Rows with a negative coefficient, where the propeller
    windmills, are left out, so each RPM band ends at the last advance ratio
    with positive thrust and power. The diameter is the one in the model line.

    Raises ``ValueError`` when the file has no model line or no data rows.
    """
    path = Path(path)
    lines = path.read_text(errors="ignore").splitlines()

    model_line = next((line.strip() for line in lines if line.strip()), "")
    model = model_line.split("(")[0].strip()
    match = _MODEL_RE.match(model)
    if not match:
        raise ValueError(f"{path.name}: no propeller size in model line {model_line!r}")

    data_by_rpm: Dict[float, List[PropellerDataPoint]] = {}
    rpm = None
    for line in lines:
        rpm_match = _RPM_RE.search(line)
        if rpm_match:
            rpm = float(rpm_match.group(1))
            continue
        parts = line.split()
        if rpm is None or len(parts) < _COLUMN_COUNT:
            continue
        try:
            j, ct, cp = float(parts[_J]), float(parts[_CT]), float(parts[_CP])
        except ValueError:
            continue
        if not all(math.isfinite(value) for value in (j, ct, cp)) or min(j, ct, cp) < 0.0:
            continue
        points = data_by_rpm.setdefault(rpm, [])
        if all(point.j != j for point in points):
            points.append(PropellerDataPoint(j=j, ct=ct, cp=cp))

    if not data_by_rpm:
        raise ValueError(f"{path.name}: no performance data rows")

    return TablePropeller(
        diameter_m=float(match.group("diam")) * _INCH_TO_M,
        data_by_rpm={rpm: sorted(points, key=lambda p: p.j) for rpm, points in data_by_rpm.items()},
    )


def read_apc_geometry(
    path: Union[str, Path],
    sections: Union[BladeSection, AirfoilPolar, Mapping[str, Union[BladeSection, AirfoilPolar]]],
) -> BladeGeometry:
    """Read an APC geometry file (``*-PERF.PE0``) into a blade geometry in SI units.

    The file gives the chord and blade angle (``TWIST``) at stations in
    inches, the tip radius, the hub transition radius and the blade count.
    Stations inside the hub transition are left out. The tip radius is the
    file's ``RADIUS``, or the last station's where that is larger: ``RADIUS``
    is rounded to two decimals. The blade angle is that of
    the chord line, between the leading- and trailing-edge mold parting lines;
    the file also gives the lower-surface (Prather gauge) pitch, which is
    lower.

    The file names two airfoils: the first up to the transition start radius,
    the second from the transition end radius. ``sections`` is one section for
    every station, or a mapping from those airfoil names to sections; a section
    is a ``BladeSection`` or an ``AirfoilPolar``, such as those of
    ``apc_airfoil_polars()``. Between the two radii, ``BladeSection`` parameters
    are interpolated linearly, and polars are mixed in a ``BlendedPolar``.

    Raises ``ValueError`` naming what is missing from a malformed file, and
    ``KeyError`` naming an airfoil that ``sections`` does not map.
    """
    path = Path(path)
    text = path.read_text(errors="ignore")

    values = {name: value for name, value in _GEOMETRY_VALUE_RE.findall(text)}
    missing = [name for name in ("RADIUS", "HUBTRA", "BLADES") if name not in values]
    if missing:
        raise ValueError(f"{path.name}: no {', '.join(missing)} line")
    try:
        radius_in = float(values["RADIUS"])
        hub_transition_in = float(values["HUBTRA"])
        blade_count = int(values["BLADES"])
    except ValueError as error:
        raise ValueError(f"{path.name}: {error}") from None

    if isinstance(sections, (BladeSection, AirfoilPolar)):
        first = second = sections
        start_in = end_in = 0.0
    else:
        airfoils = {int(index): (float(r_in), name) for index, r_in, name in _AIRFOIL_RE.findall(text)}
        if set(airfoils) != {1, 2}:
            raise ValueError(f"{path.name}: expected AIRFOIL1 and AIRFOIL2 lines")
        (start_in, first_name), (end_in, second_name) = airfoils[1], airfoils[2]
        for name in (first_name, second_name):
            if name not in sections:
                raise KeyError(f"{path.name}: no section for airfoil {name!r}")
        first, second = sections[first_name], sections[second_name]

    r_m, chord_m, blade_angle_rad, station_sections = [], [], [], []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != _GEOMETRY_COLUMN_COUNT:
            continue
        try:
            row = [float(part) for part in parts]
        except ValueError:
            continue
        r_in = row[_STATION]
        if r_in < hub_transition_in:
            continue
        r_m.append(r_in * _INCH_TO_M)
        chord_m.append(row[_CHORD] * _INCH_TO_M)
        blade_angle_rad.append(math.radians(row[_TWIST]))
        station_sections.append(_blend(first, second, _fraction(r_in, start_in, end_in)))

    try:
        return BladeGeometry(
            blade_count=blade_count,
            radius_m=max(radius_in * _INCH_TO_M, r_m[-1]) if r_m else radius_in * _INCH_TO_M,
            r_m=tuple(r_m),
            chord_m=tuple(chord_m),
            blade_angle_rad=tuple(blade_angle_rad),
            sections=tuple(station_sections),
        )
    except ValueError as error:
        raise ValueError(f"{path.name}: {error}") from error


def _fraction(r: float, start: float, end: float) -> float:
    """Position of ``r`` in the transition from ``start`` to ``end``, clipped to [0, 1]."""
    if end <= start:
        return 0.0 if r < end else 1.0
    return min(max((r - start) / (end - start), 0.0), 1.0)


def _blend(first, second, weight: float):
    if weight <= 0.0:
        return first
    if weight >= 1.0:
        return second
    if isinstance(first, AirfoilPolar) and isinstance(second, AirfoilPolar):
        return BlendedPolar(first, second, weight)
    if not (isinstance(first, BladeSection) and isinstance(second, BladeSection)):
        raise TypeError("the two airfoils' sections must both be BladeSection or both AirfoilPolar")
    return BladeSection(
        **{
            field.name: (1.0 - weight) * getattr(first, field.name) + weight * getattr(second, field.name)
            for field in fields(BladeSection)
        }
    )
