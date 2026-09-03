"""Trade simulation and metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase31.metrics import apply_costs, performance

from phase29.config import WALK_FORWARD_FOLDS

from .config import MAX_HOLD_BARS, STOP_ATR, TARGET_R


def simulate_trade(market: pd.DataFrame, entry_i: int, direction: int, *, entry_mode: str = "CURRENT") -> dict:
    if entry_mode == "NEXT_OPEN" and entry_i + 1 < len(market):
        ei = entry_i + 1
        entry = float(market.iloc[ei]["open"])
        start = ei + 1
    elif entry_mode == "ONE_BAR_CONFIRM" and entry_i + 1 < len(market):
        ei = entry_i + 1
        entry = float(market.iloc[ei]["close"])
        start = ei + 1
    else:
        ei = entry_i
        entry = float(market.iloc[ei]["close"])
        start = ei + 1
    atr = float(market.iloc[ei]["atr"])
    risk = STOP_ATR * atr
    if risk <= 0:
        return {}
    d = 1 if direction == 1 else -1
    stop = entry - risk if d == 1 else entry + risk
    target = entry + TARGET_R * risk if d == 1 else entry - TARGET_R * risk
    realized = 0.0
    mfe = mae = 0.0
    for elapsed, j in enumerate(range(start, min(len(market), ei + MAX_HOLD_BARS + 1)), start=1):
        bar = market.iloc[j]
        hi, lo, cl = float(bar.high), float(bar.low), float(bar.close)
        if d == 1:
            mfe = max(mfe, (hi - entry) / risk)
            mae = max(mae, (entry - lo) / risk)
            if lo <= stop:
                realized = -1.0
                break
            if hi >= target:
                realized = TARGET_R
                break
        else:
            mfe = max(mfe, (entry - lo) / risk)
            mae = max(mae, (hi - entry) / risk)
            if hi >= stop:
                realized = -1.0
                break
            if lo <= target:
                realized = TARGET_R
                break
        if elapsed >= MAX_HOLD_BARS:
            realized = (cl - entry) / risk * d
            break
    return {"entry_i": ei, "entry_price": entry, "stop": stop, "target": target, "realized_R": realized, "MFE_R": mfe, "MAE_R": mae}


def enrich_net(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["net_R"] = apply_costs(
        out.assign(entry_price=out["entry_price"], stop_price=out["stop"], result_R=out["realized_R"]),
        col="result_R",
    )
    return out


def cost_stress(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mult in (1.0, 1.5, 2.0):
        d = df.copy()
        d["net_R"] = apply_costs(
            d.assign(entry_price=d["entry_price"], stop_price=d["stop"], result_R=d["realized_R"]),
            multiplier=mult,
            col="result_R",
        )
        rows.append({"cost_multiplier": mult, **performance(d, col="net_R")})
    return pd.DataFrame(rows)


def monte_carlo(r: np.ndarray, *, sims: int = 10000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    n = len(r)
    if n == 0:
        return {}
    terminals = []
    max_dds = []
    for _ in range(sims):
        sample = r[rng.integers(0, n, size=n)]
        cum = np.cumsum(sample)
        terminals.append(float(cum[-1]))
        peak = np.maximum.accumulate(cum)
        max_dds.append(float(np.max(peak - cum)))
    terminals = np.array(terminals)
    max_dds = np.array(max_dds)
    # losing streak
    streaks = []
    for _ in range(min(1000, sims)):
        sample = r[rng.integers(0, n, size=n)]
        cur = mx = 0
        for x in sample:
            if x < 0:
                cur += 1
                mx = max(mx, cur)
            else:
                cur = 0
        streaks.append(mx)
    return {
        "P_terminal_pos": float((terminals > 0).mean()),
        "median_terminal_R": float(np.median(terminals)),
        "p5_terminal_R": float(np.percentile(terminals, 5)),
        "p95_terminal_R": float(np.percentile(terminals, 95)),
        "median_maxDD": float(np.median(max_dds)),
        "p95_maxDD": float(np.percentile(max_dds, 95)),
        "median_losing_streak": float(np.median(streaks)),
        "p95_losing_streak": float(np.percentile(streaks, 95)),
    }


def rth_days(index: pd.DatetimeIndex) -> float:
    if len(index) == 0:
        return 1.0
    dates = pd.Series([t.date() for t in index]).nunique()
    return max(float(dates), 1.0)


def oos_rth_days() -> float:
    """Count unique RTH session dates across all walk-forward test windows."""
    days: set = set()
    for _, _, te_s, te_e in WALK_FORWARD_FOLDS:
        for ts in pd.date_range(te_s, te_e, freq="D", tz="America/Chicago"):
            if ts.weekday() < 5:
                days.add(ts.date())
    return max(float(len(days)), 1.0)
