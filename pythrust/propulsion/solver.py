"""Core propulsion solver using SciPy root finding."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

import math

from scipy.optimize import root_scalar

from pythrust.battery import Battery, BatteryPoint, BatteryState, FixedVoltageBattery
from pythrust.motor import MotorSpec
from pythrust.propeller.model import PropellerModel
from .models import OperatingPoint, SystemSpec


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
    propeller: PropellerModel,
    rho: float,
    airspeed_mps: float,
    rpm: float,
) -> tuple[float, float, float, float, float]:
    """Calculate propeller loads and motor electrical states at a given RPM.

    Returns thrust, torque, advance ratio, motor current and back-EMF.
    """
    n = max(rpm / 60.0, 1e-6)
    j = airspeed_mps / (n * propeller.diameter_m) if propeller.diameter_m > 0 else 0.0
    thrust_n, torque_nm = propeller.thrust_torque(rho, airspeed_mps, rpm)

    kt = 30.0 / (math.pi * motor.kv_rpm_per_v * motor.torque_constant_kv_ratio)
    current_a = torque_nm / kt + motor.get_no_load_current(rpm)

    # Back-EMF with magnetic lag: V_back = (omega * (1 + tau*omega)) / Kv
    v_back = (rpm / motor.kv_rpm_per_v) * (1.0 + motor.magnetic_lag_tau * rpm * (math.pi / 30.0))

    return thrust_n, torque_nm, j, current_a, v_back


class PropulsionSolver:
    """Solve equilibrium RPM for a given operating condition."""

    def __init__(self, config: Optional[SolverConfig] = None) -> None:
        self.config = config or SolverConfig()

    def solve_operating_point(
        self,
        motor: MotorSpec,
        battery: Battery,
        system: SystemSpec,
        propeller: PropellerModel,
        rho: float,
        airspeed_mps: float,
        throttle: float,
        battery_state: BatteryState | None = None,
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
                battery_voltage_v=self._battery_voltage(battery, 0.0, battery_state),
                battery_current_a=0.0,
                battery_c_rate=0.0,
                battery_efficiency=self._battery_efficiency(battery, None),
            )

        self._validate_battery_state(battery, battery_state)

        def g(rpm: float) -> float:
            thrust_n, torque_nm, j, current_a, v_back = self._evaluate_state(
                motor,
                propeller,
                rho,
                airspeed_mps,
                rpm,
            )
            if torque_nm <= 0.0 or thrust_n < 0.0 or j < 0.0:
                return float("inf")
            v_motor = v_back + current_a * motor.get_winding_resistance(current_a)
            battery_current_for_voltage_a = throttle * current_a
            battery_voltage_v = self._battery_voltage(battery, battery_current_for_voltage_a, battery_state)
            v_applied = throttle * battery_voltage_v
            return v_motor + current_a * system.resistance_ohm - v_applied

        rpm_min = max(self.config.rpm_min, 1.0)
        if airspeed_mps > 0.0 and propeller.diameter_m > 0.0:
            rpm_min = max(rpm_min, airspeed_mps / (propeller.max_advance_ratio * propeller.diameter_m) * 60.0)

        rpm_max = motor.kv_rpm_per_v * self._battery_voltage(battery, 0.0, battery_state) * throttle
        rpm_max = max(rpm_max, rpm_min * 1.2) * self.config.rpm_max_margin

        g_min = g(rpm_min)
        if not math.isfinite(g_min):
            rpm_min = self._lowest_valid_rpm(g, rpm_min, rpm_max)
            g_min = g(rpm_min)
        g_max = g(rpm_max)

        if not (math.isfinite(g_min) and math.isfinite(g_max)) or g_min * g_max > 0:
            return self._build_infeasible_point(
                motor,
                battery,
                system,
                propeller,
                rho,
                airspeed_mps,
                rpm_min if abs(g_min) < abs(g_max) else rpm_max,
                reason="no_bracket",
                battery_state=battery_state,
                throttle=throttle,
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
                rho,
                airspeed_mps,
                result.root,
                reason="no_convergence",
                battery_state=battery_state,
                throttle=throttle,
            )

        return self._build_point(
            motor,
            battery,
            system,
            propeller,
            rho,
            airspeed_mps,
            result.root,
            battery_state=battery_state,
            throttle=throttle,
        )

    @staticmethod
    def _lowest_valid_rpm(g: Callable[[float], float], rpm_low: float, rpm_high: float) -> float:
        """Return the lowest RPM in ``[rpm_low, rpm_high]`` where ``g`` is finite.

        The bracket starts at the propeller data's largest advance ratio, where the
        coefficients can already describe a windmilling propeller. The coefficients
        become valid as the RPM rises, so the search moves the bracket's lower end
        onto the first valid RPM. ``g(rpm_low)`` is not finite; the method returns
        ``rpm_high`` when no sample is valid.
        """
        samples = [rpm_low + (rpm_high - rpm_low) * index / 32 for index in range(33)]
        valid = next((index for index, rpm in enumerate(samples) if math.isfinite(g(rpm))), None)
        if valid is None:
            return rpm_high
        invalid_rpm, valid_rpm = samples[valid - 1], samples[valid]
        for _ in range(40):
            mid = 0.5 * (invalid_rpm + valid_rpm)
            if math.isfinite(g(mid)):
                valid_rpm = mid
            else:
                invalid_rpm = mid
        return valid_rpm

    def _evaluate_state(
        self,
        motor: MotorSpec,
        propeller: PropellerModel,
        rho: float,
        airspeed_mps: float,
        rpm: float,
    ) -> tuple[float, float, float, float, float]:
        return evaluate_propulsion_state(motor, propeller, rho, airspeed_mps, rpm)

    def _build_point(
        self,
        motor: MotorSpec,
        battery: Battery,
        system: SystemSpec,
        propeller: PropellerModel,
        rho: float,
        airspeed_mps: float,
        rpm: float,
        battery_state: BatteryState | None = None,
        throttle: float = 1.0,
    ) -> OperatingPoint:
        thrust_n, torque_nm, j, current_a, v_back = self._evaluate_state(
            motor,
            propeller,
            rho,
            airspeed_mps,
            rpm,
        )

        n = max(rpm / 60.0, 1e-6)
        shaft_power_w = torque_nm * 2.0 * math.pi * n
        dynamic_force_n = rho * (n**2) * (propeller.diameter_m**4)
        if dynamic_force_n > 0.0:
            ct = thrust_n / dynamic_force_n
            cp = 2.0 * math.pi * torque_nm / (dynamic_force_n * propeller.diameter_m)
        else:
            ct = cp = 0.0
        motor_voltage_v = v_back + current_a * motor.get_winding_resistance(current_a)
        motor_power_w = motor_voltage_v * current_a
        battery_power_w = self._battery_power(
            battery,
            current_a=current_a,
            motor_power_w=motor_power_w,
            system=system,
        )
        battery_current_for_voltage_a = throttle * current_a
        battery_point = self._battery_point(battery, battery_current_for_voltage_a, battery_state)
        battery_voltage_v = self._battery_voltage_from_point(
            battery,
            battery_current_for_voltage_a,
            battery_state,
            battery_point,
        )
        battery_current_a = self._battery_current_from_point_or_power(
            battery_power_w,
            battery_voltage_v,
            battery_point,
        )
        battery_c_rate = battery_point.c_rate if battery_point is not None else 0.0
        battery_efficiency = self._battery_efficiency(battery, battery_point)

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

        reason = None
        if current_a > motor.current_max_a:
            reason = "current_limit"
        if reason is None and system.max_current_a is not None and current_a > system.max_current_a:
            reason = "esc_current_limit"
        if reason is None and battery_point is not None and not battery_point.is_feasible:
            reason = f"battery_{battery_point.infeasible_reason}"
        if reason is None and (ct < 0.0 or cp < 0.0 or j < 0.0):
            reason = "invalid_coefficients"
        if reason is None and (
            propeller_efficiency > 1.0001 or propeller_efficiency < 0.0 or
            motor_efficiency > 1.0001 or motor_efficiency < 0.0 or
            system_efficiency > 1.0001 or system_efficiency < 0.0
        ):
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
            is_feasible=reason is None,
            infeasible_reason=reason,
            propeller_efficiency=float(propeller_efficiency),
            motor_efficiency=float(motor_efficiency),
            system_efficiency=float(system_efficiency),
            battery_voltage_v=float(battery_voltage_v),
            battery_current_a=float(battery_current_a),
            battery_c_rate=float(battery_c_rate),
            battery_efficiency=float(battery_efficiency),
        )

    def _build_infeasible_point(
        self,
        motor: MotorSpec,
        battery: Battery,
        system: SystemSpec,
        propeller: PropellerModel,
        rho: float,
        airspeed_mps: float,
        rpm: float,
        reason: str,
        battery_state: BatteryState | None = None,
        throttle: float = 1.0,
    ) -> OperatingPoint:
        point = self._build_point(
            motor,
            battery,
            system,
            propeller,
            rho,
            airspeed_mps,
            rpm,
            battery_state=battery_state,
            throttle=throttle,
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
            battery_voltage_v=point.battery_voltage_v,
            battery_current_a=point.battery_current_a,
            battery_c_rate=point.battery_c_rate,
            battery_efficiency=point.battery_efficiency,
        )

    @staticmethod
    def _validate_battery_state(battery: Battery, state: BatteryState | None) -> None:
        if state is None and not isinstance(battery, FixedVoltageBattery):
            raise ValueError("battery_state is required for dynamic battery models")

    def _battery_voltage(
        self,
        battery: Battery,
        current_a: float,
        state: BatteryState | None,
    ) -> float:
        point = self._battery_point(battery, current_a, state)
        if point is not None:
            return point.terminal_voltage_v
        return float(battery.terminal_voltage(current_a=current_a, state=state))

    def _battery_voltage_from_point(
        self,
        battery: Battery,
        current_a: float,
        state: BatteryState | None,
        point: BatteryPoint | None,
    ) -> float:
        if point is not None:
            return point.terminal_voltage_v
        return self._battery_voltage(battery, current_a, state)

    @staticmethod
    def _battery_current_from_point_or_power(
        battery_power_w: float,
        battery_voltage_v: float,
        point: BatteryPoint | None,
    ) -> float:
        if point is not None:
            return point.current_a
        return battery_power_w / max(1e-6, battery_voltage_v)

    @staticmethod
    def _battery_point(
        battery: Battery,
        current_a: float,
        state: BatteryState | None,
    ) -> BatteryPoint | None:
        if isinstance(battery, FixedVoltageBattery):
            return None
        if state is None:
            raise ValueError("battery_state is required for dynamic battery models")
        return battery.state_at_current(state=state, current_a=current_a)

    @staticmethod
    def _battery_power(
        battery: Battery,
        current_a: float,
        motor_power_w: float,
        system: SystemSpec,
    ) -> float:
        power_w = motor_power_w + (current_a**2) * system.resistance_ohm
        if isinstance(battery, FixedVoltageBattery):
            return power_w / max(1e-6, battery.discharge_efficiency)
        return power_w

    @staticmethod
    def _battery_efficiency(
        battery: Battery,
        point: BatteryPoint | None,
    ) -> float:
        if point is not None:
            return point.efficiency
        if isinstance(battery, FixedVoltageBattery):
            return battery.discharge_efficiency
        return 1.0
