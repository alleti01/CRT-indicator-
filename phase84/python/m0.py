"""M0 simulation — Phase73 management authority."""
from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ
from phase73.config.loader import Phase73Config
from phase73.trader.management import build_management, evaluate_exit
from phase73.market_data.bar import Bar

from phase84.python.config import (
    M0_COLLISION,
    M0_MAX_HOLD_MIN,
    M0_REFERENCE_FUNCTIONS,
    M0_REFERENCE_PATH,
    M0_STOP_ATR,
    M0_TARGET_R,
    TICK_SLIPPAGE,
    COST_MULTS,
    NQ_TICK,
)


def m0_provenance() -> dict:
    return {
        "M0_REFERENCE_PATH": M0_REFERENCE_PATH,
        "M0_REFERENCE_FUNCTION": ",".join(M0_REFERENCE_FUNCTIONS),
        "stop_atr": M0_STOP_ATR,
        "target_r": M0_TARGET_R,
        "max_hold_minutes": M0_MAX_HOLD_MIN,
        "collision": M0_COLLISION,
    }


def simulate_m0_trade(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    op: np.ndarray,
    ts_index: pd.DatetimeIndex,
    entry_i: int,
    direction: str,
    entry_price: float,
    signal_atr: float,
    tick_slippage: int = 0,
    cost_mult: float = 1.0,
) -> dict:
    """Simulate one trade using phase73 M0 evaluate_exit loop."""
    cfg = Phase73Config()
    d = 1 if direction == "LONG" else -1
    slip = tick_slippage * NQ_TICK
    ep = entry_price + slip * d

    et = ts_index[entry_i].to_pydatetime()
    mgmt = build_management(direction, ep, signal_atr, cfg, et)
    risk = mgmt.risk
    if risk <= 0:
        risk = max(signal_atr * M0_STOP_ATR, 1e-9)

    n = len(hi)
    exit_i = entry_i
    exit_price = ep
    exit_reason = "MAX_HOLD_60M"
    gross_r = 0.0

    for k in range(entry_i, min(entry_i + M0_MAX_HOLD_MIN + 1, n)):
        bar = Bar(
            timestamp=ts_index[k].to_pydatetime(),
            open=float(op[k]),
            high=float(hi[k]),
            low=float(lo[k]),
            close=float(cl[k]),
            volume=0.0,
        )
        now = bar.timestamp
        dec = evaluate_exit(mgmt, bar, cfg, now)
        if dec is not None:
            exit_i = k
            exit_price = float(dec.exit_price if dec.exit_price is not None else bar.close)
            gross_r = (exit_price - ep) * d / risk
            exit_reason = dec.reason
            break

    cost = NQ.cost_r(ep, ep - risk if d == 1 else ep + risk, mult=cost_mult)
    net_r = gross_r - cost

    return {
        "entry_i": entry_i,
        "exit_i": exit_i,
        "entry_price": ep,
        "exit_price": exit_price,
        "gross_R": gross_r,
        "cost_R": cost,
        "net_R": net_r,
        "exit_reason": exit_reason,
        "MFE_R": mgmt.mfe_r,
        "MAE_R": mgmt.mae_r,
        "hold_bars": exit_i - entry_i,
    }


def simulate_opportunities(
    signals: pd.DataFrame,
    m1: pd.DataFrame,
    entry_i_col: str = "entry_i",
    atr_col: str = "atr_signal",
) -> pd.DataFrame:
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr_series = m1["atr"].values.astype(float) if "atr" in m1.columns else (hi - lo)
    idx = m1.index

    rows = []
    for _, sig in signals.iterrows():
        ei = int(sig[entry_i_col])
        si = int(sig["signal_i"])
        direction = sig["phase72a_direction"]
        atr = float(sig[atr_col]) if atr_col in sig and pd.notna(sig.get(atr_col)) else float(atr_series[si])
        ep = float(op[ei])
        if "entry_price" in sig and pd.notna(sig.get("entry_price")):
            ep = float(sig["entry_price"])

        base = simulate_m0_trade(hi, lo, cl, op, idx, ei, direction, ep, atr)
        row = {**sig.to_dict(), **base}
        rows.append(row)

    return pd.DataFrame(rows)


def verify_m0_baseline_sample(n_sample: int = 20) -> dict:
    """Sanity check M0 path produces finite outcomes on sample bars."""
    from phase84.python.data import load_m1

    m1 = load_m1()
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    idx = m1.index

    ok = 0
    for ei in range(100, 100 + n_sample):
        r = simulate_m0_trade(hi, lo, cl, op, idx, ei, "LONG", float(op[ei]), float(atr[ei]))
        if np.isfinite(r["gross_R"]):
            ok += 1
    return {"n": n_sample, "finite_outcomes": ok, "pass": ok == n_sample}
