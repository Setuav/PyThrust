"""Tabulated propeller performance: thrust and power coefficients by RPM and advance ratio."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class PropellerDataPoint:
    """Single data point in J space for one RPM band."""
    j: float
    ct: float
    cp: float


class TablePropeller:
    """Propeller model interpolating a table of thrust and power coefficients.

    ``data_by_rpm`` maps each RPM band to its points, sorted by advance ratio.
    Coefficients are interpolated linearly in advance ratio within a band, then
    between the two bands around the RPM. Outside the RPM range the nearest band
    is used; below a band's lowest advance ratio its first point is used; past
    its largest advance ratio the coefficients are zero.
    """

    def __init__(self, diameter_m: float, data_by_rpm: Dict[float, List[PropellerDataPoint]]) -> None:
        self.diameter_m = float(diameter_m)
        self.data_by_rpm = data_by_rpm

    @property
    def rpm_levels(self) -> List[float]:
        return sorted(self.data_by_rpm.keys())

    @property
    def max_advance_ratio(self) -> float:
        """Lower quartile of the largest advance ratio of each RPM band; 0.6 without data."""
        j_maxes = sorted(points[-1].j for points in self.data_by_rpm.values() if points)
        if not j_maxes:
            return 0.6
        return j_maxes[len(j_maxes) // 4]

    def scaled(self, diameter_m: float) -> "TablePropeller":
        """Return the propeller at another diameter with its coefficients unchanged.

        This describes a geometrically similar propeller, without the Reynolds
        number effects of the size change.
        """
        return TablePropeller(diameter_m, self.data_by_rpm)

    def thrust_torque(self, rho: float, airspeed_mps: float, rpm: float) -> Tuple[float, float]:
        """Thrust in N and torque in N m; NaN for both where the table gives no thrust and power.

        That is where the interpolated power coefficient is not positive or the
        thrust coefficient is negative: past the table's data, or in windmilling
        rows a table may hold.
        """
        n = max(rpm / 60.0, 1e-6)
        j = airspeed_mps / (n * self.diameter_m) if self.diameter_m > 0 else 0.0
        ct, cp = self.get_coefficients(rpm, j)
        if cp <= 0.0 or ct < 0.0:
            return math.nan, math.nan
        thrust_n = ct * rho * (n**2) * (self.diameter_m**4)
        torque_nm = cp * rho * (n**2) * (self.diameter_m**5) / (2.0 * math.pi)
        return thrust_n, torque_nm

    def get_coefficients(self, rpm: float, advance_ratio: float) -> Tuple[float, float]:
        """Return Ct/Cp for a given RPM and advance ratio."""
        if not self.data_by_rpm:
            return 0.0, 0.0

        rpm_levels = self.rpm_levels
        rpm_clamped = max(min(rpm, rpm_levels[-1]), rpm_levels[0])

        low_idx, high_idx = _find_bracketing_indices(rpm_levels, rpm_clamped)
        rpm_low = rpm_levels[low_idx]
        rpm_high = rpm_levels[high_idx]

        # First interpolate on J at each RPM band, then blend between RPM bands.
        ct_low, cp_low = self._interp_at_rpm(rpm_low, advance_ratio)
        ct_high, cp_high = self._interp_at_rpm(rpm_high, advance_ratio)

        if rpm_high == rpm_low:
            return ct_low, cp_low

        frac = (rpm_clamped - rpm_low) / (rpm_high - rpm_low)
        ct = ct_low + frac * (ct_high - ct_low)
        cp = cp_low + frac * (cp_high - cp_low)
        return float(ct), float(cp)

    def _interp_at_rpm(self, rpm: float, advance_ratio: float) -> Tuple[float, float]:
        """Interpolate Ct/Cp at a fixed RPM band."""
        points = self.data_by_rpm.get(rpm)
        if not points:
            return 0.0, 0.0

        j_values = [p.j for p in points]
        ct_values = [p.ct for p in points]
        cp_values = [p.cp for p in points]

        # Clamp to the lowest J in the dataset.
        if advance_ratio <= j_values[0]:
            return ct_values[0], cp_values[0]

        # Do not extrapolate past J_max.
        if advance_ratio > j_values[-1]:
            return 0.0, 0.0

        # Linear interpolation between the two nearest J points.
        idx = _find_insert_index(j_values, advance_ratio)
        j_low = j_values[idx - 1]
        j_high = j_values[idx]
        ct_low = ct_values[idx - 1]
        ct_high = ct_values[idx]
        cp_low = cp_values[idx - 1]
        cp_high = cp_values[idx]

        frac = (advance_ratio - j_low) / (j_high - j_low)
        ct = ct_low + frac * (ct_high - ct_low)
        cp = cp_low + frac * (cp_high - cp_low)
        return float(ct), float(cp)


def _find_bracketing_indices(values: List[float], target: float) -> Tuple[int, int]:
    """Return indices of the two values that bracket the target."""
    if target <= values[0]:
        return 0, 0
    if target >= values[-1]:
        return len(values) - 1, len(values) - 1

    idx = _find_insert_index(values, target)
    return idx - 1, idx


def _find_insert_index(values: List[float], target: float) -> int:
    """Find the insertion index for a sorted list."""
    lo = 0
    hi = len(values)
    while lo < hi:
        mid = (lo + hi) // 2
        if values[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return min(max(lo, 1), len(values) - 1)
