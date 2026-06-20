import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pythrust.battery import BatteryState, FixedVoltageBattery, RateMapBattery
from pythrust.propellers import PropellerDatabase
from pythrust.propulsion import MotorSpec, PropellerSpec, PropulsionSolver, SystemSpec
from pythrust.propulsion.autotune import ManufacturerTestPoint, PropulsionCalibrator


IMAGE_DIR = Path("docs/images")
FIGSIZE = (9.6, 5.4)
DPI = 170

COLORS = {
    "blue": "#2563eb",
    "green": "#059669",
    "orange": "#d97706",
    "red": "#dc2626",
    "purple": "#7c3aed",
    "teal": "#0891b2",
    "ink": "#111827",
    "muted": "#6b7280",
    "grid": "#d1d5db",
    "panel": "#f8fafc",
}


def configure_style():
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#374151",
            "axes.labelcolor": COLORS["ink"],
            "axes.titlecolor": COLORS["ink"],
            "xtick.color": COLORS["ink"],
            "ytick.color": COLORS["ink"],
            "grid.color": COLORS["grid"],
            "grid.linewidth": 0.8,
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "figure.titlesize": 15,
        }
    )


def save_figure(fig, path):
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print(f"Saved: {path}")


def apply_two_panel_layout(fig):
    fig.subplots_adjust(
        left=0.09,
        right=0.90,
        bottom=0.17,
        top=0.78,
        wspace=0.48,
    )


def build_baseline_specs():
    motor = MotorSpec(
        kv_rpm_per_v=860.0,
        resistance_ohm=0.0258,
        no_load_current_a=1.3,
        current_max_a=65.0,
    )
    system = SystemSpec(resistance_ohm=0.095)
    propeller = PropellerSpec(diameter_m=0.3302)
    return motor, system, propeller


def generate_calibration_plot(prop_entry):
    print("Generating Calibration Plot...")
    motor = MotorSpec(
        kv_rpm_per_v=860.0,
        resistance_ohm=0.0258,
        no_load_current_a=1.3,
        current_max_a=65.0,
    )
    battery = FixedVoltageBattery(voltage_v=14.8)
    system = SystemSpec(resistance_ohm=0.05)
    propeller = PropellerSpec(diameter_m=0.3302)

    raw_table = [
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
        for r in raw_table
    ]

    result = PropulsionCalibrator().calibrate(
        test_points=points,
        motor=motor,
        battery=battery,
        system=system,
        propeller=propeller,
        prop_entry=prop_entry,
    )
    fitted_system = result.to_system_spec()
    solver = PropulsionSolver()

    model_rpms = np.linspace(3500, 9500, 100)
    model_thrusts_g = []
    model_currents_a = []
    for rpm in model_rpms:
        point = solver._build_point(
            motor=motor,
            battery=battery,
            system=fitted_system,
            propeller=propeller,
            prop_entry=prop_entry,
            rho=1.225,
            airspeed_mps=0.0,
            rpm=rpm,
        )
        model_thrusts_g.append(point.thrust_n * 1000.0 / 9.80665)
        model_currents_a.append(point.battery_current_a)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGSIZE)
    fig.suptitle("System Resistance Calibration", weight="bold")
    fig.text(
        0.5,
        0.91,
        f"Fitted wiring/ESC loss term: {result.system_resistance_ohm:.3f} ohm",
        ha="center",
        color=COLORS["muted"],
        fontsize=10,
    )

    ax1.plot(model_rpms, model_thrusts_g, color=COLORS["blue"], linewidth=2.2, label="PyThrust fit")
    ax1.scatter(
        [p.rpm for p in points],
        [p.thrust_g for p in points],
        color=COLORS["red"],
        s=32,
        label="test data",
        zorder=3,
    )
    ax1.set_title("Thrust match")
    ax1.set_xlabel("Shaft speed [RPM]")
    ax1.set_ylabel("Thrust [g]")
    ax1.grid(True)
    ax1.legend(frameon=False)

    ax2.plot(model_rpms, model_currents_a, color=COLORS["orange"], linewidth=2.2, label="PyThrust fit")
    ax2.scatter(
        [p.rpm for p in points],
        [p.current_a for p in points],
        color=COLORS["red"],
        s=32,
        label="test data",
        zorder=3,
    )
    ax2.set_title("Battery current match")
    ax2.set_xlabel("Shaft speed [RPM]")
    ax2.set_ylabel("Battery current [A]")
    ax2.grid(True)
    ax2.legend(frameon=False)

    apply_two_panel_layout(fig)
    save_figure(fig, IMAGE_DIR / "calibration_results.png")


def generate_propeller_plot(prop_entry):
    print("Generating Propeller Database Plot...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGSIZE)
    fig.suptitle("Empirical Propeller Database", weight="bold")
    fig.text(
        0.5,
        0.91,
        "APC 13x6.5E coefficient maps used by the operating-point solver",
        ha="center",
        color=COLORS["muted"],
        fontsize=10,
    )

    rpms = prop_entry.rpm_levels
    selected = [rpms[i] for i in [0, len(rpms) // 3, 2 * len(rpms) // 3, len(rpms) - 1] if i < len(rpms)]
    selected = sorted(set(selected))
    palette = [COLORS["blue"], COLORS["green"], COLORS["orange"], COLORS["purple"]]

    for color, rpm in zip(palette, selected):
        points = prop_entry.data_by_rpm[rpm]
        j_vals = [p.j for p in points]
        ax1.plot(j_vals, [p.ct for p in points], color=color, linewidth=2.0, label=f"{int(rpm)} RPM")
        ax2.plot(j_vals, [p.cp for p in points], color=color, linewidth=2.0, label=f"{int(rpm)} RPM")

    ax1.set_title("Thrust coefficient")
    ax1.set_xlabel("Advance ratio J")
    ax1.set_ylabel("Ct")
    ax1.grid(True)
    ax1.legend(frameon=False)

    ax2.set_title("Power coefficient")
    ax2.set_xlabel("Advance ratio J")
    ax2.set_ylabel("Cp")
    ax2.grid(True)
    ax2.legend(frameon=False)

    apply_two_panel_layout(fig)
    save_figure(fig, IMAGE_DIR / "propeller_coefficients.png")


def generate_battery_mission_plot(prop_entry):
    print("Generating Rate-Map Battery Mission Plot...")
    battery = RateMapBattery.from_json("data/batteries/example_liion_cell.json", series=4, parallel=2)
    motor, system, propeller = build_baseline_specs()
    solver = PropulsionSolver()
    state = BatteryState(soc=0.95)

    segments = [
        {"name": "takeoff", "duration_s": 45.0, "throttle": 0.70, "airspeed_mps": 0.0},
        {"name": "climb", "duration_s": 90.0, "throttle": 0.65, "airspeed_mps": 5.0},
        {"name": "cruise", "duration_s": 180.0, "throttle": 0.50, "airspeed_mps": 10.0},
        {"name": "return", "duration_s": 120.0, "throttle": 0.45, "airspeed_mps": 8.0},
    ]

    times_min = [0.0]
    soc = [state.soc]
    voltages = []
    currents = []
    c_rates = []
    labels = []
    elapsed_s = 0.0

    for segment in segments:
        point = solver.solve_operating_point(
            motor=motor,
            battery=battery,
            battery_state=state,
            system=system,
            propeller=propeller,
            prop_entry=prop_entry,
            rho=1.225,
            airspeed_mps=segment["airspeed_mps"],
            throttle=segment["throttle"],
        )
        elapsed_s += segment["duration_s"]
        state = battery.step_current(state=state, current_a=point.battery_current_a, dt_s=segment["duration_s"])
        times_min.append(elapsed_s / 60.0)
        soc.append(state.soc)
        voltages.append(point.battery_voltage_v)
        currents.append(point.battery_current_a)
        c_rates.append(point.battery_c_rate)
        labels.append(segment["name"])

    centers = [(times_min[i] + times_min[i + 1]) / 2 for i in range(len(segments))]
    widths = [times_min[i + 1] - times_min[i] for i in range(len(segments))]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGSIZE)
    fig.suptitle("Rate-Map Battery Mission Example", weight="bold")
    fig.text(
        0.5,
        0.91,
        "A short segment schedule updates battery state from solved pack current",
        ha="center",
        color=COLORS["muted"],
        fontsize=10,
    )

    ax1.plot(times_min, soc, color=COLORS["green"], marker="o", linewidth=2.3, label="SoC")
    ax1.set_title("State of charge")
    ax1.set_xlabel("Elapsed time [min]")
    ax1.set_ylabel("SoC")
    ax1.set_ylim(0.75, 0.98)
    ax1.grid(True)

    ax2.plot(
        centers,
        currents,
        color=COLORS["orange"],
        marker="o",
        linewidth=2.4,
        label="current",
    )
    ax2.set_title("Solved pack current")
    ax2.set_xlabel("Mission segment")
    ax2.set_ylabel("Battery current [A]")
    ax2.set_xticks(centers)
    ax2.set_xticklabels(labels, rotation=20, ha="right")
    ax2.grid(True)
    ax2.set_ylim(0.0, max(currents) * 1.18)
    for x, current, segment in zip(centers, currents, segments):
        ax2.text(
            x,
            current + max(currents) * 0.035,
            f"{segment['throttle'] * 100:.0f}%",
            ha="center",
            va="bottom",
            color=COLORS["muted"],
            fontsize=9,
        )

    apply_two_panel_layout(fig)
    save_figure(fig, IMAGE_DIR / "rate_map_battery_mission.png")


def generate_heatmap_plot(db):
    print("Generating Efficiency Heatmap...")
    kv_grid = np.linspace(400, 1200, 25)
    dia_grid = np.linspace(10, 18, 25)
    efficiency = np.zeros((len(dia_grid), len(kv_grid)))

    battery = FixedVoltageBattery(voltage_v=14.8)
    system = SystemSpec(resistance_ohm=0.05)
    solver = PropulsionSolver()
    target_thrust_n = 4.903

    def find_hover_throttle(motor, propeller, prop_entry):
        low, high = 0.1, 0.99
        mid = 0.5
        for _ in range(15):
            mid = (low + high) / 2.0
            point = solver.solve_operating_point(
                motor=motor,
                battery=battery,
                system=system,
                propeller=propeller,
                prop_entry=prop_entry,
                rho=1.225,
                airspeed_mps=0.0,
                throttle=mid,
            )
            residual = point.thrust_n - target_thrust_n
            if abs(residual) < 1e-3:
                break
            if residual < 0:
                low = mid
            else:
                high = mid

        point = solver.solve_operating_point(
            motor=motor,
            battery=battery,
            system=system,
            propeller=propeller,
            prop_entry=prop_entry,
            rho=1.225,
            airspeed_mps=0.0,
            throttle=mid,
        )
        return point if point.is_feasible and abs(point.thrust_n - target_thrust_n) < 0.1 else None

    for i, dia_in in enumerate(dia_grid):
        prop_entry = db.find_by_size(dia_in, pitch_in=dia_in * 0.5, blade_count=2, tolerance=2.0)
        if prop_entry is None:
            prop_entry = db.get("APC_13x6.5E")
        propeller = PropellerSpec(diameter_m=dia_in * 0.0254)

        for j, kv in enumerate(kv_grid):
            motor = MotorSpec(
                kv_rpm_per_v=kv,
                resistance_ohm=0.0258,
                no_load_current_a=1.3,
                current_max_a=65.0,
            )
            point = find_hover_throttle(motor, propeller, prop_entry)
            if point is not None and point.battery_power_w > 0:
                thrust_g = point.thrust_n * 1000.0 / 9.80665
                efficiency[i, j] = thrust_g / point.battery_power_w
            else:
                efficiency[i, j] = np.nan

    fig = plt.figure(figsize=FIGSIZE)
    ax = fig.add_axes([0.08, 0.13, 0.76, 0.70])
    contour = ax.contourf(kv_grid, dia_grid, efficiency, levels=16, cmap="viridis")
    cax = fig.add_axes([0.87, 0.13, 0.025, 0.70])
    cbar = fig.colorbar(contour, cax=cax)
    cbar.set_label("Hover efficiency [g/W]", rotation=270, labelpad=15)
    ax.set_xlabel("Motor Kv [RPM/V]")
    ax.set_ylabel("Propeller diameter [in]")
    fig.suptitle("Hover Efficiency Design Map", fontweight="bold")
    fig.text(
        0.5,
        0.91,
        "Target thrust: 500 g",
        ha="center",
        color=COLORS["muted"],
        fontsize=10,
    )
    ax.grid(True, linestyle=":", alpha=0.6)
    save_figure(fig, IMAGE_DIR / "efficiency_heatmap.png")


def main():
    configure_style()

    db_prop = PropellerDatabase()
    if not db_prop.load(Path("data/propellers/apc_202602"), strict=False):
        print("Error: Could not load propeller database.")
        sys.exit(1)

    prop_entry = db_prop.get("APC_13x6.5E")
    if prop_entry is None:
        print("Error: Propeller APC_13x6.5E not found.")
        sys.exit(1)

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    generate_battery_mission_plot(prop_entry)
    generate_calibration_plot(prop_entry)
    generate_propeller_plot(prop_entry)
    generate_heatmap_plot(db_prop)


if __name__ == "__main__":
    main()
