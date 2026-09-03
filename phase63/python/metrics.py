"""Phase63 — path and retention metrics from entry."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase62.python.analysis import path_ordering
from phase62.python.sim_engine import TradeConfig, simulate_trade, summarize
from phase58b.research.simulation import metrics


def path_summary(m1_hi, m1_lo, m1_op, m1_cl, trades: pd.DataFrame) -> dict:
    """Aggregate path ordering + MFE/MAE from entry."""
    pairs = {}
    pair_totals = {}
    mfe15, mae15, mfe60, mae60 = [], [], [], []
    early_win, early_total = 0, 0
    move_ret_2, move_ret_3 = 0, 0
    move_tot_2, move_tot_3 = 0, 0
    delays, chases = [], []

    for _, t in trades.iterrows():
        ei = int(t["entry_i"])
        a = float(t["atr"]) if t["atr"] > 0 else 1.0
        d = t["direction"]
        ep = float(m1_op[ei])
        po = path_ordering(m1_hi, m1_lo, m1_op, ei, d, a)
        for k, v in po["pairs"].items():
            if v is None:
                continue
            pair_totals[k] = pair_totals.get(k, 0) + 1
            if v:
                pairs[k] = pairs.get(k, 0) + 1
        end15 = min(ei + 15, len(m1_hi))
        end60 = min(ei + 60, len(m1_hi))
        hs, ls = m1_hi[ei:end15], m1_lo[ei:end15]
        if d == "LONG":
            mfe15.append((np.max(hs) - ep) / a if len(hs) else 0)
            mae15.append((ep - np.min(ls)) / a if len(ls) else 0)
        else:
            mfe15.append((ep - np.min(ls)) / a if len(ls) else 0)
            mae15.append((np.max(hs) - ep) / a if len(ls) else 0)
        hs60, ls60 = m1_hi[ei:end60], m1_lo[ei:end60]
        if d == "LONG":
            mfe60.append((np.max(hs60) - ep) / a)
            mae60.append((ep - np.min(ls60)) / a)
        else:
            mfe60.append((ep - np.min(ls60)) / a)
            mae60.append((np.max(hs60) - ep) / a)
        # early 5m ordering
        end5 = min(ei + 5, len(m1_hi))
        hs5, ls5 = m1_hi[ei:end5], m1_lo[ei:end5]
        if d == "LONG":
            fav5 = (np.max(hs5) - ep) / a
            adv5 = (ep - np.min(ls5)) / a
        else:
            fav5 = (ep - np.min(ls5)) / a
            adv5 = (np.max(hs5) - ep) / a
        early_total += 1
        if fav5 >= 1.0 and (adv5 < 1.0 or fav5 >= adv5):
            early_win += 1
        # move retention (did path reach +2/+3 at all from entry)
        if po["times"].get("+2.0") is not None:
            move_tot_2 += 1
            move_ret_2 += 1
        elif po["pairs"].get("+2_before_-1"):
            move_tot_2 += 1
            move_ret_2 += 1
        else:
            # check if MFE60 >= 2
            if mfe60[-1] >= 2.0:
                move_tot_2 += 1
                move_ret_2 += 1
            else:
                move_tot_2 += 1
        if mfe60[-1] >= 3.0:
            move_tot_3 += 1
            move_ret_3 += 1
        else:
            move_tot_3 += 1
        if "delay_bars" in t:
            delays.append(t["delay_bars"])
        if "signal_i" in t:
            chase = abs(ep - float(m1_op[int(t["signal_i"])])) / a
            chases.append(chase)

    out = {k: pairs.get(k, 0) / pair_totals[k] for k in pair_totals if pair_totals[k] > 0}
    out["n"] = len(trades)
    out["median_mfe_15"] = float(np.median(mfe15)) if mfe15 else 0
    out["median_mae_15"] = float(np.median(mae15)) if mae15 else 0
    out["median_mfe_60"] = float(np.median(mfe60)) if mfe60 else 0
    out["median_mae_60"] = float(np.median(mae60)) if mae60 else 0
    out["early_5m_fav_first"] = early_win / early_total if early_total else 0
    out["median_delay"] = float(np.median(delays)) if delays else 0
    out["median_chase"] = float(np.median(chases)) if chases else 0
    out["move_ret_2"] = move_ret_2 / move_tot_2 if move_tot_2 else 0
    out["move_ret_3"] = move_ret_3 / move_tot_3 if move_tot_3 else 0
    return out


def sim_summary(m, trades: pd.DataFrame, cost_mult: float = 0.0) -> dict:
    cfg = TradeConfig(stop_mode="hybrid", target_mode="fixed_25r", protection="none", cost_mult=cost_mult)
    rows = []
    for _, t in trades.iterrows():
        if t.get("decision") not in ("TAKE", None) and "decision" in t:
            continue
        si = int(t["signal_i"])
        ei = int(t["entry_i"])
        rows.append(simulate_trade(m, si, ei, t["direction"], float(t["atr"]), cfg))
    if not rows:
        return {"N": 0, "AvgR": 0, "PF": 0, "TotalR": 0, "MaxDD": 0}
    return summarize(pd.DataFrame(rows))


def classify_direction_audit(m1_hi, m1_lo, m1_op, opp: pd.DataFrame) -> dict:
    """Original vs reaction direction groups (retrospective path quality)."""
    groups = {"ORIGINAL_CONFIRMED": [], "ORIGINAL_CONTRADICTED": [], "AMBIGUOUS": [], "REVERSAL_CONFIRMED": []}
    for _, r in opp.iterrows():
        si, ei = int(r["signal_i"]), int(r["entry_i"])
        orig = r["direction"]
        a = float(r["atr"])
        po_orig = path_ordering(m1_hi, m1_lo, m1_op, ei, orig, a)
        opp_dir = "SHORT" if orig == "LONG" else "LONG"
        po_opp = path_ordering(m1_hi, m1_lo, m1_op, ei, opp_dir, a)
        o2 = po_orig["pairs"].get("+2_before_-1")
        x2 = po_opp["pairs"].get("+2_before_-1")
        if o2 is True and (x2 is not True):
            groups["ORIGINAL_CONFIRMED"].append(r)
        elif x2 is True and o2 is not True:
            groups["ORIGINAL_CONTRADICTED"].append(r)
        elif o2 is True and x2 is True:
            groups["AMBIGUOUS"].append(r)
        elif x2 is True:
            groups["REVERSAL_CONFIRMED"].append(r)
        else:
            groups["AMBIGUOUS"].append(r)
    report = {}
    for g, rows in groups.items():
        if not rows:
            report[g] = {"n": 0}
            continue
        df = pd.DataFrame(rows)
        po = path_summary(m1_hi, m1_lo, m1_op, None, df)
        report[g] = {"n": len(rows), "+2_before_-1": po.get("+2_before_-1", 0)}
    return report


def glbd_glbd_audit(m1_hi, m1_lo, m1_op, opp: pd.DataFrame, reaction_df: pd.DataFrame) -> dict:
    """Good location bad/good direction retrospective."""
    glbd, glgd = 0, 0
    glbd_handled, glgd_preserved = 0, 0
    for _, r in opp.iterrows():
        si, ei = int(r["signal_i"]), int(r["entry_i"])
        orig, a = r["direction"], float(r["atr"])
        po_orig = path_ordering(m1_hi, m1_lo, m1_op, ei, orig, a)
        opp_dir = "SHORT" if orig == "LONG" else "LONG"
        po_opp = path_ordering(m1_hi, m1_lo, m1_op, ei, opp_dir, a)
        end60 = min(ei + 60, len(m1_hi))
        ep = m1_op[ei]
        mfe = (np.max(m1_hi[ei:end60]) - ep) / a if orig == "LONG" else (ep - np.min(m1_lo[ei:end60])) / a
        opp_mfe = (ep - np.min(m1_lo[ei:end60])) / a if orig == "LONG" else (np.max(m1_hi[ei:end60]) - ep) / a
        is_glbd = opp_mfe >= 2.0 and po_orig["pairs"].get("+2_before_-1") is not True
        is_glgd = po_orig["pairs"].get("+2_before_-1") is True and mfe >= 1.5
        if is_glbd:
            glbd += 1
            react = reaction_df[reaction_df["signal_i"] == si]
            if len(react) and (react.iloc[0]["decision"] == "PASS" or react.iloc[0]["direction"] != orig):
                glbd_handled += 1
        if is_glgd:
            glgd += 1
            react = reaction_df[reaction_df["signal_i"] == si]
            if len(react) and react.iloc[0]["decision"] == "TAKE" and react.iloc[0]["direction"] == orig:
                glgd_preserved += 1
    return {
        "glbd_count": glbd,
        "glbd_handled_pct": glbd_handled / glbd if glbd else 0,
        "glgd_count": glgd,
        "glgd_preserved_pct": glgd_preserved / glgd if glgd else 0,
    }
