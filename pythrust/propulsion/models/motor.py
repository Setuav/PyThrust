"""Motor model data structures."""

from __future__ import annotations

from dataclasses import dataclass
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
    torque_constant_kv_ratio: float = 1.0
    magnetic_lag_tau: float = 0.0
    no_load_current_linear: float = 0.0
    no_load_current_quadratic: float = 0.0
    resistance_quadratic: float = 0.0

    # Simplified power-law iron loss parameters
    no_load_voltage_v: float = 10.0
    iron_loss_exponent: float = 0.0

    def get_no_load_current(self, rpm: float) -> float:
        """Calculate the no-load current at a given shaft speed (RPM)."""
        if rpm <= 0.0:
            return self.no_load_current_a

        if self.iron_loss_exponent > 0.0:
            rpm_0 = self.kv_rpm_per_v * self.no_load_voltage_v
            if rpm_0 > 0.0:
                return self.no_load_current_a * (rpm / rpm_0) ** self.iron_loss_exponent

        omega = rpm * (math.pi / 30.0)
        return (
            self.no_load_current_a
            + self.no_load_current_linear * omega
            + self.no_load_current_quadratic * (omega**2)
        )

    def get_winding_resistance(self, current_a: float) -> float:
        """Calculate winding resistance including current-dependent heating."""
        if self.resistance_quadratic <= 0.0:
            return self.resistance_ohm
        return self.resistance_ohm + self.resistance_quadratic * (current_a**2)
