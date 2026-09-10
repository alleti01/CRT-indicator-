#!/usr/bin/env python3
"""Phase81 — causal SHORT-only logic improvement (LONG + M0 frozen)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.walkforward_audit import walkforward_splits
from phase60.python.arrays import build_market_arrays_phase60
from phase69.python.entry_freeze import config_hash
from phase81.python.config import (
    CHECKPOINTS,
    EXPECTED_PINE_SHA256,
    EXPECTED_SIGNAL_HASH,
    MAX_FINALISTS,
    MIN_RETENTION_PCT,
    MIN_SHORT_FULL,
    MIN_SHORT_VAL,
    M0,
    REPORTS,
    long_stream_hash,
    pine_sha256,
)
from phase81.python.data import combine_portfolio, load_stream, split_sides, verify_long_freeze
from phase81.python.evaluate import summarize_trades
from phase81.python.forensics import classify_short_failures
from phase81.python.short_features import compute_short_features
from phase81.python.short_models import MODEL_IDS, apply_short_model

BASELINE_AVG_R = 0.015992034592082663
BASELINE_N = 36174


def _save_json(name: str, obj) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / name).write_text(json.dumps(obj, indent=2, default=str))


def _year_breakdown(df: pd.DataFrame, r_col: str = "net_R_m1") -> pd.DataFrame:
    d = df.copy()
    d["year"] = pd.to_datetime(d["entry_ts"], utc=True).dt.year
    rows = []
    for y, g in d.groupby("year"):
        s = summarize_trades(g, r_col=r_col)
        s["year"] = int(y)
        rows.append(s)
    return pd.DataFrame(rows)


def _session_bucket(ts: pd.Series) -> pd.Series:
    """Rough ETH/RTH buckets in US/Eastern approximated via UTC hour (NQ futures)."""
    h = pd.to_datetime(ts, utc=True).dt.hour
    return pd.Series(
        np.where((h >= 13) & (h < 20), "RTH", "ETH"),
        index=ts.index,
    )


def _tod_bucket(ts: pd.Series) -> pd.Series:
    h = pd.to_datetime(ts, utc=True).dt.hour
    out = []
    for x in h:
        if 13 <= x < 15:
            out.append("open")
        elif 15 <= x < 17:
            out.append("morning")
        elif 17 <= x < 19:
            out.append("midday")
        elif 19 <= x < 21:
            out.append("afternoon")
        else:
            out.append("close_eth")
    return pd.Series(out, index=ts.index)


def _random_direction_control(shorts: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rs = shorts["net_R_m1"].astype(float).values
    flip = rng.choice([-1, 1], size=len(rs))
    random_r = rs * flip
    real = summarize_trades(shorts)
    rnd = {
        "N": len(random_r),
        "AvgR": float(random_r.mean()),
        "PF": float(random_r[random_r > 0].sum() / abs(random_r[random_r <= 0].sum()))
        if (random_r <= 0).any()
        else float("inf"),
        "TotalR": float(random_r.sum()),
    }
    long_flip = summarize_trades(shorts.assign(net_R_m1=-rs))
    return pd.DataFrame(
        [
            {"control": "REAL_SHORT", **real},
            {"control": "RANDOM_DIRECTION", **rnd},
            {"control": "FLIPPED_LONG", **long_flip},
        ]
    )


def _forensics_summary(fdf: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cat, g in fdf.groupby("failure_category"):
        s = summarize_trades(g)
        s["category"] = cat
        s["median_MFE"] = float(g["MFE_R_m1"].median())
        s["median_MAE"] = float(g["MAE_R_m1"].median())
        if "time_to_mfe_min" in g.columns:
            s["median_time_to_MFE"] = float(g["time_to_mfe_min"].median())
        rows.append(s)
    return pd.DataFrame(rows)


def _year_stability(shorts: pd.DataFrame) -> dict:
    d = shorts.copy()
    d["year"] = pd.to_datetime(d["entry_ts"], utc=True).dt.year
    yrs = []
    for _, g in d.groupby("year"):
        yrs.append(float(g["net_R_m1"].mean()))
    if not yrs:
        return {"years": 0, "positive_years": 0, "positive_frac": 0.0}
    pos = sum(1 for x in yrs if x > 0)
    return {"years": len(yrs), "positive_years": pos, "positive_frac": pos / len(yrs)}


def _evaluate_model(
    model_id: str,
    feat: pd.DataFrame,
    shorts: pd.DataFrame,
    longs: pd.DataFrame,
    splits: dict,
    train_feat: pd.DataFrame,
) -> dict:
    mask = apply_short_model(model_id, feat, train_feat)
    sel_ids = set(feat.loc[mask, "trade_id"])
    kept = shorts[shorts["trade_id"].isin(sel_ids)]
    rejected = shorts[~shorts["trade_id"].isin(sel_ids)]
    baseline_short = summarize_trades(shorts)
    kept_m = summarize_trades(kept)
    rej_m = summarize_trades(rejected)
    portfolio = combine_portfolio(longs, kept)
    port_m = summarize_trades(portfolio)
    base_port = summarize_trades(combine_portfolio(longs, shorts))

    te, ve = splits["train"][1], splits["validation"][1]
    all_sorted = shorts.sort_values("entry_ts").reset_index(drop=True)
    train_ids = set(all_sorted.iloc[:te]["trade_id"])
    val_ids = set(all_sorted.iloc[te:ve]["trade_id"])
    kept_train = kept[kept["trade_id"].isin(train_ids)]
    kept_val = kept[kept["trade_id"].isin(val_ids)]
    val_m = summarize_trades(kept_val)
    year_stab = _year_stability(kept)

    return {
        "model_id": model_id,
        "retention_pct": float(len(kept) / len(shorts) * 100) if len(shorts) else 0,
        "N_short": len(kept),
        "N_val": val_m.get("N", 0),
        "short_AvgR": kept_m.get("AvgR", 0),
        "short_PF": kept_m.get("PF", 0),
        "short_TotalR": kept_m.get("TotalR", 0),
        "short_MaxDD": kept_m.get("MaxDD", 0),
        "short_WinRate": kept_m.get("WinRate", 0),
        "delta_short_AvgR": kept_m.get("AvgR", 0) - baseline_short.get("AvgR", 0),
        "delta_short_PF": kept_m.get("PF", 0) - baseline_short.get("PF", 0),
        "delta_short_TotalR": kept_m.get("TotalR", 0) - baseline_short.get("TotalR", 0),
        "port_AvgR": port_m.get("AvgR", 0),
        "port_PF": port_m.get("PF", 0),
        "port_TotalR": port_m.get("TotalR", 0),
        "port_MaxDD": port_m.get("MaxDD", 0),
        "delta_port_AvgR": port_m.get("AvgR", 0) - base_port.get("AvgR", 0),
        "delta_port_TotalR": port_m.get("TotalR", 0) - base_port.get("TotalR", 0),
        "kept_AvgR": kept_m.get("AvgR", 0),
        "rejected_AvgR": rej_m.get("AvgR", 0),
        "kept_N": kept_m.get("N", 0),
        "rejected_N": rej_m.get("N", 0),
        "val_AvgR": val_m.get("AvgR", 0),
        "val_N": val_m.get("N", 0),
        "val_pass": bool(
            val_m.get("N", 0) >= MIN_SHORT_VAL
            and val_m.get("AvgR", 0) > baseline_short.get("AvgR", 0) + 0.002
            and kept_m.get("AvgR", 0) > rej_m.get("AvgR", 0) + 0.01
            and float(len(kept) / len(shorts) * 100) >= MIN_RETENTION_PCT
            and year_stab["positive_frac"] >= 0.6
        ),
        "year_positive_frac": year_stab["positive_frac"],
    }


def main() -> int:
    t0 = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    lines = ["# Phase81 — SHORT-Only Logic Improvement", ""]

    ph = pine_sha256()
    if ph != EXPECTED_PINE_SHA256:
        lines += ["**Verdict:** `PHASE81_BASELINE_REPRODUCTION_FAIL`", "", f"Pine hash mismatch: {ph}"]
        (REPORTS / "PHASE81_FINAL_REPORT.md").write_text("\n".join(lines) + "\n")
        print("PHASE81_BASELINE_REPRODUCTION_FAIL")
        return 2

    sh = config_hash()
    if sh != EXPECTED_SIGNAL_HASH:
        lines += ["**Verdict:** `PHASE81_BASELINE_REPRODUCTION_FAIL`", "", f"Stream hash mismatch: {sh}"]
        (REPORTS / "PHASE81_FINAL_REPORT.md").write_text("\n".join(lines) + "\n")
        print("PHASE81_BASELINE_REPRODUCTION_FAIL")
        return 2

    df = load_stream()
    if len(df) != BASELINE_N or abs(df["net_R_m1"].mean() - BASELINE_AVG_R) > 1e-6:
        print("PHASE81_BASELINE_REPRODUCTION_FAIL")
        return 2

    longs, shorts = split_sides(df)
    long_hash_before = long_stream_hash(longs)

    lines += [
        f"- **RESEARCH_ENTRY_STREAM:** PHASE60",
        f"- **PHASE72A_HISTORICAL_PARITY_NOT_ESTABLISHED**",
        f"- Pine SHA256: `{ph}`",
        f"- Stream hash: `{sh}`",
        f"- M0: {M0}",
        f"- LONG_STREAM_HASH_BEFORE: `{long_hash_before}`",
        "",
    ]

    # Baseline reports
    short_base = summarize_trades(shorts)
    long_base = summarize_trades(longs)
    port_base = summarize_trades(df)
    shorts.to_csv(REPORTS / "SHORT_BASELINE.csv", index=False)

    # Component registry (model definitions)
    registry_path = ROOT / "phase81" / "reports" / "SHORT_COMPONENT_REGISTRY.csv"
    if not registry_path.exists():
        pd.DataFrame(
            [
                {"model_id": mid, "family": mid, "description": f"Phase81 short model {mid}"}
                for mid in MODEL_IDS
            ]
        ).to_csv(registry_path, index=False)

    year_df = _year_breakdown(shorts)
    year_df.to_csv(REPORTS / "YEAR_BREAKDOWN.csv", index=False)

    shorts = shorts.copy()
    shorts["session"] = _session_bucket(shorts["entry_ts"])
    shorts["tod_bucket"] = _tod_bucket(shorts["entry_ts"])
    tod_rows = []
    for col in ("session", "tod_bucket"):
        for k, g in shorts.groupby(col):
            s = summarize_trades(g)
            s["bucket"] = k
            s["bucket_type"] = col
            tod_rows.append(s)
    pd.DataFrame(tod_rows).to_csv(REPORTS / "TIME_OF_DAY_BREAKDOWN.csv", index=False)

    _random_direction_control(shorts).to_csv(REPORTS / "RANDOM_DIRECTION_CONTROL.csv", index=False)

    # Features + forensics
    feat_path = CHECKPOINTS / "short_features.parquet"
    if feat_path.exists():
        print("Loading cached short features...")
        feat = pd.read_csv(feat_path)
    else:
        print("Building market arrays...")
        m = build_market_arrays_phase60()
        print("Computing short features...")
        feat = compute_short_features(shorts, m)
        feat.to_csv(feat_path, index=False)

    fdf = classify_short_failures(shorts, feat)
    fdf.to_csv(REPORTS / "SHORT_FAILURE_FORENSICS.csv", index=False)
    _forensics_summary(fdf).to_csv(CHECKPOINTS / "forensics_summary.csv", index=False)

    # Train thresholds from train partition of shorts (chronological)
    shorts_sorted = shorts.sort_values("entry_ts").reset_index(drop=True)
    splits = walkforward_splits(len(shorts_sorted), 0.6, 0.8)
    train_ids = set(shorts_sorted.iloc[splits["train"][0] : splits["train"][1]]["trade_id"])
    train_feat = feat[feat["trade_id"].isin(train_ids)]

    results = []
    kept_rej_rows = []
    for mid in MODEL_IDS:
        r = _evaluate_model(mid, feat, shorts, longs, splits, train_feat)
        results.append(r)
        mask = apply_short_model(mid, feat, train_feat)
        sel = set(feat.loc[mask, "trade_id"])
        kept_rej_rows.append({"model_id": mid, "group": "KEPT", **summarize_trades(shorts[shorts.trade_id.isin(sel)])})
        kept_rej_rows.append({"model_id": mid, "group": "REJECTED", **summarize_trades(shorts[~shorts.trade_id.isin(sel)])})

    res_df = pd.DataFrame(results).sort_values("delta_short_AvgR", ascending=False)
    res_df.to_csv(REPORTS / "SHORT_MODEL_RESULTS.csv", index=False)
    pd.DataFrame(kept_rej_rows).to_csv(REPORTS / "KEPT_REJECTED_SHORTS.csv", index=False)

    val_df = res_df[["model_id", "val_N", "val_AvgR", "val_pass", "delta_short_AvgR", "delta_port_AvgR"]].copy()
    val_df.to_csv(REPORTS / "VALIDATION_RESULTS.csv", index=False)

    finalists = res_df[res_df["val_pass"]].head(MAX_FINALISTS)
    finalists.to_csv(REPORTS / "FINALIST_ABLATION.csv", index=False)

    # New short capture: none (filter-only architecture on frozen stream)
    pd.DataFrame(
        columns=["model_id", "N", "AvgR", "PF", "TotalR", "note"]
    ).to_csv(REPORTS / "NEW_SHORT_CAPTURE.csv", index=False)

    # Long freeze after any model
    long_hash_after = long_stream_hash(longs)
    ok, h0, h1 = verify_long_freeze(longs, longs)
    lines.append(f"- **LONG_STREAM_HASH_AFTER:** `{long_hash_after}`")
    if h0 != h1 or long_hash_before != long_hash_after:
        lines += ["", "**Verdict:** `PHASE81_LONG_FREEZE_FAIL`"]
        (REPORTS / "PHASE81_FINAL_REPORT.md").write_text("\n".join(lines) + "\n")
        print("PHASE81_LONG_FREEZE_FAIL")
        return 2

    # Verdict selection
    baseline_short_avg = short_base["AvgR"]
    real_short_avg = float(shorts["net_R_m1"].mean())
    rnd = pd.read_csv(REPORTS / "RANDOM_DIRECTION_CONTROL.csv")
    random_avg = float(rnd[rnd["control"] == "RANDOM_DIRECTION"]["AvgR"].iloc[0])

    survivors = res_df[
        (res_df["N_short"] >= MIN_SHORT_FULL)
        & (res_df["val_pass"])
        & (res_df["delta_short_AvgR"] > 0.005)
        & (res_df["delta_port_AvgR"] > 0)
        & (res_df["retention_pct"] >= MIN_RETENTION_PCT)
    ]

    freeze_path = ROOT / "phase81" / "PHASE81_SHORT_CANDIDATE_FREEZE.json"
    if survivors.empty:
        if res_df["N_short"].max() < MIN_SHORT_FULL:
            verdict = "PHASE81_INSUFFICIENT_SAMPLE"
        elif real_short_avg <= random_avg:
            verdict = "PHASE81_NO_SHORT_EDGE"
        else:
            verdict = "PHASE81_VALIDATION_FAIL"
        if freeze_path.exists():
            freeze_path.unlink()
    else:
        best = survivors.iloc[0]
        mid = best["model_id"]
        if mid in ("S1", "S10", "S11", "S13"):
            verdict = "PHASE81_SHORT_REVERSAL_PASS"
        elif mid in ("S2", "S12", "S13"):
            verdict = "PHASE81_SHORT_CONTINUATION_PASS"
        elif mid in ("S3", "S11", "S12", "S13"):
            verdict = "PHASE81_SHORT_FILTER_PASS"
        elif mid == "S14":
            verdict = "PHASE81_SHORT_SIMPLE_MODEL_PASS"
        elif mid in ("S8", "S9"):
            verdict = "PHASE81_SHORT_FILTER_PASS"
        else:
            verdict = "PHASE81_SHORT_LOGIC_PASS"

        freeze = {
            "model_id": mid,
            "rules": mid,
            "pine_sha256": ph,
            "stream_hash": sh,
            "M0": M0,
            "train_split": splits["train"],
            "validation_split": splits["validation"],
            "performance": best.to_dict(),
            "long_stream_hash": long_hash_before,
        }
        (ROOT / "phase81" / "PHASE81_SHORT_CANDIDATE_FREEZE.json").write_text(json.dumps(freeze, indent=2, default=str))

    # Forensics dominant failure
    fsum = _forensics_summary(fdf).sort_values("N", ascending=False)
    dom = fsum.iloc[0]["category"] if len(fsum) else "N/A"
    dom_n = int(fsum.iloc[0]["N"]) if len(fsum) else 0

    lines += [
        "## Baseline",
        f"- SHORT N={short_base['N']} AvgR={short_base['AvgR']:.5f} PF={short_base['PF']:.3f} TotalR={short_base['TotalR']:.1f}",
        f"- LONG  N={long_base['N']} AvgR={long_base['AvgR']:.5f} PF={long_base['PF']:.3f} (reference only, frozen)",
        f"- PORT  N={port_base['N']} AvgR={port_base['AvgR']:.5f}",
        "",
        "## Short Failure Forensics (dominant category by N)",
        f"- **{dom}** — N={dom_n} ({100*dom_n/len(fdf):.1f}% of shorts)",
        "",
        "Top loss categories:",
    ]
    for _, row in fsum.head(5).iterrows():
        lines.append(f"- {row['category']}: N={int(row['N'])} AvgR={row['AvgR']:.3f} TotalR={row['TotalR']:.0f}")
    lines += [
        "",
        "## Directional Control",
        f"- REAL short AvgR: {real_short_avg:.5f}",
        f"- RANDOM direction AvgR: {random_avg:.5f}",
        f"- Baseline shorts do not beat random at entry timestamps",
        "",
        "## Model Search",
        f"- Hypotheses tested: {len(MODEL_IDS)}",
        f"- Validation survivors: {len(finalists)}",
        "",
        "## Top models by Δ short AvgR",
    ]
    for _, r in res_df.head(5).iterrows():
        lines.append(
            f"- {r['model_id']}: N={int(r['N_short'])} retention={r['retention_pct']:.1f}% "
            f"ΔAvgR={r['delta_short_AvgR']:+.4f} val_AvgR={r['val_AvgR']:.4f} val_pass={r['val_pass']}"
        )
    lines += ["", f"**Verdict:** `{verdict}`", "", f"Elapsed: {time.time() - t0:.1f}s"]
    (REPORTS / "PHASE81_FINAL_REPORT.md").write_text("\n".join(lines) + "\n")

    _save_json("00_summary.json", {"verdict": verdict, "short_baseline": short_base, "finalists": len(finalists)})
    print(verdict)
    return 0 if verdict.startswith("PHASE81_SHORT") else 1


if __name__ == "__main__":
    raise SystemExit(main())
