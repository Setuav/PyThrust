"""Propulsion model data structures."""

from .battery import BatterySpec
from .motor import MotorSpec
from .operating_point import OperatingPoint
from .propeller import PropellerSpec
from .system import SystemSpec

__all__ = [
    "BatterySpec",
    "MotorSpec",
    "OperatingPoint",
    "PropellerSpec",
    "SystemSpec",
]
