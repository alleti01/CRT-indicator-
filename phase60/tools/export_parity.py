#!/usr/bin/env python3
"""Export Phase60 parity reference trades for Python ↔ Pine validation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase60.python.arrays import build_mtf_arrays_phase60

OUT = ROOT / "phase60" / "diagnostics" / "parity"
CANON = ROOT / "phase60" / "diagnostics" / "cache" / "canon_full_phase60.parquet"


def _pick(df: pd.DataFrame, n: int, **filters) -> pd.DataFrame:
    sub = df.copy()
    for k, v in filters.items():
        col = k if k in sub.columns else f"{k}_d58"
        if col in sub.columns:
            sub = sub[sub[col] == v]
    return sub.head(n)


def export_references() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    if not CANON.exists():
        return {"error": "Run phase60/tools/run_phase60.py first"}

    canon = pd.read_parquet(CANON)
    m = build_mtf_arrays_phase60()
    dev = m.phase60

    positive = []
    for direction, outcome, n in [
        ("LONG", "TARGET", 10),
        ("LONG", "STOP", 10),
        ("SHORT", "TARGET", 10),
        ("SHORT", "STOP", 10),
    ]:
        pool = canon[(canon["direction_d58"] == direction) & (canon["m1_outcome"] == outcome)]
        pool = pool.sample(min(n, len(pool)), random_state=42) if len(pool) > n else pool
        positive.append(pool)

    pos = pd.concat(positive).drop_duplicates(subset=["entry_ts"])
    rows = []
    for _, t in pos.iterrows():
        si = int(t.get("signal_m1_i", t["entry_i_d58"] - 1))
        rows.append(
            {
                "trade_id": t["trade_id"],
                "opportunity_ts": str(m.m1_idx[si]),
                "take_ts": str(m.m1_idx[si]),
                "entry_ts": str(t["entry_ts"]),
                "direction": t["direction_d58"],
                "entry_price": float(t.get("entry_price_m1", t.get("entry_price_d58", 0))),
                "outcome": t["m1_outcome"],
                "net_R": float(t["net_R_m1"]),
                "m5_O": float(dev.m5_dev_op[si]),
                "m5_H": float(dev.m5_dev_hi[si]),
                "m5_L": float(dev.m5_dev_lo[si]),
                "m5_C": float(dev.m5_dev_cl[si]),
                "m15_O": float(dev.m15_dev_op[si]),
                "m15_H": float(dev.m15_dev_hi[si]),
                "m15_L": float(dev.m15_dev_lo[si]),
                "m15_C": float(dev.m15_dev_cl[si]),
            }
        )

    pos_path = OUT / "phase60_positive_references.csv"
    pd.DataFrame(rows).to_csv(pos_path, index=False)

    manifest = {
        "positive_count": len(rows),
        "negative_count": 0,
        "note": "Negative references require decision stream export — extend with Phase58D shadow rows.",
        "positive_path": str(pos_path),
    }
    (OUT / "parity_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    print(json.dumps(export_references(), indent=2))
