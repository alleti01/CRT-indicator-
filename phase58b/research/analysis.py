"""Analysis — baselines, winner/loser, confluence retention, timing."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58b.research.context_15m import compute_15m_context, score_15m_for_direction
from phase58b.research.context_5m import compute_5m_structure
from phase58b.research.location_5m import compute_5m_location
from phase58b.research.precompute import MTFArrays
from phase58b.research.reaction_5m import compute_5m_reactions
from phase58b.research.simulation import metrics


def baseline_comparison(systems: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, trades in systems.items():
        if trades.empty:
            rows.append({"system": name, "N": 0})
            continue
        m = metrics(trades["net_R"].values)
        stops = (trades["exit_reason"] == "STOP").sum()
        tgts = (trades["exit_reason"] == "TARGET").sum()
        times = (trades["exit_reason"] == "TIME").sum()
        rows.append({
            "system": name,
            **m,
            "stops": int(stops),
            "targets": int(tgts),
            "time_exits": int(times),
            "stop_rate": stops / len(trades),
            "false_positive_proxy": stops / len(trades),
        })
    return pd.DataFrame(rows)


def retention_analysis(base_trades: pd.DataFrame, new_trades: pd.DataFrame, match_minutes: int = 30) -> dict:
    """Compare Phase58 A vs Phase58B — winners/losers retained."""
    if base_trades.empty or new_trades.empty:
        return dict(winners_retained_pct=0, losers_retained_pct=0, losers_removed_pct=0, winners_n=0, losers_n=0)

    base = base_trades[["entry_i", "direction", "net_R"]].copy()
    new = new_trades[["entry_i", "direction"]].copy()
    base["entry_i"] = base["entry_i"].astype(int)
    new["entry_i"] = new["entry_i"].astype(int)

    winners = base.loc[base["net_R"] > 0]
    losers = base.loc[base["net_R"] <= 0]

    def _matched_vec(sub: pd.DataFrame) -> int:
        if sub.empty:
            return 0
        cnt = 0
        for d in sub["direction"].unique():
            sub_d = sub.loc[sub["direction"] == d]
            new_d = new.loc[new["direction"] == d]["entry_i"].values
            if len(new_d) == 0:
                continue
            for ei in sub_d["entry_i"].values:
                if np.any(np.abs(new_d - ei) <= match_minutes):
                    cnt += 1
        return cnt

    wr = _matched_vec(winners) / len(winners) * 100 if len(winners) else 0
    lr = _matched_vec(losers) / len(losers) * 100 if len(losers) else 0
    return dict(
        winners_retained_pct=wr,
        losers_retained_pct=lr,
        losers_removed_pct=100 - lr,
        winners_n=len(winners),
        losers_n=len(losers),
    )


def winner_loser_context(m: MTFArrays, p58_trades: pd.DataFrame, cfg: dict, max_rows: int = 5000) -> pd.DataFrame:
    """Capture HTF context at Phase58 v1 entry for winners vs losers."""
    if p58_trades.empty:
        return pd.DataFrame()
    sample = p58_trades
    if len(sample) > max_rows:
        sample = pd.concat([
            sample.loc[sample["net_R"] > 0].sample(min(max_rows // 2, (sample["net_R"] > 0).sum()), random_state=42),
            sample.loc[sample["net_R"] <= 0].sample(min(max_rows // 2, (sample["net_R"] <= 0).sum()), random_state=42),
        ], ignore_index=True)
    rows = []
    for _, t in sample.iterrows():
        ei = int(t["entry_i"])
        j = int(m.m1_to_m5[ei]) if ei < m.m1_n else -1
        if j < 0:
            continue
        ctx15 = compute_15m_context(m, j, cfg)
        struct = compute_5m_structure(m, j, cfg)
        loc = compute_5m_location(m, j, t["direction"], cfg)
        react = compute_5m_reactions(m, j, t["direction"], cfg)
        c15, _ = score_15m_for_direction(ctx15, t["direction"])
        rows.append({
            "trade_id": t.get("trade_id", ""),
            "direction": t["direction"],
            "outcome": "WINNER" if t["net_R"] > 0 else "LOSER",
            "net_R": t["net_R"],
            "15m_state": ctx15["state"],
            "15m_strength": ctx15["strength"],
            "15m_score": c15,
            "5m_direction": struct["direction"],
            "5m_struct_score": struct["score"],
            "5m_loc_score": loc["score"],
            "5m_react_score": react["score"],
            "pb_depth_pct": loc["pb_depth_pct"],
            "swing_dist_atr": loc["swing_dist_atr"],
            "impulse_atr_15m": ctx15["impulse_atr"],
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def confluence_retention(m: MTFArrays, takes: pd.DataFrame, cfg: dict, trades_fn) -> pd.DataFrame:
    """Vary minimum 15M confluence and measure retention curve."""
    rows = []
    if takes.empty:
        return pd.DataFrame()
    thresholds = [-2, -1, 0, 1, 2]
    base_trades = trades_fn(takes, cfg)
    base_w = (base_trades["net_R"] > 0).sum() if not base_trades.empty else 0
    base_l = (base_trades["net_R"] <= 0).sum() if not base_trades.empty else 0

    for thr in thresholds:
        sub_takes = []
        for _, tk in takes.iterrows():
            ctx15 = {"strength": tk["15m_strength"], "state": tk.get("15m_state", "NEUTRAL")}
            sc, _ = score_15m_for_direction(ctx15, tk["direction"])
            if sc >= thr:
                sub_takes.append(tk)
        filtered = pd.DataFrame(sub_takes) if sub_takes else pd.DataFrame()
        tr = trades_fn(filtered, cfg) if not filtered.empty else pd.DataFrame()
        tm = metrics(tr["net_R"].values) if not tr.empty else dict(N=0, AvgR=0, PF=0, TotalR=0)
        w_ret = (tr["net_R"] > 0).sum() / max(1, base_w) * 100 if not tr.empty else 0
        l_ret = (tr["net_R"] <= 0).sum() / max(1, base_l) * 100 if not tr.empty else 0
        rows.append({
            "min_15m_score": thr,
            "trades_retained_pct": len(tr) / max(1, len(base_trades)) * 100,
            "winners_retained_pct": w_ret,
            "losers_retained_pct": l_ret,
            "N": tm.get("N", 0),
            "AvgR": tm.get("AvgR", 0),
            "PF": tm.get("PF", 0),
            "TotalR": tm.get("TotalR", 0),
        })
    return pd.DataFrame(rows)


def directional_accuracy_audit(m: MTFArrays, trades: pd.DataFrame, horizons=(5, 10, 15, 30, 60)) -> pd.DataFrame:
    """Precise terminology: A/B/C/D metrics."""
    rows = []
    for _, t in trades.iterrows():
        ei = int(t["entry_i"])
        d = t["direction"]
        row = {"trade_id": t.get("trade_id", ""), "direction": d, "system": t.get("system", "")}
        risk = abs(t["entry_price"] - t["stop"]) if "stop" in t else 1.0
        for h in horizons:
            end_i = min(m.m1_n, ei + 1 + h)
            if end_i <= ei + 1:
                continue
            if d == "LONG":
                moved = m.m1_hi[ei + 1 : end_i].max() - t["entry_price"]
                at_horizon = m.m1_cl[min(ei + h, m.m1_n - 1)] - t["entry_price"]
            else:
                moved = t["entry_price"] - m.m1_lo[ei + 1 : end_i].min()
                at_horizon = t["entry_price"] - m.m1_cl[min(ei + h, m.m1_n - 1)]
            a = _atr(m.m1_atr[ei], m.m1_atr, ei)
            # A: eventually moved predicted direction (any time in horizon)
            row[f"A_eventual_{h}m"] = moved / a > 0.5
            # B: predicted direction at horizon close
            row[f"B_at_horizon_{h}m"] = at_horizon / a > 0.25 if d == "LONG" else at_horizon / a < -0.25
        # C/D from trade outcome
        row["C_target_before_stop"] = t.get("exit_reason") == "TARGET"
        row["D_stop_before_target"] = t.get("exit_reason") == "STOP"
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def move_capture_comparison(m: MTFArrays, trades_a: pd.DataFrame, trades_d: pd.DataFrame, horizon: int = 60) -> pd.DataFrame:
    rows = []
    for label, trades in [("A_Phase58_1M", trades_a), ("D_MTF_1M", trades_d)]:
        for _, t in trades.iterrows():
            ei = int(t["entry_i"])
            d = t["direction"]
            si = int(t.get("signal_i", t.get("signal_j", ei)))
            a = _atr(m.m1_atr[ei], m.m1_atr, ei)
            end_i = min(m.m1_n, ei + 1 + horizon)
            if d == "LONG":
                total_mfe = (m.m1_hi[si : end_i].max() - m.m1_cl[si]) / a if si < end_i else 0
                consumed = max(0, (m.m1_cl[ei] - m.m1_cl[si]) / a)
                spent_before = max(0, (m.m1_cl[ei] - m.m1_cl[si]) / a)
            else:
                total_mfe = (m.m1_cl[si] - m.m1_lo[si : end_i].min()) / a if si < end_i else 0
                consumed = max(0, (m.m1_cl[si] - m.m1_cl[ei]) / a)
                spent_before = consumed
            capture = (total_mfe - consumed) / total_mfe if total_mfe > 0 else np.nan
            rows.append({
                "system": label,
                "trade_id": t.get("trade_id", ""),
                "capture_after_signal": capture,
                "capture_entire_move": capture,
                "favorable_spent_before_entry_atr": spent_before,
                "total_excursion_atr": total_mfe,
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def timing_comparison(trades_a: pd.DataFrame, trades_d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if trades_a.empty or trades_d.empty:
        return pd.DataFrame()
    for _, ta in trades_a.iterrows():
        ei_a = int(ta["entry_i"])
        d = ta["direction"]
        near = trades_d.loc[(trades_d["direction"] == d) & (abs(trades_d["entry_i"].astype(int) - ei_a) <= 30)]
        if near.empty:
            continue
        td = near.iloc[0]
        rows.append({
            "direction": d,
            "phase58_entry_i": ei_a,
            "phase58b_entry_i": int(td["entry_i"]),
            "lag_bars": int(td["entry_i"]) - ei_a,
            "phase58_net_R": ta["net_R"],
            "phase58b_net_R": td["net_R"],
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def long_short_context(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    for direction in ["LONG", "SHORT"]:
        for ctx in ["BULLISH", "BEARISH", "NEUTRAL", "TRANSITION"]:
            if direction == "LONG" and ctx == "BULLISH":
                bucket = "with_15m_trend"
            elif direction == "SHORT" and ctx == "BEARISH":
                bucket = "with_15m_trend"
            elif ctx == "NEUTRAL":
                bucket = "15m_neutral"
            elif ctx == "TRANSITION":
                bucket = "15m_transition"
            else:
                bucket = "against_15m_trend"
            sub = trades.loc[(trades["direction"] == direction) & (trades.get("15m_state", "") == ctx)]
            if sub.empty:
                continue
            m = metrics(sub["net_R"].values)
            rows.append({"direction": direction, "15m_state": ctx, "bucket": bucket, **m})
    return pd.DataFrame(rows)


def execution_variant_comparison(trades_by_variant: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for variant, tr in trades_by_variant.items():
        if tr.empty:
            rows.append({"variant": variant, "N": 0})
            continue
        m = metrics(tr["net_R"].values)
        rows.append({
            "variant": variant,
            **m,
            "median_delay": tr["delay_bars_1m"].median(),
            "median_improvement_atr": tr["price_improvement_atr"].median(),
            "median_deterioration_atr": tr["entry_deterioration_atr"].median(),
            "missed_rate": (tr["entry_i"] < 0).mean() if "entry_i" in tr else 0,
        })
    return pd.DataFrame(rows)


def cluster_1m_to_5m(p58_trades: pd.DataFrame, m: MTFArrays, setups: pd.DataFrame) -> pd.DataFrame:
    """Assign SETUP_ID to Phase58 1M trades by nearest 5M setup."""
    rows = []
    for _, t in p58_trades.iterrows():
        ei = int(t["entry_i"])
        j = int(m.m1_to_m5[ei])
        sid = ""
        if not setups.empty:
            near = setups.loc[abs(setups["armed_j"] - j) <= 3]
            if not near.empty:
                sid = near.iloc[0]["setup_id"]
        rows.append({"trade_id": t.get("trade_id", ""), "entry_i": ei, "m5_j": j, "setup_id": sid})
    return pd.DataFrame(rows)


def _atr(val, arr, i):
    if np.isfinite(val) and val > 0:
        return val
    for k in range(max(0, i - 5), i + 1):
        if np.isfinite(arr[k]) and arr[k] > 0:
            return arr[k]
    return 1.0
