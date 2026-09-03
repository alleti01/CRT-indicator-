"""Slippage and cost stress — independent simulator only."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ
from phase58j.research.independent_simulator import simulate_bar_path
from phase58b.research.simulation import metrics


def run_slippage_stress(
    m,
    trades: pd.DataFrame,
    stop_atr: float,
    cfg: dict,
    ticks: list[int],
) -> pd.DataFrame:
    rows = []
    slip_pts = NQ.tick_size
    for tick in ticks:
        rs = []
        for _, t in trades.iterrows():
            ep = float(t["entry_price"])
            d = t["direction"]
            if tick:
                ep += slip_pts * tick if d == "LONG" else -slip_pts * tick
            r = simulate_bar_path(
                m.m1_hi, m.m1_lo, m.m1_cl,
                int(t["entry_i"]), d, ep,
                stop_atr, m.m1_atr, cfg["target_r"], cfg["max_hold_min_m0"],
            )
            exit_adj = 0.0
            if tick and r.exit_reason in ("STOP", "TARGET"):
                exit_adj = slip_pts * tick
            if d == "LONG":
                exit_px = r.exit_price - exit_adj
            else:
                exit_px = r.exit_price + exit_adj
            sign = 1.0 if d == "LONG" else -1.0
            gross = sign * (exit_px - ep) / r.risk_pts if r.exit_reason == "TIME" else (
                -1.0 if r.exit_reason == "STOP" else cfg["target_r"]
            )
            if r.exit_reason == "STOP":
                gross = sign * (exit_px - ep) / r.risk_pts
            elif r.exit_reason == "TARGET":
                gross = sign * (exit_px - ep) / r.risk_pts
            cr = NQ.cost_r(ep, r.risk_pts, 1.0)
            rs.append(gross - cr)
        rows.append({"tick_slip": tick, **metrics(np.array(rs))})
    return pd.DataFrame(rows)


def run_cost_stress(
    m,
    trades: pd.DataFrame,
    stop_atr: float,
    cfg: dict,
    mults: list[float],
) -> pd.DataFrame:
    rows = []
    for mult in mults:
        rs = []
        for _, t in trades.iterrows():
            r = simulate_bar_path(
                m.m1_hi, m.m1_lo, m.m1_cl,
                int(t["entry_i"]), t["direction"], float(t["entry_price"]),
                stop_atr, m.m1_atr, cfg["target_r"], cfg["max_hold_min_m0"],
            )
            cr = NQ.cost_r(float(t["entry_price"]), r.risk_pts, mult)
            rs.append(r.gross_r - cr)
        rows.append({"cost_mult": mult, **metrics(np.array(rs))})
    return pd.DataFrame(rows)


def run_stop_neighborhood(m, trades: pd.DataFrame, cfg: dict, stops: list[float]) -> pd.DataFrame:
    rows = []
    for sa in stops:
        rs = []
        for _, t in trades.iterrows():
            r = simulate_bar_path(
                m.m1_hi, m.m1_lo, m.m1_cl,
                int(t["entry_i"]), t["direction"], float(t["entry_price"]),
                sa, m.m1_atr, cfg["target_r"], cfg["max_hold_min_m0"],
            )
            cr = NQ.cost_r(float(t["entry_price"]), r.risk_pts, 1.0)
            rs.append(r.gross_r - cr)
        rows.append({"stop_atr": sa, **metrics(np.array(rs))})
    return pd.DataFrame(rows)


def run_target_neighborhood(m, trades: pd.DataFrame, stop_atr: float, cfg: dict, targets: list[float]) -> pd.DataFrame:
    rows = []
    for tr in targets:
        rs = []
        for _, t in trades.iterrows():
            r = simulate_bar_path(
                m.m1_hi, m.m1_lo, m.m1_cl,
                int(t["entry_i"]), t["direction"], float(t["entry_price"]),
                stop_atr, m.m1_atr, tr, cfg["max_hold_min_m0"],
            )
            cr = NQ.cost_r(float(t["entry_price"]), r.risk_pts, 1.0)
            rs.append(r.gross_r - cr)
        rows.append({"target_r": tr, **metrics(np.array(rs))})
    return pd.DataFrame(rows)


def run_parameter_surface(m, trades: pd.DataFrame, cfg: dict, stops: list[float], targets: list[float]) -> pd.DataFrame:
    rows = []
    for sa in stops:
        for tr in targets:
            rs = []
            for _, t in trades.iterrows():
                r = simulate_bar_path(
                    m.m1_hi, m.m1_lo, m.m1_cl,
                    int(t["entry_i"]), t["direction"], float(t["entry_price"]),
                    sa, m.m1_atr, tr, cfg["max_hold_min_m0"],
                )
                cr = NQ.cost_r(float(t["entry_price"]), r.risk_pts, 1.0)
                rs.append(r.gross_r - cr)
            rows.append({"stop_atr": sa, "target_r": tr, **metrics(np.array(rs))})
    return pd.DataFrame(rows)


def fixed_m1_stop_m0_target(m, trades: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """DIAGNOSTIC_ONLY: M1 stop width, M0 absolute target distance."""
    from phase58j.research.independent_simulator import entry_atr

    rows = []
    m0_atr = cfg["m0_stop_atr"]
    m1_atr = cfg["m1_stop_atr"]
    hold = cfg["max_hold_min_m0"]
    for _, t in trades.iterrows():
        ei = int(t["entry_i"])
        ep = float(t["entry_price"])
        d = t["direction"]
        atr_e = entry_atr(m.m1_atr, ei)
        m0_risk = m0_atr * atr_e
        m1_risk = m1_atr * atr_e
        if d == "LONG":
            stop = ep - m1_risk
            target = ep + cfg["target_r"] * m0_risk
        else:
            stop = ep + m1_risk
            target = ep - cfg["target_r"] * m0_risk
        sign = 1.0 if d == "LONG" else -1.0
        deadline = min(len(m.m1_cl) - 1, ei + hold)
        gross = 0.0
        reason = "TIME"
        for i in range(ei + 1, deadline + 1):
            h, l = float(m.m1_hi[i]), float(m.m1_lo[i])
            if d == "LONG":
                if l <= stop:
                    gross, reason = -1.0, "STOP"
                    break
                if h >= target:
                    gross = (target - ep) / m1_risk
                    reason = "TARGET"
                    break
            else:
                if h >= stop:
                    gross, reason = -1.0, "STOP"
                    break
                if l <= target:
                    gross = (ep - target) / m1_risk
                    reason = "TARGET"
                    break
        else:
            c = float(m.m1_cl[deadline])
            gross = sign * (c - ep) / m1_risk
        cr = NQ.cost_r(ep, m1_risk, 1.0)
        rows.append({
            "trade_id": t["trade_id"],
            "gross_r": gross,
            "net_r": gross - cr,
            "exit_reason": reason,
            "label": "DIAGNOSTIC_ONLY",
        })
    return pd.DataFrame(rows)
