#!/usr/bin/env python3
"""Run preregistered one-shot OOS validation for V2-B-LEGACY-EXP6."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase16.config import FrozenConfig
from phase16.crt_setup_v2_oos import run_oos_validation
from phase16.data_loader import load_ohlcv_csv


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = ROOT / "phase16/data/raw/nq_continuous_1m_oos_20171001_20201201.csv"
DEFAULT_PROCESSED = ROOT / "phase16/data/processed/nq_5m_oos_20171001_20201201.csv"
DEFAULT_OUTPUT = ROOT / "phase16/results/crt_setup_v2_oos"
DEFAULT_VALIDATION = DEFAULT_OUTPUT / "data_validation"

OOS_START = "2018-01-01"
OOS_END = "2020-11-30"
ACQUISITION_START = "2017-10-01"
ACQUISITION_END_EXCLUSIVE = "2020-12-01"
DEVELOPMENT_START = "2024-01-01"


def estimate_cost() -> float:
    command = [
        sys.executable,
        str(ROOT / "phase16/download_databento.py"),
        "--start",
        ACQUISITION_START,
        "--end",
        ACQUISITION_END_EXCLUSIVE,
        "--symbols",
        "NQ.v.0",
        "--dataset",
        "GLBX.MDP3",
        "--schema",
        "ohlcv-1m",
        "--estimate-only",
    ]
    output = subprocess.check_output(command, text=True)
    for line in output.splitlines():
        if "Estimated Databento cost:" in line:
            return float(line.split("$")[1].strip())
    raise RuntimeError("could not parse Databento cost estimate")


def download_raw(destination: Path, *, max_cost_usd: float) -> None:
    command = [
        sys.executable,
        str(ROOT / "phase16/download_databento.py"),
        "--start",
        ACQUISITION_START,
        "--end",
        ACQUISITION_END_EXCLUSIVE,
        "--symbols",
        "NQ.v.0",
        "--dataset",
        "GLBX.MDP3",
        "--schema",
        "ohlcv-1m",
        "--output",
        str(destination),
        "--max-cost-usd",
        str(max_cost_usd),
    ]
    subprocess.check_call(command)


def prepare_data(raw_path: Path, processed_path: Path, validation_dir: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "phase16/prepare_oos_data.py"),
        "--input",
        str(raw_path),
        "--output",
        str(processed_path),
        "--validation-dir",
        str(validation_dir),
        "--oos-start",
        OOS_START,
        "--oos-end",
        OOS_END,
        "--development-start",
        DEVELOPMENT_START,
    ]
    subprocess.check_call(command)
    validation_json = validation_dir / "data_validation.json"
    validation_md = DEFAULT_OUTPUT / "data_validation.md"
    payload = json.loads(validation_json.read_text())
    lines = [
        "# CRT Setup V2 OOS Data Validation",
        "",
        f"**OOS window:** {OOS_START} through {OOS_END} America/Chicago",
        f"**Acquisition:** {ACQUISITION_START} through {ACQUISITION_END_EXCLUSIVE} exclusive",
        f"**Development boundary:** {DEVELOPMENT_START} (no overlap permitted)",
        "",
        "## Checks",
        "",
        f"- OOS 5m bars: {payload.get('oos_5m_rows')}",
        f"- Duplicate 5m timestamps: {payload.get('duplicate_5m_rows')}",
        f"- Invalid OHLC rows: {payload.get('invalid_ohlc_rows')}",
        f"- Roll transitions: {payload.get('roll_count')}",
        f"- Development overlap rows: {payload.get('development_overlap_rows')} (must be 0)",
        "",
        "Full machine-readable validation is in `data_validation/data_validation.json`.",
    ]
    validation_md.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-prepare", action="store_true")
    parser.add_argument("--raw", default=str(DEFAULT_RAW))
    parser.add_argument("--data", default=str(DEFAULT_PROCESSED))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-cost-usd", type=float, default=10.0)
    args = parser.parse_args()

    output = Path(args.output)
    raw_path = Path(args.raw)
    processed_path = Path(args.data)
    validation_dir = output / "data_validation"

    cost = estimate_cost()
    print(f"Databento estimated cost: ${cost:.4f}")
    if cost > args.max_cost_usd:
        raise SystemExit(
            f"Estimated cost ${cost:.4f} exceeds approval cap ${args.max_cost_usd:.2f}; aborting."
        )

    if not args.skip_download:
        download_raw(raw_path, max_cost_usd=args.max_cost_usd)
    if not args.skip_prepare:
        prepare_data(raw_path, processed_path, validation_dir)

    config = FrozenConfig()
    data = load_ohlcv_csv(processed_path, exchange_timezone=config.exchange_timezone)
    validation = json.loads((validation_dir / "data_validation.json").read_text())
    manifest = run_oos_validation(
        data,
        oos_start=OOS_START,
        oos_end=OOS_END,
        output=output,
        config=config,
        databento_cost_usd=cost,
        acquisition_start=ACQUISITION_START,
        acquisition_end_exclusive=ACQUISITION_END_EXCLUSIVE,
        oos_bars=int(validation.get("oos_5m_rows", 0)),
    )
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
