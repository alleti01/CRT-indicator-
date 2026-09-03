"""Entry stage engine — E0 through E4 with move capture diagnostics.

E0 = location entry (first valid interaction)
E1 = first reaction (first closed 1M bar showing reaction)
E2 = early micro confirmation (minimal causal evidence pullback ending)
E3 = structure confirmation (stronger local confirmation)
E4 = late / full confirmation (diagnostic — move clearly underway)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase57.research.outcomes import move_capture, simulate_trade
from phase57.research.sequences import Sequence


def compute_entry_stages(
    m1: pd.DataFrame,
    seq: Sequence,
) -> list[dict]:
    """Compute E0-E4 entry timestamps and outcomes for a sequence."""
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    idx = m1.index
    n = len(m1)
    d = 1 if seq.direction == "BULL" else -1
    results: list[dict] = []

    # E0: location entry — at the setup bar (pullback deepest point)
    e0_i = seq.setup_i
    if e0_i >= n - 61:
        return results

    # E1: first reaction bar (already identified in sequence)
    e1_i = seq.reaction_i

    # E2: early micro confirmation — first bar after setup where close is
    #     directionally favorable vs setup close
    e2_i = None
    setup_cl = cl[e0_i]
    for j in range(e0_i + 1, min(n - 61, e0_i + 4)):
        if seq.direction == "BULL" and cl[j] > setup_cl:
            e2_i = j
            break
        elif seq.direction == "BEAR" and cl[j] < setup_cl:
            e2_i = j
            break

    # E3: structure confirmation — first bar where close exceeds pullback
    #     recovery threshold (50% of pullback recovered)
    e3_i = None
    recovery_target = seq.pullback.depth_pts * 0.5
    for j in range(e0_i + 1, min(n - 61, e0_i + 8)):
        if seq.direction == "BULL":
            recovery = cl[j] - cl[e0_i]
        else:
            recovery = cl[e0_i] - cl[j]
        if recovery >= recovery_target:
            e3_i = j
            break

    # E4: late confirmation — first bar where close exceeds leg end price
    e4_i = None
    for j in range(e0_i + 1, min(n - 61, e0_i + 15)):
        if seq.direction == "BULL" and cl[j] > seq.leg1.end_price:
            e4_i = j
            break
        elif seq.direction == "BEAR" and cl[j] < seq.leg1.end_price:
            e4_i = j
            break

    entries = [
        ("E0", e0_i),
        ("E1", e1_i),
        ("E2", e2_i),
        ("E3", e3_i),
        ("E4", e4_i),
    ]
    trade_dir = "LONG" if seq.direction == "BULL" else "SHORT"

    for stage, entry_i in entries:
        if entry_i is None or entry_i >= n - 61:
            results.append({
                "seq_id": seq.seq_id,
                "stage": stage,
                "entry_i": None,
                "entry_ts": None,
                "entry_price": None,
                "delay_bars": None,
                "net_R": np.nan,
                "MFE_R": np.nan,
                "MAE_R": np.nan,
                "move_capture_pct": np.nan,
                "excursion_before_entry_atr": np.nan,
                "excursion_after_entry_atr": np.nan,
            })
            continue

        trade = simulate_trade(m1, entry_i, trade_dir)
        mc = move_capture(m1, seq.setup_i, entry_i, trade_dir)
        delay = entry_i - e0_i
        results.append({
            "seq_id": seq.seq_id,
            "stage": stage,
            "entry_i": entry_i,
            "entry_ts": idx[entry_i],
            "entry_price": cl[entry_i],
            "delay_bars": delay,
            "net_R": trade["net_R"],
            "gross_R": trade["gross_R"],
            "MFE_R": trade["MFE_R"],
            "MAE_R": trade["MAE_R"],
            "exit_reason": trade["exit_reason"],
            "direction": trade_dir,
            "move_capture_pct": mc["move_capture_pct"],
            "excursion_before_entry_atr": mc["excursion_before_entry_atr"],
            "excursion_after_entry_atr": mc.get("excursion_after_entry_atr", np.nan),
        })
    return results


def batch_entry_stages(
    m1: pd.DataFrame,
    sequences: list[Sequence],
) -> pd.DataFrame:
    """Compute entry stages for all sequences."""
    rows: list[dict] = []
    for seq in sequences:
        rows.extend(compute_entry_stages(m1, seq))
    return pd.DataFrame(rows) if rows else pd.DataFrame()
