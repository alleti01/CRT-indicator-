"""Phase62 — opportunity state and trade simulation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ
from phase58.research.precompute import MarketArrays
from phase58b.research.simulation import metrics

ProtectionMode = Literal["none", "be_1r", "be_15r", "partial_05r", "mfe_giveback_50", "structure_trail"]
StopMode = Literal["fixed_1.0", "fixed_1.25", "structure", "hybrid"]
TargetMode = Literal["fixed_25r", "fixed_3r", "runner"]


@dataclass
class TradeConfig:
    stop_mode: StopMode = "fixed_1.0"
    target_mode: TargetMode = "fixed_25r"
    protection: ProtectionMode = "none"
    max_hold: int = 60
    cost_mult: float = 0.0  # 0 = gross R (Phase61 comparable); 1.0 = NQ RT costs
    fixed_stop_atr: float = 1.0
    hybrid_cap_atr: float = 1.75
    hybrid_floor_atr: float = 0.75
    partial_floor_r: float = 0.5
    mfe_giveback_frac: float = 0.50
    trail_activate_r: float = 1.5


def causal_stop(
    m: MarketArrays,
    signal_i: int,
    entry_i: int,
    entry: float,
    atr: float,
    direction: str,
    mode: StopMode,
    cfg: TradeConfig,
) -> tuple[float, float]:
    """Return (stop_price, risk_points)."""
    d = 1 if direction == "LONG" else -1
    a = atr if atr > 0 else 1.0
    if mode == "fixed_1.0":
        risk = cfg.fixed_stop_atr * a
        return entry - d * risk, risk
    if mode == "fixed_1.25":
        risk = 1.25 * a
        return entry - d * risk, risk
    # structure at signal bar (known at entry)
    struct = m.sl[signal_i] if direction == "LONG" else m.sh[signal_i]
    if not np.isfinite(struct):
        risk = 1.25 * a
        return entry - d * risk, risk
    if mode == "structure":
        risk = abs(entry - struct)
        risk = max(risk, 0.25 * a)
        return entry - d * risk, risk
    # hybrid M3
    risk_struct = abs(entry - struct)
    cap = cfg.hybrid_cap_atr * a
    floor = cfg.hybrid_floor_atr * a
    if risk_struct > cap:
        risk = cap
    elif risk_struct < floor:
        risk = floor
    else:
        risk = risk_struct
    return entry - d * risk, risk


def simulate_trade(
    m: MarketArrays,
    signal_i: int,
    entry_i: int,
    direction: str,
    atr: float,
    cfg: TradeConfig,
    opposite_signals: list[int] | None = None,
    same_dir_signals: list[int] | None = None,
) -> dict:
    """Bar-by-bar causal trade simulation. Returns normalized R and diagnostics."""
    ep = float(m.op[entry_i])
    stop, risk = causal_stop(m, signal_i, entry_i, ep, atr, direction, cfg.stop_mode, cfg)
    if risk <= 0:
        risk = atr if atr > 0 else 1.0
    d = 1 if direction == "LONG" else -1
    target_r = 2.5 if cfg.target_mode == "fixed_25r" else 3.0 if cfg.target_mode == "fixed_3r" else 999.0
    target = ep + d * target_r * risk
    stop_r = -1.0
    current_stop = stop
    max_r = 0.0
    max_mfe_r = 0.0
    events: list[str] = ["ENTRY:EARLY_LOCATION"]
    exit_r = 0.0
    exit_reason = "TIME"
    exit_i = entry_i
    peak_mfe_r = 0.0
    runner_mode = cfg.target_mode == "runner"

    for k in range(entry_i, min(entry_i + cfg.max_hold, m.n)):
        hi, lo, cl = m.hi[k], m.lo[k], m.cl[k]
        cur_r = (cl - ep) * d / risk
        fav = (hi - ep) * d / risk if d == 1 else (ep - lo) / risk
        adv = (ep - lo) / risk if d == 1 else (hi - ep) / risk
        max_r = max(max_r, cur_r)
        peak_mfe_r = max(peak_mfe_r, fav)

        # Protection updates (causal, bar close)
        if cfg.protection == "be_1r" and peak_mfe_r >= 1.0:
            be = ep
            if d == 1:
                current_stop = max(current_stop, be)
            else:
                current_stop = min(current_stop, be)
        elif cfg.protection == "be_15r" and peak_mfe_r >= 1.5:
            be = ep
            current_stop = max(current_stop, be) if d == 1 else min(current_stop, be)
        elif cfg.protection == "partial_05r" and peak_mfe_r >= 1.5:
            floor = ep + d * cfg.partial_floor_r * risk
            current_stop = max(current_stop, floor) if d == 1 else min(current_stop, floor)
        elif cfg.protection == "mfe_giveback_50" and peak_mfe_r >= 1.5:
            floor_r = peak_mfe_r * (1.0 - cfg.mfe_giveback_frac)
            floor = ep + d * floor_r * risk
            current_stop = max(current_stop, floor) if d == 1 else min(current_stop, floor)
        elif cfg.protection == "structure_trail" and peak_mfe_r >= cfg.trail_activate_r:
            sv = m.sl[k] if direction == "LONG" else m.sh[k]
            if np.isfinite(sv):
                current_stop = max(current_stop, sv) if d == 1 else min(current_stop, sv)

        # Opposite signal tracking (informational)
        if opposite_signals and k in opposite_signals:
            events.append(f"OPPOSITE_SIGNAL@{k}")

        # Check stop
        hit_stop = (lo <= current_stop) if d == 1 else (hi >= current_stop)
        if hit_stop:
            exit_r = (current_stop - ep) * d / risk
            exit_reason = "STOP" if exit_r <= -0.5 else "PROFIT_PROTECTED"
            exit_i = k
            break

        # Target (unless runner past activation)
        active_target = target
        if runner_mode and peak_mfe_r >= 2.0:
            active_target = ep + d * 999 * risk  # effectively disabled
        hit_tgt = (hi >= active_target) if d == 1 else (lo <= active_target)
        if hit_tgt and not (runner_mode and peak_mfe_r >= 2.0):
            exit_r = target_r
            exit_reason = "TARGET"
            exit_i = k
            break

    else:
        c = m.cl[min(entry_i + cfg.max_hold - 1, m.n - 1)]
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
        "stop_price": stop,
        "risk_pts": risk,
        "risk_atr": risk / atr if atr > 0 else 1.0,
        "gross_R": exit_r,
        "cost_R": cost,
        "net_R": net_r,
        "exit_reason": exit_reason,
        "exit_i": exit_i,
        "max_mfe_R": peak_mfe_r,
        "realization_efficiency": net_r / peak_mfe_r if peak_mfe_r > 0.01 else 0.0,
        "duration": exit_i - entry_i,
        "events": "|".join(events),
        "hit_25r": peak_mfe_r >= 2.5,
        "hit_3r": peak_mfe_r >= 3.0,
    }


def run_simulation(m: MarketArrays, opps: pd.DataFrame, cfg: TradeConfig) -> pd.DataFrame:
    rows = []
    for _, t in opps.iterrows():
        si = int(t["signal_i"])
        ei = int(t.get("entry_i", si + 1))
        rows.append(simulate_trade(m, si, ei, t["direction"], float(t["atr"]), cfg))
    return pd.DataFrame(rows)


def summarize(sim: pd.DataFrame) -> dict:
    m = metrics(sim["net_R"].values)
    m["realization_efficiency_median"] = float(sim["realization_efficiency"].median())
    m["realization_efficiency_mean"] = float(sim["realization_efficiency"].mean())
    m["winner_25r_retention"] = float((sim["net_R"] >= 2.0).sum() / max(1, sim["hit_25r"].sum()))
    m["winner_3r_retention"] = float((sim["net_R"] >= 2.5).sum() / max(1, sim["hit_3r"].sum()))
    m["avg_risk_atr"] = float(sim["risk_atr"].mean())
    m["median_risk_atr"] = float(sim["risk_atr"].median())
    m["median_hold"] = float(sim["duration"].median())
    m["avg_hold"] = float(sim["duration"].mean())
    return m
