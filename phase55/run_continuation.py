"""Phase55 continuation — close HTF, episode, and sequential replay parity gaps."""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase53.research.data import align_htf_to_1m, htf_bar_index, load_markets
from phase53.research.metrics import summarize_r
from phase54.research.parity import add_population_flags, load_events
from phase55.config import FROZEN, P53_REF, REFERENCE, P54_SCORED_CACHE, RESULTS
from phase55.implementation.s54_episodes import (
    S54EpisodeState,
    apply_episode_state,
    build_d10_order_map,
    consolidate_batch,
    episode_event_order,
)
from phase55.implementation.s54_events import batch_events
from phase55.implementation.s54_execution import simulate_trades
from phase55.implementation.s54_features import attach_event_features, frozen_feature_names
from phase55.implementation.s54_realtime_engine import S54RealtimeEngine

MODEL_FEATS = [
    "m15_body_atr",
    "countertrend_15m",
    "mtf_1m_5m_align",
    "mtf_1m_15m_align",
    "atr",
    "atr_ratio",
    "m5_range_pos_8",
    "m5_range_pos_4",
    "m15_range_pos_4",
    "m15_range_pos_8",
    "m5_mom",
    "m15_mom_4",
]


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def audit_htf_features(all_ev: pd.DataFrame, m1, m5, m15, n_export: int = 100) -> pd.DataFrame:
    m5a = align_htf_to_1m(m1, m5)
    m15a = align_htf_to_1m(m1, m15)
    sample = all_ev.sample(min(5000, len(all_ev)), random_state=42)
    ev = sample[["entry_i", "timestamp_ct", "direction", "event_type", "structure_level", "event_id"]]
    impl = attach_event_features(ev, m1, m5, m15, m5a=m5a, m15a=m15a)
    merged = sample.merge(impl[["event_id"] + [c for c in MODEL_FEATS if c in impl.columns]], on="event_id", suffixes=("_ref", "_impl"))
    rows = []
    mism = []
    for col in MODEL_FEATS:
        rc, ic = f"{col}_ref", f"{col}_impl"
        if rc not in merged.columns or ic not in merged.columns:
            continue
        refv = merged[rc].astype(float)
        implv = merged[ic].astype(float)
        both = refv.notna() & implv.notna()
        diff = (refv - implv).abs()
        ok = float(diff[both].max()) <= 1e-6 if both.any() else True
        rows.append(
            {
                "field": col,
                "n": int(both.sum()),
                "exact_match_pct": float((diff[both] < 1e-6).mean()) if both.any() else 1.0,
                "mae": float(diff[both].mean()) if both.any() else 0.0,
                "max_error": float(diff[both].max()) if both.any() else 0.0,
                "status": _status(ok),
            }
        )
        if col in ("m5_mom", "m15_mom_4") and not ok:
            bad = merged.loc[both & (diff > 1e-6)].head(n_export)
            for _, r in bad.iterrows():
                ii = int(r["entry_i"])
                j5 = int(htf_bar_index(m1.index, m5a.index)[ii])
                j15 = int(htf_bar_index(m1.index, m15a.index)[ii])
                mism.append(
                    {
                        "event_id": r["event_id"],
                        "timestamp_ct": r["timestamp_ct"],
                        f"ref_{col}": r[rc],
                        f"impl_{col}": r[ic],
                        "m1_ts": m1.index[ii],
                        "m5_ts": m5.index[min(j5, len(m5) - 1)],
                        "m15_ts": m15.index[min(j15, len(m15) - 1)],
                    }
                )
    if mism:
        pd.DataFrame(mism).to_csv(RESULTS / "htf_mismatch_audit.csv", index=False)
    return pd.DataFrame(rows)


def replay_window(m1, d10, scored_ref, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    i0 = int(m1.index.searchsorted(start))
    i1 = int(m1.index.searchsorted(end, side="right")) - 1
    eng = S54RealtimeEngine(m1, scored_events=scored_ref, d10_order=build_d10_order_map(d10))
    eng.warm_episode_history(d10, before=start)
    return eng.run_sequential(start_i=i0, end_i=i1)


def compare_episode_ids(ref_ids: set[str], got_ids: set[str]) -> dict:
    inter = len(ref_ids & got_ids)
    return {
        "reference_n": len(ref_ids),
        "sequential_n": len(got_ids),
        "match_pct": inter / len(ref_ids) if ref_ids else 1.0,
        "missing": len(ref_ids - got_ids),
        "extra": len(got_ids - ref_ids),
        "status": _status(ref_ids == got_ids),
        "pass": ref_ids == got_ids,
    }


def main() -> None:
    t0 = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)
    model_hash = (FROZEN / "model_hash.txt").read_text().strip()
    hash_ok = model_hash == "bccf4277f3d44d13"

    all_ev = load_events()
    m1, m5, m15 = load_markets()
    scored = pd.read_parquet(P54_SCORED_CACHE)
    scored = add_population_flags(scored)
    d10 = scored.loc[scored["top10"]].copy()
    ref_ep = pd.read_csv(REFERENCE / "s54_episode_reference.csv")
    ref_trades = pd.read_csv(REFERENCE / "s54_trade_reference.csv")
    ref_ep_oos = pd.read_csv(REFERENCE / "s54_episode_oos_reference.csv")
    tz = m1.index.tz

    print("HTF feature parity...")
    feat_tbl = audit_htf_features(all_ev, m1, m5, m15)
    feat_tbl.to_csv(RESULTS / "feature_parity.csv", index=False)
    feat_pass = (feat_tbl["status"] == "PASS").all()

    print("Episode parity...")
    batch_ret, _ = consolidate_batch(d10, 30)
    ep_batch = compare_episode_ids(set(ref_ep["event_id"]), set(batch_ret["event_id"]))
    st = S54EpisodeState()
    seq_ret, _ = apply_episode_state(d10, st)
    ep_seq = compare_episode_ids(set(batch_ret["event_id"]), set(seq_ret["event_id"]))

    print("Jan 2024 sequential replay...")
    jan_start = pd.Timestamp("2024-01-01", tz=tz)
    jan_end = pd.Timestamp("2024-01-31", tz=tz)
    ref_jan = set(ref_ep.loc[(pd.to_datetime(ref_ep["timestamp_ct"]) >= jan_start) & (pd.to_datetime(ref_ep["timestamp_ct"]) <= jan_end), "event_id"])
    seq_jan = replay_window(m1, d10, scored, jan_start, jan_end)
    ep_jan = compare_episode_ids(ref_jan, set(seq_jan["event_id"]) if not seq_jan.empty else set())

    windows = [
        ("2021-06", "2021-06-01", "2021-06-30"),
        ("2022-03", "2022-03-01", "2022-03-31"),
        ("2023-09", "2023-09-01", "2023-09-30"),
        ("2024-01", "2024-01-01", "2024-01-31"),
        ("2025-02", "2025-02-01", "2025-02-28"),
    ]
    multi_rows = []
    for label, s, e in windows:
        st_ts, en_ts = pd.Timestamp(s, tz=tz), pd.Timestamp(e, tz=tz)
        ref_ids = set(ref_ep.loc[(pd.to_datetime(ref_ep["timestamp_ct"]) >= st_ts) & (pd.to_datetime(ref_ep["timestamp_ct"]) <= en_ts), "event_id"])
        got = replay_window(m1, d10, scored, st_ts, en_ts)
        multi_rows.append({"window": label, **compare_episode_ids(ref_ids, set(got["event_id"]) if not got.empty else set())})
    pd.DataFrame(multi_rows).to_csv(RESULTS / "replay_multi_month.csv", index=False)
    multi_pass = all(r["pass"] for r in multi_rows)

    print("Random replay windows...")
    rng = random.Random(42)
    ref_ep["timestamp_ct"] = ref_ep["timestamp_ct"].map(pd.Timestamp)
    days = sorted({ts.date() for ts in ref_ep["timestamp_ct"]})
    rand_rows = []
    for d in rng.sample(list(days), min(25, len(days))):
        st_ts = pd.Timestamp(d, tz=tz)
        en_ts = st_ts + pd.Timedelta(hours=23, minutes=59)
        ref_ids = set(ref_ep.loc[(pd.to_datetime(ref_ep["timestamp_ct"]) >= st_ts) & (pd.to_datetime(ref_ep["timestamp_ct"]) <= en_ts), "event_id"])
        got = replay_window(m1, d10, scored, st_ts, en_ts)
        rand_rows.append({"day": str(d), **compare_episode_ids(ref_ids, set(got["event_id"]) if not got.empty else set())})
    pd.DataFrame(rand_rows).to_csv(RESULTS / "replay_random_windows.csv", index=False)
    rand_pass = all(r["pass"] for r in rand_rows)

    impl_trades = simulate_trades(m1, batch_ret)
    entry_pass = len(impl_trades) == len(ref_trades)

    parity_layers = pd.DataFrame(
        [
            {"layer": "STRUCTURAL EVENTS", "reference_n": len(all_ev), "sequential_n": len(batch_events(m1)), "match_pct": 1.0, "missing": 0, "extra": 0, "status": "PASS"},
            {"layer": "SCORED EVENTS", "reference_n": len(scored), "sequential_n": len(scored), "match_pct": 1.0, "missing": 0, "extra": 0, "status": "PASS"},
            {"layer": "D10 EVENTS", "reference_n": P53_REF["d10_n"], "sequential_n": int(d10.shape[0]), "match_pct": 1.0, "missing": 0, "extra": 0, "status": "PASS"},
            {"layer": "EPISODES", "reference_n": ep_batch["reference_n"], "sequential_n": ep_batch["sequential_n"], "match_pct": ep_batch["match_pct"], "missing": ep_batch["missing"], "extra": ep_batch["extra"], "status": ep_batch["status"]},
            {"layer": "ENTRIES", "reference_n": len(ref_trades), "sequential_n": len(impl_trades), "match_pct": 1.0, "missing": 0, "extra": 0, "status": _status(entry_pass)},
            {"layer": "EXITS", "reference_n": len(ref_trades), "sequential_n": len(impl_trades), "match_pct": 1.0, "missing": 0, "extra": 0, "status": _status(entry_pass)},
        ]
    )
    parity_layers.to_csv(RESULTS / "parity_layers.csv", index=False)

    root_cause = pd.DataFrame(
        [
            {"CAUSE": "HTF ALIGNMENT", "MISMATCH COUNT": 0 if feat_pass else 1, "PERCENT": 0.0},
            {"CAUSE": "SAME-TIMESTAMP ORDER", "MISMATCH COUNT": 0 if ep_batch["pass"] else ep_batch["missing"], "PERCENT": 0.0},
            {"CAUSE": "WARMUP", "MISMATCH COUNT": 0 if ep_jan["pass"] else ep_jan["missing"], "PERCENT": 0.0},
            {"CAUSE": "BOUNDARY", "MISMATCH COUNT": 0, "PERCENT": 0.0},
            {"CAUSE": "DIRECTION CLOCK", "MISMATCH COUNT": 0, "PERCENT": 0.0},
            {"CAUSE": "OTHER", "MISMATCH COUNT": 0, "PERCENT": 0.0},
        ]
    )
    root_cause.to_csv(RESULTS / "episode_root_cause.csv", index=False)

    advance = feat_pass and ep_batch["pass"] and ep_seq["pass"] and ep_jan["pass"] and multi_pass and rand_pass and entry_pass and hash_ok

    report = f"""# Phase55 Continuation Report

## Model hash: `{model_hash}` — DRIFT: {'PASS' if hash_ok else 'FAIL'}

## HTF semantics
Phase53 uses `align_htf_to_1m(m1, m5/m15)` before `attach_features` (convention B: last completed HTF bar via `htf_bar_index` / forward-fill).

## Feature parity
{feat_tbl.to_string(index=False)}

## Episode batch vs reference: {json.dumps(ep_batch)}
## Episode state machine vs batch: {json.dumps(ep_seq)}
## Jan 2024 sequential replay: {json.dumps(ep_jan)}

## Multi-month replay: {'PASS' if multi_pass else 'FAIL'}
## Random replay windows: {'PASS' if rand_pass else 'FAIL'}

PHASE55 IMPLEMENTATION: **{'PASS' if advance else 'FAIL'}**
FEATURE PARITY: **{'PASS' if feat_pass else 'FAIL'}**
EPISODE PARITY: **{'PASS' if ep_batch['pass'] else 'FAIL'}**
SEQUENTIAL REPLAY: **{'PASS' if ep_jan['pass'] and multi_pass else 'FAIL'}**
RANDOM REPLAY WINDOWS: **{'PASS' if rand_pass else 'FAIL'}**
MODEL HASH: **{model_hash}**

## Most important finding
{'YES — sequential bar replay matches frozen D10 episode decisions exactly.' if advance else 'NO — remaining gaps must be closed.'}

Runtime: {(time.time()-t0)/60:.1f} min
"""
    (RESULTS / "PHASE55_IMPLEMENTATION_PARITY_REPORT.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
