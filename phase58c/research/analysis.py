"""Phase58C analysis tables and retention metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58c.research.evaluation import retention_tier


def trade_level_retention(trades_a: pd.DataFrame, trades_5m: pd.DataFrame, window: int = 30) -> dict:
    """Reproduce Phase58B trade-level winner retention."""
    winners = trades_a.loc[trades_a["net_R"] > 0]
    losers = trades_a.loc[trades_a["net_R"] <= 0]
    new_ei = trades_5m["entry_i"].astype(int).values
    new_d = trades_5m["direction"].values

    def _match(sub):
        cnt = 0
        for _, t in sub.iterrows():
            ei = int(t["entry_i"])
            d = t["direction"]
            mask = (new_d == d) & (np.abs(new_ei - ei) <= window)
            if mask.any():
                cnt += 1
        return cnt

    wr = _match(winners) / len(winners) * 100 if len(winners) else 0
    lr = _match(losers) / len(losers) * 100 if len(losers) else 0
    tr = _match(trades_a) / len(trades_a) * 100 if len(trades_a) else 0
    return {
        "1m_trade_retention_pct": tr,
        "1m_winner_retention_pct": wr,
        "1m_loser_retention_pct": lr,
        "1m_loser_removal_pct": 100 - lr,
    }


def opportunity_retention(opps_1m: pd.DataFrame, matches: pd.DataFrame, opps_1m_only: pd.DataFrame) -> pd.DataFrame:
    matched_ids = set(matches.loc[
        matches["classification"].isin(["SAME_OPPORTUNITY", "5M_EARLIER", "1M_EARLIER", "AMBIGUOUS_MATCH"]),
        "matched_opportunity_id",
    ])
    total = len(opps_1m)
    matched = sum(1 for o in opps_1m["opportunity_id"] if o in matched_ids)
    win_opps = opps_1m.loc[opps_1m["has_winner"]]
    win_matched = sum(1 for o in win_opps["opportunity_id"] if o in matched_ids)
    rows = [{
        "metric": "overall_opportunity_retention_pct",
        "value": matched / total * 100 if total else 0,
        "numerator": matched,
        "denominator": total,
    }, {
        "metric": "winning_opportunity_retention_pct",
        "value": win_matched / len(win_opps) * 100 if len(win_opps) else 0,
        "numerator": win_matched,
        "denominator": len(win_opps),
    }, {
        "metric": "1m_only_opportunities",
        "value": int((opps_1m_only["5m_match"] == "1M_ONLY").sum()),
        "numerator": int((opps_1m_only["5m_match"] == "1M_ONLY").sum()),
        "denominator": total,
    }, {
        "metric": "5m_only_takes",
        "value": int((matches["classification"] == "5M_ONLY").sum()),
        "numerator": int((matches["classification"] == "5M_ONLY").sum()),
        "denominator": len(matches),
    }]
    return pd.DataFrame(rows)


def redundant_signal_analysis(opps_1m: pd.DataFrame, total_trades: int) -> pd.DataFrame:
    sig_counts = opps_1m["signal_count"]
    redundant = int(sig_counts.sum() - len(opps_1m))
    return pd.DataFrame([{
        "total_1m_trades": total_trades,
        "total_opportunity_clusters": len(opps_1m),
        "mean_signals_per_opportunity": float(sig_counts.mean()),
        "median_signals_per_opportunity": float(sig_counts.median()),
        "p90_signals_per_opportunity": float(sig_counts.quantile(0.9)),
        "max_signals_per_opportunity": int(sig_counts.max()),
        "redundant_signals": redundant,
        "redundant_signal_pct": redundant / total_trades * 100 if total_trades else 0,
        "redundant_signal_ratio": total_trades / len(opps_1m) if len(opps_1m) else 0,
    }])


def timing_stats(matches: pd.DataFrame, opps_1m: pd.DataFrame) -> pd.DataFrame:
    rows = []
    opp_map = opps_1m.set_index("opportunity_id")
    lags_arm = []
    lags_take_first = []
    lags_take_nearest = []
    for _, m in matches.iterrows():
        oid = m["matched_opportunity_id"]
        if not oid or oid not in opp_map.index:
            continue
        o = opp_map.loc[oid]
        lags_arm.append(int(m["5m_arm_m1_i"]) - int(o["first_signal_i"]))
        lags_take_first.append(int(m["5m_take_m1_i"]) - int(o["first_signal_i"]))
        lags_take_nearest.append(int(m["5m_take_m1_i"]) - int(o["first_signal_i"]))
    for name, arr in [
        ("arm_vs_first_1m", lags_arm),
        ("take_vs_first_1m", lags_take_first),
        ("take_vs_nearest_1m", lags_take_nearest),
    ]:
        if not arr:
            continue
        a = np.array(arr, dtype=float)
        rows.append({
            "metric": name,
            "median": float(np.median(a)),
            "mean": float(np.mean(a)),
            "p25": float(np.percentile(a, 25)),
            "p75": float(np.percentile(a, 75)),
            "p90": float(np.percentile(a, 90)),
            "n": len(a),
        })
    return pd.DataFrame(rows)


def price_comparison(matches: pd.DataFrame, opps_1m: pd.DataFrame, trades_1m: pd.DataFrame, atr: np.ndarray) -> pd.DataFrame:
    from phase58c.research.evaluation import price_bucket

    opp_map = opps_1m.set_index("opportunity_id")
    trade_first = trades_1m.sort_values("signal_i").groupby("opportunity_id").first()
    rows = []
    for _, m in matches.iterrows():
        oid = m["matched_opportunity_id"]
        if not oid or oid not in opp_map.index or oid not in trade_first.index:
            continue
        tf = trade_first.loc[oid]
        si = int(tf["signal_i"])
        a = atr[si] if si < len(atr) and np.isfinite(atr[si]) and atr[si] > 0 else 1.0
        p5 = float(m["5m_take_price"])
        p1 = float(tf["entry_price"])
        d = m["direction"]
        diff = (p1 - p5) / a if d == "LONG" else (p5 - p1) / a
        rows.append({
            "setup_id": m["setup_id"],
            "opportunity_id": oid,
            "direction": d,
            "price_diff_atr": diff,
            "price_diff_ticks": (p1 - p5) / 0.25,
            "bucket": price_bucket(diff),
        })
    return pd.DataFrame(rows)


def meaningful_move_recall(
    opps_1m: pd.DataFrame,
    labels_1m: pd.DataFrame,
    takes_5m: pd.DataFrame,
    labels_5m: pd.DataFrame,
    threshold: float = 1.0,
    horizon: int = 60,
) -> pd.DataFrame:
    col = f"meaningful_{threshold}atr_{horizon}m"
    rows = []
    if col in labels_1m.columns:
        meaningful_1m = set(labels_1m.loc[labels_1m[col], "opportunity_id"])
        rows.append({
            "system": "Phase58_1M",
            "meaningful_opportunities": len(meaningful_1m),
            "total_opportunities": len(opps_1m),
            "recall_pct": len(meaningful_1m) / len(opps_1m) * 100 if len(opps_1m) else 0,
            "threshold_atr": threshold,
            "horizon_min": horizon,
        })
    if not labels_5m.empty and col in labels_5m.columns:
        rows.append({
            "system": "Phase58B_5M",
            "meaningful_opportunities": int(labels_5m[col].sum()),
            "total_opportunities": len(labels_5m),
            "recall_pct": labels_5m[col].mean() * 100,
            "threshold_atr": threshold,
            "horizon_min": horizon,
        })
    return pd.DataFrame(rows)


def clustering_sensitivity(trades: pd.DataFrame, armed_i: np.ndarray, minutes: list[int]) -> pd.DataFrame:
    from phase58c.research.clustering import cluster_by_time_gap, cluster_1m_opportunities, summarize_opportunities

    struct = cluster_1m_opportunities(trades, armed_i)
    struct_opps = len(struct["opportunity_id"].unique())
    rows = [{"method": "structural", "clusters": struct_opps, "mean_signals": len(trades) / struct_opps if struct_opps else 0}]
    for m in minutes:
        c = cluster_by_time_gap(trades, m)
        n = c["opportunity_id"].nunique()
        rows.append({"method": f"time_{m}m", "clusters": n, "mean_signals": len(trades) / n if n else 0})
    return pd.DataFrame(rows)


def year_stability(trades_1m: pd.DataFrame, opps_1m: pd.DataFrame, matches: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.DataFrame:
    trades_1m = trades_1m.copy()
    trades_1m["year"] = [idx[int(i)].year for i in trades_1m["entry_i"]]
    opps_1m = opps_1m.copy()
    opps_1m["year"] = [idx[int(i)].year for i in opps_1m["first_signal_i"]]
    matched_ids = set(matches.loc[
        matches["classification"].isin(["SAME_OPPORTUNITY", "5M_EARLIER", "1M_EARLIER", "AMBIGUOUS_MATCH"]),
        "matched_opportunity_id",
    ])
    rows = []
    for y, g in opps_1m.groupby("year"):
        m = sum(1 for o in g["opportunity_id"] if o in matched_ids)
        w = g.loc[g["has_winner"]]
        wm = sum(1 for o in w["opportunity_id"] if o in matched_ids)
        t_y = trades_1m.loc[trades_1m["year"] == y]
        rows.append({
            "year": y,
            "1m_trades": len(t_y),
            "1m_opportunities": len(g),
            "5m_matched_opportunities": m,
            "opportunity_retention_pct": m / len(g) * 100 if len(g) else 0,
            "winning_opportunity_retention_pct": wm / len(w) * 100 if len(w) else 0,
            "redundant_signal_rate": 1 - len(g) / len(t_y) if len(t_y) else 0,
        })
    return pd.DataFrame(rows)


def build_retention_table(
    trade_ret: dict,
    opp_ret: pd.DataFrame,
    redundant: pd.DataFrame,
    timing: pd.DataFrame,
    meaningful: pd.DataFrame,
) -> pd.DataFrame:
    def _get(metric):
        r = opp_ret.loc[opp_ret["metric"] == metric]
        return float(r["value"].iloc[0]) if len(r) else 0

    red = redundant.iloc[0] if len(redundant) else {}
    med_arm = timing.loc[timing["metric"] == "arm_vs_first_1m", "median"]
    med_take = timing.loc[timing["metric"] == "take_vs_first_1m", "median"]
    mm = meaningful.loc[meaningful["system"] == "Phase58B_5M", "recall_pct"]

    rows = [
        ("1M trade retention", trade_ret.get("1m_trade_retention_pct", 0)),
        ("1M winner retention", trade_ret.get("1m_winner_retention_pct", 0)),
        ("1M loser removal", trade_ret.get("1m_loser_removal_pct", 0)),
        ("Opportunity retention", _get("overall_opportunity_retention_pct")),
        ("Winning opportunity retention", _get("winning_opportunity_retention_pct")),
        ("Meaningful move retention (5M)", float(mm.iloc[0]) if len(mm) else 0),
        ("Redundant 1M signals removed %", red.get("redundant_signal_pct", 0)),
        ("Median 5M ARM lead/lag (bars)", float(med_arm.iloc[0]) if len(med_arm) else 0),
        ("Median 5M TAKE lead/lag (bars)", float(med_take.iloc[0]) if len(med_take) else 0),
    ]
    return pd.DataFrame(rows, columns=["metric", "result"])
