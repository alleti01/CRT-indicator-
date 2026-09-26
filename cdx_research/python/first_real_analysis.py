"""Score frozen Candidate V1 and existing features after MEDIUM alignment passes.

Does not retune V1. Does not optimize P&L. T+1..T+20 are outcome-only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cdx_research.python.causality import run_causality
from cdx_research.python.features import add_causal_features
from cdx_research.python.rules import apply_candidate_v1
from cdx_research.python.tzutil import ET

PRIORITY_FEATURES = [
    "dist_low_20",
    "dist_high_20",
    "near_low_20",
    "near_high_20",
    "near_low_5",
    "near_high_5",
    "near_low_10",
    "near_high_10",
    "lower_wick_frac",
    "upper_wick_frac",
    "close_loc",
    "body_frac",
    "atr14",
    "rsi_14",
    "dist_ema_8",
    "dist_ema_21",
    "ema8_gt_ema21",
    "ret_1",
    "ret_3",
    "ret_5",
    "wick_through_low_20",
    "wick_through_high_20",
    "close_through_low_20",
    "close_through_high_20",
    "efficiency_10",
    "overlap_1",
    "range",
    "rel_volume",
    "vol_expand",
]

TRANS_LAGS = (0, 1, 2, 3, 5, 10, 20)
HYPOTHESES = {
    "A_local_extreme_reversal": ("near_low_20", "near_high_20"),
    "B_failed_bounce_fade": ("wick_through_high_20", "wick_through_low_20"),
    "C_pullback_continuation": ("dist_ema_21", "ema8_gt_ema21"),
    "D_breakout_failure": ("close_through_high_20", "close_through_low_20"),
}


def _et_index(m1: pd.DataFrame) -> pd.DataFrame:
    out = m1.copy()
    out.index = m1.index.tz_convert(ET)
    return out


def attach_targets(feat: pd.DataFrame, matched: pd.DataFrame) -> pd.DataFrame:
    """LONG=+1, SHORT=-1, NONE=0. Matched MEDIUM only."""
    out = feat.copy()
    out["cdx_target"] = 0
    for rec in matched.itertuples(index=False):
        ts = pd.Timestamp(rec.matched_time_et)
        if ts.tzinfo is None:
            ts = ts.tz_localize(ET)
        else:
            ts = ts.tz_convert(ET)
        if ts in out.index:
            out.loc[ts, "cdx_target"] = 1 if rec.direction == "LONG" else -1
    return out


def screenshot_cover_mask(feat: pd.DataFrame, labels: pd.DataFrame) -> pd.Series:
    mask = pd.Series(False, index=feat.index)
    for sid, grp in labels.groupby("screenshot_id"):
        times = pd.to_datetime(grp["signal_time_et"])
        times = times.map(lambda t: t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET))
        start = times.min() - pd.Timedelta(minutes=120)
        end = times.max() + pd.Timedelta(minutes=60)
        mask |= (feat.index >= start) & (feat.index <= end)
    return mask


def extract_windows(matched: pd.DataFrame, m1: pd.DataFrame, before: int = 100, after: int = 20) -> pd.DataFrame:
    m1_et = _et_index(m1)
    chunks = []
    for rec in matched.itertuples(index=False):
        ts = pd.Timestamp(rec.matched_time_et)
        if ts.tzinfo is None:
            ts = ts.tz_localize(ET)
        loc = m1_et.index.get_loc(ts)
        start = max(0, int(loc) - before)
        end = min(len(m1_et), int(loc) + after + 1)
        win = m1_et.iloc[start:end][["open", "high", "low", "close", "volume"]].copy()
        win["label_id"] = rec.label_id
        win["screenshot_id"] = rec.screenshot_id
        win["direction"] = rec.direction
        win["confidence"] = rec.confidence
        win["offset"] = range(start - int(loc), start - int(loc) + len(win))
        win["role"] = ["PRE" if o < 0 else ("SIGNAL" if o == 0 else "POST_OUTCOME_ONLY") for o in win["offset"]]
        chunks.append(win.reset_index())
    return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()


def score_candidate_v1(feat: pd.DataFrame, matched: pd.DataFrame, cover: pd.Series) -> dict[str, Any]:
    pred = apply_candidate_v1(feat)
    scoped = pred.where(cover, 0)
    exact = pm1 = missed = extras = wrong = 0
    rth_hits = globex_hits = rth_labels = globex_labels = 0
    days = set()

    for rec in matched.itertuples(index=False):
        ts = pd.Timestamp(rec.matched_time_et)
        if ts.tzinfo is None:
            ts = ts.tz_localize(ET)
        want = 1 if rec.direction == "LONG" else -1
        is_rth = bool(feat.loc[ts, "rth"]) if ts in feat.index else False
        if is_rth:
            rth_labels += 1
        else:
            globex_labels += 1
        got = int(scoped.loc[ts]) if ts in scoped.index else 0
        got_m = int(scoped.loc[ts - pd.Timedelta(minutes=1)]) if (ts - pd.Timedelta(minutes=1)) in scoped.index else 0
        got_p = int(scoped.loc[ts + pd.Timedelta(minutes=1)]) if (ts + pd.Timedelta(minutes=1)) in scoped.index else 0
        if got == want:
            exact += 1
            if is_rth:
                rth_hits += 1
            else:
                globex_hits += 1
        elif got == -want:
            wrong += 1
        elif got_m == want or got_p == want:
            pm1 += 1
            if is_rth:
                rth_hits += 1
            else:
                globex_hits += 1
        else:
            missed += 1

    signal_times = set()
    for rec in matched.itertuples(index=False):
        ts = pd.Timestamp(rec.matched_time_et)
        if ts.tzinfo is None:
            ts = ts.tz_localize(ET)
        signal_times.add(ts)
        signal_times.add(ts - pd.Timedelta(minutes=1))
        signal_times.add(ts + pd.Timedelta(minutes=1))

    extra_idx = scoped.index[(scoped != 0) & ~scoped.index.isin(signal_times)]
    extras = int(len(extra_idx))
    for ts in extra_idx:
        days.add(ts.date())
        if ts in signal_times:
            continue
    n_days = max(1, int(cover[cover].index.normalize().nunique()) if cover.any() else 1)
    tp = exact + pm1
    fp = extras + wrong
    fn = missed
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec_ = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec_ / (prec + rec_) if (prec + rec_) else 0.0
    return {
        "exact": exact,
        "plus_minus_1": pm1,
        "missed": missed,
        "extras": extras,
        "wrong_direction": wrong,
        "precision": round(prec, 4),
        "recall": round(rec_, 4),
        "f1": round(f1, 4),
        "extras_per_day": round(extras / n_days, 4),
        "rth_labels": rth_labels,
        "globex_labels": globex_labels,
        "rth_hits_exact_or_pm1": rth_hits,
        "globex_hits_exact_or_pm1": globex_hits,
        "cover_bars": int(cover.sum()),
        "v1_fires_in_cover": int((scoped != 0).sum()),
    }


def discriminate(feat: pd.DataFrame, cover: pd.Series) -> pd.DataFrame:
    scoped = feat.loc[cover]
    rows = []
    for col in PRIORITY_FEATURES:
        if col not in scoped.columns:
            continue
        s = scoped[col]
        long_s = s[scoped["cdx_target"] == 1]
        short_s = s[scoped["cdx_target"] == -1]
        none_s = s[scoped["cdx_target"] == 0]
        binary = set(pd.concat([s.dropna(), pd.Series([0, 1])]).unique()).issubset({0, 1, 0.0, 1.0})
        rec: dict[str, Any] = {"feature": col}
        for name, ser in (("long", long_s), ("short", short_s), ("none", none_s)):
            rec[f"{name}_n"] = int(ser.notna().sum())
            rec[f"{name}_median"] = float(ser.median()) if ser.notna().any() else np.nan
            rec[f"{name}_q25"] = float(ser.quantile(0.25)) if ser.notna().any() else np.nan
            rec[f"{name}_q75"] = float(ser.quantile(0.75)) if ser.notna().any() else np.nan
            if binary:
                rec[f"{name}_freq"] = float(ser.mean()) if len(ser) else np.nan
        if binary:
            rec["long_vs_none"] = (rec.get("long_freq", np.nan) or np.nan) - (rec.get("none_freq", np.nan) or np.nan)
            rec["short_vs_none"] = (rec.get("short_freq", np.nan) or np.nan) - (rec.get("none_freq", np.nan) or np.nan)
        else:
            rec["long_vs_none"] = rec["long_median"] - rec["none_median"]
            rec["short_vs_none"] = rec["short_median"] - rec["none_median"]
        rec["discrimination"] = max(abs(rec["long_vs_none"] or 0), abs(rec["short_vs_none"] or 0))
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("discrimination", ascending=False)


def transitions(feat: pd.DataFrame, matched: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rec in matched.itertuples(index=False):
        ts = pd.Timestamp(rec.matched_time_et)
        if ts.tzinfo is None:
            ts = ts.tz_localize(ET)
        if ts not in feat.index:
            continue
        loc = feat.index.get_loc(ts)
        for col in PRIORITY_FEATURES:
            if col not in feat.columns:
                continue
            row: dict[str, Any] = {
                "label_id": rec.label_id,
                "direction": rec.direction,
                "feature": col,
            }
            vals = {}
            for lag in TRANS_LAGS:
                idx = loc - lag
                vals[lag] = float(feat.iloc[idx][col]) if idx >= 0 and pd.notna(feat.iloc[idx][col]) else np.nan
                row[f"t_minus_{lag}"] = vals[lag]
            row["delta_t_vs_t1"] = vals[0] - vals[1] if pd.notna(vals[0]) and pd.notna(vals[1]) else np.nan
            row["delta_t_vs_t5"] = vals[0] - vals[5] if pd.notna(vals[0]) and pd.notna(vals[5]) else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def state_table(feat: pd.DataFrame, matched: pd.DataFrame) -> pd.DataFrame:
    rows = []
    events = []
    for rec in matched.itertuples(index=False):
        ts = pd.Timestamp(rec.matched_time_et)
        if ts.tzinfo is None:
            ts = ts.tz_localize(ET)
        events.append((ts, rec.direction, rec.label_id))
    events.sort()
    for i, (ts, direction, lid) in enumerate(events):
        same = opp = None
        for prev_ts, prev_dir, _ in reversed(events[:i]):
            if same is None and prev_dir == direction:
                same = int((ts - prev_ts).total_seconds() // 60)
            if opp is None and prev_dir != direction:
                opp = int((ts - prev_ts).total_seconds() // 60)
            if same is not None and opp is not None:
                break
        rows.append(
            {
                "label_id": lid,
                "direction": direction,
                "matched_time_et": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "bars_since_same_direction": same if same is not None else "",
                "bars_since_opposite": opp if opp is not None else "",
                "rth": int(feat.loc[ts, "rth"]) if ts in feat.index else "",
            }
        )
    return pd.DataFrame(rows)


def quantify_hypotheses(feat: pd.DataFrame, cover: pd.Series) -> dict[str, Any]:
    scoped = feat.loc[cover]
    long_s = scoped[scoped["cdx_target"] == 1]
    short_s = scoped[scoped["cdx_target"] == -1]
    none_s = scoped[scoped["cdx_target"] == 0]
    out: dict[str, Any] = {}
    if "near_low_20" in scoped.columns and len(long_s):
        out["A_long_near_low_20"] = float(long_s["near_low_20"].mean())
        out["A_none_near_low_20"] = float(none_s["near_low_20"].mean()) if len(none_s) else np.nan
    if "near_high_20" in scoped.columns and len(short_s):
        out["A_short_near_high_20"] = float(short_s["near_high_20"].mean())
        out["A_none_near_high_20"] = float(none_s["near_high_20"].mean()) if len(none_s) else np.nan
    if "wick_through_high_20" in scoped.columns and len(short_s):
        out["B_short_wick_through_high_20"] = float(short_s["wick_through_high_20"].mean())
        out["B_none_wick_through_high_20"] = float(none_s["wick_through_high_20"].mean()) if len(none_s) else np.nan
    if "dist_ema_21" in scoped.columns and len(long_s):
        out["C_long_dist_ema_21_median"] = float(long_s["dist_ema_21"].median())
        out["C_none_dist_ema_21_median"] = float(none_s["dist_ema_21"].median()) if len(none_s) else np.nan
    if "close_through_high_20" in scoped.columns:
        out["D_long_close_through_high_20"] = float(long_s["close_through_high_20"].mean()) if len(long_s) else np.nan
        out["D_none_close_through_high_20"] = float(none_s["close_through_high_20"].mean()) if len(none_s) else np.nan
    same_gaps = []
    # E: same-direction repeats vs 8-bar cooldown assumption
    out["E_note"] = "see state_table bars_since_same_direction; do not impose 8-bar cooldown unless data supports it"
    return out


def run_analysis(
    m1: pd.DataFrame,
    labels: pd.DataFrame,
    matched: pd.DataFrame,
    out_dir: Path,
) -> dict[str, Any]:
    m1_et = _et_index(m1)
    feat = add_causal_features(m1_et)
    feat = attach_targets(feat, matched)
    cover = screenshot_cover_mask(feat, labels)
    feat["in_screenshot_cover"] = cover.astype(int)
    feat["candidate_v1"] = apply_candidate_v1(feat)

    windows = extract_windows(matched, m1)
    windows.to_csv(out_dir / "signal_windows_t100_t20.csv", index=False)

    sig_feat = feat.loc[feat["cdx_target"] != 0, PRIORITY_FEATURES + ["cdx_target", "rth"]].copy()
    sig_feat.to_csv(out_dir / "matched_signal_features.csv", index=True)

    v1 = score_candidate_v1(feat, matched, cover)
    disc = discriminate(feat, cover)
    disc.to_csv(out_dir / "feature_discrimination.csv", index=False)
    trans = transitions(feat, matched)
    trans.to_csv(out_dir / "transition_table.csv", index=False)
    state = state_table(feat, matched)
    state.to_csv(out_dir / "state_table.csv", index=False)
    hyps = quantify_hypotheses(feat, cover)

    # Causality on the covered region plus warmup, not the entire multi-year file.
    if cover.any():
        first = feat.index[cover][0]
        last = feat.index[cover][-1]
        warm = feat.index.searchsorted(first) 
        start = max(0, int(warm) - 250)
        end = int(feat.index.searchsorted(last)) + 1
        causal_slice = m1_et.iloc[start:end]
    else:
        causal_slice = m1_et.iloc[: min(len(m1_et), 2000)]
    causality = run_causality(causal_slice, sample_n=min(500, max(0, len(causal_slice) - 260)))

    return {
        "v1": v1,
        "hypotheses": hyps,
        "causality": causality,
        "top_features": disc.head(8).to_dict(orient="records") if not disc.empty else [],
        "state_rows": state.to_dict(orient="records"),
    }
