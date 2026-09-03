"""Phase58K — entry-time diagnostic: M1 TARGET vs STOP (causal features only)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58.research.instrument import NQ
from phase58b.research.precompute import build_mtf_arrays
from phase58i.research.canonical import canonical_trades
from phase58i.research.management import executions_from_trades, simulate_management
from phase58j.research.lw_data import build_mtf_arrays_lw

RESULTS = ROOT / "phase58j" / "results"
REPORTS = ROOT / "phase58j" / "reports"
LW_CSV = RESULTS / "last_week_all_canonical_trades.csv"

FROZEN_HASHES = {
    "phase58_v1": "facad8ebfae648be",
    "phase58d": "3c25fbacad3fff92",
    "phase58f": "956f66036a568820",
    "phase58h": "4db76ffe5f9b701d",
    "phase58i": "c104ebd37590db03",
}


def _verify_frozen() -> bool:
    def h(p):
        return hashlib.sha256(json.dumps(json.load(open(p)), sort_keys=True).encode()).hexdigest()[:16]

    checks = {
        "phase58_v1": h(ROOT / "phase58/config/phase58_v1_frozen.json"),
        "phase58d": h(ROOT / "phase58d/config/phase58d_frozen.json"),
        "phase58f": h(ROOT / "phase58f/config/phase58f_frozen.json"),
        "phase58h": h(ROOT / "phase58h/config/phase58h_frozen.json"),
        "phase58i": h(ROOT / "phase58i/config/phase58i_frozen.json"),
    }
    return all(checks[k] == FROZEN_HASHES[k] for k in FROZEN_HASHES)


def _sign(direction: str) -> int:
    return 1 if direction == "LONG" else -1


def _causal_swing_distance(hi, lo, i: int, direction: str, atr: float, lookback: int = 120) -> tuple[float, float]:
    """Left-only 3-bar swing; distance from entry to last causal swing."""
    if i < 3 or atr <= 0:
        return np.nan, np.nan
    start = max(2, i - lookback)
    last_sh_i = last_sl_i = -1
    for j in range(i - 1, start - 1, -1):
        if j >= 2 and hi[j] >= hi[j - 1] and hi[j] >= hi[j - 2] and last_sh_i < 0:
            last_sh_i = j
        if j >= 2 and lo[j] <= lo[j - 1] and lo[j] <= lo[j - 2] and last_sl_i < 0:
            last_sl_i = j
        if last_sh_i >= 0 and last_sl_i >= 0:
            break
    if direction == "LONG" and last_sl_i >= 0:
        return float((lo[i] - lo[last_sl_i]) / atr), float(i - last_sl_i)
    if direction == "SHORT" and last_sh_i >= 0:
        return float((hi[last_sh_i] - hi[i]) / atr), float(i - last_sh_i)
    return np.nan, np.nan


def compute_causal_features(m, row: pd.Series, opp_start: dict[str, int] | None = None) -> dict:
    ei = int(row["entry_i"])
    si = int(row.get("signal_m1_i", row.get("signal_i", ei - 1)))
    direction = row["direction"] if "direction" in row else row.get("direction_m1", "LONG")
    sign = _sign(direction)
    atr = float(row.get("atr", row.get("atr_mgmt", m.m1_atr[ei])))
    if not np.isfinite(atr) or atr <= 0:
        atr = float(m.m1_atr[ei]) if np.isfinite(m.m1_atr[ei]) and m.m1_atr[ei] > 0 else 1.0

    op, hi, lo, cl = m.m1_op, m.m1_hi, m.m1_lo, m.m1_cl
    ep = float(row.get("entry_price", op[ei]))

    def window_move(n: int) -> float:
        a = max(0, ei - n)
        if a >= ei:
            return 0.0
        return sign * (cl[ei - 1] - cl[a]) / atr

    def dist_extreme(n: int) -> float:
        a = max(0, ei - n)
        if a >= ei:
            return 0.0
        wh, wl = hi[a:ei], lo[a:ei]
        if direction == "LONG":
            return (ep - np.max(wh)) / atr
        return (np.min(wl) - ep) / atr

    def range_atr(a: int, b: int) -> float:
        if b <= a:
            return 0.0
        return float(np.max(hi[a:b]) - np.min(lo[a:b])) / atr

    prior_i = ei - 1
    prior_range = (hi[prior_i] - lo[prior_i]) / atr if prior_i >= 0 else np.nan
    gap_prior = (op[ei] - cl[prior_i]) / atr if prior_i >= 0 else np.nan

    same_dir = opp_dir = 0
    for j in range(ei - 1, max(0, ei - 30), -1):
        bd = 1 if cl[j] > cl[j - 1] else (-1 if cl[j] < cl[j - 1] else 0)
        if bd == sign:
            same_dir += 1
        elif bd == -sign:
            break
        else:
            break
    for j in range(ei - 1, max(0, ei - 30), -1):
        bd = 1 if cl[j] > cl[j - 1] else (-1 if cl[j] < cl[j - 1] else 0)
        if bd == -sign:
            opp_dir += 1
        elif bd == sign:
            break
        else:
            break

    oid = str(row.get("opportunity_id", row.get("setup_id", "")))
    opp_start_i = opp_start.get(oid, si) if opp_start else si
    opp_age = ei - opp_start_i
    dist_origin = sign * (ep - cl[opp_start_i]) / atr if 0 <= opp_start_i < ei else sign * (ep - cl[si]) / atr

    # pullback extreme: most adverse point in last 10 bars before entry
    pb_i = max(0, ei - 10)
    if direction == "LONG":
        pb_ext = np.min(lo[pb_i:ei])
        dist_pb = (ep - pb_ext) / atr
    else:
        pb_ext = np.max(hi[pb_i:ei])
        dist_pb = (pb_ext - ep) / atr

    move3, move5, move10, move20 = window_move(3), window_move(5), window_move(10), window_move(20)
    d5, d10, d20 = dist_extreme(5), dist_extreme(10), dist_extreme(20)

    # 5m / 15m move into entry (causal completed bars)
    m5_i = m.m1_to_m5[ei] if ei < len(m.m1_to_m5) else 0
    m5_move = np.nan
    m15_move = np.nan
    if m5_i >= 2:
        m5_move = sign * (m.m5_cl[m5_i - 1] - m.m5_cl[m5_i - 6]) / atr if m5_i >= 6 else sign * (m.m5_cl[m5_i - 1] - m.m5_cl[0]) / atr
    if m5_i >= 1 and m5_i < len(m.m15_cl):
        m15_move = sign * (m.m15_cl[m5_i - 1] - m.m15_cl[max(0, m5_i - 4)]) / atr

    comp_5 = range_atr(max(0, ei - 5), ei) / max(range_atr(max(0, ei - 20), max(0, ei - 5)), 1e-9)
    near_ext = abs(d10) <= 0.25
    expansion_bar = prior_range >= 1.0
    follows_pullback = dist_pb >= 0.5 and move5 <= 0.5
    chasing = move10 >= 1.0

    swing_dist, swing_bars = _causal_swing_distance(hi, lo, ei, direction, atr)

    return {
        "move_3_atr": move3,
        "move_5_atr": move5,
        "move_10_atr": move10,
        "move_20_atr": move20,
        "dist_5_ext_atr": d5,
        "dist_10_ext_atr": d10,
        "dist_20_ext_atr": d20,
        "dist_origin_atr": dist_origin,
        "dist_pullback_ext_atr": dist_pb,
        "m5_move_atr": m5_move,
        "m15_move_atr": m15_move,
        "prior_bar_range_atr": prior_range,
        "entry_gap_prior_close_atr": gap_prior,
        "same_dir_streak": same_dir,
        "opp_dir_streak": opp_dir,
        "range_compression_ratio": comp_5,
        "bars_since_opp_start": opp_age,
        "bars_signal_to_entry": ei - si,
        "swing_distance_atr": swing_dist,
        "bars_since_swing": swing_bars,
        "near_recent_extreme": near_ext,
        "follows_expansion_bar": expansion_bar,
        "follows_pullback": follows_pullback,
        "chasing_extended_move": chasing,
    }


def classify_archetype(r: pd.Series) -> str:
    ctx15 = str(r.get("15m_state", r.get("15m_state_x", "")))
    mstate = str(r.get("market_state", ""))
    m10 = float(r.get("move_10_atr", 0))
    m5 = float(r.get("move_5_atr", 0))
    age = float(r.get("bars_since_opp_start", 1))

    if ctx15 == "TRANSITION" or mstate == "TRANSITION":
        return "TRANSITION"
    if mstate == "UNCERTAIN" or bool(r.get("ambiguous_reaction", False)):
        return "CHOP"
    if m10 >= 2.0 or m5 >= 1.5:
        return "LATE_CHASE"
    if m10 >= 1.0:
        return "EXTENDED_CONTINUATION"
    if bool(r.get("follows_pullback", False)) and m10 < 0.5:
        return "PULLBACK_CONTINUATION"
    if m10 <= 0.25 and age <= 3:
        return "EARLY_TURN"
    if 0 <= m10 <= 0.75:
        return "EARLY_CONTINUATION"
    return "OTHER"


def classify_loser_cause(r: pd.Series) -> str:
    if r.get("m1_outcome") != "STOP":
        return ""
    arch = r.get("entry_archetype", "")
    m10 = float(r.get("move_10_atr", 0))
    if m10 >= 1.5 or arch in ("LATE_CHASE", "EXTENDED_CONTINUATION"):
        return "LATE_EXTENSION"
    if not bool(r.get("aligned_with_active", True)):
        return "WRONG_DIRECTION"
    if arch == "CHOP":
        return "CHOP"
    if arch == "TRANSITION":
        return "TRANSITION"
    if m10 < 0.5:
        return "EARLY_BUT_FAILED"
    return "FAILED_CONTINUATION"


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return np.nan
    va, vb = np.var(a, ddof=1), np.var(b, ddof=1)
    pooled = np.sqrt(((len(a) - 1) * va + (len(b) - 1) * vb) / (len(a) + len(b) - 2))
    return (np.mean(a) - np.mean(b)) / pooled if pooled > 0 else np.nan


def feature_comparison(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    tgt = df.loc[df["m1_outcome"] == "TARGET"]
    stp = df.loc[df["m1_outcome"] == "STOP"]
    rows = []
    for f in features:
        a = tgt[f].astype(float).values
        b = stp[f].astype(float).values
        rows.append({
            "feature": f,
            "target_n": len(a),
            "target_mean": np.nanmean(a),
            "target_median": np.nanmedian(a),
            "target_p25": np.nanpercentile(a, 25),
            "target_p75": np.nanpercentile(a, 75),
            "stop_n": len(b),
            "stop_mean": np.nanmean(b),
            "stop_median": np.nanmedian(b),
            "stop_p25": np.nanpercentile(b, 25),
            "stop_p75": np.nanpercentile(b, 75),
            "cohens_d": cohens_d(a, b),
            "mean_diff": np.nanmean(a) - np.nanmean(b),
        })
    out = pd.DataFrame(rows).sort_values("cohens_d", key=abs, ascending=False)
    return out


def extension_deciles(df: pd.DataFrame, col: str) -> pd.DataFrame:
    x = df[col].astype(float)
    df = df.assign(_ext=x)
    df["_dec"] = pd.qcut(df["_ext"].rank(method="first"), 10, labels=False, duplicates="drop")
    rows = []
    for d, g in df.groupby("_dec"):
        rows.append({
            "metric": col,
            "decile": int(d) + 1,
            "N": len(g),
            "target_rate": (g["m1_outcome"] == "TARGET").mean(),
            "m1_avg_r": g["m1_net_r"].mean(),
            "m1_total_r": g["m1_net_r"].sum(),
        })
    return pd.DataFrame(rows)


def opp_age_buckets(df: pd.DataFrame) -> pd.DataFrame:
    bins = [0, 1, 3, 5, 10, 9999]
    labels = ["0-1", "2-3", "4-5", "6-10", "11+"]
    df = df.copy()
    df["opp_age_bucket"] = pd.cut(df["bars_since_opp_start"].clip(lower=0), bins=bins, labels=labels, right=True)
    rows = []
    for (bucket, direction), g in df.groupby(["opp_age_bucket", "direction"], observed=True):
        rows.append({
            "opp_age_bucket": str(bucket),
            "direction": direction,
            "N": len(g),
            "target_rate": (g["m1_outcome"] == "TARGET").mean(),
            "m1_avg_r": g["m1_net_r"].mean(),
            "m1_total_r": g["m1_net_r"].sum(),
        })
    return pd.DataFrame(rows)


def quantile_sweep(df: pd.DataFrame, feature: str) -> pd.DataFrame:
    x = df[feature].astype(float)
    rows = []
    for q in range(10, 101, 10):
        thr = np.nanpercentile(x, 100 - q)
        kept = df.loc[x <= thr]
        excl = df.loc[x > thr]
        rows.append({
            "feature": feature,
            "exclude_top_pct": q,
            "threshold": thr,
            "trades_excluded": len(excl),
            "losers_excluded": (excl["m1_outcome"] == "STOP").sum(),
            "winners_excluded": (excl["m1_outcome"] == "TARGET").sum(),
            "winner_retention": 1 - (excl["m1_outcome"] == "TARGET").sum() / max((df["m1_outcome"] == "TARGET").sum(), 1),
            "kept_avg_r": kept["m1_net_r"].mean(),
            "kept_total_r": kept["m1_net_r"].sum(),
        })
    return pd.DataFrame(rows)


def build_diagnostics(df: pd.DataFrame, m, opp_start: dict | None, cohort: str) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        feats = compute_causal_features(m, row, opp_start)
        rec = {
            "cohort": cohort,
            "trade_id": row.get("trade_id", ""),
            "timestamp": row.get("entry_ts", ""),
            "direction": row.get("direction", row.get("direction_m1", "")),
            "entry_price": row.get("entry_price", row.get("entry_price_m1")),
            "atr": row.get("atr", row.get("atr_mgmt")),
            "m1_outcome": row.get("m1_outcome", row.get("exit_reason_m1", "")),
            "m1_net_r": row.get("m1_net_r", row.get("net_R_m1", np.nan)),
            "15m_context": row.get("15m_state", row.get("15m_state_x", "")),
            "5m_context": row.get("5m_state", row.get("5m_state_c", "")),
            "phase58d_decision": row.get("phase58d_decision", "TAKE"),
            "p4_status": row.get("p4_status", ""),
            "h1_status": row.get("h1_status", ""),
            "location_score": row.get("location_score"),
            "direction_score": row.get("direction_score"),
            "reaction_score": row.get("reaction_score"),
            "total_evidence": row.get("total_evidence"),
            "direction_confidence_band": row.get("direction_confidence_band", ""),
            "market_state": row.get("market_state", ""),
            "aligned_with_active": row.get("aligned_with_active"),
            "reason_codes": row.get("reason_codes", ""),
            "feature_combo": row.get("feature_combo", ""),
            **feats,
        }
        rows.append(rec)
    out = pd.DataFrame(rows)
    out["entry_archetype"] = out.apply(classify_archetype, axis=1)
    out["loser_cause"] = out.apply(classify_loser_cause, axis=1)
    return out


def load_last_week() -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(LW_CSV)
    df["m1_outcome"] = df["exit_reason_m1"]
    df["m1_net_r"] = df["net_R_m1"]
    ev = pd.read_csv(RESULTS / "last_week_event_stream.csv")
    opp_start = ev.groupby("opportunity_id")["bar_i"].min().to_dict()
    return df, opp_start


def load_historical_sample(max_rows: int | None = None) -> pd.DataFrame:
    cfg = json.load(open(ROOT / "phase58i/config/phase58i_frozen.json"))
    canon = canonical_trades("H1")
    if max_rows:
        canon = canon.head(max_rows)
    execs = executions_from_trades(canon)
    m1 = simulate_management(build_mtf_arrays(), execs, cfg, "M1_1.0")
    out = canon.merge(m1[["trade_id", "exit_reason", "net_R"]].rename(columns={"exit_reason": "m1_outcome", "net_R": "m1_net_r"}), on="trade_id")
    return out


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    frozen_ok = _verify_frozen()

    lw_df, opp_start = load_last_week()
    m_lw = build_mtf_arrays_lw()
    lw_diag = build_diagnostics(lw_df, m_lw, opp_start, "last_week")

    counts = lw_diag["m1_outcome"].value_counts()
    n_tgt, n_stp = int(counts.get("TARGET", 0)), int(counts.get("STOP", 0))
    n_time = int(counts.get("TIME", 0))

    numeric_feats = [
        "move_3_atr", "move_5_atr", "move_10_atr", "move_20_atr",
        "dist_5_ext_atr", "dist_10_ext_atr", "dist_20_ext_atr",
        "dist_origin_atr", "dist_pullback_ext_atr", "m5_move_atr", "m15_move_atr",
        "prior_bar_range_atr", "entry_gap_prior_close_atr",
        "same_dir_streak", "opp_dir_streak", "range_compression_ratio",
        "bars_since_opp_start", "bars_signal_to_entry",
        "swing_distance_atr", "bars_since_swing",
        "location_score", "direction_score", "reaction_score", "total_evidence",
    ]
    feat_cmp = feature_comparison(lw_diag, numeric_feats)

    ext_dec = pd.concat([
        extension_deciles(lw_diag, c) for c in
        ["move_3_atr", "move_5_atr", "move_10_atr", "move_20_atr", "dist_5_ext_atr", "dist_10_ext_atr", "dist_20_ext_atr", "dist_origin_atr"]
    ], ignore_index=True)

    opp_age = opp_age_buckets(lw_diag)

    top3 = feat_cmp.head(3)["feature"].tolist()
    sweeps = pd.concat([quantile_sweep(lw_diag, f) for f in top3], ignore_index=True)

    # Historical stability (full canonical — may take ~1-2 min)
    print("Running historical M1 replay for stability check...")
    m_hist = build_mtf_arrays()
    hist_canon = canonical_trades("H1")
    hist_execs = executions_from_trades(hist_canon)
    cfg = json.load(open(ROOT / "phase58i/config/phase58i_frozen.json"))
    hist_m1 = simulate_management(m_hist, hist_execs, cfg, "M1_1.0")
    hist_df = hist_canon.merge(hist_m1[["trade_id", "exit_reason", "net_R"]].rename(columns={"exit_reason": "m1_outcome", "net_R": "m1_net_r"}), on="trade_id")
    hist_diag = build_diagnostics(hist_df, m_hist, None, "historical")
    hist_cmp = feature_comparison(hist_diag, numeric_feats)

    # Stability: compare sign of cohens_d for top features
    stability = []
    for f in feat_cmp.head(10)["feature"]:
        lw_d = feat_cmp.loc[feat_cmp["feature"] == f, "cohens_d"].iloc[0]
        h_d = hist_cmp.loc[hist_cmp["feature"] == f, "cohens_d"].iloc[0] if f in hist_cmp["feature"].values else np.nan
        same_sign = np.sign(lw_d) == np.sign(h_d) if np.isfinite(lw_d) and np.isfinite(h_d) else False
        stability.append({"feature": f, "lw_cohens_d": lw_d, "hist_cohens_d": h_d, "same_direction": same_sign})

    # #9 vs #11
    t9 = lw_diag.loc[lw_diag["trade_id"] == "LW-063194"].iloc[0]
    t11 = lw_diag.loc[lw_diag["trade_id"] == "LW-063196"].iloc[0]
    compare_cols = numeric_feats + ["entry_archetype", "15m_context", "5m_context", "market_state"]
    cmp94 = []
    for c in compare_cols:
        v9, v11 = t9.get(c, np.nan), t11.get(c, np.nan)
        diff = v9 - v11 if isinstance(v9, (int, float)) and isinstance(v11, (int, float)) else ""
        cmp94.append({"feature": c, "LW-063194": v9, "LW-063196": v11, "difference": diff})

    lw_diag.to_csv(RESULTS / "phase58k_entry_diagnostics.csv", index=False)
    feat_cmp.to_csv(RESULTS / "phase58k_feature_comparison.csv", index=False)
    ext_dec.to_csv(RESULTS / "phase58k_extension_deciles.csv", index=False)
    opp_age.to_csv(RESULTS / "phase58k_opportunity_age.csv", index=False)
    lw_diag[["trade_id", "entry_archetype", "loser_cause", "m1_outcome", "move_10_atr", "bars_since_opp_start"]].to_csv(RESULTS / "phase58k_archetypes.csv", index=False)

    # Report
    top10 = feat_cmp.head(10)
    ext10_lw = ext_dec.loc[ext_dec["metric"] == "move_10_atr"]
    ext10_hist = extension_deciles(hist_diag, "move_10_atr")
    ext_agree = (ext10_lw["target_rate"].corr(ext10_hist["target_rate"]) < 0) if len(ext10_lw) == len(ext10_hist) else None

    best_sweep = sweeps.sort_values("winner_retention", ascending=False).iloc[0] if len(sweeps) else None
    clear_sep = best_sweep["winner_retention"] >= 0.85 and best_sweep["losers_excluded"] >= 10 if best_sweep is not None else False

    report = f"""# PHASE58K — GOOD VS LATE ENTRY DIAGNOSTIC

## Frozen config intact: {"PASS" if frozen_ok else "FAIL"}

## Last-week M1 outcomes
| Outcome | N |
|---------|---|
| TARGET | {n_tgt} |
| STOP | {n_stp} |
| TIME | {n_time} |

## Top 10 features separating TARGET vs STOP (Cohen's d)
{top10.to_string(index=False)}

## LW-063194 (#9) vs LW-063196 (#11)
| Feature | #9 | #11 | Diff |
|---------|----|----|------|
"""
    for r in cmp94[:20]:
        report += f"| {r['feature']} | {r['LW-063194']} | {r['LW-063196']} | {r['difference']} |\n"

    report += f"""
## Archetypes (last week)
{lw_diag.groupby(['entry_archetype','m1_outcome']).size().unstack(fill_value=0).to_string()}

## Loser forensics (71 stops)
{lw_diag.loc[lw_diag['m1_outcome']=='STOP'].groupby('loser_cause').agg(N=('trade_id','count'), AvgR=('m1_net_r','mean')).to_string()}

## Extension decile — move_10_atr (last week)
{ext10_lw.to_string(index=False)}

## Historical stability (top features same Cohen's d sign)
{pd.DataFrame(stability).to_string(index=False)}

## Quantile sweep (top feature: {top3[0] if top3 else 'n/a'})
{sweeps.loc[sweeps['feature']==top3[0]].to_string(index=False) if top3 else ''}
"""
    (REPORTS / "PHASE58K_GOOD_VS_LATE_ENTRY_DIAGNOSTIC.md").write_text(report)

    # Entry parity
    parity = []
    for i, row in lw_df.iterrows():
        ei = int(row["entry_i"])
        ok = abs(float(m_lw.m1_op[ei]) - float(row["entry_price"])) < 0.01
        parity.append(ok)

    print("PHASE58K — ENTRY QUALITY DIAGNOSTIC")
    print("FROZEN CONFIG INTACT:", "PASS" if frozen_ok else "FAIL")
    print(f"LAST-WEEK: TARGET={n_tgt} STOP={n_stp} TIME={n_time}")
    print("TOP 10 FEATURES:")
    for i, r in feat_cmp.head(10).iterrows():
        print(f"  {r['feature']}: d={r['cohens_d']:.3f}")
    print(f"LW-063194 archetype: {t9['entry_archetype']}")
    print(f"LW-063196 archetype: {t11['entry_archetype']}")
    print("ENTRY PARITY:", sum(parity), "/", len(parity))
    print("OUTPUTS written to phase58j/results/ and phase58j/reports/")


if __name__ == "__main__":
    main()
