"""Phase58I management models M0–M5 — causal, risk-normalized."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ, InstrumentSpec
from phase58b.research.precompute import MTFArrays, build_mtf_arrays
from phase58b.research.simulation import metrics, simulate_trades, _atr
from phase58d.research.context_maps import m1_market_view
from phase58e.research.active_move import active_move_at_bar, side_aligned_with_active
from phase58e.research.structure import structural_features, structure_context


def simulate_management(
    m: MTFArrays,
    executions: pd.DataFrame,
    cfg: dict,
    model: str,
    instrument: InstrumentSpec = NQ,
    cost_mult: float = 1.0,
) -> pd.DataFrame:
    if model == "M0":
        return simulate_trades(m, executions, cfg, model, instrument=instrument, cost_mult=cost_mult)

    rows = []
    for n, (_, ex) in enumerate(executions.iterrows()):
        if ex.get("entry_i", -1) < 0:
            continue
        res = _simulate_one(m, ex, cfg, model, instrument, cost_mult)
        if res:
            res["trade_id"] = ex.get("trade_id", f"{model}-{n:06d}")
            rows.append(res)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _simulate_one(m, ex, cfg, model, instrument, cost_mult):
    ei = int(ex["entry_i"])
    if ei >= m.m1_n - 2:
        return None
    d = ex["direction"]
    ep = float(ex["entry_price"])
    ai = min(ei, m.m1_n - 1)
    a = _atr(m.m1_atr[ai], m.m1_atr, ai)

    stop_atr = cfg.get("stop_atr_m0", 0.75)
    if model.startswith("M1_"):
        stop_atr = float(model.split("_")[1])
    risk_pts = stop_atr * a
    target_r = cfg.get("target_r", 2.5)

    if d == "LONG":
        stop = ep - risk_pts
        target = ep + target_r * risk_pts
    else:
        stop = ep + risk_pts
        target = ep - target_r * risk_pts

    if model == "M2":
        stop = _structural_stop(m, ei, d, ep, a, cfg)

    max_hold = cfg.get("max_hold_min_m0", 60)
    if model == "M4":
        max_hold = cfg.get("m4_max_hold_min", 90)

    exit_i, exit_price, reason, gross_r, mfe, mae, events = _walk_managed(
        m, ei, d, ep, stop, target, max_hold, cfg, model,
    )
    cr = instrument.cost_r(ep, abs(ep - stop), cost_mult)
    return {
        "direction": d,
        "entry_i": ei,
        "entry_price": ep,
        "exit_i": exit_i,
        "exit_price": exit_price,
        "exit_reason": reason,
        "stop": stop,
        "target": target,
        "gross_R": gross_r,
        "cost_R": cr,
        "net_R": gross_r - cr,
        "MFE_R": mfe,
        "MAE_R": mae,
        "duration_min": exit_i - ei,
        "management_model": model,
        "event_count": len(events),
    }


def _structural_stop(m, ei, direction, ep, atr, cfg) -> float:
    m1 = m1_market_view(m, cfg.get("swing_period", 5))
    buf = 0.1 * atr
    min_d = 0.5 * cfg.get("stop_atr_m0", 0.75) * atr
    max_d = 2.0 * cfg.get("stop_atr_m0", 0.75) * atr
    if direction == "LONG" and np.isfinite(m1.sl1[ei]):
        lvl = float(m1.sl1[ei]) - buf
        dist = ep - lvl
        dist = float(np.clip(dist, min_d, max_d))
        return ep - dist
    if direction == "SHORT" and np.isfinite(m1.sh1[ei]):
        lvl = float(m1.sh1[ei]) + buf
        dist = lvl - ep
        dist = float(np.clip(dist, min_d, max_d))
        return ep + dist
    return ep - cfg.get("stop_atr_m0", 0.75) * atr if direction == "LONG" else ep + cfg.get("stop_atr_m0", 0.75) * atr


def _walk_managed(m, ei, direction, ep, stop, target, max_hold, cfg, model):
    d = 1 if direction == "LONG" else -1
    risk = abs(ep - stop)
    if risk < 1e-9:
        risk = 1e-9
    mfe = mae = 0.0
    cur_stop = stop
    be_active = prot_active = False
    events = [("ENTRY", ei, ep)]
    base_deadline = min(m.m1_n - 1, ei + cfg.get("max_hold_min_m0", 60))
    deadline = min(m.m1_n - 1, ei + max_hold)

    i = ei
    while i < m.m1_n - 1:
        i += 1
        h, l, c = m.m1_hi[i], m.m1_lo[i], m.m1_cl[i]
        if d == 1:
            mfe = max(mfe, (h - ep) / risk)
            mae = max(mae, (ep - l) / risk)
        else:
            mfe = max(mfe, (ep - l) / risk)
            mae = max(mae, (h - ep) / risk)

        if model.startswith("M3"):
            if model == "M3A" and mfe >= 1.0 and not be_active:
                cur_stop = ep
                be_active = True
                events.append(("BREAKEVEN_ACTIVATED", i, ep))
            elif model == "M3B" and mfe >= 1.5 and not prot_active:
                cur_stop = ep + 0.5 * risk * d
                prot_active = True
                events.append(("PROFIT_LOCK_ACTIVATED", i, cur_stop))
            elif model == "M3C" and mfe >= 1.5:
                m1 = m1_market_view(m, cfg.get("swing_period", 5))
                if d == 1 and np.isfinite(m1.sl1[i]):
                    cur_stop = max(cur_stop, float(m1.sl1[i]) - 0.1 * risk)
                elif d == -1 and np.isfinite(m1.sh1[i]):
                    cur_stop = min(cur_stop, float(m1.sh1[i]) + 0.1 * risk)

        if model == "M2":
            struct = structural_features(m, i, cfg)
            active = active_move_at_bar(m, i, cfg)
            ctx = structure_context(struct, active, direction)
            if not ctx["structure_intact"]:
                realized = (c - ep) / risk * d
                events.append(("EXIT_STRUCTURE", i, c))
                return i, c, "STRUCTURE", realized, mfe, mae, events

        if d == 1:
            if l <= cur_stop:
                r = (cur_stop - ep) / risk
                events.append(("EXIT_STOP", i, cur_stop))
                return i, cur_stop, "STOP", r, mfe, mae, events
            if h >= target:
                events.append(("EXIT_TARGET", i, target))
                return i, target, "TARGET", 2.5, mfe, mae, events
        else:
            if h >= cur_stop:
                r = (ep - cur_stop) / risk
                events.append(("EXIT_STOP", i, cur_stop))
                return i, cur_stop, "STOP", r, mfe, mae, events
            if l <= target:
                events.append(("EXIT_TARGET", i, target))
                return i, target, "TARGET", 2.5, mfe, mae, events

        if i >= base_deadline:
            if model == "M4" and i == base_deadline:
                active = active_move_at_bar(m, i, cfg)
                aligned = side_aligned_with_active(direction, active)
                if aligned and mfe >= 0.25:
                    events.append(("TIME_EXTENSION_ALLOWED", i, c))
                    base_deadline = deadline
                    continue
            c = m.m1_cl[i]
            realized = (c - ep) / risk * d
            events.append(("EXIT_TIME", i, c))
            return i, c, "TIME", realized, mfe, mae, events

    c = m.m1_cl[min(deadline, m.m1_n - 1)]
    realized = (c - ep) / risk * d
    return min(deadline, m.m1_n - 1), c, "TIME", realized, mfe, mae, events


def management_comparison(m, executions: pd.DataFrame, cfg: dict, models: list[str]) -> pd.DataFrame:
    rows = []
    m0 = None
    for model in models:
        t = simulate_management(m, executions, cfg, model)
        if t.empty:
            continue
        met = metrics(t["net_R"].values)
        row = {
            "model": model,
            "trades": met.get("N", 0),
            "AvgR": met.get("AvgR", 0),
            "PF": met.get("PF", 0),
            "TotalR": met.get("TotalR", 0),
            "MaxDD": met.get("MaxDD", 0),
            "WinRate": met.get("WinRate", 0),
            "stop_rate": (t["exit_reason"] == "STOP").mean(),
            "target_rate": (t["exit_reason"] == "TARGET").mean(),
            "time_exit_rate": (t["exit_reason"].isin(["TIME", "STRUCTURE"])).mean(),
            "median_hold": t["duration_min"].median(),
            "mfe_capture": (t["net_R"] / t["MFE_R"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).median(),
            "avg_giveback": (t["MFE_R"] - t["net_R"]).mean(),
        }
        if m0 is None:
            m0 = row
            row["delta_vs_m0"] = 0
        else:
            row["delta_vs_m0"] = row["TotalR"] - m0["TotalR"]
        rows.append(row)
    return pd.DataFrame(rows)


def executions_from_trades(trades: pd.DataFrame) -> pd.DataFrame:
    return trades[[
        "trade_id", "setup_id", "direction", "signal_m1_i", "entry_i", "entry_price",
    ]].rename(columns={"setup_id": "setup_id"})
