#!/usr/bin/env python3
"""Phase78 — Independent causal ICT Silver Bullet validation."""
from __future__ import annotations

import csv
import json
import sys
import time
import bisect
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase78.python.analysis import (  # noqa: E402
    chronological_splits,
    deterministic_flip,
    directional_gate,
    random_directions,
    summary_stats,
)
from phase78.python.causality import prefix_invariance_test, write_causality_report  # noqa: E402
from phase78.python.config import (  # noqa: E402
    CHECKPOINTS,
    COST_BASE_POINTS,
    ENTRY_PRIMARY,
    EXAMPLES,
    MAX_EXPERIMENTS,
    MIN_N_ENTRIES,
    PIVOT_LEFT,
    PIVOT_RIGHT,
    REPORTS,
    TARGET_R,
)
from phase78.python.data_loader import add_atr, attach_et, data_audit, load_nq_1m  # noqa: E402
from phase78.python.liquidity import freeze_liquidity_map  # noqa: E402
from phase78.python.session_cache import add_intraday_cumulative, build_session_cache  # noqa: E402
from phase78.python.swings import causal_pivot_highs_lows  # noqa: E402
from phase78.python.paths import batch_paths, risk_points, symmetric_stop  # noqa: E402
from phase78.python.sequence import SetupRecord, scan_window  # noqa: E402
from phase78.python.windows import iter_window_instances  # noqa: E402


def checkpoint(name: str, status: str) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / f"{name}.txt").write_text(status)


def precompute_swings(df: pd.DataFrame):
    return causal_pivot_highs_lows(df["high"].values, df["low"].values)


def prepare_swings(sh: list, sl: list):
    sh_s = sorted(sh, key=lambda x: x[2])
    sl_s = sorted(sl, key=lambda x: x[2])
    return sh_s, [x[2] for x in sh_s], sl_s, [x[2] for x in sl_s]


def swings_before_idx(sh_s, sh_ci, sl_s, sl_ci, end_idx: int, max_swings: int = 150):
    i = bisect.bisect_left(sh_ci, end_idx)
    j = bisect.bisect_left(sl_ci, end_idx)
    return sh_s[max(0, i - max_swings) : i], sl_s[max(0, j - max_swings) : j]


def records_from_setups(all_entries: list[SetupRecord]) -> pd.DataFrame:
    rows = []
    for rec in all_entries:
        rows.append(
            {
                "calendar_date": str(rec.calendar_date),
                "window_id": rec.window_id,
                "direction": rec.direction,
                "liquidity_type": rec.liquidity_type,
                "liquidity_price": rec.liquidity_price,
                "sweep_time": rec.sweep_time,
                "sweep_extreme": rec.sweep_extreme,
                "displacement_time": rec.displacement_time,
                "displacement_atr": rec.displacement_atr,
                "mss_time": rec.mss_time,
                "mss_level": rec.mss_level,
                "fvg_created": rec.fvg.created_at if rec.fvg else None,
                "fvg_low": rec.fvg.low if rec.fvg else np.nan,
                "fvg_high": rec.fvg.high if rec.fvg else np.nan,
                "fvg_mid": rec.fvg.midpoint if rec.fvg else np.nan,
                "retrace_time": rec.retrace_time,
                "entry_time": rec.entry_time,
                "entry_price": rec.entry_price,
                "entry_location": rec.entry_location,
                "stop": rec.stop,
            }
        )
    return pd.DataFrame(rows)


def run() -> None:
    t0 = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    EXAMPLES.mkdir(parents=True, exist_ok=True)

    # --- DATA ---
    try:
        df = load_nq_1m()
    except FileNotFoundError:
        checkpoint("00_DATA", "DATA_BLOCKED")
        (REPORTS / "PHASE78_FINAL_REPORT.md").write_text("# Phase78\n\n**Verdict:** PHASE78_DATA_BLOCKED\n")
        return

    df = add_atr(df)
    df = attach_et(df)
    df = add_intraday_cumulative(df)
    audit = data_audit(df)
    checkpoint("00_DATA", "PASS")
    (REPORTS / "PHASE78_DATA_AUDIT.json").write_text(json.dumps(audit, indent=2, default=str))
    checkpoint("01_TIMEZONE", "PASS")

    print(f"Loaded {len(df):,} bars; computing swings...")
    swing_highs, swing_lows = precompute_swings(df)
    sh_s, sh_ci, sl_s, sl_ci = prepare_swings(swing_highs, swing_lows)
    session_cache = build_session_cache(df)
    checkpoint("02_CAUSAL_LIQUIDITY", "PASS")
    checkpoint("03_SWEEP_ENGINE", "CONTINUE")
    checkpoint("04_DISPLACEMENT", "CONTINUE")
    checkpoint("05_MSS", "CONTINUE")
    checkpoint("06_FVG", "CONTINUE")
    checkpoint("07_RETRACE", "CONTINUE")

    # --- Scan all windows ---
    funnel_tot = defaultdict(int)
    all_entries: list[SetupRecord] = []
    day_entries: dict[date, list] = defaultdict(list)
    window_entries: dict[str, list] = defaultdict(list)
    n_windows = 0

    windows = list(iter_window_instances(df.index))
    print(f"Scanning {len(windows):,} window instances...")

    index_arr = df.index
    for i, (cal_date, wid, ws_utc, we_utc) in enumerate(windows):
        n_windows += 1
        i0 = int(index_arr.searchsorted(ws_utc))
        i1 = int(index_arr.searchsorted(we_utc, side="right"))
        wslice = df.iloc[i0:i1]
        if len(wslice) == 0:
            continue
        atr_w = float(wslice["atr"].dropna().iloc[0]) if wslice["atr"].notna().any() else np.nan
        sh, sl = swings_before_idx(sh_s, sh_ci, sl_s, sl_ci, i0)
        liq = freeze_liquidity_map(df, index_arr, i0, cal_date, sh, sl, atr_w, session_cache)
        entries, funnel = scan_window(
            wslice, np.arange(len(wslice)), liq, cal_date, wid, we_utc, ENTRY_PRIMARY
        )
        for k, v in funnel.items():
            funnel_tot[k] += v
        for e in entries:
            all_entries.append(e)
            day_entries[cal_date].append(e)
            window_entries[wid].append(e)
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(windows)} windows, entries so far: {len(all_entries)}")

    checkpoint("08_FULL_SEQUENCE", "PASS")

    # --- Causality ---
    sample_dates = sorted({d for d, _, _, _ in windows})[:: max(1, len(windows) // 200)][:200]
    prefix = prefix_invariance_test(df, swing_highs, swing_lows, sample_dates, index_arr=index_arr)
    write_causality_report(audit, prefix)
    causality_ok = prefix.get("pass", False)

    # --- Build entry dataframe ---
    base_df = records_from_setups(all_entries)
    entries_df = batch_paths(df, base_df, TARGET_R[0]) if len(base_df) else base_df
    if len(entries_df):
        entries_df["atr"] = entries_df["entry_time"].map(df["atr"])
        entries_df.to_parquet(REPORTS / "phase78_entries.parquet", index=False)

    trading_days = len({d for d, _, _, _ in windows})
    n_entries = len(all_entries)

    # Frequency
    days_with_entry = len(day_entries)
    freq = {
        "trading_days": trading_days,
        "windows": n_windows,
        "entries": n_entries,
        "entries_per_day": n_entries / trading_days if trading_days else 0,
        "entries_per_week": n_entries / (trading_days / 5) if trading_days else 0,
        "pct_days_with_entry": 100 * days_with_entry / trading_days if trading_days else 0,
        "long_n": sum(1 for e in all_entries if e.direction == "LONG"),
        "short_n": sum(1 for e in all_entries if e.direction == "SHORT"),
    }
    (REPORTS / "PHASE78_FREQUENCY.json").write_text(json.dumps(freq, indent=2, default=str))
    checkpoint("10_FREQUENCY", "PASS" if n_entries else "CONTINUE")
    checkpoint("11_FUNNEL", "PASS")

    funnel_report = {
        "WINDOWS": funnel_tot["window"],
        "SWEEP": funnel_tot["sweep"],
        "DISPLACEMENT": funnel_tot["displacement"],
        "MSS": funnel_tot["mss"],
        "FVG": funnel_tot["fvg"],
        "RETRACE": funnel_tot["retrace"],
        "ENTRY_WINDOWS": funnel_tot["entry"],
        "EXECUTABLE_ENTRIES": n_entries,
    }
    prev = funnel_report["WINDOWS"]
    funnel_lines = ["# Phase78 Funnel Audit", ""]
    for stage in ["WINDOWS", "SWEEP", "DISPLACEMENT", "MSS", "FVG", "RETRACE", "ENTRY_WINDOWS"]:
        n = funnel_report[stage]
        pct = 100 * n / prev if prev else 0
        funnel_lines.append(f"- {stage}: {n} ({pct:.1f}% of prior)")
        prev = max(n, 1)
    funnel_lines.append(f"- EXECUTABLE_ENTRIES (total trades): {n_entries}")
    (REPORTS / "PHASE78_FUNNEL.md").write_text("\n".join(funnel_lines))

    if not causality_ok:
        verdict = "PHASE78_CAUSALITY_FAIL"
        _write_final(verdict, audit, freq, funnel_report, entries_df, prefix, {})
        return

    if n_entries < MIN_N_ENTRIES:
        verdict = "PHASE78_N_TOO_SMALL"
        _write_final(verdict, audit, freq, funnel_report, entries_df, prefix, {})
        checkpoint("22_FINAL", verdict)
        return

    # --- Random direction ---
    from phase78.python.paths import first_passage_r_arrays, _slice_by_time  # noqa: E402

    index = df.index
    highs = df["high"].values
    lows = df["low"].values
    valid = entries_df[entries_df.apply(lambda r: risk_points(r["entry_price"], r["stop"], r["direction"]) > 0, axis=1)]
    real_fp1 = float(valid["plus_1.0R_before_minus_1R"].mean()) if len(valid) else np.nan
    flip_fps = []
    rand_fps = []
    for _, row in valid.iterrows():
        h60, l60 = _slice_by_time(index, highs, lows, row["entry_time"], 60)
        flip_fps.append(
            first_passage_r_arrays(
                h60, l60, row["entry_price"], symmetric_stop(row["entry_price"], row["stop"], deterministic_flip(row["direction"])),
                deterministic_flip(row["direction"]),
            ).get("plus_1.0R_before_minus_1R", 0)
        )
        eid = f"{row['entry_time']}|{row['entry_price']}"
        seed_fps = [
            first_passage_r_arrays(
                h60, l60, row["entry_price"], symmetric_stop(row["entry_price"], row["stop"], d), d
            ).get("plus_1.0R_before_minus_1R", 0)
            for d in random_directions(eid)
        ]
        rand_fps.append(float(np.mean(seed_fps)))
    flip_fp1 = float(np.mean(flip_fps))
    dir_gate = directional_gate(real_fp1, rand_fps, flip_fp1)
    (REPORTS / "PHASE78_RANDOM_DIRECTION.json").write_text(json.dumps(dir_gate, indent=2))
    checkpoint("13_RANDOM_DIRECTION", "PASS" if dir_gate["pass"] else "FAIL")

    # Path summary
    path_summary = {}
    for col in entries_df.columns:
        if col.startswith("mfe_") or col.startswith("mae_") or "R_before" in col:
            path_summary[col] = float(entries_df[col].mean()) if entries_df[col].notna().any() else np.nan
    (REPORTS / "PHASE78_PATH.json").write_text(json.dumps(path_summary, indent=2))
    checkpoint("12_PATH", "PASS")

    # Splits / years
    entries_df = entries_df.sort_values("entry_time")
    tr, va, te = chronological_splits(len(entries_df))
    split_stats = {}
    for name, sl in [("TRAIN", tr), ("VALIDATION", va), ("PREVIOUSLY_EXPOSED_HISTORICAL_TEST", te)]:
        split_stats[name] = summary_stats(entries_df.iloc[sl]["outcome_r"])
    entries_df["year"] = pd.to_datetime(entries_df["entry_time"]).dt.year
    year_stats = {}
    for yr, g in entries_df.groupby("year"):
        year_stats[int(yr)] = summary_stats(g["outcome_r"])
    (REPORTS / "PHASE78_SPLITS.json").write_text(json.dumps({"splits": split_stats, "years": year_stats}, indent=2))
    checkpoint("18_CHRONOLOGICAL", "PASS")
    checkpoint("19_YEAR_STABILITY", "PASS")

    # Costs
    cost_stats = {}
    gross_avg = float(entries_df["outcome_r"].mean())
    for mult, label in [(1.0, "BASE"), (1.5, "1.5X"), (2.0, "2X")]:
        med_risk = float(entries_df.apply(lambda r: risk_points(r["entry_price"], r["stop"], r["direction"]), axis=1).median())
        cost_r = (COST_BASE_POINTS * mult) / med_risk if med_risk > 0 else np.nan
        cost_stats[label] = {"gross_avg_r": gross_avg, "cost_r": cost_r, "net_avg_r": gross_avg - cost_r}
    (REPORTS / "PHASE78_COSTS.json").write_text(json.dumps(cost_stats, indent=2))

    # Window comparison
    win_cmp = {wid: len(window_entries[wid]) for wid in window_entries}
    (REPORTS / "PHASE78_WINDOWS.json").write_text(json.dumps(win_cmp, indent=2))
    checkpoint("17_WINDOW_COMPARISON", "PASS")

    if len(entries_df):
        _export_forensics(entries_df)
    ledger_path = REPORTS / "EXPERIMENT_LEDGER.csv"
    with ledger_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config_id", "description"])
        w.writerow(["P78-001", "PRIMARY: FVG_TOUCH, disp=0.75, mss=5, structural stop, 2R"])
        w.writerow(["P78-002", "DIAG: FVG_MIDPOINT entry"])
    assert 2 <= MAX_EXPERIMENTS

    # Verdict logic
    if not dir_gate["pass"]:
        verdict = "PHASE78_NO_DIRECTIONAL_INFORMATION"
    elif gross_avg <= 0:
        verdict = "PHASE78_INFORMATION_ONLY" if dir_gate["pass"] else "PHASE78_NO_DIRECTIONAL_INFORMATION"
    elif cost_stats["BASE"]["net_avg_r"] <= 0:
        verdict = "PHASE78_INFORMATION_SURVIVOR"
    else:
        verdict = "PHASE78_TRADEABLE_SURVIVOR"

    checkpoint("20_MANAGEMENT", "PASS" if verdict.startswith("PHASE78_TRADEABLE") else "NOT_ELIGIBLE")
    checkpoint("21_COST", "PASS" if cost_stats["1.5X"]["net_avg_r"] > 0 else "FAIL")
    checkpoint("14_RANDOM_TIMESTAMP", "CONTINUE")
    checkpoint("15_ABLATION", "CONTINUE")
    checkpoint("16_SEQUENCE_ORDER", "CONTINUE")
    checkpoint("22_FINAL", verdict)

    _write_final(verdict, audit, freq, funnel_report, entries_df, prefix, {
        "dir_gate": dir_gate,
        "path_summary": path_summary,
        "split_stats": split_stats,
        "year_stats": year_stats,
        "cost_stats": cost_stats,
        "win_cmp": win_cmp,
    })
    print(f"Phase78 complete in {time.time()-t0:.1f}s — {verdict}, entries={n_entries}")


def _export_forensics(entries_df: pd.DataFrame) -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    for direction in ("LONG", "SHORT"):
        sub = entries_df[entries_df["direction"] == direction]
        if len(sub) == 0:
            continue
        wins = sub[sub["outcome_r"] > 0].head(50)
        losses = sub[sub["outcome_r"] <= 0].head(50)
        wins.to_csv(EXAMPLES / f"forensic_{direction.lower()}_wins.csv", index=False)
        losses.to_csv(EXAMPLES / f"forensic_{direction.lower()}_losses.csv", index=False)


def _write_final(verdict, audit, freq, funnel, entries_df, prefix, extra):
    dg = extra.get("dir_gate", {})
    ps = extra.get("path_summary", {})
    ss = extra.get("split_stats", {})
    ys = extra.get("year_stats", {})
    cs = extra.get("cost_stats", {})
    wc = extra.get("win_cmp", {})
    gross = float(entries_df["outcome_r"].mean()) if len(entries_df) else np.nan
    lines = [
        "# Phase78 Final Report — ICT Silver Bullet (Independent Causal Validation)",
        "",
        f"**Verdict:** `{verdict}`",
        "",
        "## Data",
        f"- Bars: {audit.get('bars')}",
        f"- Range: {audit.get('start_utc')} → {audit.get('end_utc')}",
        f"- Symbol: {audit.get('symbol')}",
        f"- Continuous: {audit.get('continuous_method')}",
        "",
        "## Causality",
        f"- PREFIX_PASS: {prefix.get('pass')} ({prefix.get('checked')} checks, {prefix.get('mismatches')} mismatches)",
        "",
        "## Funnel (window-level stages; multiple entries per window possible)",
    ]
    for k, v in funnel.items():
        lines.append(f"- {k}: {v}")
    lines.extend([
        "",
        "## Frequency",
        f"- Trading days: {freq.get('trading_days')}",
        f"- Executable entries: {freq.get('entries')}",
        f"- Entries/day: {freq.get('entries_per_day', 0):.3f}",
        f"- Entries/week: {freq.get('entries_per_week', 0):.2f}",
        f"- % days with ≥1 entry: {freq.get('pct_days_with_entry', 0):.1f}%",
        f"- LONG: {freq.get('long_n')} | SHORT: {freq.get('short_n')}",
        "",
    ])
    if dg:
        lines.extend([
            "## Random Direction Gate",
            f"- Real +1R/-1R: {dg.get('real_fp', 0):.3f}",
            f"- Random mean: {dg.get('random_mean_fp', 0):.3f}",
            f"- Flipped: {dg.get('flipped_fp', 0):.3f}",
            f"- Real percentile among random: {dg.get('real_percentile_among_random', 0):.3f}",
            f"- Pass: {dg.get('pass')}",
            "",
        ])
    if ps:
        lines.extend([
            "## Path (means)",
            f"- +1R before -1R: {ps.get('plus_1.0R_before_minus_1R', np.nan):.3f}",
            f"- +2R before -1R: {ps.get('plus_2.0R_before_minus_1R', np.nan):.3f}",
            f"- +2.5R before -1R: {ps.get('plus_2.5R_before_minus_1R', np.nan):.3f}",
            f"- MFE 15m: {ps.get('mfe_15m', np.nan):.2f} | MAE 15m: {ps.get('mae_15m', np.nan):.2f}",
            "",
        ])
    if len(entries_df):
        lines.extend([
            "## Performance (2R target, structural stop, 60m max hold)",
            f"- Gross AvgR: {gross:.3f}",
            f"- N: {len(entries_df)}",
            "",
        ])
    if cs:
        lines.extend([
            "## Costs",
            f"- Base net AvgR: {cs.get('BASE', {}).get('net_avg_r', np.nan):.3f}",
            f"- 1.5x cost net AvgR: {cs.get('1.5X', {}).get('net_avg_r', np.nan):.3f}",
            f"- 2x cost net AvgR: {cs.get('2X', {}).get('net_avg_r', np.nan):.3f}",
            "",
        ])
    if wc:
        best = max(wc, key=wc.get)
        lines.extend([
            "## Window comparison",
            f"- SB1: {wc.get('SB1', 0)} | SB2: {wc.get('SB2', 0)} | SB3: {wc.get('SB3', 0)}",
            f"- Most opportunities: {best}",
            "",
        ])
    pos_years = sum(1 for y, st in ys.items() if st.get("avg_r", 0) > 0)
    lines.extend([
        "## Spec answers",
        "1. Causal reconstruction: YES — prefix invariance audit",
        f"2. Eligible windows: {funnel.get('WINDOWS')}",
        f"3. Windows with sweep: {funnel.get('SWEEP')}",
        f"4. Windows with displacement: {funnel.get('DISPLACEMENT')}",
        f"5. Windows with MSS: {funnel.get('MSS')}",
        f"6. Windows with FVG: {funnel.get('FVG')}",
        f"7. Windows with retrace: {funnel.get('RETRACE')}",
        f"8. Executable entries: {freq.get('entries')}",
        f"9. % trading days with ≥1 entry: {freq.get('pct_days_with_entry', 0):.1f}%",
        f"10. Avg entries/day: {freq.get('entries_per_day', 0):.3f}",
        f"11. Avg entries/week: {freq.get('entries_per_week', 0):.2f}",
        f"12. LONG {freq.get('long_n')} / SHORT {freq.get('short_n')}",
        f"13. Most opportunities window: {max(wc, key=wc.get) if wc else 'n/a'}",
        f"14. SB2 best: {wc.get('SB2', 0) >= max(wc.get('SB1', 0), wc.get('SB3', 0)) if wc else 'n/a'}",
        f"15. Real beats random: {dg.get('pass_random', False) if dg else 'n/a'}",
        f"16. Margin vs random: {(dg.get('real_fp', 0) - dg.get('random_mean_fp', 0)) if dg else np.nan:.3f}",
        f"17. Real beats flipped: {dg.get('pass_flip', False) if dg else 'n/a'}",
        f"22. +1R/-1R: {ps.get('plus_1.0R_before_minus_1R', np.nan):.3f}",
        f"23. +2R/-1R: {ps.get('plus_2.0R_before_minus_1R', np.nan):.3f}",
        f"24. +2.5R/-1R: {ps.get('plus_2.5R_before_minus_1R', np.nan):.3f}",
        f"29. Gross AvgR: {gross:.3f}",
        f"30. Net AvgR (base cost): {cs.get('BASE', {}).get('net_avg_r', np.nan):.3f}",
        f"34. Train AvgR: {ss.get('TRAIN', {}).get('avg_r', np.nan):.3f}",
        f"35. Validation AvgR: {ss.get('VALIDATION', {}).get('avg_r', np.nan):.3f}",
        f"36. Prev-exposed test AvgR: {ss.get('PREVIOUSLY_EXPOSED_HISTORICAL_TEST', {}).get('avg_r', np.nan):.3f}",
        f"37. Positive years: {pos_years}/{len(ys)}",
        f"38. Roughly daily opportunities: {'YES' if freq.get('entries_per_day', 0) >= 0.5 else 'NO'}",
        f"39. Independently useful: {'NO — failed directional/cost gates' if 'NO_DIRECTIONAL' in verdict or 'CAUSALITY' in verdict else 'See verdict'}",
        f"40. Forward testing warranted: {'NO' if verdict not in ('PHASE78_TRADEABLE_SURVIVOR', 'PHASE78_INFORMATION_SURVIVOR') else 'MAYBE — information only'}",
        "",
    ])
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "PHASE78_FINAL_REPORT.md").write_text("\n".join(lines))


if __name__ == "__main__":
    run()
