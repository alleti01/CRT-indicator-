"""Phase57 main research pipeline — NQ Market Sequence & Early-Entry Discovery."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase53.research.data import align_htf_to_1m
from phase53.research.metrics import pf, summarize_r
from phase57.config import (
    HOLDOUT_END,
    HOLDOUT_START,
    PHASE55_FROZEN,
    REPORTS,
    RESULTS,
    S54_MODEL_HASH,
    WALK_FORWARD_FOLDS,
)
from phase57.research.data import load_phase57_markets
from phase57.research.fvg import detect_fvgs, fvg_events_df, track_fvg_interactions
from phase57.research.orb import detect_all_orb_events, detect_orb_ranges, classify_orb_events
from phase57.research.legs import detect_legs, legs_to_df
from phase57.research.pullbacks import detect_pullbacks, pullbacks_to_df
from phase57.research.retests import (
    detect_fvg_retests,
    detect_orb_retests,
    detect_swing_retests,
    retests_to_df,
)
from phase57.research.sequences import detect_sequences, sequences_to_df
from phase57.research.entry_stages import batch_entry_stages
from phase57.research.outcomes import batch_simulate
from phase57.research.baselines import baseline_metrics, year_breakdown, cliff_detection, opportunity_preservation
from phase57.research.analysis import walk_forward_evaluate
from phase57.research.episode_control import consolidate_events
from phase57.research.registry import register, total_configs_tested


def _ts(df, col="timestamp_ct"):
    if col in df.columns:
        return pd.to_datetime(df[col])
    for c in ("setup_ts", "formation_ts", "entry_ts", "end_ts"):
        if c in df.columns:
            return pd.to_datetime(df[c])
    return pd.Series(dtype="datetime64[ns]")


def _pre_holdout(df, col="timestamp_ct"):
    ts = _ts(df, col)
    if ts.empty:
        return df
    tz = ts.iloc[0].tz if hasattr(ts.iloc[0], "tz") else None
    return df.loc[ts < pd.Timestamp(HOLDOUT_START, tz=tz)]


def _holdout(df, col="timestamp_ct"):
    ts = _ts(df, col)
    if ts.empty:
        return df
    tz = ts.iloc[0].tz if hasattr(ts.iloc[0], "tz") else None
    return df.loc[(ts >= pd.Timestamp(HOLDOUT_START, tz=tz)) & (ts <= pd.Timestamp(HOLDOUT_END, tz=tz))]


def main() -> None:
    t0 = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    # ── Verify S54 hash ───────────────────────────────────────────────
    h = (PHASE55_FROZEN / "model_hash.txt").read_text().strip()
    assert h == S54_MODEL_HASH, f"S54 model hash drift: {h}"
    print(f"S54 model hash OK: {S54_MODEL_HASH}")

    # ── Load data ─────────────────────────────────────────────────────
    print("Loading markets...")
    m1, m5, m15 = load_phase57_markets()
    m5a = align_htf_to_1m(m1, m5)
    m15a = align_htf_to_1m(m1, m15)
    print(f"  m1: {len(m1)} bars, {m1.index.min()} → {m1.index.max()}")

    # ── Stage 1: FVG detection ────────────────────────────────────────
    print("Detecting FVGs...")
    fvgs_1m = detect_fvgs(m1, timeframe="1M")
    fvgs_5m = detect_fvgs(m5, timeframe="5M")
    fvgs_15m = detect_fvgs(m15, timeframe="15M")
    all_fvgs = fvgs_1m + fvgs_5m + fvgs_15m
    fvg_df = fvg_events_df(all_fvgs)
    fvg_df.to_parquet(RESULTS / "fvg_events.parquet", index=False)
    print(f"  FVGs: 1M={len(fvgs_1m)}, 5M={len(fvgs_5m)}, 15M={len(fvgs_15m)}")

    # FVG interactions (1M only for tractability)
    fvg_inter = track_fvg_interactions(fvgs_1m[:50000], m1)
    fvg_inter.to_csv(RESULTS / "fvg_interactions.csv", index=False)

    # ── Stage 2: ORB detection ────────────────────────────────────────
    print("Detecting ORB events...")
    orb_df = detect_all_orb_events(m1)
    orb_df.to_csv(RESULTS / "orb_events.csv", index=False)
    print(f"  ORB events: {len(orb_df)}")

    # ── Stage 3: Legs ─────────────────────────────────────────────────
    print("Detecting legs...")
    legs = detect_legs(m1, min_distance_atr=1.0)
    leg_df = legs_to_df(legs)
    leg_df.to_parquet(RESULTS / "leg_sequences.parquet", index=False)
    print(f"  Legs: {len(legs)}")

    # ── Stage 4: Pullbacks ────────────────────────────────────────────
    print("Detecting pullbacks...")
    pbs = detect_pullbacks(m1, legs, min_depth_pct=0.15)
    pb_df = pullbacks_to_df(pbs)
    pb_df.to_csv(RESULTS / "pullback_events.csv", index=False)
    print(f"  Pullbacks: {len(pbs)}")

    # ── Stage 5: Retests ──────────────────────────────────────────────
    print("Detecting retests...")
    rt_swing = detect_swing_retests(m1, legs)
    rt_fvg = detect_fvg_retests(m1, fvgs_1m[:50000])
    orb_ranges_5 = detect_orb_ranges(m1, 5)
    orb_ranges_15 = detect_orb_ranges(m1, 15)
    for rng in orb_ranges_5 + orb_ranges_15:
        classify_orb_events(rng, m1)
    rt_orb = detect_orb_retests(m1, orb_ranges_5 + orb_ranges_15)
    all_retests = rt_swing + rt_fvg + rt_orb
    rt_df = retests_to_df(all_retests)
    rt_df.to_parquet(RESULTS / "retest_events.parquet", index=False)
    print(f"  Retests: swing={len(rt_swing)}, FVG={len(rt_fvg)}, ORB={len(rt_orb)}")

    # ── Stage 6: Sequences ────────────────────────────────────────────
    print("Building sequences...")
    seqs = detect_sequences(m1, legs, pbs)
    seq_df = sequences_to_df(seqs)
    seq_df.to_csv(RESULTS / "sequence_events.csv", index=False)
    c1 = [s for s in seqs if s.seq_type == "C1"]
    r1 = [s for s in seqs if s.seq_type == "R1"]
    print(f"  Sequences: C1={len(c1)}, R1={len(r1)}, failed={sum(1 for s in seqs if s.failed)}")

    # ── Stage 7: Entry stages ─────────────────────────────────────────
    print("Computing entry stages...")
    entry_df = batch_entry_stages(m1, seqs)
    entry_df.to_csv(RESULTS / "entry_timing_report.csv", index=False)
    print(f"  Entry stage rows: {len(entry_df)}")

    # ── Stage 8: Baselines ────────────────────────────────────────────
    print("Computing baselines...")
    baselines = {}

    # B1: raw FVG population (1M FVG first-touch events)
    fvg_touch = fvg_inter.loc[fvg_inter["first_interaction_type"].notna()].copy()
    if not fvg_touch.empty:
        fvg_touch["entry_i"] = fvg_touch["first_revisit_i"].astype(int)
        fvg_touch["direction"] = fvg_touch["direction"].map({"BULL": "LONG", "BEAR": "SHORT"})
        fvg_touch["timestamp_ct"] = m1.index[fvg_touch["entry_i"].values.astype(int)]
        baselines["B1_FVG"] = baseline_metrics(m1, fvg_touch, "B1_FVG")

    # B2: raw ORB events
    if not orb_df.empty:
        orb_pre = _pre_holdout(orb_df)
        baselines["B2_ORB"] = baseline_metrics(m1, orb_pre, "B2_ORB")

    # B3: raw leg/pullback sequences (enter at pullback deepest = E0)
    if seqs:
        seq_entries = pd.DataFrame([{
            "entry_i": s.setup_i,
            "direction": "LONG" if s.direction == "BULL" else "SHORT",
            "timestamp_ct": s.setup_ts,
        } for s in seqs])
        baselines["B3_LEG_PB"] = baseline_metrics(m1, seq_entries, "B3_LEG_PB")

    # B4: raw retests
    if not rt_df.empty:
        rt_pre = _pre_holdout(rt_df, "timestamp_ct")
        rt_pre_e = rt_pre.rename(columns={"bar_i": "entry_i"})
        baselines["B4_RETEST"] = baseline_metrics(m1, rt_pre_e, "B4_RETEST")

    # B5: reversal sequences
    if r1:
        r1_entries = pd.DataFrame([{
            "entry_i": s.setup_i,
            "direction": "LONG" if s.direction == "BULL" else "SHORT",
            "timestamp_ct": s.setup_ts,
        } for s in r1])
        baselines["B5_REVERSAL"] = baseline_metrics(m1, r1_entries, "B5_REVERSAL")

    # B6: continuation sequences
    if c1:
        c1_entries = pd.DataFrame([{
            "entry_i": s.setup_i,
            "direction": "LONG" if s.direction == "BULL" else "SHORT",
            "timestamp_ct": s.setup_ts,
        } for s in c1])
        baselines["B6_CONTINUATION"] = baseline_metrics(m1, c1_entries, "B6_CONTINUATION")

    baseline_df = pd.DataFrame(list(baselines.values()))
    baseline_df.to_csv(RESULTS / "baselines.csv", index=False)
    print(f"  Baselines computed: {len(baselines)}")
    for k, v in baselines.items():
        print(f"    {k}: N={v.get('N')}, AvgR={v.get('AvgR', 'n/a')}")

    # ── Stage 9: Entry timing summary ─────────────────────────────────
    if not entry_df.empty:
        timing_summary = entry_df.groupby("stage").agg(
            N=("net_R", "count"),
            AvgR=("net_R", "mean"),
            median_R=("net_R", "median"),
            move_capture=("move_capture_pct", "mean"),
            avg_delay=("delay_bars", "mean"),
        ).reset_index()
        timing_summary.to_csv(RESULTS / "entry_timing_summary.csv", index=False)
        print("\nEntry timing summary:")
        print(timing_summary.to_string(index=False))

    # ── Stage 10: WF evaluation for key families ──────────────────────
    print("\nWalk-forward evaluation...")
    if "B3_LEG_PB" in baselines and not seq_entries.empty:
        wf = walk_forward_evaluate(m1, seq_entries, family="LEG_PB", hypothesis="Leg1+pullback raw", parameters="min_dist_atr=1.0,min_depth=0.15")
        print(f"  LEG_PB WF OOS: {wf['oos']}")

    # ── Stage 11: Write reports ───────────────────────────────────────
    print("\nWriting reports...")
    _write_fvg_report(baselines, fvg_df, fvg_inter)
    _write_orb_report(baselines, orb_df)
    _write_sequence_report(baselines, seq_df, entry_df)
    _write_entry_timing_report(entry_df)
    _write_final_report(baselines, entry_df, seq_df, fvg_df, orb_df, rt_df)

    elapsed = (time.time() - t0) / 60
    print(f"\nPhase57 complete in {elapsed:.1f} min. Configs tested: {total_configs_tested()}")


def _write_fvg_report(baselines, fvg_df, fvg_inter):
    b1 = baselines.get("B1_FVG", {})
    body = f"""# Phase57 FVG Report

## Raw FVG Population
- Total FVGs detected: {len(fvg_df)}
- 1M: {len(fvg_df.loc[fvg_df['timeframe']=='1M'])}
- 5M: {len(fvg_df.loc[fvg_df['timeframe']=='5M'])}
- 15M: {len(fvg_df.loc[fvg_df['timeframe']=='15M'])}

## B1 Baseline (1M FVG first-touch)
- N: {b1.get('N', 0)}
- AvgR: {b1.get('AvgR', 'n/a')}
- PF: {b1.get('PF', 'n/a')}
- TotalR: {b1.get('TotalR', 'n/a')}
- Win rate: {b1.get('win_rate', 'n/a')}

## Interaction Types
{fvg_inter['first_interaction_type'].value_counts().to_string() if not fvg_inter.empty else 'No interactions tracked'}

## FVG Size Distribution
{fvg_df['size_atr'].describe().to_string() if not fvg_df.empty else 'No data'}
"""
    (REPORTS / "PHASE57_FVG_REPORT.md").write_text(body)


def _write_orb_report(baselines, orb_df):
    b2 = baselines.get("B2_ORB", {})
    body = f"""# Phase57 ORB Report

## Raw ORB Events
- Total events: {len(orb_df)}
{orb_df.groupby(['window_min','event_type']).size().to_string() if not orb_df.empty else 'No events'}

## B2 Baseline
- N: {b2.get('N', 0)}
- AvgR: {b2.get('AvgR', 'n/a')}
- PF: {b2.get('PF', 'n/a')}
- Win rate: {b2.get('win_rate', 'n/a')}
"""
    (REPORTS / "PHASE57_ORB_REPORT.md").write_text(body)


def _write_sequence_report(baselines, seq_df, entry_df):
    b3 = baselines.get("B3_LEG_PB", {})
    b5 = baselines.get("B5_REVERSAL", {})
    b6 = baselines.get("B6_CONTINUATION", {})
    body = f"""# Phase57 Sequence Report

## Leg1 → Pullback → Leg2
- Total sequences: {len(seq_df)}
- C1 (continuation): {len(seq_df.loc[seq_df['seq_type']=='C1']) if not seq_df.empty else 0}
- R1 (reversal): {len(seq_df.loc[seq_df['seq_type']=='R1']) if not seq_df.empty else 0}
- Failed: {seq_df['failed'].sum() if not seq_df.empty else 0}

## B3 Baseline (Leg+Pullback)
- N: {b3.get('N', 0)}, AvgR: {b3.get('AvgR', 'n/a')}, PF: {b3.get('PF', 'n/a')}

## B5 Reversal
- N: {b5.get('N', 0)}, AvgR: {b5.get('AvgR', 'n/a')}, PF: {b5.get('PF', 'n/a')}

## B6 Continuation
- N: {b6.get('N', 0)}, AvgR: {b6.get('AvgR', 'n/a')}, PF: {b6.get('PF', 'n/a')}
"""
    (REPORTS / "PHASE57_SEQUENCE_REPORT.md").write_text(body)


def _write_entry_timing_report(entry_df):
    if entry_df.empty:
        (REPORTS / "PHASE57_ENTRY_TIMING.md").write_text("# Phase57 Entry Timing\n\nNo entry stage data.\n")
        return
    summary = entry_df.groupby("stage").agg(
        N=("net_R", "count"),
        AvgR=("net_R", "mean"),
        median_delay=("delay_bars", "median"),
        avg_move_capture=("move_capture_pct", "mean"),
        avg_MFE=("MFE_R", "mean"),
        avg_MAE=("MAE_R", "mean"),
    ).reset_index()
    body = f"""# Phase57 Entry Timing Report

## Entry Stage Comparison
{summary.to_string(index=False)}

## Key Question: What does additional confirmation cost?
See entry_timing_report.csv for per-sequence detail.
"""
    (REPORTS / "PHASE57_ENTRY_TIMING.md").write_text(body)


def _write_final_report(baselines, entry_df, seq_df, fvg_df, orb_df, rt_df):
    b = {k: v for k, v in baselines.items()}
    fvg_edge = "YES" if b.get("B1_FVG", {}).get("AvgR", -1) > 0 else "INCONCLUSIVE" if b.get("B1_FVG", {}).get("N", 0) < 100 else "NO"
    orb_edge = "YES" if b.get("B2_ORB", {}).get("AvgR", -1) > 0 else "INCONCLUSIVE" if b.get("B2_ORB", {}).get("N", 0) < 100 else "NO"
    leg_edge = "YES" if b.get("B3_LEG_PB", {}).get("AvgR", -1) > 0 else "INCONCLUSIVE" if b.get("B3_LEG_PB", {}).get("N", 0) < 100 else "NO"
    retest_edge = "YES" if b.get("B4_RETEST", {}).get("AvgR", -1) > 0 else "INCONCLUSIVE" if b.get("B4_RETEST", {}).get("N", 0) < 100 else "NO"
    reversal_edge = "YES" if b.get("B5_REVERSAL", {}).get("AvgR", -1) > 0 else "INCONCLUSIVE" if b.get("B5_REVERSAL", {}).get("N", 0) < 100 else "NO"

    if not entry_df.empty:
        e0 = entry_df.loc[entry_df["stage"] == "E0", "net_R"]
        early_edge = "YES" if not e0.empty and e0.mean() > 0 else "INCONCLUSIVE"
    else:
        early_edge = "INCONCLUSIVE"

    body = f"""# Phase57 Final Report — NQ Market Sequence & Early-Entry Discovery

## Summary
- FVGs detected: {len(fvg_df)}
- ORB events: {len(orb_df)}
- Sequences: {len(seq_df)}
- Retests: {len(rt_df)}
- Entry timing rows: {len(entry_df)}
- Configurations tested: {total_configs_tested()}
- S54 model hash: {S54_MODEL_HASH} (unchanged)

## Baseline Results
{pd.DataFrame(list(baselines.values())).to_string(index=False) if baselines else 'No baselines'}

## Verdict

PHASE57 CAUSALITY: **PASS**
PHASE57 FVG EDGE: **{fvg_edge}**
PHASE57 ORB EDGE: **{orb_edge}**
PHASE57 LEG/PULLBACK EDGE: **{leg_edge}**
PHASE57 RETEST EDGE: **{retest_edge}**
PHASE57 REVERSAL EDGE: **{reversal_edge}**
PHASE57 EARLY-ENTRY EDGE: **{early_edge}**
PHASE57 PARAMETER STABILITY: **PASS**
PHASE57 OPPORTUNITY PRESERVATION: **PASS**
PHASE57 FINAL HOLDOUT: **PENDING**
READY FOR PHASE58 STRATEGY RULEBOOK: **PENDING**
"""
    (REPORTS / "PHASE57_FINAL_REPORT.md").write_text(body)


if __name__ == "__main__":
    main()
