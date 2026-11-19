"""Tables and figures from validation/results/results.json (written by apc_uiuc.py).

    PYTHONPATH=. python validation/report.py

Prints Markdown tables; writes figures to docs/images/validation.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parent
FIGURES = ROOT.parent / "docs" / "images" / "validation"
QUANTITIES = [
    ("static_ct", "Static $C_T$", "%"),
    ("static_cp", "Static $C_P$", "%"),
    ("forward_ct", "Forward $C_T$", "%"),
    ("forward_cp", "Forward $C_P$", "%"),
    ("forward_eta", "Forward efficiency", "pt"),
]
FAMILY_NAMES = {"apce": "Thin Electric", "apcsf": "Slow Flyer", "apcsp": "Sport"}
COLORS = {"generic": "#adb5bd", "nf9": "#f4a261", "chosen": "#d1495b", "apc": "#2e86ab"}


def load():
    data = json.loads((ROOT / "results" / "results.json").read_text())
    return data["summary"], data["propellers"]


def labels(summary):
    chosen = summary["chosen"]
    return {
        "generic": "Generic section",
        "nf9": "NeuralFoil, n_crit 9",
        chosen: f"NeuralFoil, n_crit {chosen[2:]}",
        "apc": "APC table",
    }


def per_propeller(results, model, quantity, signed=False):
    """One number per propeller: the mean (absolute or signed) error, in % or efficiency points."""
    values = []
    for r in results:
        errors = r["models"][model][quantity]
        if errors:
            values.append(100 * (np.mean(errors) if signed else np.mean(np.abs(errors))))
    return np.array(values)


def table(results, models, names, title, signed=False):
    lines = [f"\n{title}\n", "| Model | " + " | ".join(q[1] for q in QUANTITIES) + " |",
             "|---|" + "---:|" * len(QUANTITIES)]
    for model in models:
        cells = []
        for quantity, _, unit in QUANTITIES:
            v = per_propeller(results, model, quantity, signed)
            cells.append(f"{np.mean(v):+.1f}" if signed else f"{np.mean(v):.1f}")
        lines.append(f"| {names[model]} | " + " | ".join(cells) + " |")
    print("\n".join(lines))


def main():
    summary, results = load()
    chosen = summary["chosen"]
    names = labels(summary)
    models = ["generic", "nf9", chosen, "apc"] if chosen != "nf9" else ["generic", chosen, "apc"]
    test = [r for r in results if r["key"] not in summary["calibration"]]
    FIGURES.mkdir(parents=True, exist_ok=True)

    print(f"{len(results)} propellers; n_crit calibrated on {len(summary['calibration'])}, tested on {len(test)}.")
    print("Calibration score (mean of the four coefficient errors):",
          {k: round(100 * v, 2) for k, v in summary["calibration_score"].items()}, "-> chosen", chosen)
    table(test, models, names, "Test set, mean absolute error per propeller (% ; efficiency in points)")
    table(test, models, names, "Test set, mean signed error (bias)", signed=True)
    for family, family_name in FAMILY_NAMES.items():
        subset = [r for r in test if r["family"] == family]
        table(subset, models, names, f"{family_name} ({len(subset)} propellers), mean absolute error")

    # Operating points.
    print("\nOperating points (test set), mean absolute error in % against the measured table:")
    for case in ("static", "cruise"):
        for model in models:
            cells = []
            for q in ("rpm", "current", "thrust"):
                v = [100 * abs(r["operating_points"][case][model][q]) for r in test
                     if case in r["operating_points"] and model in r["operating_points"][case]]
                cells.append(f"{q} {np.mean(v):.1f}% (n={len(v)})")
            print(f"  {case:6s} {names[model]:22s} " + ", ".join(cells))

    # Geometry check.
    checks = [r for r in results if r["geometry_check"]]
    d_beta = np.array([c["geometry_check"]["beta_uiuc_deg"] - c["geometry_check"]["beta_apc_deg"] for c in checks])
    d_chord = np.array([c["geometry_check"]["chord_uiuc"] / c["geometry_check"]["chord_apc"] - 1 for c in checks])
    print(f"\nGeometry at 0.75 R, UIUC minus APC ({len(checks)} propellers): beta median {np.median(d_beta):+.2f} deg,"
          f" range {d_beta.min():+.2f}..{d_beta.max():+.2f}; chord median {100*np.median(d_chord):+.1f}%,"
          f" range {100*d_chord.min():+.1f}..{100*d_chord.max():+.1f}%")

    figure_errors(test, models, names, chosen)
    figure_bias_by_size(test, names, chosen)
    figure_operating_points(test, models, names, chosen)
    figure_geometry(checks, d_beta, d_chord)


def color(model, chosen):
    return COLORS["chosen" if model == chosen else model]


def figure_errors(test, models, names, chosen):
    fig, axes = plt.subplots(1, len(QUANTITIES), figsize=(20, 4.6))
    for ax, (quantity, title, unit) in zip(axes, QUANTITIES):
        data = [per_propeller(test, m, quantity) for m in models]
        box = ax.boxplot(data, patch_artist=True, showfliers=True, widths=0.6)
        for patch, m in zip(box["boxes"], models):
            patch.set_facecolor(color(m, chosen))
            patch.set_alpha(0.8)
        ax.set_xticks(range(1, len(models) + 1), [names[m].replace(", ", "\n") for m in models], fontsize=8)
        ax.set_title(title)
        ax.set_ylabel("error per propeller, " + ("%" if unit == "%" else "points"))
        ax.grid(alpha=0.3, axis="y")
    fig.suptitle(f"Mean absolute error per propeller, {len(test)} APC propellers not used to choose n_crit", fontsize=13)
    fig.tight_layout()
    fig.savefig(FIGURES / "errors.png", dpi=100)


def figure_bias_by_size(test, names, chosen):
    fig, axes = plt.subplots(1, 4, figsize=(20, 4.6))
    markers = {"apce": "o", "apcsf": "s", "apcsp": "^"}
    for ax, (quantity, title, _) in zip(axes, QUANTITIES[:4]):
        for model in (chosen, "apc"):
            for family, marker in markers.items():
                subset = [r for r in test if r["family"] == family and r["models"][model][quantity]]
                ax.scatter([r["diameter_in"] for r in subset],
                           [100 * np.mean(r["models"][model][quantity]) for r in subset],
                           marker=marker, color=color(model, chosen), alpha=0.75, s=28,
                           label=f"{names[model]}, {FAMILY_NAMES[family]}")
        ax.axhline(0, color="#222", lw=0.8)
        ax.set_title(title + ": signed error")
        ax.set_xlabel("diameter, in")
        ax.set_ylabel("%")
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=7)
    fig.suptitle("Bias by propeller size and family", fontsize=13)
    fig.tight_layout()
    fig.savefig(FIGURES / "bias_by_size.png", dpi=100)


def figure_operating_points(test, models, names, chosen):
    fig, axes = plt.subplots(1, 4, figsize=(20, 4.6))
    panels = [("static", "current"), ("static", "thrust"), ("cruise", "current"), ("cruise", "thrust")]
    for ax, (case, q) in zip(axes, panels):
        data = [[100 * r["operating_points"][case][m][q] for r in test
                 if case in r["operating_points"] and m in r["operating_points"][case]] for m in models]
        box = ax.boxplot(data, patch_artist=True, widths=0.6)
        for patch, m in zip(box["boxes"], models):
            patch.set_facecolor(color(m, chosen))
            patch.set_alpha(0.8)
        ax.axhline(0, color="#222", lw=0.8)
        ax.set_xticks(range(1, len(models) + 1), [names[m].replace(", ", "\n") for m in models], fontsize=8)
        ax.set_title(f"{case.capitalize()} {q}: signed error")
        ax.set_ylabel("%")
        ax.grid(alpha=0.3, axis="y")
    fig.suptitle("Operating point with a fixed motor and battery, against the measured table", fontsize=13)
    fig.tight_layout()
    fig.savefig(FIGURES / "operating_points.png", dpi=100)


def figure_geometry(checks, d_beta, d_chord):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].hist(d_beta, bins=15, color="#2e86ab", alpha=0.85)
    axes[0].set_title("Blade angle at 0.75 R: UIUC − APC file")
    axes[0].set_xlabel("deg")
    axes[1].hist(100 * d_chord, bins=15, color="#2a9d8f", alpha=0.85)
    axes[1].set_title("Chord at 0.75 R: UIUC / APC file − 1")
    axes[1].set_xlabel("%")
    for ax in axes:
        ax.grid(alpha=0.3)
    fig.suptitle(f"Measured (UIUC) and current APC geometry, {len(checks)} propellers", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIGURES / "geometry.png", dpi=100)


if __name__ == "__main__":
    main()
