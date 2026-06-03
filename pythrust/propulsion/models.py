"""Core propulsion model data structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


import math


@dataclass(frozen=True)
class MotorSpec:
    """Motor electrical parameters (supporting both 1st and 2nd order models).

    All values are taken directly from the manufacturer datasheet or calibrated.

    Units:
    - kv_rpm_per_v: RPM / V
    - resistance_ohm: ohm
    - no_load_current_a: A
    - current_max_a: A
    """

    kv_rpm_per_v: float
    resistance_ohm: float
    no_load_current_a: float
    current_max_a: float

    # Optional 2nd-order parameters (Drela / QPROP model)
    torque_constant_kv_ratio: float = 1.0     # Kq / Kv ratio (default: 1.0)
    magnetic_lag_tau: float = 0.0             # tau (magnetic lag time constant)
    no_load_current_linear: float = 0.0       # Io1 (A/(rad/s))
    no_load_current_quadratic: float = 0.0    # Io2 (A/(rad/s)^2)
    resistance_quadratic: float = 0.0         # R2 (Ohms/Amp^2)

    # Simplified power-law iron loss parameters
    no_load_voltage_v: float = 10.0           # Datasheet measurement voltage
    iron_loss_exponent: float = 0.0           # If >0, scales I0 by (RPM / RPM_0)^exponent

    def get_no_load_current(self, rpm: float) -> float:
        """Calculate the no-load current at a given shaft speed (RPM)."""
        if rpm <= 0.0:
            return self.no_load_current_a

        # 1. Check if power-law exponent is specified
        if self.iron_loss_exponent > 0.0:
            rpm_0 = self.kv_rpm_per_v * self.no_load_voltage_v
            if rpm_0 > 0.0:
                return self.no_load_current_a * (rpm / rpm_0) ** self.iron_loss_exponent

        # 2. Otherwise use Drela's quadratic speed model: Io0 + Io1*omega + Io2*omega^2
        omega = rpm * (math.pi / 30.0)
        return (
            self.no_load_current_a
            + self.no_load_current_linear * omega
            + self.no_load_current_quadratic * (omega ** 2)
        )

    def get_winding_resistance(self, current_a: float) -> float:
        """Calculate winding resistance including current-dependent heating."""
        if self.resistance_quadratic <= 0.0:
            return self.resistance_ohm
        return self.resistance_ohm + self.resistance_quadratic * (current_a ** 2)


@dataclass(frozen=True)
class BatterySpec:
    """Battery pack parameters.

    Units:
    - voltage_v: V
    - discharge_efficiency: 0-1
    """

    voltage_v: float
    discharge_efficiency: float = 1.0


@dataclass(frozen=True)
class SystemSpec:
    """System transmission/line electrical parameters.

    Units:
    - resistance_ohm: ohm
    """

    resistance_ohm: float = 0.0


@dataclass(frozen=True)
class PropellerSpec:
    """Propeller geometry.

    Units:
    - diameter_m: m
    - pitch_m: m (optional)
    """

    diameter_m: float
    blade_count: int = 2
    pitch_m: Optional[float] = None


@dataclass(frozen=True)
class OperatingPoint:
    """Solved operating point for a given condition."""

    rpm: float
    advance_ratio: float
    ct: float
    cp: float
    thrust_n: float
    torque_nm: float
    shaft_power_w: float
    motor_power_w: float
    battery_power_w: float
    motor_current_a: float
    motor_voltage_v: float
    is_feasible: bool
    infeasible_reason: Optional[str] = None
    propeller_efficiency: float = 0.0
    motor_efficiency: float = 0.0
    system_efficiency: float = 0.0
