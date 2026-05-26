import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pythrust.propellers import PropellerDatabase
from pythrust.propulsion import (
    BatterySpec,
    MotorSpec,
    PropellerSpec,
    SystemSpec,
    PropulsionSolver,
)
from pythrust.propulsion.autotune import ManufacturerTestPoint, PropulsionCalibrator

def generate_calibration_plot(db, prop_entry):
    print("Generating Calibration Plot...")
    
    motor = MotorSpec(
        kv_rpm_per_v=860.0,
        resistance_ohm=0.0258,
        no_load_current_a=1.3,
        current_max_a=65.0,
    )
    battery = BatterySpec(voltage_v=14.8)
    system = SystemSpec(resistance_ohm=0.05)
    propeller = PropellerSpec(diameter_m=0.3302)
    
    RAW_TABLE = [
        {"rpm": 3897, "thrust_g": 500, "current_a": 3.9},
        {"rpm": 4804, "thrust_g": 750, "current_a": 6.7},
        {"rpm": 5421, "thrust_g": 1000, "current_a": 10.2},
        {"rpm": 6071, "thrust_g": 1250, "current_a": 13.9},
        {"rpm": 6564, "thrust_g": 1500, "current_a": 18.1},
        {"rpm": 7077, "thrust_g": 1750, "current_a": 22.6},
        {"rpm": 7560, "thrust_g": 2000, "current_a": 27.6},
        {"rpm": 8016, "thrust_g": 2250, "current_a": 33.5},
        {"rpm": 8346, "thrust_g": 2500, "current_a": 40.1},
        {"rpm": 8695, "thrust_g": 2750, "current_a": 47.5},
        {"rpm": 9230, "thrust_g": 3350, "current_a": 63.2},
    ]
    
    points = [
        ManufacturerTestPoint(rpm=r["rpm"], thrust_g=r["thrust_g"], current_a=r["current_a"])
        for r in RAW_TABLE
    ]
    
    calibrator = PropulsionCalibrator()
    result = calibrator.calibrate(
        test_points=points,
        motor=motor,
        battery=battery,
        system=system,
        propeller=propeller,
        prop_entry=prop_entry,
    )
    fitted_system = result.to_system_spec()
    
    solver = PropulsionSolver()
    
    # Generate smooth fitted predictions
    model_rpms = np.linspace(3500, 9500, 100)
    model_thrusts_g = []
    model_currents_a = []
    
    for rpm in model_rpms:
        pt = solver._build_point(
            motor=motor,
            battery=battery,
            system=fitted_system,
            propeller=propeller,
            prop_entry=prop_entry,
            rho=1.225,
            airspeed_mps=0.0,
            rpm=rpm
        )
        model_thrusts_g.append(pt.thrust_n * 1000.0 / 9.80665)
        model_currents_a.append(pt.battery_power_w / battery.voltage_v)
        
    # Plotting
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    
    # Left subplot: Thrust vs RPM
    ax1.plot(model_rpms, model_thrusts_g, color='C0', label='Fitted Model')
    ax1.scatter([p.rpm for p in points], [p.thrust_g for p in points], color='red', marker='o', label='Datasheet')
    ax1.set_xlabel('RPM')
    ax1.set_ylabel('Thrust (g)')
    ax1.set_title('Thrust vs RPM')
    ax1.grid(True)
    ax1.legend()
    
    # Right subplot: Current vs RPM
    ax2.plot(model_rpms, model_currents_a, color='C1', label='Fitted Model')
    ax2.scatter([p.rpm for p in points], [p.current_a for p in points], color='red', marker='o', label='Datasheet')
    ax2.set_xlabel('RPM')
    ax2.set_ylabel('Current (A)')
    ax2.set_title('Current vs RPM')
    ax2.grid(True)
    ax2.legend()
    
    fig.suptitle('Propulsion Calibration & Auto-Tuning Results', fontsize=14)
    plt.tight_layout()
    
    out_path = Path("docs/images/calibration_results.png")
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {out_path}")

def generate_propeller_plot(prop_entry):
    print("Generating Propeller Coefficients Plot...")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    
    # Plot Ct and Cp vs J for a few RPM bands
    rpms = prop_entry.rpm_levels
    # Pick a few evenly spaced RPM bands
    selected_rpms = [rpms[i] for i in [0, len(rpms)//3, 2*len(rpms)//3, len(rpms)-1] if i < len(rpms)]
    selected_rpms = sorted(list(set(selected_rpms)))
    
    for rpm in selected_rpms:
        points = prop_entry.data_by_rpm[rpm]
        j_vals = [p.j for p in points]
        ct_vals = [p.ct for p in points]
        cp_vals = [p.cp for p in points]
        
        ax1.plot(j_vals, ct_vals, label=f'{int(rpm)} RPM')
        ax2.plot(j_vals, cp_vals, label=f'{int(rpm)} RPM')
        
    ax1.set_xlabel('Advance Ratio (J)')
    ax1.set_ylabel('Thrust Coefficient (Ct)')
    ax1.set_title('Ct vs J')
    ax1.grid(True)
    ax1.legend()
    
    ax2.set_xlabel('Advance Ratio (J)')
    ax2.set_ylabel('Power Coefficient (Cp)')
    ax2.set_title('Cp vs J')
    ax2.grid(True)
    ax2.legend()
    
    fig.suptitle('Propeller Aerodynamic Coefficients (APC 13x6.5E)', fontsize=14)
    plt.tight_layout()
    
    out_path = Path("docs/images/propeller_coefficients.png")
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {out_path}")

def generate_heatmap_plot(db):
    print("Generating Efficiency Heatmap...")
    
    # Set up a grid of Motor Kv vs Propeller Diameter
    kv_grid = np.linspace(400, 1200, 25)
    dia_grid = np.linspace(10, 18, 25) # in inches
    
    Z_eff = np.zeros((len(dia_grid), len(kv_grid)))
    
    battery = BatterySpec(voltage_v=14.8)
    system = SystemSpec(resistance_ohm=0.05)
    solver = PropulsionSolver()
    
    # Target 500 grams of thrust (4.903 N)
    target_thrust_n = 4.903
    
    def find_hover_throttle(motor, propeller, prop_entry):
        def residual(throttle):
            pt = solver.solve_operating_point(
                motor=motor, battery=battery, system=system,
                propeller=propeller, prop_entry=prop_entry,
                rho=1.225, airspeed_mps=0.0, throttle=throttle
            )
            if not pt.is_feasible:
                # Retain directionality
                return pt.thrust_n - target_thrust_n
            return pt.thrust_n - target_thrust_n
        
        # Binary search for throttle
        low, high = 0.1, 0.99
        for _ in range(15):
            mid = (low + high) / 2.0
            res = residual(mid)
            if abs(res) < 1e-3:
                break
            if res < 0:
                low = mid
            else:
                high = mid
        
        pt = solver.solve_operating_point(
            motor=motor, battery=battery, system=system,
            propeller=propeller, prop_entry=prop_entry,
            rho=1.225, airspeed_mps=0.0, throttle=mid
        )
        return pt if (pt.is_feasible and abs(pt.thrust_n - target_thrust_n) < 0.1) else None

    for i, dia_in in enumerate(dia_grid):
        # Retrieve the propeller entry closest to this size
        prop_entry = db.find_by_size(dia_in, pitch_in=dia_in * 0.5, blade_count=2, tolerance=2.0)
        if prop_entry is None:
            # Fallback to standard 13x6.5E
            prop_entry = db.get("APC_13x6.5E")
            
        propeller = PropellerSpec(diameter_m=dia_in * 0.0254)
        
        for j, kv in enumerate(kv_grid):
            motor = MotorSpec(
                kv_rpm_per_v=kv,
                resistance_ohm=0.0258,
                no_load_current_a=1.3,
                current_max_a=65.0
            )
            
            pt = find_hover_throttle(motor, propeller, prop_entry)
            if pt is not None and pt.battery_power_w > 0:
                thrust_g = pt.thrust_n * 1000.0 / 9.80665
                Z_eff[i, j] = thrust_g / pt.battery_power_w # g/W
            else:
                Z_eff[i, j] = np.nan
                
    # Plotting
    plt.figure(figsize=(7.5, 5.5))
    cp = plt.contourf(kv_grid, dia_grid, Z_eff, levels=15, cmap='viridis')
    cbar = plt.colorbar(cp)
    cbar.set_label('Hover Efficiency (g/W)', rotation=270, labelpad=15)
    
    plt.xlabel('Motor Kv (RPM/V)')
    plt.ylabel('Propeller Diameter (in)')
    plt.title('Propulsion Hover Efficiency Map (at 500g Thrust)')
    plt.grid(True, linestyle=':', alpha=0.6)
    
    out_path = Path("docs/images/efficiency_heatmap.png")
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {out_path}")

def main():
    # Load databases
    db_prop = PropellerDatabase()
    if not db_prop.load(Path("data/propellers/apc_202602"), strict=False):
        print("Error: Could not load propeller database.")
        sys.exit(1)
        
    prop_entry = db_prop.get("APC_13x6.5E")
    if prop_entry is None:
        print("Error: Propeller APC_13x6.5E not found.")
        sys.exit(1)
        
    # Ensure docs/images directory exists
    Path("docs/images").mkdir(parents=True, exist_ok=True)
    
    generate_calibration_plot(db_prop, prop_entry)
    generate_propeller_plot(prop_entry)
    generate_heatmap_plot(db_prop)

if __name__ == '__main__':
    main()
