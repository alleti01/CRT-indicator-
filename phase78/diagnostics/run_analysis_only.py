#!/usr/bin/env python3
"""Re-run Phase78 analysis gates from cached entries (no rescan)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase78.python.analysis import deterministic_flip, directional_gate, random_directions  # noqa: E402
from phase78.python.config import REPORTS  # noqa: E402
from phase78.python.data_loader import load_nq_1m  # noqa: E402
from phase78.python.paths import _slice_by_time, first_passage_r_arrays, risk_points, symmetric_stop  # noqa: E402


def main() -> None:
    df = load_nq_1m()
    entries = pd.read_parquet(REPORTS / "phase78_entries.parquet")
    valid = entries[entries.apply(lambda r: risk_points(r["entry_price"], r["stop"], r["direction"]) > 0, axis=1)]
    index = df.index
    highs = df["high"].values
    lows = df["low"].values
    real = float(valid["plus_1.0R_before_minus_1R"].mean())
    rand, flip = [], []
    for _, row in valid.iterrows():
        h, l = _slice_by_time(index, highs, lows, row["entry_time"], 60)
        fd = deterministic_flip(row["direction"])
        flip.append(
            first_passage_r_arrays(
                h, l, row["entry_price"], symmetric_stop(row["entry_price"], row["stop"], fd), fd
            )["plus_1.0R_before_minus_1R"]
        )
        eid = f"{row['entry_time']}|{row['entry_price']}"
        rand.append(
            float(
                np.mean(
                    [
                        first_passage_r_arrays(
                            h, l, row["entry_price"], symmetric_stop(row["entry_price"], row["stop"], d), d
                        )["plus_1.0R_before_minus_1R"]
                        for d in random_directions(eid)
                    ]
                )
            )
        )
    gate = directional_gate(real, rand, float(np.mean(flip)))
    out = {
        **gate,
        "n_valid": len(valid),
        "n_invalid_structural_risk": len(entries) - len(valid),
        "note": "Random/flipped use symmetric 1R stop at same distance as structural stop.",
    }
    (REPORTS / "PHASE78_RANDOM_DIRECTION.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
