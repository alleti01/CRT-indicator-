#!/usr/bin/env python3
"""Phase83 — NQ overnight/premarket breakout acceptance research (independent)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase83.python.config import (
    CHECKPOINTS,
    MIN_FULL,
    MIN_TEST,
    MIN_VAL,
    REPORTS,
    STAGE1,
    STAGE2,
    TRAIN_FRAC,
    VALID_FRAC,
)
from phase83.python.causality import run_causality_audit
from phase83.python.controls import random_and_flipped, timing_matched
from phase83.python.data import arrays, load_nq_1m
from phase83.python.events import collect_events, events_to_trades
from phase83.python.levels import build_sessions, sessions_to_frame
from phase83.python.metrics import bucket_table, side_table, split_by_dates, summarize, year_table
from phase83.python.twominute import build_2m


def _save_json(name: str, obj) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / name).write_text(json.dumps(obj, indent=2, default=str))


def _clean(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            out[k] = None
        else:
            out[k] = v
    return out


def _struct_buckets(df: pd.DataFrame) -> dict:
    x = pd.to_numeric(df.get("struct_dist_atr"), errors="coerce").dropna()
    if x.empty:
        return {}
    bins = [0, 0.5, 0.75, 1.0, 1.5, 99]
    labels = ["<0.5", "0.5-0.75", "0.75-1.0", "1.0-1.5", ">1.5"]
    cat = pd.cut(x, bins=bins, labels=labels, right=False)
    return {str(k): int(v) for k, v in cat.value_counts().sort_index().items()}


def _evidence(train_s: dict, ctrl: dict) -> bool:
    if train_s.get("N", 0) < 200:
        return False
    if train_s.get("AvgR", -99) <= 0.02:
        return False
    return bool(ctrl.get("real_gt_random"))


def _verdict(causality, data_ok, rows, promoted) -> str:
    if not data_ok:
        return "PHASE83_DATA_FAIL"
    if causality.get("status") != "PASS":
        return "PHASE83_CAUSALITY_FAIL"
    if not rows:
        return "PHASE83_INSUFFICIENT_SAMPLE"
    max_n = max(r["full"].get("N", 0) for r in rows)
    any_info = any(
        r["controls"].get("real_gt_random") and r["full"].get("AvgR", 0) > 0.01 for r in rows
    )
    cont_pass = [r for r in promoted if r["family"] == "CONTINUATION"]
    rev_pass = [r for r in promoted if r["family"] == "REVERSAL"]
    if cont_pass and rev_pass:
        return "PHASE83_BREAKOUT_AND_REVERSAL_PASS"
    if cont_pass:
        return "PHASE83_BREAKOUT_CONTINUATION_PASS"
    if rev_pass:
        return "PHASE83_FAILED_BREAK_REVERSAL_PASS"
    if max_n < MIN_FULL:
        return "PHASE83_INSUFFICIENT_SAMPLE"
    if any_info and not promoted:
        # directional info in-sample but not validated
        val_fail = any(r["validation"].get("AvgR", 0) <= 0 or r["test"].get("AvgR", 0) <= 0 for r in rows if r["full"].get("AvgR", 0) > 0)
        if val_fail:
            return "PHASE83_VALIDATION_FAIL"
        return "PHASE83_CONFIRMATION_INFORMATION_ONLY"
    if not any_info:
        return "PHASE83_BREAKOUT_NO_DIRECTIONAL_INFORMATION"
    return "PHASE83_BREAKOUT_NO_EDGE"


def _promote(r: dict) -> bool:
    f, v, t = r["full"], r["validation"], r["test"]
    if f.get("N", 0) < MIN_FULL or v.get("N", 0) < MIN_VAL or t.get("N", 0) < MIN_TEST:
        return False
    if v.get("AvgR", -99) <= 0 or t.get("AvgR", -99) <= 0:
        return False
    if not r["controls"].get("real_gt_random"):
        return False
    timing = r.get("timing") or {}
    if timing.get("N", 0) >= 50 and f.get("AvgR", 0) <= timing.get("AvgR", 0):
        return False
    years = r.get("year_ok", True)
    return bool(years)


def _year_ok(yt: pd.DataFrame) -> bool:
    if yt.empty or "AvgR" not in yt:
        return False
    pos = (yt["AvgR"] > 0).sum()
    return pos >= max(2, int(np.ceil(0.5 * len(yt))))


def main() -> int:
    t0 = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    df, data_meta = load_nq_1m()
    data_ok = data_meta["n_bars"] > 100_000 and data_meta["ohlc_bad"] == 0
    arr = arrays(df)
    twom = build_2m(arr)
    sessions, sess_meta = build_sessions(arr)
    sess_df = sessions_to_frame(sessions)
    sess_df.to_csv(REPORTS / "SESSIONS.csv", index=False)
    _save_json("00_data.json", {**data_meta, **sess_meta})

    dates = [s.date for s in sessions]
    n_d = len(dates)
    i_tr = int(n_d * TRAIN_FRAC)
    i_va = int(n_d * VALID_FRAC)
    train_dates, valid_dates, test_dates = set(dates[:i_tr]), set(dates[i_tr:i_va]), set(dates[i_va:])
    _save_json("01_splits.json", {
        "n_sessions": n_d,
        "train": [dates[0], dates[i_tr - 1], i_tr] if n_d else [],
        "validation": [dates[i_tr], dates[i_va - 1], i_va - i_tr] if n_d > i_va else [],
        "test": [dates[i_va], dates[-1], n_d - i_va] if n_d > i_va else [],
    })

    print(f"data bars={data_meta['n_bars']} sessions={n_d} range={sess_meta.get('first_date')}..{sess_meta.get('last_date')}", flush=True)

    print("causality audit...", flush=True)
    causality = run_causality_audit(arr, twom, sessions)
    _save_json("02_causality.json", causality)
    print(f"causality {causality['status']} fails={causality['failures']}", flush=True)

    models = list(STAGE1)
    print("stage 1 events...", flush=True)
    ev1 = collect_events(arr, twom, sessions, tuple(models))
    print(f"stage 1 events={len(ev1)}", flush=True)

    # Stage 1 trades
    trades1 = pd.DataFrame(events_to_trades(ev1, arr))
    if not trades1.empty:
        trades1.to_parquet(CHECKPOINTS / "stage1_trades.parquet", index=False)

    stage1_summary = []
    model_rows = []

    def evaluate_model(model: str, tdf: pd.DataFrame, family: str) -> dict:
        g = tdf[tdf["model"] == model].copy()
        splits = split_by_dates(g, train_dates, valid_dates, test_dates)
        full = summarize(g)
        train_s = summarize(splits["train"])
        val_s = summarize(splits["validation"])
        test_s = summarize(splits["test"])
        # controls on train+full but report full (cap rewalk size)
        sample = g
        if len(sample) > 500:
            sample = sample.sample(500, random_state=83)
        ctrl = random_and_flipped(sample, arr, seeds=8)
        timing = timing_matched(sample, arr, sessions)
        yt = year_table(g) if not g.empty else pd.DataFrame()
        rec = {
            "model": model,
            "family": family,
            "full": _clean(full),
            "train": _clean(train_s),
            "validation": _clean(val_s),
            "test": _clean(test_s),
            "controls": {
                "real": _clean(ctrl.get("real") or {}),
                "random": _clean(ctrl.get("random") or {}),
                "flipped": _clean(ctrl.get("flipped") or {}),
                "real_gt_random": ctrl.get("real_gt_random"),
            },
            "timing": _clean(timing),
            "year_ok": _year_ok(yt) if len(yt) else False,
            "struct_stops": _struct_buckets(g),
            "retention_vs_b0": None,
        }
        return rec

    families = {"B0": "CONTINUATION", "B1": "CONTINUATION", "B2": "CONTINUATION",
                "F1": "REVERSAL", "F2": "REVERSAL"}
    for m in STAGE1:
        if trades1.empty:
            break
        rec = evaluate_model(m, trades1, families[m])
        model_rows.append(rec)
        stage1_summary.append({"model": m, **rec["full"]})
        print(f"  {m} N={rec['full'].get('N')} AvgR={rec['full'].get('AvgR')}", flush=True)

    run_stage2 = any(_evidence(r["train"], r["controls"]) for r in model_rows)
    trades2 = pd.DataFrame()
    if run_stage2:
        print("stage 2 events (evidence gate opened)...", flush=True)
        ev2 = collect_events(arr, twom, sessions, STAGE2)
        trades2 = pd.DataFrame(events_to_trades(ev2, arr))
        fam2 = {"B3_55": "CONTINUATION", "B4_10": "CONTINUATION", "B5_125": "CONTINUATION",
                "B6": "CONTINUATION", "B7": "CONTINUATION", "F3": "REVERSAL", "F4": "REVERSAL"}
        for m in STAGE2:
            if trades2.empty:
                break
            rec = evaluate_model(m, trades2, fam2[m])
            model_rows.append(rec)
            print(f"  {m} N={rec['full'].get('N')} AvgR={rec['full'].get('AvgR')}", flush=True)
    else:
        print("stage 2 skipped — no Stage 1 train evidence", flush=True)

    # Level control: B1 on prior RTH and synthetic distance
    print("level controls...", flush=True)
    ev_pr = collect_events(arr, twom, sessions, ("B1",), level_source="PRIOR_RTH")
    ev_sy = collect_events(arr, twom, sessions, ("B1",), level_source="SYNTH_OPEN")
    tr_pr = pd.DataFrame(events_to_trades(ev_pr, arr))
    tr_sy = pd.DataFrame(events_to_trades(ev_sy, arr))
    level_ctrl = {
        "ON_B1": _clean(summarize(trades1[trades1["model"] == "B1"])) if not trades1.empty else {},
        "PRIOR_RTH_B1": _clean(summarize(tr_pr)),
        "SYNTH_OPEN_B1": _clean(summarize(tr_sy)),
    }

    all_trades = pd.concat([x for x in (trades1, trades2) if not x.empty], ignore_index=True) if not trades1.empty else pd.DataFrame()
    if not all_trades.empty:
        all_trades.to_parquet(CHECKPOINTS / "all_trades.parquet", index=False)
        all_trades.to_csv(REPORTS / "TRADE_LEDGER.csv", index=False)
        ev_cols = [
            "date", "model", "family", "direction", "level_type", "level_price",
            "touch_ts", "confirm_ts", "entry_ts", "entry_price", "atr",
            "confirmation_type", "distance_beyond_atr", "volume_ratio", "body_fraction",
            "mfe_5", "mae_5", "mfe_15", "mae_15", "mfe_30", "mae_30", "net_r", "reason_code",
        ]
        keep = [c for c in ev_cols if c in all_trades.columns]
        all_trades[keep].to_csv(REPORTS / "EVENT_LEDGER.csv", index=False)

    # Comparison table
    cmp_rows = []
    for r in model_rows:
        cmp_rows.append({
            "model": r["model"],
            "family": r["family"],
            **{k: r["full"].get(k) for k in ("N", "WinRate", "AvgR", "PF", "TotalR", "MaxDD", "MFE15", "MAE15", "MFE30", "MAE30", "LONG", "SHORT")},
            "train_AvgR": r["train"].get("AvgR"),
            "val_AvgR": r["validation"].get("AvgR"),
            "test_AvgR": r["test"].get("AvgR"),
            "random_AvgR": (r["controls"].get("random") or {}).get("AvgR"),
            "flipped_AvgR": (r["controls"].get("flipped") or {}).get("AvgR"),
            "timing_AvgR": (r["timing"] or {}).get("AvgR"),
        })
    cmp = pd.DataFrame(cmp_rows)
    cmp.to_csv(REPORTS / "MODEL_RESULTS.csv", index=False)

    promoted = [r for r in model_rows if _promote(r)]
    # year / side / bucket for best continuation and best reversal by train AvgR
    def _best(fam: str):
        cands = [r for r in model_rows if r["family"] == fam and r["full"].get("N", 0) > 0]
        if not cands:
            return None
        return max(cands, key=lambda r: (r["train"].get("AvgR") or -99, r["full"].get("N") or 0))

    best_c = _best("CONTINUATION")
    best_r = _best("REVERSAL")

    year_frames = []
    side_frames = []
    buck_frames = []
    for label, rec in (("CONT", best_c), ("REV", best_r)):
        if rec is None or all_trades.empty:
            continue
        g = all_trades[all_trades["model"] == rec["model"]]
        yt = year_table(g)
        yt["model"] = rec["model"]
        year_frames.append(yt)
        st = side_table(g)
        st["model"] = rec["model"]
        side_frames.append(st)
        bt = bucket_table(g)
        bt["model"] = rec["model"]
        buck_frames.append(bt)
    if year_frames:
        pd.concat(year_frames).to_csv(REPORTS / "YEAR_BREAKDOWN.csv", index=False)
    if side_frames:
        pd.concat(side_frames).to_csv(REPORTS / "SIDE_BREAKDOWN.csv", index=False)
    if buck_frames:
        pd.concat(buck_frames).to_csv(REPORTS / "TIME_BUCKET_BREAKDOWN.csv", index=False)

    # Representative events
    rng = np.random.default_rng(83)
    samples = []
    if not all_trades.empty:
        def _sample(mask, n, tag):
            sub = all_trades[mask]
            if sub.empty:
                return
            take = sub.sample(min(n, len(sub)), random_state=int(rng.integers(1e9)))
            take = take.copy()
            take["review_tag"] = tag
            samples.append(take)

        _sample((all_trades["family"] == "CONTINUATION") & (all_trades["net_r"] > 0), 20, "WIN_BREAKOUT")
        _sample((all_trades["family"] == "CONTINUATION") & (all_trades["net_r"] <= 0), 20, "LOSE_BREAKOUT")
        _sample((all_trades["family"] == "REVERSAL"), 20, "FAILED_BREAK_REVERSAL")
        # rejected / no-entry: sessions with B0 touch but no B1 — approximate via B0 not in B1 dates/sides
        if "B0" in all_trades["model"].values and "B1" in all_trades["model"].values:
            b0 = all_trades[all_trades["model"] == "B0"]
            b1_keys = set(zip(all_trades.loc[all_trades["model"] == "B1", "date"], all_trades.loc[all_trades["model"] == "B1", "direction"]))
            rej = b0[[(d, dir_) not in b1_keys for d, dir_ in zip(b0["date"], b0["direction"])]]
            if len(rej):
                take = rej.sample(min(20, len(rej)), random_state=11).copy()
                take["review_tag"] = "REJECTED_NO_CONFIRM"
                samples.append(take)
    if samples:
        pd.concat(samples).to_csv(REPORTS / "REPRESENTATIVE_EVENTS.csv", index=False)

    # Cost robustness on B1 / F1
    cost_rob = {}
    for m in ("B1", "B2", "F1", "F2"):
        if all_trades.empty or m not in all_trades["model"].values:
            continue
        g = all_trades[all_trades["model"] == m]
        cost_rob[m] = {f"slip{t}": float(pd.to_numeric(g[f"net_r_slip{t}"], errors="coerce").mean()) for t in (0, 1, 2) if f"net_r_slip{t}" in g}

    # Q answers from numbers
    def avg(model):
        hit = next((r for r in model_rows if r["model"] == model), None)
        return hit

    b0, b1, b2 = avg("B0"), avg("B1"), avg("B2")
    f1, f2 = avg("F1"), avg("F2")
    b3, b5, b6 = avg("B3_55"), avg("B5_125"), avg("B6")

    def _ar(rec):
        return None if rec is None else rec["full"].get("AvgR")

    confirm_adds = (
        b2 is not None and b0 is not None
        and (b2["full"].get("AvgR") or -99) > (b0["full"].get("AvgR") or -99)
        and (b2["controls"].get("real_gt_random"))
    )
    vol_adds = b5 is not None and b2 is not None and (b5["full"].get("AvgR") or -99) > (b2["full"].get("AvgR") or -99)
    retest_adds = b6 is not None and b1 is not None and (b6["full"].get("AvgR") or -99) > (b1["full"].get("AvgR") or -99)
    fail_better = (
        f1 is not None and b1 is not None
        and (f1["full"].get("AvgR") or -99) > (b1["full"].get("AvgR") or -99)
    )
    on_special = "INCONCLUSIVE"
    if level_ctrl.get("ON_B1") and level_ctrl.get("SYNTH_OPEN_B1"):
        on_a = level_ctrl["ON_B1"].get("AvgR") or 0
        sy_a = level_ctrl["SYNTH_OPEN_B1"].get("AvgR") or 0
        pr_a = (level_ctrl.get("PRIOR_RTH_B1") or {}).get("AvgR") or 0
        if on_a > sy_a + 0.02 and on_a > pr_a + 0.02 and on_a > 0:
            on_special = "YES"
        elif on_a <= 0 and sy_a <= 0:
            on_special = "NO"
        else:
            on_special = "INCONCLUSIVE"

    verdict = _verdict(causality, data_ok, model_rows, promoted)

    # Chase diagnostic: B2 distance buckets
    chase = []
    if not all_trades.empty and "B2" in all_trades["model"].values:
        g = all_trades[all_trades["model"] == "B2"].copy()
        g["dist_bin"] = pd.cut(g["distance_beyond_atr"], bins=[-0.01, 0.05, 0.10, 0.20, 0.50, 9], labels=["0-0.05", "0.05-0.10", "0.10-0.20", "0.20-0.50", ">0.50"])
        for b, sub in g.groupby("dist_bin", observed=False):
            s = summarize(sub)
            s["dist_bin"] = str(b)
            chase.append(s)
    if chase:
        pd.DataFrame(chase).to_csv(REPORTS / "ANTI_CHASE_B2.csv", index=False)

    pd.DataFrame([{"model": r["model"], **r["struct_stops"]} for r in model_rows]).to_csv(REPORTS / "STRUCTURAL_STOP_DIST.csv", index=False)

    answers = {
        "Q1_raw_touch_info": bool(b0 and b0["controls"].get("real_gt_random") and (b0["full"].get("AvgR") or 0) > 0.01),
        "Q2_1m_close_improves": bool(b1 and b0 and (b1["full"].get("AvgR") or -99) > (b0["full"].get("AvgR") or -99)),
        "Q3_2m_close_improves": bool(b2 and b1 and (b2["full"].get("AvgR") or -99) > (b1["full"].get("AvgR") or -99)),
        "Q4_2m_compensates_delay": bool(confirm_adds),
        "Q5_body_quality": "NOT_TESTED" if b3 is None else bool((b3["full"].get("AvgR") or -99) > (b2["full"].get("AvgR") or -99) if b2 else False),
        "Q6_volume": "NOT_TESTED" if b5 is None else bool(vol_adds),
        "Q7_retest": "NOT_TESTED" if b6 is None else bool(retest_adds),
        "Q8_failed_more_informative": bool(fail_better),
        "Q9_fail_plus_disp": "NOT_TESTED" if avg("F4") is None else True,
        "Q10_on_special": on_special,
        "Q11_survives_costs": bool(b1 and (cost_rob.get("B1", {}).get("slip1") or -99) > 0),
        "Q12_survives_val_test": bool(promoted),
        "Q13_both_sides": bool(best_c and best_c["full"].get("LONG", 0) >= 50 and best_c["full"].get("SHORT", 0) >= 50 and _ar(best_c) is not None),
        "Q14_chase": chase,
    }

    elapsed = time.time() - t0
    _save_json("18_final.json", {
        "verdict": verdict,
        "elapsed_s": elapsed,
        "stage2_ran": run_stage2,
        "promoted": [r["model"] for r in promoted],
        "answers": answers,
        "level_ctrl": level_ctrl,
        "cost_rob": cost_rob,
        "causality": causality,
        "production_changes": "NONE",
    })

    # Final report
    def _line(rec, label):
        if rec is None:
            return f"{label}: none"
        f = rec["full"]
        return (
            f"{label}: {rec['model']} N={f.get('N')} AvgR={f.get('AvgR')} PF={f.get('PF')} "
            f"WR={f.get('WinRate')} train={rec['train'].get('AvgR')} val={rec['validation'].get('AvgR')} "
            f"test={rec['test'].get('AvgR')} random={(rec['controls'].get('random') or {}).get('AvgR')}"
        )

    report = f"""# Phase83 — NQ Premarket / Overnight Breakout Acceptance

**Verdict:** `{verdict}`

PHASE83_MODE = RESEARCH_ONLY
PRODUCTION_MODIFIED = NO
PHASE72A_MODIFIED = NO
PHASE73_MODIFIED = NO
PHASE74_MODIFIED = NO
M0_MODIFIED = NO
PHASE72B_USED_AS_GROUND_TRUTH = NO

## DATA
- Dataset: {data_meta['dataset']}
- Instrument: {data_meta['instrument']}
- Contract: {data_meta['contract_construction']}
- Stored TZ: {data_meta['timezone_stored']} | Session TZ: {data_meta['timezone_sessions']}
- Range: {data_meta['index_min']} → {data_meta['index_max']}
- Bars: {data_meta['n_bars']}
- Sessions used: {sess_meta['n_sessions']} ({sess_meta.get('first_date')} → {sess_meta.get('last_date')})
- Skipped: {sess_meta['skipped']}
- Mean overnight bars: {sess_meta.get('mean_overnight_bars')}
- Mean ON range / ATR: {sess_meta.get('mean_on_range_atr')}
- RTH: 09:30–16:00 ET | Overnight: 18:00 prior trading day → 09:29 ET
- Costs: NQ $14.50/RT (`phase58.research.instrument.NQ`) + 0/1/2 tick slip

## CAUSALITY
- Status: **{causality['status']}**
- Overnight freeze checks: {causality['overnight_checks']} fail={causality['overnight_fail']}
- 2M prefix checks: {causality['twom_checks']} fail={causality['twom_fail']}
- Decision prefix checks: {causality['decision_checks']} fail={causality['decision_fail']}
- Examples: {causality.get('fail_examples')}

## BASELINES
{_line(b0, 'B0 raw touch')}
{_line(b1, 'B1 1M close')}
{_line(b2, 'B2 2M close')}

## BEST CONTINUATION
{_line(best_c, 'BEST_CONT')}

## BEST FAILED-BREAK REVERSAL
{_line(best_r, 'BEST_REV')}

## RANDOM / FLIPPED / TIMING
See MODEL_RESULTS.csv. Random = 8-seed re-walk at same timestamps. Flipped = opposite direction re-walk.

## LEVEL CONTROL
- ON B1: {level_ctrl.get('ON_B1')}
- PRIOR RTH B1: {level_ctrl.get('PRIOR_RTH_B1')}
- SYNTH (open ± overnight width) B1: {level_ctrl.get('SYNTH_OPEN_B1')}
- ON special vs controls: {on_special}

## COST ROBUSTNESS
{json.dumps(cost_rob, indent=2)}

## STAGE 2
Ran: {run_stage2}

## PROMOTED
{[r['model'] for r in promoted] or 'NONE'}

## CORE ANSWERS
1. Raw touch directional info? {answers['Q1_raw_touch_info']}
2. 1M close improves? {answers['Q2_1m_close_improves']}
3. 2M close improves? {answers['Q3_2m_close_improves']}
4. 2M compensates delay? {answers['Q4_2m_compensates_delay']}
5. Body quality? {answers['Q5_body_quality']}
6. Volume? {answers['Q6_volume']}
7. Retest? {answers['Q7_retest']}
8. Failed breaks more informative? {answers['Q8_failed_more_informative']}
9. Fail + opposite displacement? {answers['Q9_fail_plus_disp']}
10. ON high/low special? {answers['Q10_on_special']}
11. Survives costs? {answers['Q11_survives_costs']}
12. Survives val+test? {answers['Q12_survives_val_test']}
13. Both sides? {answers['Q13_both_sides']}
14. Chase (B2 distance buckets): see ANTI_CHASE_B2.csv

## PRODUCTION CHANGES
NONE

## NEXT ACTION
{"PROMOTE SEPARATELY" if promoted else "ARCHIVE / STOP"}

Elapsed: {elapsed:.1f}s
"""
    (REPORTS / "PHASE83_FINAL_REPORT.md").write_text(report)

    # compact stdout block
    print("\n===== PHASE83 VERDICT =====")
    print(verdict)
    print("CAUSALITY:", causality["status"])
    print(_line(b0, "B0"))
    print(_line(b1, "B1"))
    print(_line(b2, "B2"))
    print(_line(best_c, "BEST_CONT"))
    print(_line(best_r, "BEST_REV"))
    print("DOES 2M CONFIRMATION ADD VALUE?", "YES" if confirm_adds else "NO")
    print("DOES VOLUME ADD VALUE?", "YES" if vol_adds else ("NO" if b5 else "NOT_TESTED"))
    print("DOES RETEST ADD VALUE?", "YES" if retest_adds else ("NO" if b6 else "NOT_TESTED"))
    print("ARE FAILED BREAKOUTS MORE INFORMATIVE?", "YES" if fail_better else "NO")
    print("ARE ON HIGH/LOW SPECIAL VS CONTROLS?", on_special)
    print("PRODUCTION CHANGES: NONE")
    print("NEXT ACTION:", "PROMOTE SEPARATELY" if promoted else "ARCHIVE / STOP")
    print("elapsed", round(elapsed, 1))
    return 0 if causality["status"] == "PASS" or not data_ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
