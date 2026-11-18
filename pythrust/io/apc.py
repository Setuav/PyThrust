"""Reader for APC propeller performance files (``PER3_*.dat``)."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Dict, List, Union

from pythrust.propeller.table import PropellerDataPoint, TablePropeller

_RPM_RE = re.compile(r"PROP RPM\s*=\s*(\d+(?:\.\d+)?)")
_MODEL_RE = re.compile(r"(?P<diam>\d+(?:\.\d+)?)x\d+(?:\.\d+)?")
_COLUMN_COUNT = 15
"""Columns of an APC data row: V, J, Pe, Ct, Cp, then power, torque, thrust and the rest."""
_J, _CT, _CP = 1, 3, 4
_INCH_TO_M = 0.0254


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
