"""OpenMDAO wrapper component for PyThrust propulsion solver."""

from __future__ import annotations

import math
import openmdao.api as om

from pythrust.propellers.database import PropellerEntry
from pythrust.propulsion import (
    BatterySpec,
    MotorSpec,
    PropellerSpec,
    PropulsionSolver,
    SystemSpec,
)


class PropulsionComponent(om.ExplicitComponent):
    """OpenMDAO ExplicitComponent wrapping the PyThrust propulsion solver."""

    def initialize(self) -> None:
        self.options.declare(
            'prop_entry',
            types=PropellerEntry,
            desc='PropellerEntry database object',
        )

    def setup(self) -> None:
        # Inputs
        self.add_input('kv_rpm_per_v', val=860.0, desc='Motor Kv [RPM/V]')
        self.add_input('resistance_ohm', val=0.0258, desc='Motor winding resistance [ohm]')
        self.add_input('no_load_current_a', val=1.3, desc='Motor no-load current [A]')
        self.add_input('current_max_a', val=65.0, desc='Motor maximum current [A]')

        self.add_input('voltage_v', val=14.8, desc='Battery pack voltage [V]')
        self.add_input('discharge_efficiency', val=1.0, desc='Battery discharge efficiency')

        self.add_input('resistance_system_ohm', val=0.095, desc='Lumped system transmission resistance [ohm]')
        self.add_input('diameter_m', val=0.3302, desc='Propeller diameter [m]')
        self.add_input('throttle', val=0.7, desc='Throttle fraction [0, 1]')

        self.add_input('rho', val=1.225, desc='Air density [kg/m^3]')
        self.add_input('airspeed_mps', val=0.0, desc='Flight airspeed [m/s]')

        # Outputs
        self.add_output('rpm', val=5000.0, desc='Equilibrium shaft speed [RPM]')
        self.add_output('thrust_n', val=10.0, desc='Generated static/dynamic thrust [N]')
        self.add_output('torque_nm', val=0.2, desc='Propeller shaft torque [N-m]')
        self.add_output('battery_current_a', val=15.0, desc='Battery DC current draw [A]')
        self.add_output('battery_power_w', val=220.0, desc='Battery power consumption [W]')
        self.add_output('motor_current_a', val=15.0, desc='Motor winding current [A]')
        self.add_output('motor_voltage_v', val=12.0, desc='Motor terminal voltage [V]')
        self.add_output('is_feasible', val=1.0, desc='1.0 if feasible, 0.0 otherwise')

        # Declare derivatives using finite-difference
        self.declare_partials(of='*', wrt='*', method='fd')

    def _get_specs(self, inputs: om.Vector) -> tuple[MotorSpec, BatterySpec, SystemSpec, PropellerSpec]:
        motor = MotorSpec(
            kv_rpm_per_v=float(inputs['kv_rpm_per_v'][0]),
            resistance_ohm=float(inputs['resistance_ohm'][0]),
            no_load_current_a=float(inputs['no_load_current_a'][0]),
            current_max_a=float(inputs['current_max_a'][0]),
        )
        battery = BatterySpec(
            voltage_v=float(inputs['voltage_v'][0]),
            discharge_efficiency=float(inputs['discharge_efficiency'][0]),
        )
        system = SystemSpec(
            resistance_ohm=float(inputs['resistance_system_ohm'][0]),
        )
        propeller = PropellerSpec(
            diameter_m=float(inputs['diameter_m'][0]),
        )
        return motor, battery, system, propeller

    def compute(self, inputs: om.Vector, outputs: om.Vector) -> None:
        motor, battery, system, propeller = self._get_specs(inputs)
        prop_entry = self.options['prop_entry']
        throttle = float(inputs['throttle'][0])
        rho = float(inputs['rho'][0])
        airspeed_mps = float(inputs['airspeed_mps'][0])

        solver = PropulsionSolver()
        op = solver.solve_operating_point(
            motor=motor,
            battery=battery,
            system=system,
            propeller=propeller,
            prop_entry=prop_entry,
            rho=rho,
            airspeed_mps=airspeed_mps,
            throttle=throttle,
        )

        outputs['rpm'] = op.rpm
        outputs['thrust_n'] = op.thrust_n
        outputs['torque_nm'] = op.torque_nm
        outputs['battery_current_a'] = op.battery_power_w / max(1e-6, battery.voltage_v)
        outputs['battery_power_w'] = op.battery_power_w
        outputs['motor_current_a'] = op.motor_current_a
        outputs['motor_voltage_v'] = op.motor_voltage_v
        outputs['is_feasible'] = 1.0 if op.is_feasible else 0.0
