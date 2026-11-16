"""Battery models for propulsion and mission analysis."""

from .fixed import FixedVoltageBattery
from .rate_map import RateMapBattery
from .state import BatteryIntegrationResult, BatteryPoint, BatteryState

Battery = FixedVoltageBattery | RateMapBattery
"""Any battery model accepted by the propulsion solver."""

__all__ = [
    "Battery",
    "BatteryIntegrationResult",
    "BatteryPoint",
    "BatteryState",
    "FixedVoltageBattery",
    "RateMapBattery",
]
