"""Battery models for propulsion and mission analysis."""

from .fixed import FixedVoltageBattery
from .network import BatteryNetwork, NetworkIntegrationResult, NetworkPoint, NetworkState
from .rate_map import RateMapBattery
from .state import BatteryIntegrationResult, BatteryPoint, BatteryState

Battery = FixedVoltageBattery | RateMapBattery
"""Any battery model accepted by the propulsion solver."""

__all__ = [
    "Battery",
    "BatteryNetwork",
    "BatteryIntegrationResult",
    "BatteryPoint",
    "BatteryState",
    "FixedVoltageBattery",
    "NetworkIntegrationResult",
    "NetworkPoint",
    "NetworkState",
    "RateMapBattery",
]
