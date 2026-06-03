"""System resistance calibration from manufacturer test data.

This module identifies the lumped system electrical transmission resistance,
``R_system`` (system.resistance_ohm), by minimising the residual between
calculated battery DC current and measured current at the measured shaft speed (RPM).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from scipy.optimize import least_squares

from pythrust.propellers.database import PropellerEntry
from .models import BatterySpec, MotorSpec, PropellerSpec, SystemSpec
from .solver import evaluate_propulsion_state


@dataclass(frozen=True)
class ManufacturerTestPoint:
    """A single row from a manufacturer/test-stand table.

    Parameters
    ----------
    rpm:
        Measured shaft speed in RPM.
    thrust_g:
        Measured static thrust in grams.
    current_a:
        Measured battery current in Amps.
    """

    rpm: float
    thrust_g: float
    current_a: float


@dataclass(frozen=True)
class CalibrationResult:
    """Outcome of :meth:`PropulsionCalibrator.calibrate`.

    Parameters
    ----------
    system_resistance_ohm:
        Identified system transmission/line resistance (ohms).
    rmse_thrust_g:
        Root-mean-square thrust residual in grams over all valid points.
    rmse_current_a:
        Root-mean-square current residual in amps.
    r_squared_thrust:
        Coefficient of determination for thrust.
    n_points:
        Number of test points used after quality filtering.
    converged:
        Whether the optimiser converged to a solution.
    warnings:
        List of data-quality or fit-quality warning messages.
    """

    system_resistance_ohm: float
    rmse_thrust_g: float
    rmse_current_a: float
    r_squared_thrust: float
    n_points: int
    converged: bool
    warnings: List[str]

    def to_system_spec(self) -> SystemSpec:
        """Return a new :class:`SystemSpec` with the calibrated resistance."""
        return SystemSpec(resistance_ohm=self.system_resistance_ohm)


class PropulsionCalibrator:
    """Identify system resistance from a manufacturer test table.

    The system resistance represents the lumped equivalent electrical resistance
    of the ESC MOSFETs, battery internal resistance, cables, and connectors.
    """

    def __init__(self, system_bounds: tuple[float, float] = (0.0, 1.0)) -> None:
        self.system_bounds = system_bounds

    def calibrate(
        self,
        test_points: List[ManufacturerTestPoint],
        motor: MotorSpec,
        battery: BatterySpec,
        system: SystemSpec,
        propeller: PropellerSpec,
        prop_entry: PropellerEntry,
        rho: float = 1.225,
        airspeed_mps: float = 0.0,
    ) -> CalibrationResult:
        """Fit ``system.resistance_ohm`` to match the measured battery current.

        Parameters
        ----------
        test_points:
            Rows from the test table.
        motor:
            Motor spec with datasheet Kv/R/I0 values (fixed).
        battery:
            Battery used during the test.
        system:
            Initial system spec; ``system.resistance_ohm`` is the starting guess.
        propeller:
            Propeller geometry.
        prop_entry:
            Propeller aerodynamic database entry.
        rho:
            Air density during the test in kg/m³.
        airspeed_mps:
            Freestream airspeed; 0.0 for static bench test.
        """
        warnings: List[str] = []

        valid = [
            p for p in test_points
            if (p.rpm > 0.0
                and math.isfinite(p.thrust_g) and p.thrust_g >= 0.0
                and math.isfinite(p.current_a) and p.current_a > 0.0)
        ]
        n_dropped = len(test_points) - len(valid)
        if n_dropped:
            warnings.append(
                f"{n_dropped} point(s) dropped: invalid RPM, thrust, or current."
            )
        if len(valid) < 3:
            warnings.append(
                f"Only {len(valid)} valid point(s) — calibration may be unreliable."
            )
        if not valid:
            return CalibrationResult(
                system_resistance_ohm=system.resistance_ohm,
                rmse_thrust_g=float("nan"),
                rmse_current_a=float("nan"),
                r_squared_thrust=0.0,
                n_points=0,
                converged=False,
                warnings=warnings,
            )

        current_scale = max(p.current_a for p in valid)
        def _motor_state(rpm: float):
            res = evaluate_propulsion_state(motor, propeller, prop_entry, rho, airspeed_mps, rpm)
            ct, cp, j, torque_nm, i_motor, v_back = res
            if cp <= 0.0 or ct < 0.0 or j < 0.0:
                return None
            v_m = v_back + i_motor * motor.get_winding_resistance(i_motor)
            n = max(rpm / 60.0, 1e-6)
            thrust_g = ct * rho * (n ** 2) * (propeller.diameter_m ** 4) * 1000.0 / 9.80665
            return i_motor, v_m, thrust_g

        def _residuals(params: list) -> list:
            r_sys = float(params[0])
            res: list[float] = []
            for pt in valid:
                state = _motor_state(pt.rpm)
                if state is None:
                    res.append(1.0)
                    continue
                i_motor, v_m, _ = state
                i_bat_pred = (v_m * i_motor + (i_motor ** 2) * r_sys) / (battery.voltage_v * max(1e-6, battery.discharge_efficiency))
                res.append((i_bat_pred - pt.current_a) / current_scale)
            return res

        lo, hi = self.system_bounds
        opt = least_squares(
            _residuals,
            x0=[min(hi, max(lo, system.resistance_ohm))],
            bounds=([lo], [hi]),
            method="trf",
            ftol=1e-12,
            xtol=1e-12,
            gtol=1e-12,
            max_nfev=100,
        )
        r_sys_fit = float(opt.x[0])
        converged = bool(opt.success)

        thrust_errs: list[float] = []
        current_errs: list[float] = []
        for pt in valid:
            state = _motor_state(pt.rpm)
            if state is None:
                continue
            i_motor, v_m, thrust_pred_g = state
            thrust_errs.append(thrust_pred_g - pt.thrust_g)
            i_bat_pred = (v_m * i_motor + (i_motor ** 2) * r_sys_fit) / (battery.voltage_v * max(1e-6, battery.discharge_efficiency))
            current_errs.append(i_bat_pred - pt.current_a)

        rmse_thrust = (
            math.sqrt(sum(e ** 2 for e in thrust_errs) / len(thrust_errs))
            if thrust_errs else float("nan")
        )
        rmse_current = (
            math.sqrt(sum(e ** 2 for e in current_errs) / len(current_errs))
            if current_errs else float("nan")
        )

        mean_t = sum(p.thrust_g for p in valid) / len(valid)
        ss_tot = sum((p.thrust_g - mean_t) ** 2 for p in valid)
        ss_res = sum(e ** 2 for e in thrust_errs)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0

        if not math.isnan(rmse_thrust):
            max_t = max(p.thrust_g for p in valid)
            if rmse_thrust / max_t > 0.05:
                warnings.append(
                    f"Thrust RMSE {rmse_thrust:.1f} g exceeds 5 % of max thrust "
                    f"({max_t:.0f} g). Propeller entry may not match the test conditions."
                )
        if r2 < 0.90:
            warnings.append(
                f"Thrust R² = {r2:.3f} < 0.90. "
                "Check propeller database entry and test conditions."
            )
        if not math.isnan(rmse_current) and rmse_current / current_scale > 0.05:
            warnings.append(
                f"Current RMSE {rmse_current:.2f} A exceeds 5 % of max current "
                f"({current_scale:.1f} A). Motor or propeller parameters may be inaccurate."
            )

        return CalibrationResult(
            system_resistance_ohm=r_sys_fit,
            rmse_thrust_g=rmse_thrust,
            rmse_current_a=rmse_current,
            r_squared_thrust=r2,
            n_points=len(valid),
            converged=converged,
            warnings=warnings,
        )

    @staticmethod
    def load_csv(
        path: Path,
        *,
        rpm_col: str = "rpm",
        thrust_col: str = "thrust_g",
        current_col: str = "current_a",
    ) -> List[ManufacturerTestPoint]:
        """Load a manufacturer test table from a CSV file."""
        path = Path(path)
        points: List[ManufacturerTestPoint] = []

        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                return points
            fields = set(reader.fieldnames)
            if rpm_col not in fields or thrust_col not in fields or current_col not in fields:
                # Silently return empty or raise error? Let's return empty or skip
                return points

            for row in reader:
                try:
                    rpm = float(row[rpm_col])
                    thrust_g = float(row[thrust_col])
                    current_a = float(row[current_col])
                except (KeyError, ValueError):
                    continue

                points.append(
                    ManufacturerTestPoint(
                        rpm=rpm,
                        thrust_g=thrust_g,
                        current_a=current_a,
                    )
                )

        return points
