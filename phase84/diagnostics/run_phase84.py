#!/usr/bin/env python3
"""Phase84 — Phase72A price-action execution quality research runner."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase84.python.causality import truncation_test
from phase84.python.config import (
    CAUSALITY_SAMPLE,
    CHECKPOINTS,
    COST_MULTS,
    EXPECTED_PINE_SHA256,
    MIN_FULL,
    MIN_TEST,
    MIN_VAL,
    REPORTS,
    TRAIN_FRAC,
    VALID_FRAC,
    pine_sha256,
    m0_reference_hash,
)
from phase84.python.controls import random_pass_benchmark, random_wait_benchmark
from phase84.python.data import load_m1
from phase84.python.diagnostics_outcomes import attach_diagnostic_outcomes
from phase84.python.features import enrich_signals
from phase84.python.metrics import rejected_shadow, retention_stats, summarize_r
from phase84.python.m0 import m0_provenance, simulate_m0_trade, simulate_opportunities, verify_m0_baseline_sample
from phase84.python.opportunity import dedupe_opportunities
from phase84.python.signals import load_all_signals, provenance_report
from phase84.python.state_machine import ExecDecision, apply_variant
from phase84.python.wait_path import (
    classify_wait_attribution,
    decide_e5_wait_reset,
    decide_e7_retest_hold,
)

VARIANTS = ("E0", "E1", "E2", "E3", "E4", "E5", "E6", "E7")


def _chronological_splits(n: int) -> dict:
    t_end = int(n * TRAIN_FRAC)
    v_end = int(n * VALID_FRAC)
    return {"train": (0, t_end), "valid": (t_end, v_end), "test": (v_end, n)}


def _split_metrics(df: pd.DataFrame, splits: dict, r_col: str) -> dict:
    out = {}
    for name, (a, b) in splits.items():
        sub = df.iloc[a:b]
        out[name] = summarize_r(sub, r_col)
    return out


def _decision_for_variant(
    row: pd.Series,
    variant: str,
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    op: np.ndarray,
    atr: np.ndarray,
) -> tuple:
    baseline_entry_i = int(row["entry_i"])
    si = int(row["signal_i"])
    direction = row["phase72a_direction"]

    if variant == "E5":
        dec = decide_e5_wait_reset(hi, lo, cl, op, atr, si, direction, baseline_entry_i)
        return dec, dec.entry_i
    if variant == "E7":
        dec = decide_e7_retest_hold(hi, lo, cl, op, atr, si, direction, baseline_entry_i)
        return dec, dec.entry_i

    dec = apply_variant(row, variant)
    ei = baseline_entry_i if dec.entry_i < 0 else dec.entry_i
    return dec, ei


def _run_variant(enriched: pd.DataFrame, m1: pd.DataFrame, variant: str) -> pd.DataFrame:
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float) if "atr" in m1.columns else (hi - lo)
    idx = m1.index

    rows = []
    for _, row in enriched.iterrows():
        dec, ei = _decision_for_variant(row, variant, hi, lo, cl, op, atr)
        baseline = simulate_opportunities(
            pd.DataFrame([row]), m1, entry_i_col="entry_i", atr_col="atr_signal"
        ).iloc[0]

        rec = row.to_dict()
        rec["variant"] = variant
        rec["execution_decision"] = dec.decision.value
        rec["execution_reason"] = dec.reason
        rec["execution_decision_time"] = idx[int(row["signal_i"])].isoformat()
        rec["baseline_net_R"] = baseline["net_R"]
        rec["baseline_gross_R"] = baseline["gross_R"]
        rec["baseline_exit_reason"] = baseline["exit_reason"]

        take = dec.decision.value.startswith("TAKE")
        rec["take"] = take
        rec["entry_delay_bars"] = dec.entry_delay_bars

        if take and ei >= 0 and ei < len(cl):
            atr_t = float(row.get("atr_signal", atr[ei]))
            ep = float(op[ei])
            traded = simulate_m0_trade(hi, lo, cl, op, idx, ei, row["phase72a_direction"], ep, atr_t)
            rec["entry_i"] = ei
            rec["entry_price"] = traded["entry_price"]
            rec["net_R"] = traded["net_R"]
            rec["gross_R"] = traded["gross_R"]
            rec["exit_reason"] = traded["exit_reason"]
            rec["delta_R"] = traded["net_R"] - baseline["net_R"]
            rec["wait_class"] = classify_wait_attribution(baseline["net_R"], traded["net_R"])
        else:
            rec["net_R"] = np.nan
            rec["gross_R"] = np.nan
            rec["exit_reason"] = "PASS"
            rec["delta_R"] = np.nan
            rec["wait_class"] = ""

        rows.append(rec)

    return pd.DataFrame(rows)


def _stage_a_descriptive(e0: pd.DataFrame, enriched: pd.DataFrame) -> None:
    stage_a = []
    for w in (10, 20, 30):
        col = f"range_position_{w}"
        if col not in enriched.columns:
            continue
        buckets = enriched[col].apply(
            lambda x: "0.00-0.20" if x < 0.2 else "0.20-0.40" if x < 0.4 else "0.40-0.60"
            if x < 0.6 else "0.60-0.80" if x < 0.8 else "0.80-1.00"
        )
        grp = e0.groupby(buckets)["baseline_net_R"].agg(["count", "mean"])
        grp["window"] = w
        stage_a.append(grp.reset_index().rename(columns={"index": "bucket"}))

    if stage_a:
        pd.concat(stage_a).to_csv(REPORTS / "STAGE_A_MID_RANGE.csv", index=False)

    ext_rows = []
    for col in ("move_3m_ATR", "move_5m_ATR", "move_10m_ATR"):
        if col not in enriched.columns:
            continue
        for direction in ("LONG", "SHORT"):
            sub = e0.loc[e0["phase72a_direction"] == direction]
            ext_rows.append({
                "feature": col,
                "direction": direction,
                "mean": float(sub[col].mean()) if len(sub) else 0.0,
                "baseline_AvgR": float(sub["baseline_net_R"].mean()) if len(sub) else 0.0,
            })
    if ext_rows:
        pd.DataFrame(ext_rows).to_csv(REPORTS / "STAGE_A_EXTENSION.csv", index=False)

    break_rows = []
    for label, mask_col in (
        ("NO_BREAK", None),
        ("WICK_BREAK", "break_wick"),
        ("CLOSE_ACCEPT", "break_close_accept"),
    ):
        if mask_col is None:
            sub = e0.loc[~e0["break_wick"] & ~e0["break_close_accept"]]
        else:
            sub = e0.loc[e0[mask_col].astype(bool)]
        break_rows.append({
            "category": label,
            "N": len(sub),
            "AvgR": float(sub["baseline_net_R"].mean()) if len(sub) else 0.0,
        })
    pd.DataFrame(break_rows).to_csv(REPORTS / "STAGE_A_BREAKOUT_ACCEPTANCE.csv", index=False)

    fail_sub = e0.loc[e0["failed_break"].astype(bool)]
    pd.DataFrame([{
        "failed_break_N": len(fail_sub),
        "failed_break_AvgR": float(fail_sub["baseline_net_R"].mean()) if len(fail_sub) else 0.0,
        "all_AvgR": float(e0["baseline_net_R"].mean()),
    }]).to_csv(REPORTS / "STAGE_A_FAILED_BREAK.csv", index=False)


def _representative_review_set(e0: pd.DataFrame, variants: dict[str, pd.DataFrame]) -> None:
    rng = np.random.default_rng(42)
    picks = []

    def sample(df: pd.DataFrame, label: str, cond, n: int = 20):
        sub = df.loc[cond] if callable(cond) else df[cond]
        if sub.empty:
            return
        ix = rng.choice(sub.index, size=min(n, len(sub)), replace=False)
        for i in ix:
            r = sub.loc[i]
            picks.append({
                "review_set": label,
                "phase72a_event_id": r.get("phase72a_event_id"),
                "signal_time": r.get("phase72a_signal_time"),
                "direction": r.get("phase72a_direction"),
                "baseline_net_R": r.get("baseline_net_R"),
                "execution_decision": r.get("execution_decision", "E0"),
                "execution_reason": r.get("execution_reason", ""),
            })

    sample(e0, "baseline_winner", e0["baseline_net_R"] > 0)
    sample(e0, "baseline_loser", e0["baseline_net_R"] <= 0)

    for vname, vdf in variants.items():
        if vname == "E0":
            continue
        passed = ~vdf["take"].astype(bool)
        sample(vdf, f"{vname}_PASS", passed)
        waited = vdf["entry_delay_bars"].astype(int) > 0
        sample(vdf, f"{vname}_WAIT", waited)
        reset = vdf["execution_decision"] == ExecDecision.TAKE_AFTER_RESET.value
        sample(vdf, f"{vname}_TAKE_AFTER_RESET", reset)

    if picks:
        pd.DataFrame(picks).to_csv(REPORTS / "REPRESENTATIVE_REVIEW_SET.csv", index=False)


def _answer_key_questions(e0: pd.DataFrame, summaries: pd.DataFrame) -> str:
    lines = ["# Phase84 Key Questions (provisional descriptive where N insufficient)", ""]

    def q(num: str, text: str, answer: str):
        lines.append(f"**{num}.** {text}")
        lines.append(f"- {answer}")
        lines.append("")

    mid = REPORTS / "STAGE_A_MID_RANGE.csv"
    if mid.exists():
        df = pd.read_csv(mid)
        mid20 = df.loc[(df["window"] == 20) & (df["bucket"] == "0.40-0.60"), "mean"]
        all_r = float(e0["baseline_net_R"].mean()) if len(e0) else 0.0
        mr = float(mid20.iloc[0]) if len(mid20) else all_r
        q("Q1", "Are Phase72A signals in mid-range actually worse?",
          f"20-bar mid-range (0.40-0.60) AvgR={mr:.3f} vs all={all_r:.3f} (descriptive only, N={len(e0)})")
    else:
        q("Q1", "Are Phase72A signals in mid-range actually worse?", "Insufficient aligned sample.")

    ba = REPORTS / "STAGE_A_BREAKOUT_ACCEPTANCE.csv"
    if ba.exists():
        df = pd.read_csv(ba)
        acc = df.loc[df["category"] == "CLOSE_ACCEPT", "AvgR"]
        q("Q2", "Does breakout acceptance improve Phase72A execution?",
          f"Close acceptance AvgR={float(acc.iloc[0]):.3f} vs no-break (see STAGE_A_BREAKOUT_ACCEPTANCE.csv)")
    else:
        q("Q2", "Does breakout acceptance improve execution?", "Insufficient sample.")

    for qnum, col, vname, qtext in (
        ("Q3", "E3", "failed_break", "Does immediate failed-break identify bad entries?"),
        ("Q4", "E4", "extension", "Does extension identify late/chased signals?"),
        ("Q5", "E5", "wait_reset", "Does WAIT → RESET improve entries?"),
        ("Q8", "E7", "retest", "Does retest + hold add value?"),
        ("Q9", "E6", "commitment", "Does immediate commitment add value?"),
    ):
        sub = summaries.loc[summaries["variant"] == col]
        if not sub.empty:
            r = sub.iloc[0]
            q(qnum, qtext,
              f"{vname}: retention={r.get('retention_pct', 0):.1f}% AvgR={r.get('AvgR', 0):.3f} "
              f"vs E0={float(summaries.loc[summaries['variant']=='E0','AvgR'].iloc[0]):.3f}")
        else:
            q(qnum, qtext, "Not run or insufficient sample.")

    q("Q6", "Does WAIT beat random delay?", "See WAIT_ATTRIBUTION.csv and control_random_wait_*.json")
    q("Q7", "Does PASS beat random rejection?", "See control_random_pass_*.json per variant")
    q("Q10", "LONG/SHORT consistency?", "See LONG_SHORT_BREAKDOWN.csv")
    q("Q11", "Cost robustness?", "See COST_ROBUSTNESS.csv")
    q("Q12", "Validation/test survival?", "See TRAIN_VALIDATION_TEST.json")
    q("Q13", "Winners accidentally removed?", "See REJECTED_TRADE_LEDGER.csv shadow scores")
    q("Q14", "Worth complexity?", "NOT YET PROVABLE without >=500 real events and validated edge")

    return "\n".join(lines)


def main() -> int:
    t0 = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    ph = pine_sha256()
    print(f"PHASE72A HASH: {ph}")
    if ph != EXPECTED_PINE_SHA256:
        print("PHASE84_SIGNAL_FREEZE_FAIL")
        return 2
    print("PHASE72A_FREEZE_OK = TRUE")

    m0_meta = m0_provenance()
    m0_meta["M0_REFERENCE_HASH"] = m0_reference_hash()
    (REPORTS / "M0_PROVENANCE.json").write_text(json.dumps(m0_meta, indent=2))

    m0_check = verify_m0_baseline_sample(30)
    (CHECKPOINTS / "m0_baseline_check.json").write_text(json.dumps(m0_check, indent=2))
    print(f"M0 baseline sample check: {m0_check}")
    if not m0_check.get("pass"):
        print("PHASE84_BASELINE_REPRODUCTION_FAIL")
        return 2
    print("M0 BASELINE REPRODUCED: YES")

    m1 = load_m1()
    signals, sig_meta = load_all_signals(m1.index)
    (REPORTS / "SIGNAL_PROVENANCE.md").write_text(provenance_report(sig_meta))

    webhook_raw = sig_meta.get("REAL_WEBHOOK_LOG", 0)
    if signals.empty:
        verdict = "PHASE84_AWAITING_REAL_PHASE72A_SIGNAL_STREAM"
        if webhook_raw > 0:
            verdict = "PHASE84_FRAMEWORK_READY"
        final = f"""# PHASE84 Final Report

PHASE84 VERDICT: {verdict}

PHASE72A SOURCE: REAL (webhook raw={webhook_raw}) but **0 aligned to M1**

PHASE72A HASH: {ph}

M0 REFERENCE: {m0_meta['M0_REFERENCE_PATH']} ({m0_meta['M0_REFERENCE_FUNCTION']})

M0 BASELINE REPRODUCED: YES

**Alignment blocker:** Webhook signals ({sig_meta.get('alignment', {}).get('signal_range', 'n/a')})
fall outside local M1 coverage ({sig_meta.get('alignment', {}).get('m1_range', 'n/a')}).
Extend `phase16/data/nq_continuous_1m_raw.csv` or place TV/ledger exports in `phase84/data/`.

CAUSALITY: NOT RUN (no aligned opportunities)

DOES EXECUTION ADD REAL VALUE? NOT YET PROVABLE

PRODUCTION CHANGES: NONE

NEXT ACTION: WAIT FOR REAL PHASE72A DATA aligned to M1 (TV export / ledger parity / extended M1)

Elapsed: {time.time()-t0:.1f}s
"""
        (REPORTS / "PHASE84_FINAL_REPORT.md").write_text(final)
        (REPORTS / "KEY_QUESTIONS.md").write_text(
            "# Phase84 Key Questions\n\nAll deferred — zero aligned Phase72A opportunities.\n"
        )
        print(verdict)
        print("No aligned Phase72A signals. See phase84/reports/SIGNAL_PROVENANCE.md")
        return 0

    signals = dedupe_opportunities(signals)
    enriched = enrich_signals(signals, m1)
    enriched.to_csv(REPORTS / "OPPORTUNITY_LEDGER.csv", index=False)

    e0 = _run_variant(enriched, m1, "E0")
    e0 = attach_diagnostic_outcomes(e0, m1)
    e0.to_csv(REPORTS / "TRADE_LEDGER_E0.csv", index=False)
    baseline = summarize_r(e0, "baseline_net_R")
    (CHECKPOINTS / "e0_baseline.json").write_text(json.dumps(baseline, indent=2))

    splits = _chronological_splits(len(e0))
    split_e0 = _split_metrics(e0, splits, "baseline_net_R")
    (REPORTS / "TRAIN_VALIDATION_TEST.json").write_text(json.dumps(split_e0, indent=2))

    _stage_a_descriptive(e0, enriched)

    variant_frames: dict[str, pd.DataFrame] = {"E0": e0}
    variant_rows = []
    wait_rows = []

    for v in VARIANTS:
        if v == "E0":
            res = e0
        else:
            res = _run_variant(enriched, m1, v)
            res.to_csv(REPORTS / f"TRADE_LEDGER_{v}.csv", index=False)
        variant_frames[v] = res

        taken = res["take"].astype(bool)
        rej = res.loc[~taken]
        summ = summarize_r(res.loc[taken], "net_R")
        shadow = rejected_shadow(rej, "baseline_net_R")
        variant_rows.append({
            "variant": v,
            **summ,
            **retention_stats(taken),
            "rejected_baseline_N": shadow.get("N", 0),
            "rejected_baseline_AvgR": shadow.get("AvgR", 0.0),
            "rejected_baseline_TotalR": shadow.get("TotalR", 0.0),
        })

        if v != "E0" and taken.sum() > 0:
            ctrl = random_pass_benchmark(res, taken, "net_R")
            (CHECKPOINTS / f"control_random_pass_{v}.json").write_text(
                json.dumps(ctrl, indent=2, default=str)
            )

        if v in ("E5", "E7") and "wait_class" in res.columns:
            waited = res.loc[res["entry_delay_bars"].astype(int) > 0]
            if not waited.empty:
                wait_rows.extend(waited.to_dict("records"))
            rw = random_wait_benchmark(res)
            (CHECKPOINTS / f"control_random_wait_{v}.json").write_text(json.dumps(rw, indent=2))

    pd.DataFrame(variant_rows).to_csv(REPORTS / "VARIANT_SUMMARY.csv", index=False)

    if wait_rows:
        pd.DataFrame(wait_rows).to_csv(REPORTS / "WAIT_ATTRIBUTION.csv", index=False)

    rejected_all = pd.concat([
        res.loc[~res["take"].astype(bool)].assign(variant=v)
        for v, res in variant_frames.items() if v != "E0"
    ], ignore_index=True)
    if not rejected_all.empty:
        rejected_all.to_csv(REPORTS / "REJECTED_TRADE_LEDGER.csv", index=False)

    ls_rows = []
    for v, res in variant_frames.items():
        rcol = "baseline_net_R" if v == "E0" else "net_R"
        taken = res if v == "E0" else res.loc[res["take"].astype(bool)]
        for d in ("LONG", "SHORT"):
            sub = taken.loc[taken["phase72a_direction"] == d]
            ls_rows.append({"variant": v, "direction": d, **summarize_r(sub, rcol)})
    pd.DataFrame(ls_rows).to_csv(REPORTS / "LONG_SHORT_BREAKDOWN.csv", index=False)

    cost_rows = []
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    idx = m1.index
    for tick_slip in (0, 1, 2):
        for cm in COST_MULTS:
            rs = []
            for _, row in e0.iterrows():
                ei = int(row["entry_i"])
                r = simulate_m0_trade(
                    hi, lo, cl, op, idx, ei, row["phase72a_direction"],
                    float(op[ei]), float(row["atr_signal"]),
                    tick_slippage=tick_slip, cost_mult=cm,
                )
                rs.append(r["net_R"])
            cost_rows.append({
                "variant": "E0",
                "tick_slippage": tick_slip,
                "cost_mult": cm,
                "AvgR": float(np.mean(rs)),
                "TotalR": float(np.sum(rs)),
            })
    pd.DataFrame(cost_rows).to_csv(REPORTS / "COST_ROBUSTNESS.csv", index=False)

    _representative_review_set(e0, variant_frames)

    causal = truncation_test(m1, enriched, sample=min(CAUSALITY_SAMPLE, len(enriched)))
    (REPORTS / "CAUSALITY_AUDIT.json").write_text(json.dumps(causal, indent=2))
    print(f"Causality: {causal}")

    summaries = pd.DataFrame(variant_rows)
    (REPORTS / "KEY_QUESTIONS.md").write_text(_answer_key_questions(e0, summaries))

    real_n = sig_meta.get("real_count", 0)
    if real_n < MIN_FULL:
        verdict = "PHASE84_AWAITING_REAL_PHASE72A_SIGNAL_STREAM"
        if real_n > 0:
            verdict = "PHASE84_FRAMEWORK_READY"
    elif causal.get("pass") is False:
        verdict = "PHASE84_CAUSALITY_FAIL"
    else:
        verdict = "PHASE84_INFORMATION_ONLY"

    final = f"""# PHASE84 Final Report

PHASE84 VERDICT: {verdict}

PHASE72A SOURCE: {'REAL' if real_n > 0 else 'PROVISIONAL'} (n={real_n}, aligned={len(enriched)})

PHASE72A HASH: {ph}

M0 REFERENCE: {m0_meta['M0_REFERENCE_PATH']} ({m0_meta['M0_REFERENCE_FUNCTION']})

M0 BASELINE REPRODUCED: YES

BASELINE E0: {json.dumps(baseline, indent=2)}

SAMPLE: {real_n} real source events, {len(enriched)} aligned opportunities (preferred >= {MIN_FULL})

CAUSALITY: {'PASS' if causal.get('pass') else 'FAIL'}

DOES EXECUTION ADD REAL VALUE? NOT YET PROVABLE

PRODUCTION CHANGES: NONE

NEXT ACTION: WAIT FOR REAL PHASE72A DATA (TV export / ledger parity / ongoing webhook stream + M1 extension)

See KEY_QUESTIONS.md, VARIANT_SUMMARY.csv, STAGE_A_*.csv for descriptive results.

Elapsed: {time.time()-t0:.1f}s
"""
    (REPORTS / "PHASE84_FINAL_REPORT.md").write_text(final)
    print(f"\nPHASE84 VERDICT: {verdict}")
    return 0 if verdict != "PHASE84_CAUSALITY_FAIL" else 3


if __name__ == "__main__":
    sys.exit(main())
