"""Phase61 — retrospective path classification and management diagnostics."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58b.research.simulation import metrics


def classify_paths(df: pd.DataFrame) -> pd.DataFrame:
    """Retrospective research labels only."""
    labels = []
    for _, r in df.iterrows():
        mfe = r["mfe_60m_atr"]
        mae = r["mae_60m_atr"]
        fin = r.get("final_ret_60m_atr", 0)
        rank = r.get("opp_rank", 1)
        chase = abs(r["entry_price"] - r.get("opp_created_price", r["entry_price"])) / r["atr"]

        if rank > 1 and chase > 1.0:
            labels.append("LATE_ENTRY")
        elif rank > 1:
            labels.append("DUPLICATE_SIGNAL")
        elif chase > 1.5:
            labels.append("CHASED_ENTRY")
        elif mfe >= 2.0 and mae < 0.75:
            labels.append("CLEAN_WINNER")
        elif mfe >= 2.0 and mae < 1.5:
            labels.append("WINNER_AFTER_SMALL_PULLBACK")
        elif mfe >= 2.0:
            labels.append("WINNER_AFTER_DEEP_PULLBACK")
        elif mfe >= 2.0 and fin < 0.5:
            labels.append("BIG_MFE_THEN_GIVEBACK")
        elif mfe >= 1.5 and fin < 0:
            labels.append("RIGHT_DIRECTION_BAD_STOP")
        elif fin < -0.5:
            labels.append("WRONG_DIRECTION")
        elif mfe < 0.5 and mae < 0.5:
            labels.append("CHOP")
        elif mfe < 1.0:
            labels.append("STALLED")
        elif mfe >= 1.0 and fin < 0:
            labels.append("REVERSAL_AFTER_PROFIT")
        else:
            labels.append("STALLED")
    out = df.copy()
    out["path_class"] = labels
    return out


def simulate_management(
    m1_hi: np.ndarray,
    m1_lo: np.ndarray,
    m1_cl: np.ndarray,
    m1_op: np.ndarray,
    trades: pd.DataFrame,
    stop_atr: float,
    target_r: float,
    max_hold: int = 60,
) -> pd.DataFrame:
    rows = []
    for _, t in trades.iterrows():
        j = int(t["entry_i"])
        ep = float(m1_op[j])
        a = float(t["atr"]) if t["atr"] > 0 else 1.0
        d = 1 if t["direction"] == "LONG" else -1
        stop = ep - d * stop_atr * a
        risk = stop_atr * a
        target = ep + d * target_r * risk
        exit_r = 0.0
        reason = "TIME"
        for k in range(j, min(j + max_hold, len(m1_cl))):
            hi, lo = m1_hi[k], m1_lo[k]
            if d == 1:
                if lo <= stop:
                    exit_r = -1.0
                    reason = "STOP"
                    break
                if hi >= target:
                    exit_r = target_r
                    reason = "TARGET"
                    break
            else:
                if hi >= stop:
                    exit_r = -1.0
                    reason = "STOP"
                    break
                if lo <= target:
                    exit_r = target_r
                    reason = "TARGET"
                    break
        else:
            c = m1_cl[min(j + max_hold - 1, len(m1_cl) - 1)]
            exit_r = (c - ep) * d / risk if risk > 0 else 0
        rows.append({"net_R": exit_r, "exit_reason": reason, "signal_i": t["signal_i"]})
    return pd.DataFrame(rows)


def management_matrix(
    m1_hi, m1_lo, m1_cl, m1_op, first_signals: pd.DataFrame
) -> dict:
    stops = [0.75, 1.0, 1.25]
    targets = [2.0, 2.5, 3.0]
    results = {}
    for s in stops:
        for t_r in targets:
            sim = simulate_management(m1_hi, m1_lo, m1_cl, m1_op, first_signals, s, t_r)
            m = metrics(sim["net_R"].values)
            results[f"stop_{s}_target_{t_r}"] = m
    return results


def giveback_audit(
    m1_hi: np.ndarray,
    m1_lo: np.ndarray,
    m1_cl: np.ndarray,
    m1_op: np.ndarray,
    trades: pd.DataFrame,
    stop_atr: float = 1.0,
    target_r: float = 2.5,
    max_hold: int = 60,
) -> dict:
    levels = [0.5, 1.0, 1.5, 2.0, 2.25]
    buckets = {lv: {"failed_after": 0, "winners_retraced": 0, "total_failed": 0, "total_winners": 0} for lv in levels}

    for _, t in trades.iterrows():
        j = int(t["entry_i"])
        ep = float(m1_op[j])
        a = float(t["atr"]) if t["atr"] > 0 else 1.0
        d = 1 if t["direction"] == "LONG" else -1
        risk = stop_atr * a
        stop = ep - d * stop_atr * a
        target = ep + d * target_r * risk
        max_r = -999.0
        hit_target = False
        stopped = False
        for k in range(j, min(j + max_hold, len(m1_cl))):
            hi, lo, cl = m1_hi[k], m1_lo[k], m1_cl[k]
            cur = (cl - ep) * d / risk if risk > 0 else 0
            fav = (hi - ep) * d / risk if d == 1 else (ep - lo) / risk
            max_r = max(max_r, fav)
            if d == 1 and lo <= stop:
                stopped = True
                break
            if d == -1 and hi >= stop:
                stopped = True
                break
            if d == 1 and hi >= target:
                hit_target = True
                break
            if d == -1 and lo <= target:
                hit_target = True
                break

        for lv in levels:
            if hit_target:
                buckets[lv]["total_winners"] += 1
                if max_r >= lv and not hit_target:
                    pass
                # winners that retraced: reached level before target but had drawdown below entry? simplified
                if max_r >= lv:
                    buckets[lv]["winners_retraced"] += 1
            elif stopped or not hit_target:
                buckets[lv]["total_failed"] += 1
                if max_r >= lv:
                    buckets[lv]["failed_after"] += 1

    report = {}
    n = len(trades)
    for lv in levels:
        b = buckets[lv]
        report[f"reached_{lv}R_then_failed"] = {
            "count": b["failed_after"],
            "pct_of_trades": b["failed_after"] / n if n else 0,
        }
        report[f"full_winners_retraced_through_{lv}R"] = {
            "count": b["winners_retraced"],
            "pct_of_winners": b["winners_retraced"] / max(1, b["total_winners"]),
        }
    return report
