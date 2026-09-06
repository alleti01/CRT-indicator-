"""Prefix invariance and causality audit."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CHECKPOINTS, PREFIX_CUTOFFS, REPORTS
from .liquidity import freeze_liquidity_map
from .sequence import scan_window


def prefix_invariance_test(
    df: pd.DataFrame,
    swing_highs: list,
    swing_lows: list,
    sample_dates: list,
    window_id: str = "SB2",
    index_arr: pd.DatetimeIndex | None = None,
) -> dict:
    from .windows import window_bounds

    index_arr = df.index if index_arr is None else index_arr
    mismatches = 0
    checked = 0
    for d in sample_dates:
        ws, we = window_bounds(d, window_id)
        ws_utc, we_utc = ws.tz_convert("UTC"), we.tz_convert("UTC")
        i0 = int(index_arr.searchsorted(ws_utc))
        i1 = int(index_arr.searchsorted(we_utc, side="right"))
        full = df.iloc[i0:i1]
        if len(full) < 10:
            continue
        sh = [(p, px, c) for p, px, c in swing_highs if c < i0][-150:]
        sl = [(p, px, c) for p, px, c in swing_lows if c < i0][-150:]
        for frac in PREFIX_CUTOFFS:
            cut_idx = int(len(full) * frac)
            if cut_idx < 5:
                continue
            prefix = full.iloc[:cut_idx]
            atr = float(prefix["atr"].iloc[-1]) if prefix["atr"].notna().any() else np.nan
            liq = freeze_liquidity_map(df, index_arr, i0, d, sh, sl, atr)
            r_full, _ = scan_window(full, np.arange(len(full)), liq, d, window_id, we_utc)
            r_pre, _ = scan_window(prefix, np.arange(len(prefix)), liq, d, window_id, we_utc)
            checked += 1
            prefix_end = prefix.index[-1]
            full_in_prefix = [
                e for e in r_full if e.entry_time is not None and e.entry_time <= prefix_end
            ]
            if _entries_key(full_in_prefix) != _entries_key(r_pre):
                mismatches += 1
    return {"checked": checked, "mismatches": mismatches, "pass": mismatches == 0 and checked > 0}


def _entries_key(recs: list) -> tuple:
    keys = []
    for rec in recs:
        keys.append(
            (
                rec.direction,
                str(rec.entry_time),
                round(rec.entry_price, 4) if np.isfinite(rec.entry_price) else None,
            )
        )
    return tuple(sorted(keys))


def write_causality_report(audit: dict, prefix: dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    p = REPORTS / "PHASE78_CAUSALITY_AUDIT.md"
    causality_pass = prefix.get("pass", False)
    lines = [
        "# Phase78 Causality Audit",
        "",
        f"- PREFIX_PASS: {prefix.get('pass')}",
        f"- PREFIX checked: {prefix.get('checked')}",
        f"- PREFIX mismatches: {prefix.get('mismatches')}",
        "",
        "## Data audit",
        "```json",
        json.dumps(audit, indent=2, default=str),
        "```",
        "",
        f"**CAUSALITY_PASS:** {causality_pass}",
    ]
    p.write_text("\n".join(lines))
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / "09_CAUSALITY_PREFIX.txt").write_text("PASS" if causality_pass else "FAIL")
    return p
