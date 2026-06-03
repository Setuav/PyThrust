"""Core propulsion solver using SciPy root finding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import math

from scipy.optimize import root_scalar

from pythrust.propellers.database import PropellerEntry
from .models import BatterySpec, MotorSpec, OperatingPoint, PropellerSpec, SystemSpec


@dataclass(frozen=True)
class SolverConfig:
    """Configuration for the propulsion solver."""

    rpm_min: float = 100.0
    rpm_max_margin: float = 1.1
    eps_rpm: float = 1e-8
    eps_v: float = 1e-8
    max_iter: int = 100


def evaluate_propulsion_state(
    motor: MotorSpec,
    propeller: PropellerSpec,
    prop_entry: PropellerEntry,
    rho: float,
    airspeed_mps: float,
    rpm: float,
) -> tuple[float, float, float, float, float, float]:
    """Calculate aerodynamic and motor electrical states at a given RPM."""
    n = max(rpm / 60.0, 1e-6)
    j = airspeed_mps / (n * propeller.diameter_m) if propeller.diameter_m > 0 else 0.0
    ct, cp = prop_entry.get_coefficients(rpm, j)

    torque_nm = cp * rho * (n**2) * (propeller.diameter_m**5) / (2.0 * math.pi)
    kt = 30.0 / (math.pi * motor.kv_rpm_per_v * motor.torque_constant_kv_ratio)
    current_a = torque_nm / kt + motor.get_no_load_current(rpm)

    # Back-EMF with magnetic lag: V_back = (omega * (1 + tau*omega)) / Kv
    v_back = (rpm / motor.kv_rpm_per_v) * (1.0 + motor.magnetic_lag_tau * rpm * (math.pi / 30.0))

    return ct, cp, j, torque_nm, current_a, v_back


class PropulsionSolver:
    """Solve equilibrium RPM for a given operating condition."""

    def __init__(self, config: Optional[SolverConfig] = None) -> None:
        self.config = config or SolverConfig()

    def solve_operating_point(
        self,
        motor: MotorSpec,
        battery: BatterySpec,
        system: SystemSpec,
        propeller: PropellerSpec,
        prop_entry: PropellerEntry,
        rho: float,
        airspeed_mps: float,
        throttle: float,
    ) -> OperatingPoint:
        if throttle <= 0.0:
            return OperatingPoint(
                rpm=0.0,
                advance_ratio=0.0,
                ct=0.0,
                cp=0.0,
                thrust_n=0.0,
                torque_nm=0.0,
                shaft_power_w=0.0,
                motor_power_w=0.0,
                battery_power_w=0.0,
                motor_current_a=0.0,
                motor_voltage_v=0.0,
                is_feasible=False,
                infeasible_reason="throttle<=0",
            )

        def g(rpm: float) -> float:
            ct, cp, j, torque_nm, current_a, v_back = self._evaluate_state(
                motor,
                propeller,
                prop_entry,
                rho,
                airspeed_mps,
                rpm,
            )
            if cp <= 0.0 or ct < 0.0 or j < 0.0:
                return float("inf")
            v_motor = v_back + current_a * motor.get_winding_resistance(current_a)
            v_applied = throttle * battery.voltage_v
            return v_motor + current_a * system.resistance_ohm - v_applied

        rpm_min = max(self.config.rpm_min, 1.0)
        if airspeed_mps > 0.0 and propeller.diameter_m > 0.0:
            j_max = self._estimate_j_max(prop_entry)
            rpm_min = max(rpm_min, airspeed_mps / (j_max * propeller.diameter_m) * 60.0)

        rpm_max = motor.kv_rpm_per_v * battery.voltage_v * throttle
        rpm_max = max(rpm_max, rpm_min * 1.2) * self.config.rpm_max_margin

        g_min = g(rpm_min)
        g_max = g(rpm_max)

        if not (math.isfinite(g_min) and math.isfinite(g_max)) or g_min * g_max > 0:
            return self._build_infeasible_point(
                motor,
                battery,
                system,
                propeller,
                prop_entry,
                rho,
                airspeed_mps,
                rpm_min if abs(g_min) < abs(g_max) else rpm_max,
                reason="no_bracket",
            )

        result = root_scalar(
            g,
            bracket=[rpm_min, rpm_max],
            method="brentq",
            xtol=self.config.eps_rpm,
            rtol=self.config.eps_rpm,
            maxiter=self.config.max_iter,
        )

        if not result.converged:
            return self._build_infeasible_point(
                motor,
                battery,
                system,
                propeller,
                prop_entry,
                rho,
                airspeed_mps,
                result.root,
                reason="no_convergence",
            )

        return self._build_point(
            motor,
            battery,
            system,
            propeller,
            prop_entry,
            rho,
            airspeed_mps,
            result.root,
        )

    def _evaluate_state(
        self,
        motor: MotorSpec,
        propeller: PropellerSpec,
        prop_entry: PropellerEntry,
        rho: float,
        airspeed_mps: float,
        rpm: float,
    ) -> tuple[float, float, float, float, float, float]:
        return evaluate_propulsion_state(motor, propeller, prop_entry, rho, airspeed_mps, rpm)

    def _build_point(
        self,
        motor: MotorSpec,
        battery: BatterySpec,
        system: SystemSpec,
        propeller: PropellerSpec,
        prop_entry: PropellerEntry,
        rho: float,
        airspeed_mps: float,
        rpm: float,
    ) -> OperatingPoint:
        ct, cp, j, torque_nm, current_a, v_back = self._evaluate_state(
            motor,
            propeller,
            prop_entry,
            rho,
            airspeed_mps,
            rpm,
        )

        n = max(rpm / 60.0, 1e-6)
        thrust_n = ct * rho * (n**2) * (propeller.diameter_m**4)
        shaft_power_w = cp * rho * (n**3) * (propeller.diameter_m**5)
        motor_voltage_v = v_back + current_a * motor.get_winding_resistance(current_a)
        motor_power_w = motor_voltage_v * current_a
        battery_power_w = (motor_power_w + (current_a ** 2) * system.resistance_ohm) / max(1e-6, battery.discharge_efficiency)

        # Efficiency calculations
        if shaft_power_w > 0.0:
            propeller_efficiency = (thrust_n * airspeed_mps) / shaft_power_w
        else:
            propeller_efficiency = 0.0

        if motor_power_w > 0.0:
            motor_efficiency = shaft_power_w / motor_power_w
        else:
            motor_efficiency = 0.0

        if battery_power_w > 0.0:
            system_efficiency = (thrust_n * airspeed_mps) / battery_power_w
        else:
            system_efficiency = 0.0

        feasible = True
        reason = None
        if current_a > motor.current_max_a:
            feasible = False
            reason = "current_limit"
        if ct < 0.0 or cp < 0.0 or j < 0.0:
            feasible = False
            reason = "invalid_coefficients"
        if (propeller_efficiency > 1.0001 or propeller_efficiency < 0.0 or
            motor_efficiency > 1.0001 or motor_efficiency < 0.0 or
            system_efficiency > 1.0001 or system_efficiency < 0.0):
            feasible = False
            reason = "invalid_efficiency"

        return OperatingPoint(
            rpm=float(rpm),
            advance_ratio=float(j),
            ct=float(ct),
            cp=float(cp),
            thrust_n=float(thrust_n),
            torque_nm=float(torque_nm),
            shaft_power_w=float(shaft_power_w),
            motor_power_w=float(motor_power_w),
            battery_power_w=float(battery_power_w),
            motor_current_a=float(current_a),
            motor_voltage_v=float(motor_voltage_v),
            is_feasible=feasible,
            infeasible_reason=reason,
            propeller_efficiency=float(propeller_efficiency),
            motor_efficiency=float(motor_efficiency),
            system_efficiency=float(system_efficiency),
        )

    def _build_infeasible_point(
        self,
        motor: MotorSpec,
        battery: BatterySpec,
        system: SystemSpec,
        propeller: PropellerSpec,
        prop_entry: PropellerEntry,
        rho: float,
        airspeed_mps: float,
        rpm: float,
        reason: str,
    ) -> OperatingPoint:
        point = self._build_point(
            motor,
            battery,
            system,
            propeller,
            prop_entry,
            rho,
            airspeed_mps,
            rpm,
        )
        return OperatingPoint(
            rpm=point.rpm,
            advance_ratio=point.advance_ratio,
            ct=point.ct,
            cp=point.cp,
            thrust_n=point.thrust_n,
            torque_nm=point.torque_nm,
            shaft_power_w=point.shaft_power_w,
            motor_power_w=point.motor_power_w,
            battery_power_w=point.battery_power_w,
            motor_current_a=point.motor_current_a,
            motor_voltage_v=point.motor_voltage_v,
            is_feasible=False,
            infeasible_reason=reason,
            propeller_efficiency=point.propeller_efficiency,
            motor_efficiency=point.motor_efficiency,
            system_efficiency=point.system_efficiency,
        )

    @staticmethod
    def _estimate_j_max(prop_entry: PropellerEntry) -> float:
        j_maxes = []
        for points in prop_entry.data_by_rpm.values():
            if not points:
                continue
            j_maxes.append(points[-1].j)

        if not j_maxes:
            return 0.6

        j_maxes.sort()
        start = len(j_maxes) // 4
        if start >= len(j_maxes):
            start = len(j_maxes) - 1
        return j_maxes[start]
