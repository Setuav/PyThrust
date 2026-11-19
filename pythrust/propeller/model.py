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

        ``rho`` is the air density in kg/m^3. Where the model has no result, such
        as outside a table's data, it returns NaN; the solver treats that as no
        solution. Negative thrust or torque, as for a windmilling propeller, is a
        result: the solver keeps it in its search and marks an operating point
        that lands there infeasible.
        """
        ...
