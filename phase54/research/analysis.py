"""Episode metrics and analysis tables."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase53.research.metrics import max_dd, pf, summarize_r


def episode_metrics(retained: pd.DataFrame, raw: pd.DataFrame) -> dict:
    sm = summarize_r(retained.rename(columns={"timestamp_ct": "timestamp_ct"}))
    days = max((pd.to_datetime(retained["timestamp_ct"]).max() - pd.to_datetime(retained["timestamp_ct"]).min()).days, 1)
    raw_days = max((pd.to_datetime(raw["timestamp_ct"]).max() - pd.to_datetime(raw["timestamp_ct"]).min()).days, 1)
    unauth = retained.loc[retained["core_authorized"] == 0] if "core_authorized" in retained.columns else pd.DataFrame()
    long = retained.loc[retained["direction"] == "LONG"]
    short = retained.loc[retained["direction"] == "SHORT"]
    return {
        "N": len(retained),
        "events_day": len(raw) / raw_days,
        "episodes_day": len(retained) / days,
        "AvgR": sm.get("AvgR"),
        "PF": sm.get("PF"),
        "TotalR": sm.get("TotalR"),
        "MaxDD": sm.get("MaxDD"),
        "LONG_AvgR": float(long["net_R"].mean()) if len(long) else np.nan,
        "SHORT_AvgR": float(short["net_R"].mean()) if len(short) else np.nan,
        "CORE_UNAUTH_AvgR": float(unauth["net_R"].mean()) if len(unauth) else np.nan,
        "CORE_UNAUTH_PF": pf(unauth["net_R"]) if len(unauth) else np.nan,
    }


def duplication_table(raw: pd.DataFrame, retained: pd.DataFrame, suppressed: pd.DataFrame) -> pd.DataFrame:
    """Map each retained episode to count of raw events in its cluster."""
    # approximate: episode size = 1 + suppressed between retained events
    ev = raw.sort_values("timestamp_ct").reset_index(drop=True)
    ret = retained.sort_values("timestamp_ct").reset_index(drop=True)
    sizes: list[int] = []
    ri = 0
    for i, row in ev.iterrows():
        if ri < len(ret) and row["event_id"] == ret.iloc[ri]["event_id"]:
            # count until next retained
            cnt = 1
            j = i + 1
            while j < len(ev) and (ri + 1 >= len(ret) or ev.iloc[j]["event_id"] != ret.iloc[ri + 1]["event_id"]):
                if ri + 1 < len(ret) and ev.iloc[j]["event_id"] == ret.iloc[ri + 1]["event_id"]:
                    break
                cnt += 1
                j += 1
            sizes.append(min(cnt, 20))
            ri += 1
    # simpler bucket from merge
    rows = []
    if not suppressed.empty and not retained.empty:
        total_per = []
        idx = 0
        sup_list = suppressed["event_id"].tolist() if not suppressed.empty else []
        for _, r in retained.iterrows():
            cnt = 1
            idx += 1
            total_per.append(cnt)
        # use time-based clustering estimate from gap
        gaps = ret["timestamp_ct"].diff().dt.total_seconds() / 60 if len(ret) > 1 else pd.Series([999])
        for bucket in (1, 2, 3, 4, 5):
            pass
    # Direct: group raw top10 by episode assignment via consolidate output
    if "episode_id" in raw.columns:
        grp = raw.groupby("episode_id")
    else:
        # assign via merge on retained episode windows - use suppressed count +1
        ep_sizes = []
        all_sorted = pd.concat([retained.assign(suppressed=False), suppressed.assign(suppressed=True)]).sort_values("timestamp_ct")
        cur_ep = None
        cur_size = 0
        ep_map: dict[str, int] = {}
        for _, r in all_sorted.iterrows():
            if not r.get("suppressed", False):
                if cur_ep and cur_size:
                    ep_map[cur_ep] = cur_size
                cur_ep = r.get("episode_id")
                cur_size = 1
            else:
                cur_size += 1
        if cur_ep:
            ep_map[cur_ep] = cur_size
        buckets = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        bucket_avgr_first: dict[int, list] = {k: [] for k in buckets}
        bucket_avgr_sup: dict[int, list] = {k: [] for k in buckets}
        for ep_id, sz in ep_map.items():
            b = 5 if sz >= 5 else sz
            buckets[b] = buckets.get(b, 0) + 1
            sub = all_sorted.loc[all_sorted.get("episode_id", pd.Series()) == ep_id] if "episode_id" in all_sorted.columns else pd.DataFrame()
        rows = []
        for b in (1, 2, 3, 4, 5):
            label = f"{b}" if b < 5 else "5+"
            cnt = sum(1 for s in ep_map.values() if (s if s < 5 else 5) == b or (b == 5 and s >= 5))
            rows.append({"EVENTS_PER_EPISODE": label, "EPISODE_COUNT": cnt, "PERCENT": np.nan})
        return pd.DataFrame(rows)
    return pd.DataFrame()


def duplication_from_labels(retained: pd.DataFrame, suppressed: pd.DataFrame) -> pd.DataFrame:
    """Episode size = 1 + suppressed sharing episode_id pattern via order."""
    combined = pd.concat(
        [
            retained.assign(_role="first"),
            suppressed.assign(_role="sup") if not suppressed.empty else pd.DataFrame(),
        ]
    ).sort_values("timestamp_ct")
    # rebuild episode sizes by scanning
    sizes: list[int] = []
    cur = 0
    for _, r in combined.iterrows():
        if r["_role"] == "first":
            if cur:
                sizes.append(cur)
            cur = 1
        else:
            cur += 1
    if cur:
        sizes.append(cur)
    rows = []
    total = len(sizes) or 1
    sup_rs = suppressed["net_R"].astype(float) if not suppressed.empty else pd.Series(dtype=float)
    for label, cond in [("1", lambda s: s == 1), ("2", lambda s: s == 2), ("3", lambda s: s == 3), ("4", lambda s: s == 4), ("5+", lambda s: s >= 5)]:
        idxs = [i for i, s in enumerate(sizes) if cond(s)]
        cnt = len(idxs)
        first_avgs = [float(retained.iloc[i]["net_R"]) for i in idxs if i < len(retained)]
        rows.append(
            {
                "EVENTS_PER_EPISODE": label,
                "EPISODE_COUNT": cnt,
                "PERCENT": cnt / total,
                "AVGR_OF_FIRST_EVENT": float(np.mean(first_avgs)) if first_avgs else np.nan,
                "AVGR_OF_SUPPRESSED": float(sup_rs.mean()) if len(sup_rs) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def year_table(raw_d10: pd.DataFrame, episodes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    raw_ts = pd.to_datetime(raw_d10["timestamp_ct"])
    ep_ts = pd.to_datetime(episodes["timestamp_ct"])
    for yr in sorted(raw_ts.dt.year.unique()):
        rsub = raw_d10.loc[raw_ts.dt.year == yr]
        esub = episodes.loc[ep_ts.dt.year == yr]
        if len(rsub) < 10:
            continue
        days = max((rsub["timestamp_ct"].max() - rsub["timestamp_ct"].min()).days, 1)
        edays = max((esub["timestamp_ct"].max() - esub["timestamp_ct"].min()).days, 1) if len(esub) else 1
        rs = rsub["net_R"].astype(float)
        es = esub["net_R"].astype(float) if len(esub) else pd.Series(dtype=float)
        rows.append(
            {
                "YEAR": yr,
                "RAW_D10_EVENTS_DAY": len(rsub) / days,
                "RAW_D10_AVGR": float(rs.mean()),
                "EPISODES_DAY": len(esub) / edays if len(esub) else 0,
                "EPISODE_AVGR": float(es.mean()) if len(es) else np.nan,
                "EPISODE_PF": pf(es) if len(es) else np.nan,
                "MAXDD": max_dd(es) if len(es) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def time_between_events(events: pd.DataFrame) -> pd.DataFrame:
    ev = events.sort_values("timestamp_ct").reset_index(drop=True)
    same_gaps, opp_gaps = [], []
    for i in range(1, len(ev)):
        gap = (pd.Timestamp(ev.iloc[i]["timestamp_ct"]) - pd.Timestamp(ev.iloc[i - 1]["timestamp_ct"])).total_seconds() / 60.0
        if ev.iloc[i]["direction"] == ev.iloc[i - 1]["direction"]:
            same_gaps.append(gap)
        else:
            opp_gaps.append(gap)
    def bucket(gaps):
        bins = [(0, 2), (3, 5), (6, 10), (11, 15), (16, 30), (31, 60), (61, 9999)]
        rows = []
        for lo, hi in bins:
            c = sum(1 for g in gaps if lo <= g <= hi)
            rows.append({"bucket": f"{lo}-{hi if hi < 9999 else '+'}", "count": c, "pct": c / len(gaps) if gaps else 0})
        return rows
    return pd.DataFrame(
        [{"type": "same_dir", **r} for r in bucket(same_gaps)] + [{"type": "opposite_dir", **r} for r in bucket(opp_gaps)]
    )


def session_bucket_from_row(row: pd.Series) -> str:
    m = int(row.get("session_minute", 0) or 0)
    if m < 9 * 60 + 30 or m >= 16 * 60:
        return "other"
    if m < 10 * 60 + 30:
        return "open"
    if m < 11 * 60 + 30:
        return "morning"
    if m < 13 * 60 + 30:
        return "midday"
    if m < 15 * 60:
        return "afternoon"
    return "close"


def session_breakdown(episodes: pd.DataFrame) -> pd.DataFrame:
    ep = episodes.copy()
    ep["session_bucket"] = ep.apply(session_bucket_from_row, axis=1)
    rows = []
    days = max((pd.to_datetime(ep["timestamp_ct"]).max() - pd.to_datetime(ep["timestamp_ct"]).min()).days, 1)
    for seg in ("open", "morning", "midday", "afternoon", "close"):
        sub = ep.loc[ep["session_bucket"] == seg]
        if sub.empty:
            continue
        rows.append({"segment": seg, "N": len(sub), "episodes_day": len(sub) / days, **summarize_r(sub)})
    return pd.DataFrame(rows)


def volatility_regime(episodes: pd.DataFrame, train: pd.DataFrame) -> pd.DataFrame:
    if "atr_ratio" not in episodes.columns or "atr_ratio" not in train.columns:
        return pd.DataFrame()
    q1, q2 = train["atr_ratio"].dropna().quantile(0.33), train["atr_ratio"].dropna().quantile(0.66)
    rows = []
    days = max((pd.to_datetime(episodes["timestamp_ct"]).max() - pd.to_datetime(episodes["timestamp_ct"]).min()).days, 1)
    for label, mask in (
        ("LOW", episodes["atr_ratio"] <= q1),
        ("MEDIUM", (episodes["atr_ratio"] > q1) & (episodes["atr_ratio"] <= q2)),
        ("HIGH", episodes["atr_ratio"] > q2),
    ):
        sub = episodes.loc[mask]
        if sub.empty:
            continue
        rows.append({"regime": label, "N": len(sub), "episodes_day": len(sub) / days, **summarize_r(sub)})
    return pd.DataFrame(rows)


def event_family_table(episodes: pd.DataFrame) -> pd.DataFrame:
    days = max((pd.to_datetime(episodes["timestamp_ct"]).max() - pd.to_datetime(episodes["timestamp_ct"]).min()).days, 1)
    rows = []
    for et in sorted(episodes["event_type"].dropna().unique()):
        sub = episodes.loc[episodes["event_type"] == et]
        rows.append({"event_type": et, "N": len(sub), "episodes_day": len(sub) / days, **summarize_r(sub)})
    return pd.DataFrame(rows)


def frequency_day_distribution(episodes: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(episodes["timestamp_ct"])
    daily = episodes.groupby(ts.dt.date).size()
    buckets = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6-10": 0, "11+": 0}
    # count all RTH days in span for zero days
    span = pd.date_range(ts.min().date(), ts.max().date(), freq="D")
    for d in span:
        n = int(daily.get(d.date(), 0))
        if n == 0:
            buckets["0"] += 1
        elif n == 1:
            buckets["1"] += 1
        elif n == 2:
            buckets["2"] += 1
        elif n == 3:
            buckets["3"] += 1
        elif n == 4:
            buckets["4"] += 1
        elif n == 5:
            buckets["5"] += 1
        elif n <= 10:
            buckets["6-10"] += 1
        else:
            buckets["11+"] += 1
    total_days = len(span) or 1
    return pd.DataFrame([{"bucket": k, "days": v, "pct": v / total_days} for k, v in buckets.items()])


def false_opportunity_table(episodes: pd.DataFrame) -> pd.DataFrame:
    ep = episodes.copy()
    mfe = ep["MFE_R"].astype(float)
    mae = ep["MAE_R"].astype(float)
    net = ep["net_R"].astype(float)
    rows = [
        {"metric": "immediate_adverse_mae_gt_0.5R", "N": int((mae >= 0.5).sum()), "pct": float((mae >= 0.5).mean())},
        {"metric": "never_reached_0.5R", "N": int((mfe < 0.5).sum()), "pct": float((mfe < 0.5).mean())},
        {"metric": "never_reached_1R", "N": int((mfe < 1.0).sum()), "pct": float((mfe < 1.0).mean())},
        {"metric": "hit_stop_before_favorable", "N": int(((net <= -0.9) & (mfe < 0.25)).sum()), "pct": float(((net <= -0.9) & (mfe < 0.25)).mean())},
        {"metric": "losers", "N": int((net < 0).sum()), "pct": float((net < 0).mean())},
    ]
    return pd.DataFrame(rows)


def first_vs_later_events(retained: pd.DataFrame, suppressed: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat(
        [retained.assign(_role="first"), suppressed.assign(_role="sup") if not suppressed.empty else pd.DataFrame()]
    ).sort_values("timestamp_ct")
    rows_map: dict[int, list[float]] = {1: [], 2: [], 3: [], 4: []}
    later: list[float] = []
    pos_in_ep = 0
    for _, r in combined.iterrows():
        if r["_role"] == "first":
            pos_in_ep = 1
            rows_map[1].append(float(r["net_R"]))
        else:
            pos_in_ep += 1
            if pos_in_ep <= 4:
                rows_map[pos_in_ep].append(float(r["net_R"]))
            else:
                later.append(float(r["net_R"]))
    out = []
    for k in (1, 2, 3, 4):
        rs = rows_map[k]
        label = "first" if k == 1 else f"event_{k}"
        out.append({"position": label, "N": len(rs), "AvgR": float(np.mean(rs)) if rs else np.nan, "PF": pf(pd.Series(rs)) if rs else np.nan})
    if later:
        out.append({"position": "event_5plus", "N": len(later), "AvgR": float(np.mean(later)), "PF": pf(pd.Series(later))})
    return pd.DataFrame(out)


def core_overlap_table(episodes: pd.DataFrame, overlap_min: int = 30) -> pd.DataFrame:
    if "core_authorized" not in episodes.columns:
        return pd.DataFrame()
    auth = episodes.loc[episodes["core_authorized"] == 1]
    unauth = episodes.loc[episodes["core_authorized"] == 0]
    rows = [
        {"TYPE": "CORE ONLY", "N": len(auth), **summarize_r(auth)},
        {"TYPE": "P54 ONLY (core-unauth)", "N": len(unauth), **summarize_r(unauth)},
        {"TYPE": "BOTH (core-auth episodes)", "N": len(auth), **summarize_r(auth)},
    ]
    rows[0]["overlap_rate"] = len(auth) / len(episodes) if len(episodes) else 0
    return pd.DataFrame(rows)


def cost_adjusted_summary(episodes: pd.DataFrame, cost_mult: float) -> dict:
    from phase29.config import NQ_DOLLARS_PER_POINT, ROUND_TURN_COST_USD
    from phase53.config import STOP_ATR

    extra = max(cost_mult - 1.0, 0.0)
    if extra <= 0 or episodes.empty:
        return summarize_r(episodes)
    adj = []
    for _, r in episodes.iterrows():
        atr = float(r.get("atr", np.nan))
        if not np.isfinite(atr) or atr <= 0:
            adj.append(float(r["net_R"]))
            continue
        risk = STOP_ATR * atr
        cr = (ROUND_TURN_COST_USD * extra) / (risk * NQ_DOLLARS_PER_POINT)
        adj.append(float(r["net_R"]) - cr)
    tmp = episodes.copy()
    tmp["net_R"] = adj
    return summarize_r(tmp)


def score_ranking_pass(dec_yr_rows: list[dict]) -> bool:
    if not dec_yr_rows:
        return False
    dy = pd.DataFrame(dec_yr_rows)
    for yr in dy["year"].unique():
        sub = dy.loc[dy["year"] == yr]
        if len(sub) < 5:
            continue
        best_dec = int(sub.loc[sub["AvgR"].idxmax(), "decile"])
        if best_dec != int(sub["decile"].max()):
            return False
    return True


def year_stability_pass(yr_df: pd.DataFrame, min_years: int = 3) -> bool:
    valid = yr_df.dropna(subset=["EPISODE_AVGR"])
    return len(valid) >= min_years and (valid["EPISODE_AVGR"] > 0).all()


def reversal_table(episodes: pd.DataFrame) -> pd.DataFrame:
    ep = episodes.sort_values("timestamp_ct").reset_index(drop=True)
    rows = []
    flips = {"LONG->SHORT": [], "SHORT->LONG": [], "LONG->reset->LONG": [], "SHORT->reset->SHORT": []}
    for i in range(1, len(ep)):
        d0, d1 = ep.iloc[i - 1]["direction"], ep.iloc[i]["direction"]
        gap = (pd.Timestamp(ep.iloc[i]["timestamp_ct"]) - pd.Timestamp(ep.iloc[i - 1]["timestamp_ct"])).total_seconds() / 60.0
        key = f"{d0}->{d1}" if d0 != d1 else f"{d0}->reset->{d0}"
        if key in flips:
            flips[key].append({"net_R": ep.iloc[i]["net_R"], "gap": gap})
    for k, vals in flips.items():
        if not vals:
            rows.append({"TYPE": k, "N": 0, "PER_DAY": 0, "AVGR": np.nan, "PF": np.nan, "MEDIAN_GAP": np.nan})
        else:
            rs = pd.Series([v["net_R"] for v in vals], dtype=float)
            gaps = [v["gap"] for v in vals]
            days = max((ep["timestamp_ct"].max() - ep["timestamp_ct"].min()).days, 1)
            rows.append({"TYPE": k, "N": len(vals), "PER_DAY": len(vals) / days, "AVGR": float(rs.mean()), "PF": pf(rs), "MEDIAN_GAP": float(np.median(gaps))})
    return pd.DataFrame(rows)
