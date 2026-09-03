"""Trade simulation on 1M bars — stop-first, cost stress."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ, InstrumentSpec
from phase58b.research.precompute import MTFArrays


def simulate_trades(
    m: MTFArrays,
    executions: pd.DataFrame,
    cfg: dict,
    system: str,
    instrument: InstrumentSpec = NQ,
    tick_slip: int = 0,
    cost_mult: float = 1.0,
) -> pd.DataFrame:
    """Simulate trades from execution records. Same-bar stop first."""
    rows = []
    trade_n = 0
    slip = tick_slip * instrument.tick_size

    for _, ex in executions.iterrows():
        if ex.get("entry_i", -1) < 0 or not np.isfinite(ex.get("entry_price", np.nan)):
            continue
        ei = int(ex["entry_i"])
        if ei >= m.m1_n - 2:
            continue
        d = ex["direction"]
        ep = float(ex["entry_price"])
        if d == "LONG":
            ep += slip
        else:
            ep -= slip

        # ATR at signal — use 5M-aligned 1M bar
        ai = min(ei, m.m1_n - 1)
        a = _atr(m.m1_atr[ai], m.m1_atr, ai)
        risk_pts = cfg.get("stop_atr", 0.75) * a
        if d == "LONG":
            stop = ep - risk_pts
            target = ep + cfg.get("target_r", 2.5) * risk_pts
        else:
            stop = ep + risk_pts
            target = ep - cfg.get("target_r", 2.5) * risk_pts

        deadline = min(m.m1_n - 1, ei + cfg.get("max_hold_min", 60))
        exit_i, exit_price, reason, gross_r, mfe, mae = _walk(m, ei, d, ep, stop, target, deadline)

        cr = instrument.cost_r(ep, stop, cost_mult)
        trade_n += 1
        rows.append({
            "trade_id": f"{system}-{trade_n:06d}",
            "system": system,
            "setup_id": ex.get("setup_id", ""),
            "variant": ex.get("variant", ""),
            "direction": d,
            "tag": ex.get("tag", ""),
            "signal_j": ex.get("take_j", -1),
            "signal_m1_i": int(ex.get("signal_m1_i", -1)) if "signal_m1_i" in ex else -1,
            "entry_i": ei,
            "entry_ts": str(m.m1_idx[ei]),
            "entry_price": ep,
            "exit_i": exit_i,
            "exit_price": exit_price,
            "exit_reason": reason,
            "stop": stop,
            "target": target,
            "atr": a,
            "gross_R": gross_r,
            "cost_R": cr,
            "net_R": gross_r - cr,
            "MFE_R": mfe,
            "MAE_R": mae,
            "duration_min": exit_i - ei,
            "delay_bars_1m": ex.get("delay_bars_1m", 0),
            "price_improvement_atr": ex.get("price_improvement_atr", 0),
            "entry_deterioration_atr": ex.get("entry_deterioration_atr", 0),
            "15m_state": ex.get("15m_state", ""),
            "15m_strength": ex.get("15m_strength", 0),
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _walk(m, ei, direction, ep, stop, target, deadline):
    d = 1 if direction == "LONG" else -1
    risk = abs(ep - stop)
    mfe = mae = 0.0
    for i in range(ei + 1, deadline + 1):
        h, l, c = m.m1_hi[i], m.m1_lo[i], m.m1_cl[i]
        if d == 1:
            mfe = max(mfe, (h - ep) / risk)
            mae = max(mae, (ep - l) / risk)
            if l <= stop:
                return i, stop, "STOP", -1.0, mfe, mae
            if h >= target:
                return i, target, "TARGET", 2.5, mfe, mae
        else:
            mfe = max(mfe, (ep - l) / risk)
            mae = max(mae, (h - ep) / risk)
            if h >= stop:
                return i, stop, "STOP", -1.0, mfe, mae
            if l <= target:
                return i, target, "TARGET", 2.5, mfe, mae
    c = m.m1_cl[deadline]
    realized = (c - ep) / risk * d
    return deadline, c, "TIME", realized, mfe, mae


def metrics(rs: np.ndarray) -> dict:
    rs = np.asarray(rs, dtype=float)
    rs = rs[np.isfinite(rs)]
    if len(rs) == 0:
        return dict(N=0)
    eq = np.cumsum(rs)
    w = rs[rs > 0].sum()
    l = np.abs(rs[rs <= 0].sum())
    return dict(
        N=len(rs),
        AvgR=float(rs.mean()),
        PF=float(w / l) if l > 0 else np.inf,
        TotalR=float(rs.sum()),
        WinRate=float((rs > 0).mean()),
        MaxDD=float((np.maximum.accumulate(eq) - eq).max()),
    )


def _atr(val, arr, i):
    if np.isfinite(val) and val > 0:
        return val
    for k in range(max(0, i - 5), i + 1):
        if np.isfinite(arr[k]) and arr[k] > 0:
            return arr[k]
    return 1.0
