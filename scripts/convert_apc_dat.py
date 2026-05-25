"""Convert APC .dat propeller files to JSON metadata + CSV data."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Iterable


_INPUT_COLUMNS = [
    "V_mph",
    "J",
    "Pe",
    "Ct",
    "Cp",
    "Pwr_Hp",
    "Torque_inlb",
    "Thrust_lbf",
    "Pwr_W",
    "Torque_Nm",
    "Thrust_N",
    "Thr_Pwr_gW",
    "Mach",
    "Reyn",
    "FOM",
]

_OUTPUT_COLUMNS = [
    "rpm",
    "speed_mps",
    "advance_ratio",
    "efficiency",
    "thrust_coeff",
    "power_coeff",
    "power_w",
    "torque_nm",
    "thrust_n",
    "thrust_per_power_n_w",
    "mach",
    "reynolds",
    "figure_of_merit",
]

_MPH_TO_MPS = 0.44704

_RPM_RE = re.compile(r"PROP RPM\s*=\s*(\d+)")
_MODEL_RE = re.compile(r"(?P<diam>\d+(?:\.\d+)?)x(?P<pitch>\d+(?:\.\d+)?).*")


def _normalize_id(model: str) -> str:
    cleaned = model.strip().replace(" ", "")
    cleaned = cleaned.replace("(", "_").replace(")", "")
    cleaned = cleaned.replace("/", "_").replace("\\", "_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return f"APC_{cleaned}"


def _parse_model(line: str) -> tuple[str, float, float]:
    model = line.split("(")[0].strip()
    match = _MODEL_RE.match(model)
    if not match:
        raise ValueError(f"Could not parse model string: '{model}'")
    diameter_in = float(match.group("diam"))
    pitch_in = float(match.group("pitch"))
    return model, diameter_in, pitch_in


def _iter_data_rows(lines: Iterable[str]) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    rpm: int | None = None

    for line in lines:
        if "PROP RPM" in line:
            match = _RPM_RE.search(line)
            rpm = int(match.group(1)) if match else None
            continue

        if rpm is None:
            continue

        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("V") or "(mph)" in stripped or "Adv_Ratio" in stripped:
            continue

        parts = stripped.split()
        if len(parts) < len(_INPUT_COLUMNS):
            continue

        try:
            float(parts[0])
        except ValueError:
            continue

        values = parts[: len(_INPUT_COLUMNS)]
        row = {"rpm": float(rpm)}
        for key, token in zip(_INPUT_COLUMNS, values):
            row[key] = float(token)
        rows.append(row)

    return rows


def _convert_file(path: Path, output_dir: Path) -> int:
    lines = path.read_text(errors="ignore").splitlines()
    if not lines:
        return 0

    first_non_empty = next((ln for ln in lines if ln.strip()), "")
    if not first_non_empty:
        return 0

    model, diameter_in, pitch_in = _parse_model(first_non_empty)
    prop_id = _normalize_id(model)

    rows = _iter_data_rows(lines)
    if not rows:
        return 0

    csv_name = f"{prop_id}.csv"
    csv_path = output_dir / csv_name
    json_path = output_dir / f"{prop_id}.json"

    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_OUTPUT_COLUMNS)
        for row in rows:
            speed_mps = row["V_mph"] * _MPH_TO_MPS
            power_w = row["Pwr_W"]
            thrust_n = row["Thrust_N"]
            thrust_per_power = (thrust_n / power_w) if power_w > 0 else 0.0
            output = {
                "rpm": row["rpm"],
                "speed_mps": speed_mps,
                "advance_ratio": row["J"],
                "efficiency": row["Pe"],
                "thrust_coeff": row["Ct"],
                "power_coeff": row["Cp"],
                "power_w": power_w,
                "torque_nm": row["Torque_Nm"],
                "thrust_n": thrust_n,
                "thrust_per_power_n_w": thrust_per_power,
                "mach": row["Mach"],
                "reynolds": row["Reyn"],
                "figure_of_merit": row["FOM"],
            }
            writer.writerow([output[col] for col in _OUTPUT_COLUMNS])

    metadata = {
        "id": prop_id,
        "manufacturer": "APC",
        "model": model,
        "diameter_in": diameter_in,
        "pitch_in": pitch_in,
        "blade_count": 2,
        "data_csv": csv_name,
    }
    json_path.write_text(json.dumps(metadata, indent=2) + "\n")

    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert APC .dat files into JSON metadata and CSV data."
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing APC .dat files",
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Output directory for JSON and CSV files",
    )
    parser.add_argument(
        "--pattern",
        default="*.dat",
        help="Glob pattern for input files (default: *.dat)",
    )

    args = parser.parse_args()
    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir

    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    total_files = 0
    total_rows = 0
    for path in sorted(input_dir.glob(args.pattern)):
        if not path.is_file():
            continue
        row_count = _convert_file(path, output_dir)
        if row_count > 0:
            total_files += 1
            total_rows += row_count

    print(f"Converted {total_files} files with {total_rows} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
