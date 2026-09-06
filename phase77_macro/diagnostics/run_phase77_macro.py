#!/usr/bin/env python3
"""Phase77-MACRO — frozen Phase77 framework during scheduled macro windows (Jan 2024)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(line_buffering=True)

from phase77.python.data_loader import load_jan2024_m1  # noqa: E402
from phase77.python.gates import aggregate_paths, path_metrics  # noqa: E402
from phase77.python.setups import detect_setups  # noqa: E402
from phase77_macro.python.activation import activation_report, setup_counts_by_group  # noqa: E402
from phase77_macro.python.config import CHECKPOINTS, REPORTS  # noqa: E402
from phase77_macro.python.freeze import verify_freeze  # noqa: E402
from phase77_macro.python.macro_analysis import (  # noqa: E402
    add_range_covariates,
    lateness_vs_event,
    macro_random_gate,
    sample_size_class,
    two_sided_path_metrics,
)
from phase77_macro.python.macro_calendar import load_calendar, timezone_parity_check  # noqa: E402
from phase77_macro.python.windows import (  # noqa: E402
    ordinary_baseline_mask,
    same_time_control_mask,
    tag_macro_windows,
)

FEAT_CACHE = ROOT / "phase77" / "data" / "framework_features_jan2024.parquet"
SIGNALS_CACHE = ROOT / "phase77" / "data" / "framework_signals_jan2024.parquet"


def _md_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(lines)


def _final_verdict(n_macro: int, activation: dict, rand: dict, vol_only: bool) -> str:
    lifts = activation.get("lifts", {})
    rej_lift = max(
        lifts.get("UPPER_REJECTION_vs_baseline", 0) or 0,
        lifts.get("LOWER_REJECTION_vs_baseline", 0) or 0,
    )
    abs_lift = max(
        lifts.get("BUYING_ABSORBED_PROXY_vs_baseline", 0) or 0,
        lifts.get("SELLING_ABSORBED_PROXY_vs_baseline", 0) or 0,
    )
    if n_macro < 30:
        if rej_lift > 2 or abs_lift > 2:
            return "PHASE77_MACRO_N_TOO_SMALL"  # activation lift but can't infer
        return "PHASE77_MACRO_N_TOO_SMALL"
    if rej_lift < 1.5 and abs_lift < 1.5 and activation["rates"]["MACRO"].get("UPPER_REJECTION", 0) == 0:
        return "PHASE77_MACRO_NO_ACTIVATION_LIFT"
    if rand.get("status") != "PASS":
        if vol_only:
            return "PHASE77_MACRO_VOLATILITY_ONLY"
        return "PHASE77_MACRO_NO_DIRECTIONAL_INFORMATION"
    return "PHASE77_MACRO_PILOT_INFORMATION_PRESENT"


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    freeze = verify_freeze()
    (CHECKPOINTS / "00_freeze.json").write_text(json.dumps(freeze, indent=2))
    if freeze.get("status") == "PHASE77_MACRO_FREEZE_MISMATCH":
        (REPORTS / "PHASE77_MACRO_FINAL_REPORT.md").write_text(
            f"# Phase77-MACRO\n\n**Verdict:** `{freeze['status']}`\n"
        )
        return 1

    calendar = load_calendar()
    tz_check = timezone_parity_check(calendar)
    (CHECKPOINTS / "02_event_calendar.json").write_text(json.dumps({"status": "PASS", "n_events": len(calendar)}, indent=2))
    (CHECKPOINTS / "03_timezone.json").write_text(json.dumps(tz_check, indent=2, default=str))

    m1 = load_jan2024_m1()
    feat = pd.read_parquet(FEAT_CACHE)
    feat.index = pd.to_datetime(feat.index, utc=True)
    feat = add_range_covariates(feat)

    if SIGNALS_CACHE.exists():
        all_signals = pd.read_parquet(SIGNALS_CACHE)
    else:
        all_signals = detect_setups(feat)

    tags = tag_macro_windows(feat.index, calendar)
    feat = feat.join(tags)
    same_time = same_time_control_mask(feat.index, calendar, tags)
    baseline = ordinary_baseline_mask(tags, same_time, feat["in_rth"].fillna(False))

    macro_mask = tags["in_macro"] & feat["in_rth"].fillna(False)
    act = activation_report(feat, macro_mask, same_time & feat["in_rth"], baseline)

    # Attach macro event to signals
    sig_tags = tags.reindex(all_signals["signal_ts"].values if len(all_signals) else [])
    if len(all_signals):
        all_signals = all_signals.copy()
        all_signals["in_macro"] = [tags.loc[t, "in_macro"] if t in tags.index else False for t in all_signals["signal_ts"]]
        all_signals["macro_event"] = [tags.loc[t, "event_name"] if t in tags.index else "" for t in all_signals["signal_ts"]]
        all_signals["macro_subwindow"] = [tags.loc[t, "subwindow"] if t in tags.index else "" for t in all_signals["signal_ts"]]
    macro_signals = all_signals[all_signals["in_macro"]] if len(all_signals) else all_signals

    setup_counts = setup_counts_by_group(
        all_signals,
        feat.index,
        macro_mask,
        same_time & feat["in_rth"],
        baseline,
    )

    n_macro_sig = len(macro_signals)
    ss_class = sample_size_class(n_macro_sig)
    pathed = path_metrics(macro_signals, m1) if n_macro_sig else pd.DataFrame()
    pathed_ts = two_sided_path_metrics(macro_signals, m1) if n_macro_sig else pd.DataFrame()
    rand = macro_random_gate(macro_signals, m1)
    path_agg = aggregate_paths(pathed) if not pathed.empty else {"n": 0}

    # Volatility vs information
    macro_pathed_all = path_metrics(all_signals[all_signals["in_macro"]], m1) if n_macro_sig else pd.DataFrame()
    baseline_sig = all_signals[~all_signals["in_macro"]] if len(all_signals) and "in_macro" in all_signals.columns else pd.DataFrame()
    vol_macro = aggregate_paths(macro_pathed_all).get("mfe_15m", 0) if not macro_pathed_all.empty else 0
    vol_base = aggregate_paths(path_metrics(baseline_sig, m1)).get("mfe_15m", 0) if len(baseline_sig) else 0
    vol_only = vol_macro > 1.5 * max(vol_base, 0.01) and rand.get("status") != "PASS"

    lateness = lateness_vs_event(macro_signals, calendar, m1) if n_macro_sig else pd.DataFrame()

    verdict = _final_verdict(n_macro_sig, act, rand, vol_only)

    # --- Reports ---
    (REPORTS / "PHASE77_MACRO_DATA_AUDIT.md").write_text(
        "# Phase77-MACRO Data Audit\n\n"
        f"- Phase77 freeze: **{freeze['status']}**\n"
        f"- Pilot: Jan 2024 trades + 1m\n"
        f"- Tier-1 events: **{len(calendar)}**\n"
    )

    cal_lines = ["# Macro Event Calendar (Tier 1, Jan 2024)\n", _md_table(
        ["Event", "Date", "ET", "UTC", "Chicago"],
        [[r["event_name"], r["release_date"], r["scheduled_release_time_et"],
          str(r["release_ts_utc"]), str(r["release_ts_chi"])] for _, r in calendar.iterrows()],
    )]
    (REPORTS / "PHASE77_MACRO_EVENT_CALENDAR.md").write_text("\n".join(cal_lines))

    act_rows = []
    for key in (
        "UPPER_REJECTION", "LOWER_REJECTION", "BUYING_ABSORBED_PROXY", "SELLING_ABSORBED_PROXY",
        "BUYING_INEFFICIENT", "SELLING_INEFFICIENT", "CONFIRMED_LONG", "CONFIRMED_SHORT",
    ):
        act_rows.append([
            key,
            f"{act['rates']['MACRO'].get(key, 0):.4f}",
            f"{act['rates']['SAME_TIME_CONTROL'].get(key, 0):.4f}",
            f"{act['rates']['ORDINARY_BASELINE'].get(key, 0):.4f}",
            f"{act['lifts'].get(f'{key}_vs_baseline', 0):.2f}",
        ])
    (REPORTS / "PHASE77_MACRO_LAYER_ACTIVATION.md").write_text(
        "# Layer Activation\n\n" + _md_table(
            ["State", "Macro", "Same-time", "Baseline", "Lift vs baseline"],
            act_rows,
        ) + f"\n\nMacro bars: {act['rates']['MACRO'].get('n_bars', 0):,} | "
        f"Same-time: {act['rates']['SAME_TIME_CONTROL'].get('n_bars', 0):,} | "
        f"Baseline: {act['rates']['ORDINARY_BASELINE'].get('n_bars', 0):,}\n"
        f"\nSetup counts: {json.dumps(setup_counts, indent=2)}"
    )

    conf_lines = ["# Confluence Distribution\n"]
    for grp in ("MACRO", "SAME_TIME_CONTROL", "ORDINARY_BASELINE"):
        d = act["confluence"].get(grp, {})
        conf_lines.append(f"\n## {grp}\n")
        for cc in range(3, 8):
            conf_lines.append(f"- {cc}/7: {d.get(cc, 0)}")
    (REPORTS / "PHASE77_MACRO_CONFLUENCE.md").write_text("\n".join(conf_lines))

    if not macro_signals.empty:
        macro_signals.to_csv(REPORTS / "PHASE77_MACRO_SIGNALS.csv", index=False)
    else:
        (REPORTS / "PHASE77_MACRO_SIGNALS.csv").write_text("")

    (REPORTS / "PHASE77_MACRO_RANDOM_DIRECTION.md").write_text(
        f"# Random Direction\n\n```json\n{json.dumps(rand, indent=2)}\n```\n"
        f"Sample class: **{ss_class}**\n"
    )

    (REPORTS / "PHASE77_MACRO_PATH_AUDIT.md").write_text(
        f"# Path Audit (macro signals)\n\n```json\n{json.dumps(path_agg, indent=2)}\n```\n"
        f"Volatility-only flag: **{vol_only}**\n"
    )

    if not lateness.empty:
        lateness.to_csv(REPORTS / "PHASE77_MACRO_LATENESS.csv", index=False)

    (REPORTS / "PHASE77_MACRO_FINAL_REPORT.md").write_text(
        f"# Phase77-MACRO Final Report\n\n**Verdict:** `{verdict}`\n\n"
        f"## Summary\n\n"
        f"1. Framework activation during macro windows: macro bars {act['rates']['MACRO'].get('n_bars', 0):,}\n"
        f"2. UPPER_REJECTION macro rate: {act['rates']['MACRO'].get('UPPER_REJECTION', 0):.4f} "
        f"(baseline {act['rates']['ORDINARY_BASELINE'].get('UPPER_REJECTION', 0):.4f})\n"
        f"3. BUYING_ABSORBED macro: {act['rates']['MACRO'].get('BUYING_ABSORBED_PROXY', 0):.4f}\n"
        f"4. Macro O1-O6 signals: **{n_macro_sig}** (total pilot: {len(all_signals)})\n"
        f"5. Sample size: **{ss_class}**\n"
        f"6. Random direction: **{rand.get('status', 'NOT_ELIGIBLE')}**\n"
        f"7. Volatility-only: **{vol_only}**\n"
        f"8. Broader data justified: **{'No' if verdict in ('PHASE77_MACRO_N_TOO_SMALL', 'PHASE77_MACRO_NO_ACTIVATION_LIFT', 'PHASE77_MACRO_VOLATILITY_ONLY', 'PHASE77_MACRO_NO_DIRECTIONAL_INFORMATION') else 'Review'}**\n"
        f"9. Phase77 framework: **{'remain open for macro data' if 'INFORMATION' in verdict else 'no macro rescue — closed'}**\n"
    )

    cp = {
        "verdict": verdict,
        "n_macro_signals": n_macro_sig,
        "n_total_signals": len(all_signals),
        "sample_size_class": ss_class,
        "activation": act,
        "random_direction": rand,
        "setup_counts": setup_counts,
        "volatility_only": vol_only,
    }
    (CHECKPOINTS / "18_final.json").write_text(json.dumps(cp, indent=2, default=str))

    print(f"Verdict: {verdict}")
    print(f"Macro signals: {n_macro_sig} / {len(all_signals)} total")
    print(f"Macro UPPER_REJECTION rate: {act['rates']['MACRO'].get('UPPER_REJECTION', 0):.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
