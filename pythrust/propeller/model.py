"""The propeller model interface: thrust and torque at an operating condition."""

from __future__ import annotations

from typing import Protocol



class PropellerModel(Protocol):
    """What the propulsion solver needs from a propeller."""

    @property
    def diameter_m(self) -> float:
        """Propeller diameter in metres."""
        ...

    @property
    def max_advance_ratio(self) -> float:
        """Advance ratio up to which the model is expected to give thrust.

        The solver starts its RPM search at this advance ratio.
        """
        ...

    def thrust_torque(self, rho: float, airspeed_mps: float, rpm: float) -> tuple[float, float]:
        """Return thrust in N and shaft torque in N m.

        ``rho`` is the air density in kg/m^3. A model returns zero torque where
        it has no data; the solver treats that condition as having no solution.
        """
        ...
