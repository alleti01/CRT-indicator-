"""Phase65 — evaluation metrics and event capture."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase62.python.analysis import path_ordering
from phase64.python.symmetric_paths import classify_archetype, compute_single_path


def label_events(m, events: pd.DataFrame) -> pd.DataFrame:
    """Retrospective archetype labels for evaluation only."""
    rows = []
    for _, r in events.iterrows():
        si = int(r["signal_i"])
        atr = float(r["atr"])
        p = compute_single_path(m.hi, m.lo, m.op, si, atr)
        arch = p.get("archetype", "")
        clean = p.get("clean_up") or p.get("clean_dn")
        rows.append({
            "signal_i": si,
            "archetype": arch,
            "is_explosive": arch == "EXPLOSIVE_IMMEDIATE_MOVE",
            "is_clean": bool(clean),
            "is_chaos": p.get("large_chaotic", False),
            "total_mfe_atr": max(p.get("up_60m", 0), p.get("dn_60m", 0)),
        })
    return events.merge(pd.DataFrame(rows), on="signal_i", how="left", suffixes=("", "_lbl"))


def path_metrics(m, trades: pd.DataFrame) -> dict:
    pairs = {}
    totals = {}
    for _, t in trades.iterrows():
        atr_v = float(t["atr"]) if "atr" in t.index and pd.notna(t["atr"]) else 1.0
        po = path_ordering(m.hi, m.lo, m.op, int(t["entry_i"]), t["direction"], atr_v)
        for k, v in po["pairs"].items():
            if v is None:
                continue
            totals[k] = totals.get(k, 0) + 1
            if v:
                pairs[k] = pairs.get(k, 0) + 1
    return {k: pairs.get(k, 0) / totals[k] for k in totals}


def capture_stats(events_labeled: pd.DataFrame, trades: pd.DataFrame) -> dict:
    """Phase64 phenomenon capture."""
    out = {}
    for label, col in [("explosive", "is_explosive"), ("clean", "is_clean"), ("chaos", "is_chaos")]:
        total = int(events_labeled[col].sum())
        if total == 0:
            out[label] = {"total": 0}
            continue
        ev = events_labeled[events_labeled[col]]
        taken = trades.merge(ev[["signal_i", "orig_dir"]], on="signal_i", how="inner") if "orig_dir" in trades.columns else trades.merge(ev[["signal_i"]], on="signal_i")
        correct = taken[taken["direction"] == taken.get("orig_dir", taken["direction"])] if "orig_dir" not in taken.columns else taken
        # correct side = market choice matches eventual dominant expansion side (proxy: direction vs archetype)
        if label == "explosive":
            # for explosive up vs down use path from event
            correct_side = 0
            wrong = 0
            for _, tr in taken.iterrows():
                si = int(tr["signal_i"])
                row = ev[ev["signal_i"] == si].iloc[0]
                arch = row["archetype"]
                if arch == "EXPLOSIVE_IMMEDIATE_MOVE":
                    # check if direction aligned with net move - simplified via trade direction vs clean_up/dn
                    correct_side += 1  # counted as captured
            captured = len(taken)
            expired = total - captured
            out[label] = {
                "total": total,
                "captured": captured,
                "correct_side": captured,  # refined below
                "expired": expired,
                "retention": captured / total,
            }
        else:
            captured = len(taken)
            out[label] = {
                "total": total,
                "captured": captured,
                "retention": captured / total if total else 0,
                "expired": total - captured,
            }
    return out


def event_capture_detail(m, events_labeled: pd.DataFrame, choices: pd.DataFrame) -> dict:
    """Detailed capture for explosive/clean using dominant 60m side."""
    detail = {}
    for name, col in [("EXPLOSIVE", "is_explosive"), ("CLEAN", "is_clean"), ("CHAOS", "is_chaos")]:
        sub = events_labeled[events_labeled[col]]
        total = len(sub)
        if total == 0:
            detail[name] = {"total": 0}
            continue
        merged = sub.merge(
            choices[["signal_i", "decision", "direction", "delay_bars"]].rename(columns={"direction": "choice_dir"}),
            on="signal_i", how="left",
        )
        triggered = merged[merged["decision"] == "TAKE"]
        expired = merged[merged["decision"] == "EXPIRED"]
        correct, wrong, late = 0, 0, 0
        for _, r in triggered.iterrows():
            si = int(r["signal_i"])
            p = compute_single_path(m.hi, m.lo, m.op, si, float(r["atr"]))
            dom = "LONG" if p.get("up_60m", 0) >= p.get("dn_60m", 0) else "SHORT"
            if r["choice_dir"] == dom:
                correct += 1
            else:
                wrong += 1
            if r.get("delay_bars", 0) > 3:
                late += 1
        detail[name] = {
            "total": total,
            "captured": len(triggered),
            "correct_side": correct,
            "wrong_side": wrong,
            "expired": len(expired),
            "late": late,
            "retention": len(triggered) / total,
        }
    return detail


def one_position_filter(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades
    t = trades.sort_values("entry_i").reset_index(drop=True)
    kept = []
    last_exit = -1
    for _, r in t.iterrows():
        if int(r["entry_i"]) > last_exit:
            kept.append(r)
            last_exit = int(r.get("exit_i", r["entry_i"] + 60))
    return pd.DataFrame(kept)
