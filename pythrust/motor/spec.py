"""Motor model data structures."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MotorSpec:
    """Motor parameters of Mark Drela's DC motor model.

    With the optional fields at their defaults this is the first-order model:
    constant resistance, constant no-load current and a torque constant equal
    to the speed constant. The optional fields give the second-order model:

    - ``resistance_quadratic``: R(i) = R0 + R2 i^2 (winding heating)
    - ``no_load_current_linear``, ``no_load_current_quadratic``:
      io(w) = io0 + io1 w + io2 w^2, with w in rad/s
    - ``torque_constant_kv_ratio``: KQ / KV
    - ``magnetic_lag_tau``: back-EMF vm = (1 + tau w) w / KV

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

    def get_no_load_current(self, rpm: float) -> float:
        """Calculate the no-load current at a given shaft speed (RPM)."""
        if rpm <= 0.0:
            return self.no_load_current_a

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
