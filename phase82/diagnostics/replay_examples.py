#!/usr/bin/env python3
"""Generate bar-by-bar replay logs for Phase82 examples."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase82.python.config import CHECKPOINTS, REPORTS
from phase82.python.m15_causal import build_m15_causal_arrays
from phase82.python.m15_state import m15_state_at
from phase82.python.m1_state import m1_features_at


def sample_replays(n_each: int = 5) -> Path:
    ent_path = CHECKPOINTS / "phase82_entries.parquet"
    if not ent_path.exists():
        return REPORTS / "REPLAY_EXAMPLES.md"
    ent = pd.read_parquet(ent_path)
    p5 = ent[ent["model_id"] == "P5"]
    arr = build_m15_causal_arrays()
    lines = ["# Phase82 Replay Examples", ""]
    for label, sub in [
        ("winning_long", p5[(p5["direction"] == "LONG") & (p5["net_R"] > 1)]),
        ("losing_short", p5[(p5["direction"] == "SHORT") & (p5["net_R"] < -0.5)]),
        ("reset_short", p5[p5["entry_type"].str.contains("RESET", na=False)]),
    ]:
        lines.append(f"## {label}")
        for _, r in sub.head(n_each).iterrows():
            sig = int(r["sig_i"])
            for j in range(max(0, sig - 3), min(sig + 4, arr.n)):
                m15 = m15_state_at(arr, j)
                m1 = m1_features_at(arr, j)
                mark = " <-- ENTRY" if j == int(r["entry_i"]) else ""
                lines.append(
                    f"{arr.idx[j]} {m15['m15_state']} ext={m15['m15_extension_atr']:.2f} "
                    f"m1={m1.get('m1_state','?')} pb={m1.get('pullback_from_low_atr',0):.2f}"
                    f"{mark}"
                )
            lines.append("")
    out = REPORTS / "REPLAY_EXAMPLES.md"
    out.write_text("\n".join(lines) + "\n")
    return out


if __name__ == "__main__":
    p = sample_replays()
    print(f"Wrote {p}")
