"""OpenMDAO hover co-design optimization and Kv sweep.

This example optimizes motor Kv, propeller diameter, and throttle for a fixed
hover thrust, then sweeps Kv to show the design trend.

Usage::

    PYTHONPATH=. python examples/openmdao_hover_optimization.py
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import openmdao.api as om

from pythrust.openmdao import PropulsionComponent
from pythrust.propellers import PropellerDatabase


def main():
    # 1. Load propeller aerodynamic data.
    db = PropellerDatabase()
    db.load(Path("data/propellers/apc_202602"), strict=False)
    prop_entry = db.get("APC_13x6.5E")
    if prop_entry is None:
        print("Error: Propeller 'APC_13x6.5E' not found.")
        sys.exit(1)

    # 2. Set up the baseline optimization problem.
    prob = om.Problem()
    model = prob.model

    comp = PropulsionComponent(prop_entry=prop_entry)
    model.add_subsystem("prop", comp, promotes=["*"])

    model.add_design_var("kv_rpm_per_v", lower=600.0, upper=1200.0, ref=1000.0)
    model.add_design_var("diameter_m", lower=0.254, upper=0.381, ref=0.3)
    model.add_design_var("throttle", lower=0.2, upper=0.9, ref=0.5)

    model.add_constraint("thrust_n", equals=4.903, ref=5.0)
    model.add_constraint("motor_current_a", upper=25.0, ref=25.0)
    model.add_objective("battery_power_w", ref=100.0)

    prob.driver = om.ScipyOptimizeDriver(optimizer="SLSQP")
    prob.driver.options["disp"] = False
    prob.setup()

    prob.set_val("kv_rpm_per_v", 860.0)
    prob.set_val("resistance_ohm", 0.0258)
    prob.set_val("no_load_current_a", 1.3)
    prob.set_val("current_max_a", 65.0)
    prob.set_val("voltage_v", 14.8)
    prob.set_val("resistance_system_ohm", 0.095)
    prob.set_val("diameter_m", 0.3302)
    prob.set_val("throttle", 0.5)
    prob.set_val("rho", 1.225)
    prob.set_val("airspeed_mps", 0.0)

    print("=== Running Baseline Model ===")
    prob.run_model()
    base_kv = float(prob.get_val("kv_rpm_per_v")[0])
    base_dia = float(prob.get_val("diameter_m")[0]) * 39.3701
    base_power = float(prob.get_val("battery_power_w")[0])
    base_throttle = float(prob.get_val("throttle")[0]) * 100.0
    base_rpm = float(prob.get_val("rpm")[0])
    print(f"  Motor Kv          : {base_kv:.1f} RPM/V")
    print(f"  Propeller Diameter: {base_dia:.2f} inches")
    print(f"  Hover Throttle    : {base_throttle:.1f}%")
    print(f"  Hover Shaft Speed : {base_rpm:.0f} RPM")
    print(f"  Battery Power Draw: {base_power:.2f} W")

    print("\n=== Running Co-Design Optimization ===")
    prob.run_driver()
    opt_kv = float(prob.get_val("kv_rpm_per_v")[0])
    opt_dia = float(prob.get_val("diameter_m")[0]) * 39.3701
    opt_power = float(prob.get_val("battery_power_w")[0])
    opt_throttle = float(prob.get_val("throttle")[0]) * 100.0
    opt_rpm = float(prob.get_val("rpm")[0])
    print(f"  Optimal Motor Kv    : {opt_kv:.1f} RPM/V")
    print(f"  Optimal Diameter    : {opt_dia:.2f} inches")
    print(f"  Optimal Throttle    : {opt_throttle:.1f}%")
    print(f"  Optimal Shaft Speed : {opt_rpm:.0f} RPM")
    print(f"  Minimum Power Draw  : {opt_power:.2f} W")
    print(f"  Power Reduction     : {base_power - opt_power:.2f} W ({(base_power - opt_power)/base_power*100:.1f}%)")

    # 3. Sweep Kv and re-optimize diameter/throttle at each point.
    print("\n=== Performing Kv Parametric Sweep ===")
    kv_sweep = np.linspace(600, 1200, 13)
    power_draws = []
    optimal_diameters = []
    optimal_throttles = []
    optimal_rpms = []

    sweep_prob = om.Problem()
    sweep_model = sweep_prob.model
    sweep_model.add_subsystem("prop", PropulsionComponent(prop_entry=prop_entry), promotes=["*"])
    sweep_model.add_design_var("diameter_m", lower=0.254, upper=0.381, ref=0.3)
    sweep_model.add_design_var("throttle", lower=0.2, upper=0.9, ref=0.5)
    sweep_model.add_constraint("thrust_n", equals=4.903, ref=5.0)
    sweep_model.add_objective("battery_power_w", ref=100.0)
    sweep_prob.driver = om.ScipyOptimizeDriver(optimizer="SLSQP")
    sweep_prob.driver.options["disp"] = False
    sweep_prob.setup()

    sweep_prob.set_val("resistance_ohm", 0.0258)
    sweep_prob.set_val("no_load_current_a", 1.3)
    sweep_prob.set_val("current_max_a", 65.0)
    sweep_prob.set_val("voltage_v", 14.8)
    sweep_prob.set_val("resistance_system_ohm", 0.095)
    sweep_prob.set_val("rho", 1.225)
    sweep_prob.set_val("airspeed_mps", 0.0)

    for temp_kv in kv_sweep:
        sweep_prob.set_val("kv_rpm_per_v", temp_kv)
        sweep_prob.set_val("diameter_m", 0.3302)
        sweep_prob.set_val("throttle", 0.5)
        sweep_prob.run_driver()

        power = float(sweep_prob.get_val("battery_power_w")[0])
        dia = float(sweep_prob.get_val("diameter_m")[0]) * 39.3701
        thr = float(sweep_prob.get_val("throttle")[0]) * 100.0
        rpm = float(sweep_prob.get_val("rpm")[0])

        power_draws.append(power)
        optimal_diameters.append(dia)
        optimal_throttles.append(thr)
        optimal_rpms.append(rpm)

    # 4. Plot optimization trends.
    fig, (ax1, ax3) = plt.subplots(1, 2, figsize=(12, 5))

    # Left plot: Power and Diameter vs Motor Kv
    ax1.grid(True)
    ax1.set_xlabel('Motor Kv (RPM/V)')
    ax1.set_ylabel('Hover Battery Power (W)', color='C0')
    ax1.plot(kv_sweep, power_draws, color='C0', marker='o', label='Power (W)')
    ax1.tick_params(axis='y', labelcolor='C0')
    
    # Highlight the global optimum found in step 2
    ax1.plot(opt_kv, opt_power, marker='*', color='red', markersize=12, label='Global Optimum')

    ax2 = ax1.twinx()
    ax2.set_ylabel('Optimal Propeller Diameter (in)', color='C1')
    ax2.plot(kv_sweep, optimal_diameters, color='C1', marker='s', linestyle='--', label='Diameter (in)')
    ax2.tick_params(axis='y', labelcolor='C1')

    ax1.set_title('Power and Propeller Size vs Motor Kv')

    # Right plot: Throttle and RPM vs Motor Kv
    ax3.grid(True)
    ax3.set_xlabel('Motor Kv (RPM/V)')
    ax3.set_ylabel('Hover Throttle (%)', color='C2')
    ax3.plot(kv_sweep, optimal_throttles, color='C2', marker='^', label='Throttle (%)')
    ax3.tick_params(axis='y', labelcolor='C2')

    ax4 = ax3.twinx()
    ax4.set_ylabel('Hover RPM', color='C4')
    ax4.plot(kv_sweep, optimal_rpms, color='C4', marker='d', linestyle='--', label='RPM')
    ax4.tick_params(axis='y', labelcolor='C4')

    ax3.set_title('Throttle and RPM vs Motor Kv')

    fig.suptitle('Propulsion Co-Design Optimization', fontsize=14)
    plt.tight_layout()
    
    output_image = Path("docs/images/optimize_and_plot_results.png")
    plt.savefig(output_image, bbox_inches="tight")
    print(f"\nSaved default style plot to: {output_image.resolve()}")
    
if __name__ == "__main__":
    main()
