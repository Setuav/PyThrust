"""Propeller database loader for JSON metadata + CSV data files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import csv
import json
import math


@dataclass(frozen=True)
class PropellerMetadata:
    """Metadata for a propeller dataset entry."""
    id: str
    manufacturer: str
    model: str
    diameter_in: float
    pitch_in: float
    blade_count: int
    data_csv: str


@dataclass(frozen=True)
class PropellerDataPoint:
    """Single data point in J space for one RPM band."""
    j: float
    ct: float
    cp: float


@dataclass
class PropellerEntry:
    """Propeller performance data grouped by RPM bands."""
    metadata: PropellerMetadata
    data_by_rpm: Dict[float, List[PropellerDataPoint]]

    @property
    def diameter_m(self) -> float:
        return self.metadata.diameter_in * 0.0254

    @property
    def pitch_m(self) -> float:
        return self.metadata.pitch_in * 0.0254

    @property
    def rpm_levels(self) -> List[float]:
        return sorted(self.data_by_rpm.keys())

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


class PropellerDatabase:
    """Load and query propeller data from JSON + CSV files."""
    def __init__(self) -> None:
        """Create an empty propeller database."""
        self._entries: Dict[str, PropellerEntry] = {}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def propeller_count(self) -> int:
        return len(self._entries)

    def list_propellers(self) -> List[str]:
        """Return sorted propeller IDs in the database."""
        return sorted(self._entries.keys())

    def get(self, prop_id: str) -> Optional[PropellerEntry]:
        """Get a propeller entry by its ID."""
        return self._entries.get(prop_id)

    def load(self, data_dir: Path, strict: bool = False) -> bool:
        """Load all JSON/CSV entries from a dataset directory."""
        data_dir = Path(data_dir)
        if not data_dir.exists():
            self._loaded = False
            return False

        self._entries.clear()
        # Each JSON file points to a CSV with the RPM/J/Ct/Cp data.
        for json_path in sorted(data_dir.glob("*.json")):
            entry = _load_entry(json_path, data_dir, strict=strict)
            if entry is not None:
                self._entries[entry.metadata.id] = entry

        self._loaded = bool(self._entries)
        return self._loaded

    def load_entry(
        self,
        json_path: Path,
        data_dir: Optional[Path] = None,
        strict: bool = False,
    ) -> Optional[PropellerEntry]:
        """Load a single JSON metadata file and store its entry."""
        json_path = Path(json_path)
        base_dir = Path(data_dir) if data_dir is not None else json_path.parent
        entry = _load_entry(json_path, base_dir, strict=strict)
        if entry is None:
            return None

        self._entries[entry.metadata.id] = entry
        self._loaded = bool(self._entries)
        return entry

    def find_by_size(
        self,
        diameter_in: float,
        pitch_in: float,
        blade_count: int = 2,
        tolerance: float = 0.5,
    ) -> Optional[PropellerEntry]:
        """Find the closest propeller by (diameter, pitch) within tolerance."""
        candidates: List[Tuple[float, PropellerEntry]] = []

        for entry in self._entries.values():
            if entry.metadata.blade_count != blade_count:
                continue

            dist = ((entry.metadata.diameter_in - diameter_in) ** 2 +
                    (entry.metadata.pitch_in - pitch_in) ** 2) ** 0.5
            if dist <= tolerance:
                candidates.append((dist, entry))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def get_interpolated_coefficients(
        self,
        diameter_in: float,
        pitch_in: float,
        blade_count: int,
        rpm: float,
        advance_ratio: float,
        tolerance: float = 0.5,
    ) -> Tuple[float, float, bool]:
        """Convenience helper to fetch Ct/Cp by prop size."""
        entry = self.find_by_size(diameter_in, pitch_in, blade_count, tolerance)
        if entry is None:
            return 0.0, 0.0, False

        ct, cp = entry.get_coefficients(rpm, advance_ratio)
        return ct, cp, True


def _normalize_rpm(value: float) -> float:
    """Round RPM values when they are effectively integers."""
    # Keep clean integer RPM levels when possible.
    rounded = round(value)
    if abs(value - rounded) < 1e-3:
        return float(rounded)
    return float(value)


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


def _load_entry(json_path: Path, data_dir: Path, strict: bool = False) -> Optional[PropellerEntry]:
    """Load a JSON metadata file plus its CSV into a PropellerEntry."""
    try:
        metadata_raw = json.loads(json_path.read_text())
    except json.JSONDecodeError:
        return None

    required = ["id", "manufacturer", "model", "diameter_in", "pitch_in", "blade_count", "data_csv"]
    if not all(key in metadata_raw for key in required):
        return None

    metadata = PropellerMetadata(
        id=str(metadata_raw["id"]),
        manufacturer=str(metadata_raw["manufacturer"]),
        model=str(metadata_raw["model"]),
        diameter_in=float(metadata_raw["diameter_in"]),
        pitch_in=float(metadata_raw["pitch_in"]),
        blade_count=int(metadata_raw["blade_count"]),
        data_csv=str(metadata_raw["data_csv"]),
    )

    csv_path = data_dir / metadata.data_csv
    if not csv_path.exists():
        return None

    data_by_rpm: Dict[float, List[PropellerDataPoint]] = {}
    seen_keys: Dict[float, set[float]] = {}
    required_cols = {"rpm", "advance_ratio", "thrust_coeff", "power_coeff"}
    with csv_path.open("r", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not required_cols.issubset(set(reader.fieldnames)):
            if strict:
                raise ValueError(f"Missing required columns in {csv_path.name}")
            return None
        for row in reader:
            try:
                rpm = _normalize_rpm(float(row["rpm"]))
                j_value = float(row["advance_ratio"])
                ct = float(row["thrust_coeff"])
                cp = float(row["power_coeff"])
            except (KeyError, ValueError):
                if strict:
                    raise ValueError(f"Invalid numeric values in {csv_path.name}")
                continue

            if not (math.isfinite(rpm) and math.isfinite(j_value) and math.isfinite(ct) and math.isfinite(cp)):
                if strict:
                    raise ValueError(f"Non-finite values in {csv_path.name}")
                continue
            if rpm <= 0 or j_value < 0 or ct < 0 or cp < 0:
                if strict:
                    raise ValueError(f"Out-of-range values in {csv_path.name}")
                continue

            seen = seen_keys.setdefault(rpm, set())
            if j_value in seen:
                if strict:
                    raise ValueError(f"Duplicate (rpm,J) pair in {csv_path.name}")
                continue
            seen.add(j_value)

            data_by_rpm.setdefault(rpm, []).append(
                PropellerDataPoint(j=j_value, ct=ct, cp=cp)
            )

    for rpm_key, points in data_by_rpm.items():
        data_by_rpm[rpm_key] = sorted(points, key=lambda p: p.j)

    if strict:
        for rpm_key, points in data_by_rpm.items():
            if len(points) < 2:
                raise ValueError(f"Insufficient points for RPM {rpm_key} in {csv_path.name}")
        if not data_by_rpm:
            raise ValueError(f"No valid data rows in {csv_path.name}")

    return PropellerEntry(metadata=metadata, data_by_rpm=data_by_rpm)
