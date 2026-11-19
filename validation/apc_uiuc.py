"""Accuracy of PyThrust's propeller models against UIUC wind-tunnel data for APC propellers.

For every APC propeller that the UIUC Propeller Database measured and APC publishes a geometry file
for, this compares measured thrust and power coefficients with:

- the blade-element model on APC's geometry, with NeuralFoil polars at several n_crit,
- the same with the generic section of the QPROP user guide,
- APC's own performance table.

It also solves operating points with a fixed motor and battery, taking the measured table as the
truth, to show what the coefficient errors do to RPM, current and thrust.

Usage, from the repository root:

    PYTHONPATH=. python validation/apc_uiuc.py

Downloads go to validation/.cache (not in the repository); results to validation/results and
figures to docs/images/validation.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache"
RESULTS = ROOT / "results"
FIGURES = ROOT.parent / "docs" / "images" / "validation"

UIUC = "https://m-selig.ae.illinois.edu/props"
APC_GEOMETRY = "https://www.apcprop.com/propeller-technical-data-files/{name}-PERF.PE0"
APC_PERFORMANCE = "https://www.apcprop.com/files/PER3_{name}.dat"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) PyThrust-validation"

FAMILIES = {"apce": ("E", "Thin Electric"), "apcsf": ("SF", "Slow Flyer"), "apcsp": ("", "Sport")}
N_CRITS = (3.0, 5.0, 7.0, 9.0)
RHO = 1.225
MIN_CT = 0.02
"""Forward points with less measured thrust are left out of relative errors."""


# ----------------------------------------------------------------------------- data


def fetch(url: str, path: Path) -> Path | None:
    """Download once into the cache; None if the server has no such file."""
    if path.exists():
        return path if path.stat().st_size > 0 else None
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except Exception:
        data = b""
    time.sleep(0.5)
    if url.endswith(".PE0") and b"STATION" not in data:
        data = b""
    path.write_bytes(data)
    return path if data else None


def catalog() -> list[dict]:
    """APC propellers in the UIUC database with static and forward data, and their files."""
    propellers: dict[str, dict] = {}
    for volume in (1, 2, 3, 4):
        page = fetch(f"{UIUC}/volume-{volume}/propDB-volume-{volume}.html", CACHE / "uiuc" / f"volume-{volume}.html")
        html = page.read_text(errors="ignore")
        for name in sorted(set(re.findall(r'data/(apc[a-z]*_[0-9.]+x[0-9.]+_[^"]+?)\.txt', html))):
            match = re.match(r"(apc[a-z]*)_([0-9.]+)x([0-9.]+)_(.*)", name)
            family, diameter, pitch, rest = match.groups()
            if family not in FAMILIES:
                continue
            key = f"{family}_{diameter}x{pitch}"
            entry = propellers.setdefault(
                key,
                dict(key=key, family=family, diameter_in=float(diameter), pitch_in=float(pitch),
                     static=[], forward=[], volume=volume),
            )
            url = f"{UIUC}/volume-{volume}/data/{name}.txt"
            if rest.startswith("static"):
                entry["static"].append(url)
            elif re.search(r"_\d+$", rest):
                entry["forward"].append(url)
    result = []
    for entry in propellers.values():
        if not (entry["static"] and entry["forward"]):
            continue
        suffix = FAMILIES[entry["family"]][0]
        diameter, pitch = entry["key"].split("_")[1].split("x")
        entry["apc_name"] = f"{diameter}x{pitch.replace('.', '')}{suffix}"
        result.append(entry)
    return sorted(result, key=lambda e: (e["family"], e["diameter_in"], e["pitch_in"]))


def download(entry: dict) -> dict | None:
    """Local paths of a propeller's files; None without APC's geometry and performance files."""
    folder = CACHE / "uiuc" / entry["key"]
    local = dict(entry)
    local["static"] = [str(fetch(u, folder / u.rsplit("/", 1)[1])) for u in entry["static"][:1]]
    local["forward"] = [str(p) for p in (fetch(u, folder / u.rsplit("/", 1)[1]) for u in entry["forward"]) if p]
    name = entry["apc_name"]
    pe0 = fetch(APC_GEOMETRY.format(name=name), CACHE / "apc" / f"{name}-PERF.PE0")
    per3 = fetch(APC_PERFORMANCE.format(name=name), CACHE / "apc" / f"PER3_{name}.dat")
    if pe0 is None or per3 is None or not local["forward"]:
        return None
    local["pe0"], local["per3"] = str(pe0), str(per3)
    return local


# ----------------------------------------------------------------------------- evaluation


def rows(path: str) -> list[list[float]]:
    out = []
    for line in Path(path).read_text(errors="ignore").splitlines():
        tokens = line.split()
        try:
            out.append([float(t) for t in tokens])
        except ValueError:
            continue
    return [r for r in out if r]


def models(entry: dict) -> dict:
    from pythrust.io import read_apc, read_apc_geometry
    from pythrust.propeller import BladeElementPropeller, BladeSection, apc_airfoil_polars

    generic = BladeSection(0.50, 5.8, -0.3, 1.2, 0.028, 0.050, 0.020, 0.5, 70000.0, -0.7)
    result = {"generic": BladeElementPropeller(read_apc_geometry(entry["pe0"], generic)), "apc": read_apc(entry["per3"])}
    for n_crit in N_CRITS:
        result[f"nf{n_crit:g}"] = BladeElementPropeller(read_apc_geometry(entry["pe0"], apc_airfoil_polars(n_crit)))
    return result


def coefficients(model, diameter: float, airspeed: float, rpm: float) -> tuple[float, float]:
    n = rpm / 60.0
    if hasattr(model, "get_coefficients"):  # APC's table: no extrapolation past its data.
        return model.get_coefficients(rpm, airspeed / (n * diameter))
    thrust, torque = model.thrust_torque(RHO, airspeed, rpm)
    return thrust / (RHO * n**2 * diameter**4), 2 * math.pi * torque / (RHO * n**2 * diameter**5)


def evaluate_or_report(entry: dict) -> dict:
    """``evaluate``, or the propeller's key and the error that stopped it."""
    try:
        return evaluate(entry)
    except Exception as error:  # Report and go on with the other propellers.
        return {"key": entry["key"], "error": f"{type(error).__name__}: {error}"}


def evaluate(entry: dict) -> dict:
    """Coefficient errors of every model on one propeller, and its operating points."""
    diameter = entry["diameter_in"] * 0.0254
    all_models = models(entry)
    static = rows(entry["static"][0])
    forward = []
    for path in entry["forward"]:
        rpm = float(re.search(r"_(\d+)\.txt$", path).group(1))
        forward += [(rpm, *r[:3]) for r in rows(path) if len(r) == 4]

    out = {"key": entry["key"], "family": entry["family"], "diameter_in": entry["diameter_in"],
           "pitch_in": entry["pitch_in"], "models": {}}
    for name, model in all_models.items():
        s_ct, s_cp, f_ct, f_cp, f_eta, eta_max = [], [], [], [], [], []
        for rpm, ct, cp in (r for r in static if len(r) == 3):
            m_ct, m_cp = coefficients(model, diameter, 0.0, rpm)
            if m_cp > 0:
                s_ct.append(m_ct / ct - 1)
                s_cp.append(m_cp / cp - 1)
        runs: dict[float, list] = {}
        for rpm, j, ct, cp in forward:
            m_ct, m_cp = coefficients(model, diameter, j * rpm / 60.0 * diameter, rpm)
            if not (m_cp > 0 and math.isfinite(m_ct)):
                continue
            runs.setdefault(rpm, []).append((j * ct / cp, j * m_ct / m_cp))
            if ct >= MIN_CT:
                f_ct.append(m_ct / ct - 1)
                f_cp.append(m_cp / cp - 1)
                f_eta.append(j * m_ct / m_cp - j * ct / cp)
        for points in runs.values():
            measured, modelled = zip(*points)
            eta_max.append(max(modelled) - max(measured))
        out["models"][name] = dict(static_ct=s_ct, static_cp=s_cp, forward_ct=f_ct, forward_cp=f_cp,
                                   forward_eta=f_eta, eta_max=eta_max)
    out["operating_points"] = operating_points(entry, all_models, diameter)
    return out


def operating_points(entry: dict, all_models: dict, diameter: float) -> dict:
    """RPM, current and thrust with a fixed motor and battery; the measured table is the truth."""
    from pythrust.battery import FixedVoltageBattery
    from pythrust.io import read_uiuc_performance
    from pythrust.motor import MotorSpec
    from pythrust.propulsion import PropulsionSolver, SystemSpec

    truth = read_uiuc_performance(diameter, entry["static"][0], entry["forward"])
    target = statistics.median(r[0] for r in rows(entry["static"][0]) if len(r) == 3)
    voltage = 11.1
    motor = MotorSpec(kv_rpm_per_v=1.25 * target / voltage, resistance_ohm=0.05, no_load_current_a=0.5,
                      current_max_a=1e3)
    cases = {"static": 0.0, "cruise": 0.3 * target / 60.0 * diameter}
    result = {}
    for case, airspeed in cases.items():
        def solve(propeller):
            return PropulsionSolver().solve_operating_point(
                motor=motor, battery=FixedVoltageBattery(voltage_v=voltage), system=SystemSpec(resistance_ohm=0.0),
                propeller=propeller, rho=RHO, airspeed_mps=airspeed, throttle=1.0)
        reference = solve(truth)
        if not reference.is_feasible:
            continue
        result[case] = {}
        for name, model in all_models.items():
            point = solve(model)
            if point.is_feasible:
                result[case][name] = dict(
                    rpm=point.rpm / reference.rpm - 1,
                    current=point.motor_current_a / reference.motor_current_a - 1,
                    thrust=point.thrust_n / reference.thrust_n - 1,
                )
    return result


# ----------------------------------------------------------------------------- summary


def mean_abs(values) -> float:
    return float(np.mean(np.abs(values))) if len(values) else math.nan


def summarize(results: list[dict]) -> dict:
    keys = sorted(r["key"] for r in results)
    calibration = {k for f in FAMILIES for k in [k for k in keys if k.startswith(f + "_")][::3]}
    score = {}
    for n_crit in N_CRITS:
        name = f"nf{n_crit:g}"
        score[name] = float(np.mean([
            np.mean([mean_abs(r["models"][name][q]) for q in ("static_ct", "static_cp", "forward_ct", "forward_cp")])
            for r in results if r["key"] in calibration]))
    chosen = min(score, key=score.get)
    return dict(calibration=sorted(calibration), calibration_score=score, chosen=chosen)


def main() -> None:
    sys.path.insert(0, str(ROOT.parent))
    entries = [e for e in (download(e) for e in catalog()) if e]
    print(f"{len(entries)} propellers with UIUC data and APC files", flush=True)
    with ProcessPoolExecutor() as pool:
        evaluated = list(pool.map(evaluate_or_report, entries))
    failed = [r for r in evaluated if "error" in r]
    for r in failed:
        print(f"{r['key']}: {r['error']}")
    results = [r for r in evaluated if "error" not in r]
    print(f"{len(results)} evaluated, {len(failed)} failed")
    summary = summarize(results)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "results.json").write_text(json.dumps(dict(summary=summary, propellers=results, failed=failed)))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
