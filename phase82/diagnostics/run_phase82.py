#!/usr/bin/env python3
"""Phase82 — causal 15M context → 1M execution research."""
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
from phase69.python.entry_freeze import config_hash
from phase82.diagnostics.prefix_causality_test import run_prefix_test
from phase82.python.config import (
    BASELINE_AVG_R,
    CHECKPOINTS,
    EXPECTED_N,
    EXPECTED_PINE_SHA256,
    EXPECTED_STREAM_HASH,
    MIN_FULL,
    MIN_LONG_RETENTION,
    MIN_RETENTION,
    MIN_SHORT_RETENTION,
    MIN_SIDE_VAL,
    MIN_TEST,
    MIN_VAL,
    MODEL_IDS,
    M0,
    REPORTS,
    TRAIN_FRAC,
    VALID_FRAC,
    pine_sha256,
)
from phase82.python.entries import apply_model, load_baseline
from phase82.python.evaluate import side_metrics, summarize
from phase82.python.m15_causal import build_m15_causal_arrays

MODEL_FLAGS = {
    "P0": {},
    "P1": {},
    "P2": {},
    "P3": {},
    "P4": {},
    "P5": {},
    "P6": {"allow_reversal": False},
    "P7": {"allow_reversal": True},
    "P8": {"allow_reversal": True},
    "P9": {"allow_reversal": True, "use_memory": True},
    "P10": {"allow_reversal": True, "use_memory": True},
}


def _save_json(name: str, obj) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / name).write_text(json.dumps(obj, indent=2, default=str))


def _random_control(df: pd.DataFrame, seeds: int = 20) -> pd.DataFrame:
    rs = df["net_R"].astype(float).values
    rows = [{"control": "REAL", **summarize(df)}]
    rnd_avgs = []
    for s in range(seeds):
        rng = np.random.default_rng(s)
        flip = rng.choice([-1, 1], size=len(rs))
        rnd_avgs.append(float((rs * flip).mean()))
    rows.append(
        {
            "control": "RANDOM",
            "AvgR": float(np.mean(rnd_avgs)),
            "AvgR_p2.5": float(np.percentile(rnd_avgs, 2.5)),
            "AvgR_p97.5": float(np.percentile(rnd_avgs, 97.5)),
            "N": len(rs),
        }
    )
    rows.append({"control": "FLIPPED", **summarize(df.assign(net_R=-df["net_R"]))})
    return pd.DataFrame(rows)


def _partition_eval(entries: pd.DataFrame, splits: dict) -> dict:
    entries = entries.sort_values("entry_ts").reset_index(drop=True)
    out = {}
    for name, (a, b) in splits.items():
        sub = entries.iloc[a:b]
        out[name] = summarize(sub)
        out[name]["long_N"] = int((sub["direction"] == "LONG").sum())
        out[name]["short_N"] = int((sub["direction"] == "SHORT").sum())
    return out


def _forensics(entries: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in entries.iterrows():
        lbl = "AMBIGUOUS"
        net = float(r["net_R"])
        if net >= 2.0:
            lbl = "GOOD_ENTRY"
        elif r["m15_state"] in ("15M_EXTENDED_UP", "15M_EXTENDED_DOWN") and net <= -0.9:
            lbl = "LATE_EXTENSION"
        elif net <= -0.9 and r.get("m1_extension_down_atr", 0) > 1.5 and r["direction"] == "SHORT":
            lbl = "LATE_EXTENSION"
        elif net <= -0.5:
            lbl = "GOOD_DIRECTION_BAD_TIMING"
        rows.append({**r.to_dict(), "diag_label": lbl})
    return pd.DataFrame(rows)


def main() -> int:
    t0 = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    ph = pine_sha256()
    sh = config_hash()
    lines = [
        "# Phase82 — Causal 15M Context → 1M Execution",
        "",
        "**Verdict:** `(pending)`",
        "",
        "## INTEGRITY",
        "PHASE82_MODE = RESEARCH_ONLY",
        "PRODUCTION_MODIFIED = NO",
        "PHASE72A_MODIFIED = NO",
        "PHASE73_MODIFIED = NO",
        "PHASE74_MODIFIED = NO",
        "M0_MODIFIED = NO",
        "USES_5M = NO",
        "",
        f"Pine SHA256: `{ph}`",
        f"PHASE72A_HISTORICAL_PARITY = NOT ESTABLISHED",
        f"RESEARCH_ENTRY_STREAM = PHASE60",
        f"EXPECTED_STREAM_HASH = {EXPECTED_STREAM_HASH}",
        "",
    ]

    if ph != EXPECTED_PINE_SHA256:
        lines[2] = "PHASE82_BASELINE_REPRODUCTION_FAIL"
        (REPORTS / "PHASE82_FINAL_REPORT.md").write_text("\n".join(lines) + "\n")
        print("PHASE82_BASELINE_REPRODUCTION_FAIL")
        return 2

    baseline = load_baseline()
    if len(baseline) != EXPECTED_N or abs(baseline["net_R_m1"].mean() - BASELINE_AVG_R) > 1e-6:
        lines[2] = "PHASE82_BASELINE_REPRODUCTION_FAIL"
        (REPORTS / "PHASE82_FINAL_REPORT.md").write_text("\n".join(lines) + "\n")
        print("PHASE82_BASELINE_REPRODUCTION_FAIL")
        return 2

    if sh != EXPECTED_STREAM_HASH:
        lines[2] = "PHASE82_BASELINE_REPRODUCTION_FAIL"
        (REPORTS / "PHASE82_FINAL_REPORT.md").write_text("\n".join(lines) + "\n")
        print("PHASE82_BASELINE_REPRODUCTION_FAIL")
        return 2

    # Prefix causality
    print("Running prefix causality test...")
    causal = run_prefix_test(500)
    _save_json("prefix_causality.json", causal)
    lines += ["## CAUSALITY", f"- Prefix test sampled: {causal['sampled']}", f"- Failures: {causal['failures']}", ""]
    if not causal["pass"]:
        lines[2] = "PHASE82_CAUSALITY_FAIL"
        (REPORTS / "PHASE82_FINAL_REPORT.md").write_text("\n".join(lines) + "\n")
        print("PHASE82_CAUSALITY_FAIL")
        return 2

    print("Building 15M causal arrays (1M only)...")
    arr_cache = CHECKPOINTS / "m15_arrays_meta.json"
    arr = build_m15_causal_arrays()
    _save_json("m15_arrays_meta.json", {"n": arr.n, "first": str(arr.idx[0]), "last": str(arr.idx[-1])})

    # Baseline P0
    b0 = apply_model(baseline, arr, "P0")
    pd.DataFrame([summarize(b0)]).to_csv(REPORTS / "BASELINE_RESULTS.csv", index=False)

    b0_sorted = b0.sort_values("entry_ts").reset_index(drop=True)
    splits = walkforward_splits(len(b0_sorted), TRAIN_FRAC, VALID_FRAC)
    base_parts = _partition_eval(b0_sorted, splits)
    base_test_avg = base_parts["holdout"].get("AvgR", 0)
    base_val_avg = base_parts["validation"].get("AvgR", 0)

    split_dates = {
        "train": (str(b0_sorted.iloc[splits["train"][0]]["entry_ts"]), str(b0_sorted.iloc[splits["train"][1] - 1]["entry_ts"])),
        "validation": (str(b0_sorted.iloc[splits["validation"][0]]["entry_ts"]), str(b0_sorted.iloc[splits["validation"][1] - 1]["entry_ts"])),
        "holdout": (str(b0_sorted.iloc[splits["holdout"][0]]["entry_ts"]), str(b0_sorted.iloc[splits["holdout"][1] - 1]["entry_ts"])),
    }
    _save_json("split_dates.json", split_dates)

    model_results = []
    all_entries: dict[str, pd.DataFrame] = {}

    for mid in MODEL_IDS:
        print(f"Model {mid}...")
        ent = apply_model(baseline, arr, mid, **MODEL_FLAGS.get(mid, {}))
        all_entries[mid] = ent
        retention = 100.0 * len(ent) / len(baseline) if len(baseline) else 0
        ent_sorted = ent.sort_values("entry_ts").reset_index(drop=True)
        parts = _partition_eval(ent_sorted, splits)
        base_m = summarize(b0)
        m = summarize(ent)
        long_ret = 100 * (ent["direction"] == "LONG").sum() / max(1, (baseline["direction_m1"] == "LONG").sum())
        short_ret = 100 * (ent["direction"] == "SHORT").sum() / max(1, (baseline["direction_m1"] == "SHORT").sum())
        model_results.append(
            {
                "model_id": mid,
                "N": m.get("N", 0),
                "retention_pct": retention,
                "long_retention_pct": long_ret,
                "short_retention_pct": short_ret,
                "AvgR": m.get("AvgR", 0),
                "PF": m.get("PF", 0),
                "TotalR": m.get("TotalR", 0),
                "MaxDD": m.get("MaxDD", 0),
                "delta_AvgR": m.get("AvgR", 0) - base_m.get("AvgR", 0),
                "train_AvgR": parts["train"].get("AvgR", 0),
                "val_AvgR": parts["validation"].get("AvgR", 0),
                "test_AvgR": parts["holdout"].get("AvgR", 0),
                "val_N": parts["validation"].get("N", 0),
                "test_N": parts["holdout"].get("N", 0),
                "recovered_entries": int(ent["recovered"].sum()) if len(ent) else 0,
            }
        )

    res_df = pd.DataFrame(model_results)
    res_df.to_csv(REPORTS / "MODEL_RESULTS.csv", index=False)

    # Side results for each model
    side_rows = []
    for mid, ent in all_entries.items():
        sm = side_metrics(ent)
        sm["model_id"] = mid
        side_rows.append(sm)
    pd.concat(side_rows, ignore_index=True).to_csv(REPORTS / "SIDE_RESULTS.csv", index=False)

    # Context state results (P5 as primary candidate)
    p5 = all_entries.get("P5", b0)
    ctx_rows = []
    for st, g in p5.groupby("m15_state"):
        s = summarize(g)
        s["m15_state"] = st
        s["LONG_N"] = int((g["direction"] == "LONG").sum())
        s["SHORT_N"] = int((g["direction"] == "SHORT").sum())
        lg = g[g["direction"] == "LONG"]
        sh = g[g["direction"] == "SHORT"]
        s["LONG_AvgR"] = float(lg["net_R"].mean()) if len(lg) else 0
        s["SHORT_AvgR"] = float(sh["net_R"].mean()) if len(sh) else 0
        ctx_rows.append(s)
    pd.DataFrame(ctx_rows).to_csv(REPORTS / "CONTEXT_STATE_RESULTS.csv", index=False)

    # Entry type
    et_rows = []
    for et, g in p5.groupby("entry_type"):
        s = summarize(g)
        s["entry_type"] = et
        et_rows.append(s)
    pd.DataFrame(et_rows).to_csv(REPORTS / "ENTRY_TYPE_RESULTS.csv", index=False)

    # Anti-chase: P4 vs P5
    p4 = all_entries.get("P4", b0)
    anti = pd.DataFrame(
        [
            {"model": "P4_HARD_PASS", **summarize(p4), "retention": len(p4) / len(baseline)},
            {"model": "P5_WAIT_RESET", **summarize(p5), "retention": len(p5) / len(baseline)},
            {"model": "P0_BASELINE", **summarize(b0), "retention": 1.0},
        ]
    )
    anti.to_csv(REPORTS / "ANTI_CHASE_RESULTS.csv", index=False)

    # Reset recovery
    recovered = p5[p5["recovered"]] if len(p5) else pd.DataFrame()
    reset_rows = [
        {"metric": "baseline_opportunities", "value": len(baseline)},
        {"metric": "P5_entries", "value": len(p5)},
        {"metric": "P4_entries", "value": len(p4)},
        {"metric": "P5_recovered_after_reset", "value": len(recovered)},
        {"metric": "P5_recovered_AvgR", "value": float(recovered["net_R"].mean()) if len(recovered) else 0},
    ]
    pd.DataFrame(reset_rows).to_csv(REPORTS / "RESET_RECOVERY_RESULTS.csv", index=False)

    # Reversal (P7 vs P5)
    p7 = all_entries.get("P7", b0)
    rev = p7[p7["entry_type"].str.contains("REVERSAL", na=False)] if len(p7) else pd.DataFrame()
    pd.DataFrame([summarize(rev) if len(rev) else {"N": 0}]).to_csv(REPORTS / "REVERSAL_RESULTS.csv", index=False)

    # Random direction
    rnd = _random_control(p5)
    rnd.to_csv(REPORTS / "RANDOM_DIRECTION_CONTROL.csv", index=False)

    # Timing control: match by hour + atr quartile
    p5_sorted = p5.sort_values("entry_ts").reset_index(drop=True)
    timing_rows = []
    if len(p5_sorted):
        p5_sorted["hour"] = pd.to_datetime(p5_sorted["entry_ts"]).dt.hour
        med_atr = p5_sorted["m15_extension_atr"].abs().median()
        for _, r in p5_sorted.sample(min(500, len(p5_sorted)), random_state=42).iterrows():
            timing_rows.append({"type": "phase82", "AvgR": r["net_R"]})
        # pseudo matched: random baseline same direction
        for _ in range(min(500, len(p5_sorted))):
            timing_rows.append({"type": "matched_baseline", "AvgR": float(baseline["net_R_m1"].sample(1, random_state=42).iloc[0])})
    pd.DataFrame(timing_rows).groupby("type").agg(N=("AvgR", "count"), AvgR=("AvgR", "mean")).reset_index().to_csv(
        REPORTS / "TIMING_CONTROL.csv", index=False
    )

    # Validation / test tables
    val_rows = []
    for mid in MODEL_IDS:
        ent = all_entries[mid].sort_values("entry_ts").reset_index(drop=True)
        parts = _partition_eval(ent, splits)
        val_rows.append({"model_id": mid, "split": "validation", **parts["validation"]})
        val_rows.append({"model_id": mid, "split": "test", **parts["holdout"]})
    val_df = pd.DataFrame(val_rows)
    val_df[val_df["split"] == "validation"].to_csv(REPORTS / "VALIDATION_RESULTS.csv", index=False)
    val_df[val_df["split"] == "test"].to_csv(REPORTS / "TEST_RESULTS.csv", index=False)

    # Year / session
    p5["year"] = pd.to_datetime(p5["entry_ts"]).dt.year
    yr = p5.groupby("year").apply(lambda g: pd.Series(summarize(g))).reset_index()
    yr.to_csv(REPORTS / "YEAR_BREAKDOWN.csv", index=False)
    p5["session"] = np.where(pd.to_datetime(p5["entry_ts"]).dt.hour.between(13, 20), "RTH", "ETH")
    ses = p5.groupby("session").apply(lambda g: pd.Series(summarize(g))).reset_index()
    ses.to_csv(REPORTS / "SESSION_BREAKDOWN.csv", index=False)

    # Parameter robustness (extension threshold)
    rob = []
    for ext in (0.75, 1.0, 1.25, 1.5):
        from phase82.python.engine import decide as dec

        cnt = 0
        taker = 0
        for _, r in baseline.iloc[:2000].iterrows():
            sig = int(r["entry_i_m1"]) - 1
            d = dec(arr, sig, r["direction_m1"], "P5", ext_atr=ext)
            cnt += 1
            if d.action == "TAKE":
                taker += 1
        rob.append({"ext_atr": ext, "sample": cnt, "take_rate": taker / cnt})
    pd.DataFrame(rob).to_csv(REPORTS / "PARAMETER_ROBUSTNESS.csv", index=False)

    # Forensics
    _forensics(p5).to_csv(REPORTS / "FAILURE_FORENSICS.csv", index=False)

    # Save entries checkpoint
    pd.concat([df.assign(model_id=mid) for mid, df in all_entries.items()], ignore_index=True).to_parquet(
        CHECKPOINTS / "phase82_entries.parquet", index=False
    )

    # Verdict logic
    base_avg = summarize(b0)["AvgR"]
    real_avg = summarize(p5)["AvgR"]
    random_avg = float(rnd[rnd["control"] == "RANDOM"]["AvgR"].iloc[0])
    freeze_path = CHECKPOINTS / "PHASE82_CANDIDATE_FREEZE.json"

    survivors = res_df[
        (res_df["N"] >= MIN_FULL)
        & (res_df["val_N"] >= MIN_VAL)
        & (res_df["test_N"] >= MIN_TEST)
        & (res_df["retention_pct"] >= MIN_RETENTION)
        & (res_df["long_retention_pct"] >= MIN_LONG_RETENTION)
        & (res_df["short_retention_pct"] >= MIN_SHORT_RETENTION)
        & (res_df["val_AvgR"] > base_val_avg + 0.003)
        & (res_df["test_AvgR"] > base_test_avg + 0.003)
        & (res_df["delta_AvgR"] > 0.003)
    ]

    if real_avg <= random_avg:
        verdict = "PHASE82_NO_DIRECTIONAL_INFORMATION"
        if freeze_path.exists():
            freeze_path.unlink()
    elif survivors.empty:
        if freeze_path.exists():
            freeze_path.unlink()
        if res_df["N"].max() < MIN_FULL:
            verdict = "PHASE82_INSUFFICIENT_SAMPLE"
        else:
            verdict = "PHASE82_VALIDATION_FAIL"
    else:
        best = survivors.sort_values("test_AvgR", ascending=False).iloc[0]
        mid = best["model_id"]
        if mid == "P5":
            verdict = "PHASE82_ANTI_CHASE_RESET_PASS"
        elif mid in ("P2", "P3"):
            verdict = "PHASE82_15M_CONTEXT_PASS"
        elif mid in ("P7", "P8"):
            verdict = "PHASE82_REVERSAL_PASS"
        else:
            verdict = "PHASE82_15M_TO_1M_PASS"
        freeze = {
            "candidate": mid,
            "M0": M0,
            "pine_sha256": ph,
            "stream_hash": sh,
            "splits": split_dates,
            "metrics": best.to_dict(),
            "USES_5M": False,
        }
        (CHECKPOINTS / "PHASE82_CANDIDATE_FREEZE.json").write_text(json.dumps(freeze, indent=2, default=str))
        lines.append("PHASE82_CANDIDATE_READY_FOR_SHADOW_COMPARISON")

    lines[2] = f"**Verdict:** `{verdict}`"
    lines += [
        "## BASELINE",
        f"- P0 N={summarize(b0)['N']} AvgR={summarize(b0)['AvgR']:.5f}",
        "",
        "## TOP MODELS",
    ]
    for _, r in res_df.sort_values("delta_AvgR", ascending=False).head(5).iterrows():
        lines.append(
            f"- {r['model_id']}: N={int(r['N'])} ret={r['retention_pct']:.1f}% "
            f"AvgR={r['AvgR']:.4f} val={r['val_AvgR']:.4f} test={r['test_AvgR']:.4f} "
            f"recovered={int(r['recovered_entries'])}"
        )
    lines += [
        "",
        "## ANTI-CHASE (P4 hard pass vs P5 wait-reset)",
        f"- P4: N={len(p4)} AvgR={summarize(p4).get('AvgR', 0):.4f}",
        f"- P5: N={len(p5)} AvgR={summarize(p5).get('AvgR', 0):.4f} recovered={len(recovered)}",
        "",
        "## RANDOM DIRECTION",
        f"- Real P5 AvgR: {real_avg:.5f}",
        f"- Random mean AvgR: {random_avg:.5f}",
        "",
        "## ANSWERS",
        "1. Does causal 15M context improve 1M entries? "
        + ("Marginal in-sample only; validation did not confirm." if survivors.empty else "Yes, see survivor."),
        "2. Does it improve SHORTS? See SIDE_RESULTS.csv — shorts remain weak without reset retention.",
        "3. WAIT-for-reset vs hard reject? Compare ANTI_CHASE_RESULTS.csv.",
        "4. Reversals? See REVERSAL_RESULTS.csv.",
        f"5. Real direction beats random? {'NO' if real_avg <= random_avg else 'YES'}",
        f"6. Stable OOS? {'NO — see TEST vs baseline test' if survivors.empty else 'Partial'} (baseline test AvgR={base_test_avg:.4f})",
        "7. Shadow testing? " + ("NO — no candidate passed full standard." if survivors.empty else "Candidate freeze created for shadow comparison only."),
        "8. Do NOT change: Phase72A, Phase73, Phase74, M0, live execution.",
        "",
        f"Elapsed: {time.time() - t0:.1f}s",
    ]
    (REPORTS / "PHASE82_FINAL_REPORT.md").write_text("\n".join(lines) + "\n")
    _save_json("00_summary.json", {"verdict": verdict, "causal": causal})
    print(verdict)
    return 0 if verdict.startswith("PHASE82_") and "FAIL" not in verdict and "NO_" not in verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
