"""Evaluation metrics — directional accuracy, move capture, timing, false positives."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58.research.precompute import MarketArrays


def directional_accuracy(m: MarketArrays, trades: pd.DataFrame, horizons=(5, 10, 15, 30, 60)) -> pd.DataFrame:
    """For each trade, check if price moved in predicted direction within horizon (LABEL ONLY)."""
    rows = []
    for _, t in trades.iterrows():
        ei = int(t["entry_i"]); d = t["direction"]
        row = {"trade_id": t.get("trade_id", ""), "direction": d, "entry_i": ei}
        for h in horizons:
            end_i = min(m.n, ei + 1 + h)
            if end_i <= ei + 1:
                row[f"correct_{h}m"] = np.nan; continue
            if d == "LONG":
                moved = m.hi[ei + 1:end_i].max() - m.cl[ei]
            else:
                moved = m.cl[ei] - m.lo[ei + 1:end_i].min()
            a = m.atr[ei] if np.isfinite(m.atr[ei]) and m.atr[ei] > 0 else 1.0
            row[f"correct_{h}m"] = moved / a > 0.5
            row[f"excursion_{h}m_atr"] = moved / a
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def move_capture(m: MarketArrays, trades: pd.DataFrame, horizon: int = 60) -> pd.DataFrame:
    """Measure how much of the total move remains at entry (LABEL ONLY)."""
    rows = []
    for _, t in trades.iterrows():
        si = int(t.get("signal_i", t["entry_i"]))
        ei = int(t["entry_i"]); d = t["direction"]
        a = m.atr[si] if np.isfinite(m.atr[si]) and m.atr[si] > 0 else 1.0
        total_end = min(m.n, si + 1 + horizon)
        if total_end <= si + 1:
            rows.append({"trade_id": t.get("trade_id", ""), "capture_pct": np.nan}); continue
        if d == "LONG":
            total_mfe = (m.hi[si + 1:total_end].max() - m.cl[si]) / a
            consumed = max(0, (m.cl[ei] - m.cl[si]) / a)
        else:
            total_mfe = (m.cl[si] - m.lo[si + 1:total_end].min()) / a
            consumed = max(0, (m.cl[si] - m.cl[ei]) / a)
        capture = (total_mfe - consumed) / total_mfe if total_mfe > 0 else np.nan
        rows.append({"trade_id": t.get("trade_id", ""), "capture_pct": capture,
                      "total_excursion_atr": total_mfe, "consumed_atr": consumed})
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def timing_metrics(decisions: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """ARM-to-ENTRY delay. Uses vectorized index lookup, not per-trade filter."""
    if trades.empty or decisions.empty:
        return pd.DataFrame()
    # Build armed bar lookup: for each bar, track last ARMED bar
    armed_mask = decisions["decision"].values == "ARMED"
    bar_is = decisions["bar_i"].values.astype(int)
    last_armed = np.full(len(decisions), -1, dtype=int)
    running = -1
    for j in range(len(decisions)):
        if armed_mask[j]:
            running = int(bar_is[j])
        last_armed[j] = running
    # Map each trade's signal_i to the closest decision index
    dec_bar_arr = bar_is
    rows = []
    for _, t in trades.iterrows():
        si = int(t["signal_i"]); ei = int(t["entry_i"])
        idx = np.searchsorted(dec_bar_arr, si, side="right") - 1
        arm_i = int(last_armed[max(0, idx)]) if idx >= 0 else si
        rows.append({
            "trade_id": t.get("trade_id", ""),
            "armed_i": arm_i, "signal_i": si, "entry_i": ei,
            "arm_to_entry_bars": ei - arm_i,
            "signal_to_entry_bars": ei - si,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def missed_moves(m: MarketArrays, decisions: pd.DataFrame, threshold_atr: float = 1.5, horizon: int = 30) -> pd.DataFrame:
    """Detect significant directional moves where trader was in WATCH (LABEL ONLY)."""
    rows = []
    watch_bars = decisions.loc[decisions["decision"] == "WATCH", "bar_i"].values.astype(int)
    sample = watch_bars[::500] if len(watch_bars) > 5000 else watch_bars
    for bi in sample:
        if bi >= m.n - horizon:
            continue
        a = m.atr[bi] if np.isfinite(m.atr[bi]) and m.atr[bi] > 0 else 1.0
        end_i = min(m.n, bi + horizon)
        up = (m.hi[bi + 1:end_i].max() - m.cl[bi]) / a
        dn = (m.cl[bi] - m.lo[bi + 1:end_i].min()) / a
        if up >= threshold_atr or dn >= threshold_atr:
            rows.append({"bar_i": bi, "up_atr": up, "down_atr": dn,
                          "missed_dir": "LONG" if up > dn else "SHORT"})
    return pd.DataFrame(rows) if rows else pd.DataFrame()
