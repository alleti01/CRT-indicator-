#!/usr/bin/env python3
"""Recompute known_at_bar_offset from Pine GLD chart export (Part B)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from signal_ledger.gate_evaluator import (
    compute_known_at_offsets,
    compute_pivot_confirmation_offsets,
    write_known_at_offsets_csv,
)
from signal_ledger.gate_export import load_tv_gate_export


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Recompute gate known_at_bar_offset from TV GLD export")
    p.add_argument("--gate-export", type=Path, required=True)
    p.add_argument("--out-csv", type=Path, default=Path("signal_ledger/output/GATE_KNOWN_AT_OFFSETS.csv"))
    p.add_argument("--out-json", type=Path, default=Path("signal_ledger/output/PIVOT_LAG_CHECK.json"))
    args = p.parse_args(argv)

    df = load_tv_gate_export(args.gate_export)
    offsets = compute_known_at_offsets(df)
    pivot = compute_pivot_confirmation_offsets(df)

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    write_known_at_offsets_csv(offsets, args.out_csv)
    args.out_json.write_text(json.dumps(pivot, indent=2))

    print(f"Wrote {len(offsets)} gate offsets → {args.out_csv}")
    print(f"Pivot lag check → {args.out_json} confirmed={pivot.get('confirmed')}")
    print("trust_status=PENDING_REPLAY_CONFIRMATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
