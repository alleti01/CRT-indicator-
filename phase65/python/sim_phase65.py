"""Phase65 — trade simulation with origin / hybrid stops."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from phase58.research.instrument import NQ
from phase58.research.precompute import MarketArrays
from phase58b.research.simulation import metrics
from phase62.python.sim_engine import TradeConfig, causal_stop

StopMode = Literal["origin", "origin_buffer", "hybrid"]


@dataclass
class SimConfig:
    stop_mode: StopMode = "origin"
    origin_buffer_atr: float = 0.25
    target_r: float = 2.5
    max_hold: int = 60
    cost_mult: float = 1.0


def _origin_stop(entry: float, origin: float, direction: str, atr: float, buffer: float) -> tuple[float, float]:
    d = 1 if direction == "LONG" else -1
    a = atr if atr > 0 else 1.0
    if direction == "LONG":
        stop = origin - buffer * a
        risk = entry - stop
    else:
        stop = origin + buffer * a
        risk = stop - entry
    risk = max(risk, 0.25 * a)
    return stop, risk


def simulate_phase65(
    m: MarketArrays,
    signal_i: int,
    entry_i: int,
    direction: str,
    origin: float,
    atr: float,
    cfg: SimConfig,
) -> dict:
    ep = float(m.op[entry_i])
    d = 1 if direction == "LONG" else -1
    a = atr if atr > 0 else 1.0

    if cfg.stop_mode == "origin":
        stop, risk = _origin_stop(ep, origin, direction, a, 0.0)
    elif cfg.stop_mode == "origin_buffer":
        stop, risk = _origin_stop(ep, origin, direction, a, cfg.origin_buffer_atr)
    else:
        tc = TradeConfig(stop_mode="hybrid", target_mode="fixed_25r", protection="none", cost_mult=0.0)
        stop, risk = causal_stop(m, signal_i, entry_i, ep, a, direction, "hybrid", tc)

    target = ep + d * cfg.target_r * risk
    peak_mfe_r = 0.0
    exit_r = 0.0
    exit_reason = "TIME"
    exit_i = entry_i
    collisions = 0

    for k in range(entry_i, min(entry_i + cfg.max_hold, m.n)):
        hi, lo, cl = float(m.hi[k]), float(m.lo[k]), float(m.cl[k])
        fav = (hi - ep) * d / risk
        peak_mfe_r = max(peak_mfe_r, fav)
        hit_stop = lo <= stop if d == 1 else hi >= stop
        hit_tgt = hi >= target if d == 1 else lo <= target
        if hit_stop and hit_tgt:
            collisions += 1
            exit_r = -1.0
            exit_reason = "STOP"
            exit_i = k
            break
        if hit_stop:
            exit_r = (stop - ep) * d / risk
            exit_reason = "STOP"
            exit_i = k
            break
        if hit_tgt:
            exit_r = cfg.target_r
            exit_reason = "TARGET"
            exit_i = k
            break
    else:
        c = float(m.cl[min(entry_i + cfg.max_hold - 1, m.n - 1)])
        exit_r = (c - ep) * d / risk
        exit_reason = "TIME"
        exit_i = min(entry_i + cfg.max_hold - 1, m.n - 1)

    cost = NQ.cost_r(ep, stop) * cfg.cost_mult
    net_r = exit_r - cost
    return {
        "signal_i": signal_i,
        "entry_i": entry_i,
        "direction": direction,
        "entry_price": ep,
        "origin": origin,
        "stop_price": stop,
        "risk_pts": risk,
        "risk_atr": risk / a,
        "gross_R": exit_r,
        "cost_R": cost,
        "net_R": net_r,
        "exit_reason": exit_reason,
        "exit_i": exit_i,
        "max_mfe_R": peak_mfe_r,
        "duration": exit_i - entry_i,
        "collisions": collisions,
        "target_r": cfg.target_r,
    }


def remaining_mfe(m, entry_i: int, direction: str, atr: float, horizons=(5, 10, 15, 30, 60)) -> dict:
    ep = float(m.op[entry_i])
    a = atr if atr > 0 else 1.0
    d = 1 if direction == "LONG" else -1
    out = {}
    for h in horizons:
        end = min(entry_i + h, m.n)
        hs, ls = m.hi[entry_i:end], m.lo[entry_i:end]
        if d == 1:
            mfe = (float(np.max(hs)) - ep) / a if len(hs) else 0
            mae = (ep - float(np.min(ls))) / a if len(ls) else 0
        else:
            mfe = (ep - float(np.min(ls))) / a if len(ls) else 0
            mae = (float(np.max(hs)) - ep) / a if len(hs) else 0
        out[f"rem_mfe_{h}m"] = mfe
        out[f"rem_mae_{h}m"] = mae
    return out


def summarize_trades(df) -> dict:
    if df.empty:
        return {"N": 0, "AvgR": 0, "PF": 0, "TotalR": 0, "MaxDD": 0, "WinRate": 0}
    m = metrics(df["net_R"].values)
    m["gross_AvgR"] = float(df["gross_R"].mean())
    m["gross_TotalR"] = float(df["gross_R"].sum())
    m["avg_cost_R"] = float(df["cost_R"].mean())
    m["median_risk_atr"] = float(df["risk_atr"].median())
    m["median_hold"] = float(df["duration"].median())
    return m
