"""Phase55 parity comparison utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase53.research.metrics import pf, summarize_r
from phase55.config import (
    D10_AGREEMENT_MIN,
    EPISODE_MATCH_MIN,
    EVENT_COUNT_TOL,
    FEATURE_MAE_TOL,
    P53_REF,
    P54_REF,
    PERF_AVGR_TOL,
    SCORE_MAE_TOL,
)


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def compare_events(ref: pd.DataFrame, impl: pd.DataFrame) -> dict:
    ref = ref.sort_values("timestamp_ct").reset_index(drop=True)
    impl = impl.sort_values("timestamp_ct").reset_index(drop=True)
    n_ref, n_impl = len(ref), len(impl)
    merged = ref.merge(
        impl,
        on=["timestamp_ct", "event_type", "direction"],
        how="outer",
        suffixes=("_ref", "_impl"),
        indicator=True,
    )
    missing = int((merged["_merge"] == "left_only").sum())
    extra = int((merged["_merge"] == "right_only").sum())
    both = merged.loc[merged["_merge"] == "both"]
    match_pct = len(both) / n_ref if n_ref else 0
    ok = n_ref == n_impl and missing == 0 and extra == 0
    return {
        "layer": "STRUCTURAL EVENTS",
        "reference_n": n_ref,
        "implementation_n": n_impl,
        "match_pct": match_pct,
        "missing": missing,
        "extra": extra,
        "status": _status(ok),
        "pass": ok,
    }


def compare_features(ref: pd.DataFrame, impl: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    m = ref.merge(impl, on="event_id", suffixes=("_ref", "_impl"))
    rows = []
    for f in features:
        a = m[f"{f}_ref"].astype(float)
        b = m[f"{f}_impl"].astype(float)
        diff = (a - b).abs()
        rows.append(
            {
                "feature": f,
                "n": len(m),
                "mae": float(diff.mean()),
                "median_error": float(diff.median()),
                "max_error": float(diff.max()),
                "exact_match_pct": float((diff < 1e-9).mean()),
                "correlation": float(a.corr(b)) if len(m) > 2 else np.nan,
                "status": _status(float(diff.max()) <= FEATURE_MAE_TOL),
            }
        )
    return pd.DataFrame(rows)


def compare_scores(ref: pd.DataFrame, impl: pd.DataFrame) -> dict:
    r = ref[["event_id", "score"]].copy()
    if "top10" in ref.columns:
        r["top10"] = ref["top10"]
    i = impl[["event_id", "score"]].copy()
    if "top10" in impl.columns:
        i["top10"] = impl["top10"]
    m = r.merge(i, on="event_id", suffixes=("_ref", "_impl"))
    diff = (m["score_ref"] - m["score_impl"]).abs()
    d10_agree = np.nan
    if "top10_ref" in m.columns and "top10_impl" in m.columns:
        d10_agree = (m["top10_ref"] == m["top10_impl"]).mean()
    ok = float(diff.max()) <= SCORE_MAE_TOL and (np.isnan(d10_agree) or d10_agree >= D10_AGREEMENT_MIN)
    return {
        "field": "QUALITY SCORE",
        "n": len(m),
        "mae": float(diff.mean()),
        "median_error": float(diff.median()),
        "max_error": float(diff.max()),
        "correlation": float(m["score_ref"].corr(m["score_impl"])),
        "d10_agreement": float(d10_agree) if np.isfinite(d10_agree) else np.nan,
        "status": _status(ok),
        "pass": ok,
    }


def compare_d10(ref: pd.DataFrame, impl: pd.DataFrame) -> dict:
    r = ref[["event_id"]].copy()
    r["top10_ref"] = ref["top10"] if "top10" in ref.columns else ref["d10"]
    i = impl[["event_id"]].copy()
    i["top10_impl"] = impl["top10"] if "top10" in impl.columns else False
    m = r.merge(i, on="event_id", how="inner")
    tp = int(((m["top10_ref"]) & (m["top10_impl"])).sum())
    fp = int((~m["top10_ref"] & m["top10_impl"]).sum())
    fn = int((m["top10_ref"] & ~m["top10_impl"]).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    ok = len(m.loc[m["top10_ref"]]) == P53_REF["d10_n"] and fn == 0 and fp == 0
    return {
        "reference_d10_n": int(m["top10_ref"].sum()),
        "implementation_d10_n": int(m["top10_impl"].sum()),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": prec,
        "recall": rec,
        "status": _status(ok),
        "pass": ok,
    }


def compare_episodes(ref: pd.DataFrame, impl: pd.DataFrame) -> dict:
    a = ref.sort_values("timestamp_ct").reset_index(drop=True)
    b = impl.sort_values("timestamp_ct").reset_index(drop=True)
    m = a.merge(b, on="event_id", suffixes=("_ref", "_impl"), how="outer", indicator=True)
    exact = m.loc[m["_merge"] == "both"]
    dir_match = (exact["direction_ref"] == exact["direction_impl"]).mean() if len(exact) else 0
    ts_match = (
        pd.to_datetime(exact["timestamp_ct_ref"]) == pd.to_datetime(exact["timestamp_ct_impl"])
    ).mean() if len(exact) else 0
    match_pct = len(exact) / len(a) if len(a) else 0
    ok = len(a) == len(b) and match_pct >= EPISODE_MATCH_MIN and dir_match >= EPISODE_MATCH_MIN
    return {
        "layer": "EPISODES",
        "reference_n": len(a),
        "implementation_n": len(b),
        "match_pct": match_pct,
        "direction_match_pct": dir_match,
        "timestamp_match_pct": ts_match,
        "missing": int((m["_merge"] == "left_only").sum()),
        "extra": int((m["_merge"] == "right_only").sum()),
        "status": _status(ok),
        "pass": ok,
    }


def compare_trades(ref: pd.DataFrame, impl: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    m = ref.merge(impl, on="event_id", suffixes=("_ref", "_impl"))
    fields = [
        ("ENTRY PRICE", "entry_price"),
        ("ATR", "atr"),
        ("STOP", "stop"),
        ("TARGET", "target"),
        ("EXIT PRICE", "exit_price"),
        ("REALIZED R", "net_R"),
    ]
    rows = []
    all_ok = True
    for label, col in fields:
        diff = (m[f"{col}_ref"] - m[f"{col}_impl"]).abs()
        tick_diff = diff / 0.25
        ok = float(diff.max()) <= 1e-6
        all_ok = all_ok and ok
        rows.append(
            {
                "field": label,
                "mae": float(diff.mean()),
                "median_error": float(diff.median()),
                "max_error": float(diff.max()),
                "max_ticks": float(tick_diff.max()),
                "correlation": float(m[f"{col}_ref"].corr(m[f"{col}_impl"])),
                "status": _status(ok),
            }
        )
    exit_match = (m["exit_reason_ref"] == m["exit_reason_impl"]).mean()
    entry_ok = all_ok and exit_match >= 0.999
    return pd.DataFrame(rows), {"entry_exit_pass": entry_ok, "exit_reason_match": float(exit_match)}


def compare_performance(ref: pd.DataFrame, impl: pd.DataFrame, *, ref_label: str, impl_label: str) -> pd.DataFrame:
    rs = summarize_r(ref.rename(columns={"net_R": "net_R"}))
    is_ = summarize_r(impl.rename(columns={"net_R": "net_R"}))
    metrics = ["N", "AvgR", "PF", "TotalR", "MaxDD"]
    rows = []
    for m in metrics:
        rv, iv = rs.get(m, np.nan), is_.get(m, np.nan)
        if isinstance(rv, (int, float)) and isinstance(iv, (int, float)) and m == "AvgR":
            ok = abs(rv - iv) <= PERF_AVGR_TOL
        elif m in ("N",):
            ok = rv == iv
        else:
            ok = abs(float(rv) - float(iv)) <= max(0.01 * abs(float(rv)), 0.05) if np.isfinite(rv) and np.isfinite(iv) else rv == iv
        rows.append(
            {
                "metric": m,
                "reference": rv,
                "implementation": iv,
                "delta": (iv - rv) if np.isfinite(rv) and np.isfinite(iv) else np.nan,
                "status": _status(ok),
            }
        )
    long_ref = ref.loc[ref["direction"] == "LONG", "net_R"].mean()
    long_impl = impl.loc[impl["direction"] == "LONG", "net_R"].mean()
    rows.append({"metric": "LONG AvgR", "reference": long_ref, "implementation": long_impl, "delta": long_impl - long_ref, "status": _status(abs(long_ref - long_impl) <= PERF_AVGR_TOL)})
    short_ref = ref.loc[ref["direction"] == "SHORT", "net_R"].mean()
    short_impl = impl.loc[impl["direction"] == "SHORT", "net_R"].mean()
    rows.append({"metric": "SHORT AvgR", "reference": short_ref, "implementation": short_impl, "delta": short_impl - short_ref, "status": _status(abs(short_ref - short_impl) <= PERF_AVGR_TOL)})
    unauth_ref = ref.loc[ref.get("core_authorized", 0) == 0, "net_R"].mean() if "core_authorized" in ref.columns else np.nan
    unauth_impl = impl.loc[impl.get("core_authorized", 0) == 0, "net_R"].mean() if "core_authorized" in impl.columns else np.nan
    rows.append({"metric": "CORE-UNAUTH AvgR", "reference": unauth_ref, "implementation": unauth_impl, "delta": unauth_impl - unauth_ref, "status": _status(abs(unauth_ref - unauth_impl) <= PERF_AVGR_TOL if np.isfinite(unauth_ref) else True)})
    return pd.DataFrame(rows)


def parity_table(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)
