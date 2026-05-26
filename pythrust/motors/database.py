"""Brushless motor database loader and query interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Dict, List, Optional
from pythrust.propulsion.models import MotorSpec


@dataclass(frozen=True)
class MotorEntry:
    """A database entry for a single brushless motor."""
    id: str
    name: str
    manufacturer: str
    kv: float
    resistance: float
    io: float
    max_current: float
    weight_g: float
    max_power: float
    io_voltage: float

    def to_spec(self) -> MotorSpec:
        """Convert the database entry to a PyThrust MotorSpec object."""
        return MotorSpec(
            kv_rpm_per_v=self.kv,
            resistance_ohm=self.resistance,
            no_load_current_a=self.io,
            current_max_a=self.max_current,
            no_load_voltage_v=self.io_voltage,
        )


class MotorDatabase:
    """Load and query brushless motor database from JSON files."""

    def __init__(self) -> None:
        """Create an empty motor database."""
        self._entries: Dict[str, MotorEntry] = {}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """Return True if a database has been successfully loaded."""
        return self._loaded

    @property
    def motor_count(self) -> int:
        """Return the number of motors in the database."""
        return len(self._entries)

    def list_motors(self) -> List[str]:
        """Return sorted unique motor IDs in the database."""
        return sorted(self._entries.keys())

    def get(self, motor_id: str) -> Optional[MotorEntry]:
        """Get a motor entry by its unique ID."""
        return self._entries.get(motor_id)

    def load(self, data_dir: Path) -> bool:
        """Load all motor JSON entries from a dataset directory."""
        data_dir = Path(data_dir)
        if not data_dir.exists():
            self._loaded = False
            return False

        self._entries.clear()
        
        # Recursively search for and load all .json files under the directory
        for json_path in sorted(data_dir.glob("**/*.json")):
            self.load_entry(json_path)

        self._loaded = bool(self._entries)
        return self._loaded

    def load_entry(self, json_path: Path) -> Optional[MotorEntry]:
        """Load a single motor JSON file and store its entry."""
        json_path = Path(json_path)
        if not json_path.exists():
            return None
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                m = json.load(f)
            
            entry = MotorEntry(
                id=m.get("id", ""),
                name=m.get("name", "Unknown"),
                manufacturer=m.get("manufacturer", "Unknown"),
                kv=float(m.get("kv", 0.0)),
                resistance=float(m.get("resistance", 0.0)),
                io=float(m.get("io", 0.0)),
                max_current=float(m.get("max_current", 0.0)),
                weight_g=float(m.get("weight_g", 0.0)),
                max_power=float(m.get("max_power", 0.0)),
                io_voltage=float(m.get("io_voltage", 10.0)),
            )
            if entry.id:
                self._entries[entry.id] = entry
                self._loaded = True
                return entry
        except Exception:
            pass
        return None

    def search(
        self,
        min_kv: Optional[float] = None,
        max_kv: Optional[float] = None,
        min_max_current: Optional[float] = None,
        min_weight: Optional[float] = None,
        max_weight: Optional[float] = None,
    ) -> List[MotorEntry]:
        """Search and filter motors in the database matching specified criteria."""
        results = []
        for entry in self._entries.values():
            if min_kv is not None and entry.kv < min_kv:
                continue
            if max_kv is not None and entry.kv > max_kv:
                continue
            if min_max_current is not None and entry.max_current < min_max_current:
                continue
            if min_weight is not None and entry.weight_g < min_weight:
                continue
            if max_weight is not None and entry.weight_g > max_weight:
                continue
            results.append(entry)
        return results
