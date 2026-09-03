"""Retest structure-failure forensics for recovered BOS candidates."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .backtest import validation_window
from .config import FrozenConfig
from .recovered_bos_gate_forensics import (
    FOCUS_CONFIG,
    HORIZONS,
    R_LEVELS,
    _excel_safe,
    _finite,
    _horizon_excursions,
    _r_race,
    _robustness_rows,
    _summarize_sim,
    apply_sim_costs,
    run_recovered_bos_gate_forensics,
    simulate_frozen_trade,
)
from .sequential_bos_ignore_samebar import run_ignore_samebar_backtest
from .sequential_bos import _summarize_with_costs


RECLAIM_WINDOW = 3


def retest_invalidation_rule(config: FrozenConfig = FrozenConfig()) -> Dict[str, str]:
    tol = config.p12_retest_atr_tolerance
    return {
        "tolerance": f"retest_tolerance = ATR * {tol}",
        "long_touch": f"eligible bar (bar > bos_bar) AND low <= bos_level + retest_tolerance",
        "long_invalidate": f"eligible bar AND close < bos_level - retest_tolerance",
        "short_touch": f"eligible bar AND high >= bos_level - retest_tolerance",
        "short_invalidate": f"eligible bar AND close > bos_level + retest_tolerance",
        "order": "invalidation checked before retest acceptance on each bar",
        "immediate_termination": "YES — one qualifying invalid close immediately resets candidate",
        "later_reclaim_allowed": "NO — candidate is terminated; no WAIT_RECLAIM state exists",
    }


def _cohens_d(a: pd.Series, b: pd.Series) -> float:
    a = a.dropna().astype(float)
    b = b.dropna().astype(float)
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    pooled = math.sqrt(((a.var(ddof=1) + b.var(ddof=1)) / 2))
    return float((a.mean() - b.mean()) / pooled) if pooled > 0 else float("nan")


def _retest_metrics_at_bar(
    *,
    direction: int,
    bos_level: float,
    atr: float,
    open_price: float,
    high: float,
    low: float,
    close: float,
    tolerance: float,
) -> Dict[str, float]:
    probe = low if direction == 1 else high
    body = abs(close - open_price)
    rng = high - low
    wick_pen = max(0.0, (bos_level + tolerance - probe) if direction == 1 else (probe - (bos_level - tolerance)))
    close_pen = max(0.0, (bos_level - tolerance - close) if direction == 1 else (close - (bos_level + tolerance)))
    close_loc = (close - low) / rng if rng > 0 else 0.5
    return {
        "penetration_atr": abs(probe - bos_level) / atr if atr > 0 else float("nan"),
        "close_penetration_atr": close_pen / atr if atr > 0 else float("nan"),
        "wick_penetration_atr": wick_pen / atr if atr > 0 else float("nan"),
        "body_atr": body / atr if atr > 0 else float("nan"),
        "range_atr": rng / atr if atr > 0 else float("nan"),
        "close_location_in_candle": close_loc,
        "distance_from_bos_atr": (close - bos_level) / atr if atr > 0 else float("nan"),
    }


def _bar_retest_flags(
    *,
    direction: int,
    bos_level: float,
    atr: float,
    open_price: float,
    high: float,
    low: float,
    close: float,
    bos_bar: int,
    bar_index: int,
    tolerance: float,
) -> Dict[str, Any]:
    eligible = bar_index > bos_bar
    would_touch = (low <= bos_level + tolerance) if direction == 1 else (high >= bos_level - tolerance)
    invalid = eligible and (
        (close < bos_level - tolerance) if direction == 1 else (close > bos_level + tolerance)
    )
    accepted = eligible and would_touch and not invalid
    return {
        "eligible_retest_bar": eligible,
        "touched_retest_zone": eligible and would_touch,
        "structure_invalidation": invalid,
        "retest_would_accept": accepted,
        "invalidation_threshold": bos_level - tolerance if direction == 1 else bos_level + tolerance,
    }


def replay_retest_path(
    data: pd.DataFrame,
    *,
    bos_bar: int,
    bos_level: float,
    direction: int,
    config: FrozenConfig,
    end_exclusive: pd.Timestamp,
    reclaim3: bool = False,
) -> Tuple[Optional[int], str, List[Dict[str, Any]], int]:
    """Replay from BOS through retest/confirm/reclaim. Returns entry_bar, outcome, bar_rows, failure_bar."""
    state = "WAIT_RETEST"
    retest_bar = -1
    reclaim_start = -1
    bar_rows: List[Dict[str, Any]] = []
    failure_bar = -1

    for bar_index in range(bos_bar + 1, len(data)):
        ts = data.index[bar_index]
        if ts >= end_exclusive:
            break
        row = data.iloc[bar_index]
        atr = float(row.atr) if _finite(row.atr) else 1.0
        open_price = float(row.open)
        high = float(row.high)
        low = float(row.low)
        close = float(row.close)
        tolerance = atr * config.p12_retest_atr_tolerance
        flags = _bar_retest_flags(
            direction=direction,
            bos_level=bos_level,
            atr=atr,
            open_price=open_price,
            high=high,
            low=low,
            close=close,
            bos_bar=bos_bar,
            bar_index=bar_index,
            tolerance=tolerance,
        )
        prev_state = state
        outcome_event = ""

        if state == "WAIT_RETEST":
            if not flags["eligible_retest_bar"] and flags["touched_retest_zone"]:
                return None, "same_bar_bos_retest", bar_rows, bar_index
            if flags["structure_invalidation"]:
                failure_bar = bar_index
                if reclaim3:
                    state = "WAIT_RECLAIM"
                    reclaim_start = bar_index
                    outcome_event = "structure_fail_to_reclaim"
                else:
                    return None, "retest_structure_failed", bar_rows, bar_index
            elif flags["retest_would_accept"]:
                state = "WAIT_CONFIRM"
                retest_bar = bar_index
                outcome_event = "retest_accepted"
            elif bar_index - bos_bar > config.p12_expiry_bars:
                return None, "bos_retest_expiry", bar_rows, bar_index

        elif state == "WAIT_RECLAIM":
            would_confirm = (close > open_price and close > bos_level) if direction == 1 else (
                close < open_price and close < bos_level
            )
            if would_confirm:
                return bar_index, "reclaim3_entry", bar_rows, failure_bar
            if bar_index - reclaim_start > RECLAIM_WINDOW:
                return None, "reclaim3_expired", bar_rows, failure_bar

        elif state == "WAIT_CONFIRM":
            would_confirm = (close > open_price and close > bos_level) if direction == 1 else (
                close < open_price and close < bos_level
            )
            if bar_index <= retest_bar and would_confirm:
                return None, "same_bar_retest_confirm", bar_rows, failure_bar
            if bar_index > retest_bar and would_confirm:
                return bar_index, "confirm_entry", bar_rows, failure_bar
            invalid = (close < bos_level - tolerance) if direction == 1 else (close > bos_level + tolerance)
            if bar_index > retest_bar and invalid:
                return None, "confirm_failed", bar_rows, failure_bar
            if bar_index - retest_bar > config.p12_expiry_bars:
                return None, "confirm_expiry", bar_rows, failure_bar

        metrics = _retest_metrics_at_bar(
            direction=direction,
            bos_level=bos_level,
            atr=atr,
            open_price=open_price,
            high=high,
            low=low,
            close=close,
            tolerance=tolerance,
        )
        bar_rows.append(
            {
                "bar_index": bar_index,
                "timestamp": ts,
                "state_before": prev_state,
                "state_after": state,
                "outcome_event": outcome_event,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "atr": atr,
                "distance_from_bos_points": close - bos_level,
                **metrics,
                **flags,
            }
        )

    return None, "data_end", bar_rows, failure_bar


def classify_failure(
    data: pd.DataFrame,
    *,
    failure_bar: int,
    bos_level: float,
    direction: int,
    atr: float,
) -> str:
    start = failure_bar + 1
    end = min(failure_bar + 12, len(data) - 1)
    if start > end:
        return "Choppy"
    window = data.iloc[start : end + 1]
    closes = window.close.astype(float)
    if direction == 1:
        favorable = closes > bos_level
        mfe = max(0.0, float(window.high.max() - bos_level))
        mae = max(0.0, float(bos_level - window.low.min()))
    else:
        favorable = closes < bos_level
        mfe = max(0.0, float(bos_level - window.low.min()))
        mae = max(0.0, float(window.high.max() - bos_level))
    crosses = int((favorable != favorable.shift()).sum()) if len(favorable) > 1 else 0
    reclaimed = bool(favorable.any())
    if crosses >= 3:
        return "Choppy"
    if reclaimed and mfe > mae:
        return "Temporary overshoot"
    if not reclaimed and mae >= mfe:
        return "Genuine failure"
    return "Choppy"


def run_retest_structure_forensics(
    frame: pd.DataFrame,
    *,
    start: str = "2024-01-01",
    end: str = "2026-06-26",
    config: FrozenConfig = FrozenConfig(),
    output: Path,
) -> Dict[str, Any]:
    gate_dir = output.parent / "recovered_bos_gate_forensics"
    if not (gate_dir / "recovered_bos_trace.csv").exists():
        run_recovered_bos_gate_forensics(frame, start=start, end=end, config=config, output=gate_dir)
    output.mkdir(parents=True, exist_ok=True)

    trace = pd.read_csv(gate_dir / "recovered_bos_trace.csv")
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)
    from .sequential_bos import _prepare_data

    data = _prepare_data(frame, config)

    baseline_result, baseline_funnel = run_ignore_samebar_backtest(
        frame, start=start, end=end, config=config, seq_config=FOCUS_CONFIG
    )
    baseline_trades = baseline_result.trades.loc[
        baseline_result.trades.get("recovered_samebar", False) == True
    ].copy()
    baseline_summary = _summarize_with_costs(baseline_trades)

    counts = trace.final_state.value_counts()
    reproduced = (
        len(trace) == 158
        and int(trace.retest_accepted.sum()) == 88
        and int((trace.final_state == "RETEST_FAIL").sum()) == 53
        and int((trace.final_state == "RETEST_EXPIRY").sum()) == 17
        and int((trace.final_state == "ENTRY").sum()) == 54
        and baseline_summary["N"] == 54
        and abs(baseline_summary["net_TotalR"] - (-0.93)) < 0.2
        and abs(baseline_summary["net_PF"] - 0.97) < 0.05
    )
    if not reproduced:
        raise RuntimeError("Baseline reproduction failed")

    fails = trace.loc[trace.final_state == "RETEST_FAIL"].copy()
    accepted = trace.loc[trace.retest_accepted == True].copy()

    fail_summaries: List[Dict[str, Any]] = []
    fail_bars: List[Dict[str, Any]] = []

    for row in fails.itertuples():
        bos_bar = int(row.bos_bar)
        direction = int(row.direction_int)
        bos_level = float(row.bos_level)
        _, outcome, bars, failure_bar = replay_retest_path(
            data,
            bos_bar=bos_bar,
            bos_level=bos_level,
            direction=direction,
            config=config,
            end_exclusive=end_exclusive,
            reclaim3=False,
        )
        first_touch = next((b for b in bars if b.get("touched_retest_zone")), None)
        fail_bar = failure_bar if failure_bar >= 0 else (bars[-1]["bar_index"] if bars else bos_bar)
        fail_row = data.iloc[fail_bar]
        atr_fail = float(fail_row.atr)
        metrics = _retest_metrics_at_bar(
            direction=direction,
            bos_level=bos_level,
            atr=atr_fail,
            open_price=float(fail_row.open),
            high=float(fail_row.high),
            low=float(fail_row.low),
            close=float(fail_row.close),
            tolerance=atr_fail * config.p12_retest_atr_tolerance,
        )
        risk = config.trade_stop_atr * float(row.risk_points) / config.trade_stop_atr
        risk = float(row.risk_points)
        fail_class = classify_failure(
            data, failure_bar=fail_bar, bos_level=bos_level, direction=direction, atr=atr_fail
        )
        post = {}
        ref = float(data.iloc[fail_bar].close)
        for horizon in HORIZONS:
            post.update(
                _horizon_excursions(
                    data,
                    start_bar=fail_bar,
                    direction=direction,
                    ref_price=ref,
                    risk=risk,
                    atr=atr_fail,
                    horizon=horizon,
                )
            )
        for target in R_LEVELS:
            post[f"hit_{str(target).replace('.', '_')}R_before_stop"] = _r_race(
                data,
                start_bar=fail_bar,
                direction=direction,
                ref_price=ref,
                risk=risk,
                target_r=target,
            )

        reclaim_bar = -1
        reclaim_confirm = False
        for offset in range(1, RECLAIM_WINDOW + 1):
            pos = fail_bar + offset
            if pos >= len(data):
                break
            bar = data.iloc[pos]
            close = float(bar.close)
            open_price = float(bar.open)
            if direction == 1 and close > bos_level and close > open_price:
                reclaim_bar = pos
                reclaim_confirm = True
                break
            if direction == -1 and close < bos_level and close < open_price:
                reclaim_bar = pos
                reclaim_confirm = True
                break
            if direction == 1 and close > bos_level:
                reclaim_bar = pos
            if direction == -1 and close < bos_level:
                reclaim_bar = pos

        summary = {
            "candidate_id": int(row.candidate_id),
            "direction": row.direction,
            "setup_timestamp": row.setup_timestamp,
            "bos_timestamp": row.bos_timestamp,
            "bos_level": bos_level,
            "atr_at_bos": float(row.atr_at_bos),
            "first_retest_touch_timestamp": first_touch["timestamp"] if first_touch else pd.NaT,
            "failure_timestamp": data.index[fail_bar],
            "failure_bar": fail_bar,
            "bars_bos_to_failure": fail_bar - bos_bar,
            "failure_class": fail_class,
            "reclaim_within_3_bars": reclaim_bar >= 0 and reclaim_bar - fail_bar <= RECLAIM_WINDOW,
            "reclaim_bar": reclaim_bar,
            "reclaim_confirm_passes": reclaim_confirm,
            "reclaim_bars_after_fail": reclaim_bar - fail_bar if reclaim_bar >= 0 else pd.NA,
            "outcome_replay": outcome,
            **metrics,
            **post,
        }
        fail_summaries.append(summary)
        for bar in bars:
            fail_bars.append({"candidate_id": int(row.candidate_id), **bar})

    fail_df = pd.DataFrame(fail_summaries)
    fail_bar_df = pd.DataFrame(fail_bars)

    accepted_metrics = []
    for row in accepted.itertuples():
        rb = int(row.retest_bar)
        br = data.iloc[rb]
        atr = float(br.atr)
        accepted_metrics.append(
            {
                "candidate_id": int(row.candidate_id),
                "direction": row.direction,
                "session": row.session,
                "htf_regime": row.htf_regime,
                "bars_bos_to_retest": rb - int(row.bos_bar),
                "bos_displacement_atr": abs(float(br.close) - float(row.bos_level)) / float(row.atr_at_bos),
                **_retest_metrics_at_bar(
                    direction=int(row.direction_int),
                    bos_level=float(row.bos_level),
                    atr=atr,
                    open_price=float(br.open),
                    high=float(br.high),
                    low=float(br.low),
                    close=float(br.close),
                    tolerance=atr * config.p12_retest_atr_tolerance,
                ),
            }
        )
    accepted_df = pd.DataFrame(accepted_metrics)

    compare_metrics = [
        "penetration_atr",
        "close_penetration_atr",
        "wick_penetration_atr",
        "body_atr",
        "range_atr",
        "close_location_in_candle",
    ]
    comparison_rows = []
    for metric in compare_metrics:
        a = accepted_df[metric]
        f = fail_df[metric]
        comparison_rows.append(
            {
                "metric": metric,
                "accepted_mean": float(a.mean()),
                "accepted_median": float(a.median()),
                "failed_mean": float(f.mean()),
                "failed_median": float(f.median()),
                "cohens_d": _cohens_d(a, f),
            }
        )
    comparison_rows.append(
        {
            "metric": "bars_bos_to_retest",
            "accepted_mean": float(accepted_df["bars_bos_to_retest"].mean()),
            "accepted_median": float(accepted_df["bars_bos_to_retest"].median()),
            "failed_mean": float(fail_df["bars_bos_to_failure"].mean()),
            "failed_median": float(fail_df["bars_bos_to_failure"].median()),
            "cohens_d": _cohens_d(accepted_df["bars_bos_to_retest"], fail_df["bars_bos_to_failure"]),
        }
    )
    comparison_df = pd.DataFrame(comparison_rows)

    class_rows = []
    for cls, group in fail_df.groupby("failure_class"):
        class_rows.append(
            {
                "failure_class": cls,
                "N": len(group),
                "pct": len(group) / len(fail_df) * 100,
                "median_h12_mfe_atr": float(group["h12_mfe_atr"].median()),
                "median_h12_mae_atr": float(group["h12_mae_atr"].median()),
            }
        )
    classification_df = pd.DataFrame(class_rows)

    overshoots = fail_df.loc[fail_df.failure_class == "Temporary overshoot"]
    reclaim_rows = []
    for bucket, lo, hi in [
        ("1 bar", 1, 1),
        ("2 bars", 2, 2),
        ("3 bars", 3, 3),
        ("4-6 bars", 4, 6),
        ("7-12 bars", 7, 12),
        (">12 bars", 13, 999),
    ]:
        if bucket == ">12 bars":
            mask = overshoots.reclaim_bars_after_fail > 12
        else:
            mask = overshoots.reclaim_bars_after_fail.between(lo, hi)
        reclaim_rows.append({"bucket": bucket, "N": int(mask.sum())})
    reclaim_timing_df = pd.DataFrame(reclaim_rows)

    current_trades: List[Dict[str, Any]] = []
    reclaim_trades: List[Dict[str, Any]] = []
    for row in trace.itertuples():
        direction = int(row.direction_int)
        entry_bar, outcome, _, _ = replay_retest_path(
            data,
            bos_bar=int(row.bos_bar),
            bos_level=float(row.bos_level),
            direction=direction,
            config=config,
            end_exclusive=end_exclusive,
            reclaim3=False,
        )
        if entry_bar is not None and outcome == "confirm_entry":
            trade = simulate_frozen_trade(
                data, entry_bar=entry_bar, direction=direction, config=config, end_exclusive=end_exclusive
            )
            if trade:
                trade["candidate_id"] = int(row.candidate_id)
                trade["entry_source"] = "existing_confirm"
                current_trades.append(trade)

        entry_bar_r, outcome_r, _, _ = replay_retest_path(
            data,
            bos_bar=int(row.bos_bar),
            bos_level=float(row.bos_level),
            direction=direction,
            config=config,
            end_exclusive=end_exclusive,
            reclaim3=True,
        )
        if entry_bar_r is not None:
            trade_r = simulate_frozen_trade(
                data, entry_bar=entry_bar_r, direction=direction, config=config, end_exclusive=end_exclusive
            )
            if trade_r:
                trade_r["candidate_id"] = int(row.candidate_id)
                trade_r["entry_source"] = (
                    "existing_confirm" if outcome_r == "confirm_entry" else "new_reclaim3"
                )
                reclaim_trades.append(trade_r)

    current_df = apply_sim_costs(pd.DataFrame(current_trades))
    reclaim_df = apply_sim_costs(pd.DataFrame(reclaim_trades))
    current_perf = _summarize_sim(current_df)
    reclaim_perf = _summarize_sim(reclaim_df)
    existing_perf = _summarize_sim(reclaim_df.loc[reclaim_df.entry_source == "existing_confirm"])
    new_perf = _summarize_sim(reclaim_df.loc[reclaim_df.entry_source == "new_reclaim3"])

    model_comparison = pd.DataFrame(
        [
            {"model": "CURRENT_CONFIRM", **current_perf},
            {"model": "RECLAIM_3", **reclaim_perf},
            {"model": "EXISTING_54", **existing_perf},
            {"model": "NEW_RECLAIM_ONLY", **new_perf},
        ]
    )

    robustness = pd.DataFrame()
    if new_perf.get("net_TotalR", 0) > 0:
        new_only = reclaim_df.loc[reclaim_df.entry_source == "new_reclaim3"]
        robustness = pd.DataFrame(_robustness_rows(new_only, config=config, prefix="new_reclaim_"))

    rule = retest_invalidation_rule(config)
    overshoot_3 = int(fail_df.reclaim_within_3_bars.sum())
    confirm_pass_3 = int(fail_df.reclaim_confirm_passes.sum())

    if new_perf.get("net_TotalR", 0) > 0 and new_perf.get("net_AvgR", 0) > 0:
        reclaim_verdict = "HELPFUL"
    elif new_perf.get("net_TotalR", 0) < -2:
        reclaim_verdict = "HARMFUL"
    elif abs(reclaim_perf.get("net_TotalR", 0) - current_perf.get("net_TotalR", 0)) < 0.5:
        reclaim_verdict = "NEUTRAL"
    else:
        reclaim_verdict = "INCONCLUSIVE"

    report = _build_report(
        rule=rule,
        fail_df=fail_df,
        classification_df=classification_df,
        comparison_df=comparison_df,
        model_comparison=model_comparison,
        overshoot_3=overshoot_3,
        confirm_pass_3=confirm_pass_3,
        reclaim_verdict=reclaim_verdict,
        reproduced=reproduced,
    )

    fail_df.to_csv(output / "retest_structure_fail_trace.csv", index=False)
    fail_bar_df.to_csv(output / "retest_structure_fail_bars.csv", index=False)
    comparison_df.to_csv(output / "accepted_vs_failed_comparison.csv", index=False)
    classification_df.to_csv(output / "failure_classification.csv", index=False)
    reclaim_timing_df.to_csv(output / "reclaim_timing.csv", index=False)
    model_comparison.to_csv(output / "model_comparison.csv", index=False)
    if not robustness.empty:
        robustness.to_csv(output / "robustness.csv", index=False)
    (output / "RETEST_STRUCTURE_FAILURE_FORENSICS.md").write_text(report)

    try:
        with pd.ExcelWriter(output / "RETEST_STRUCTURE_FAILURE_FORENSICS.xlsx", engine="openpyxl") as writer:
            for name, df in {
                "fail_trace": fail_df,
                "fail_bars": fail_bar_df,
                "comparison": comparison_df,
                "classification": classification_df,
                "model_comparison": model_comparison,
                "reclaim_timing": reclaim_timing_df,
            }.items():
                _excel_safe(df).to_excel(writer, sheet_name=name[:31], index=False)
    except ImportError:
        pass

    manifest = {
        "reproduced": reproduced,
        "reclaim_verdict": reclaim_verdict,
        "current": current_perf,
        "reclaim3": reclaim_perf,
        "new_reclaim_only": new_perf,
        "existing_54": existing_perf,
        "failure_classes": classification_df.to_dict(orient="records"),
        "overshoot_reclaim_3": overshoot_3,
        "confirm_pass_3": confirm_pass_3,
    }
    (output / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return manifest


def _build_report(
    *,
    rule: Dict[str, str],
    fail_df: pd.DataFrame,
    classification_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    model_comparison: pd.DataFrame,
    overshoot_3: int,
    confirm_pass_3: int,
    reclaim_verdict: str,
    reproduced: bool,
) -> str:
    current = model_comparison.loc[model_comparison.model == "CURRENT_CONFIRM"].iloc[0]
    reclaim = model_comparison.loc[model_comparison.model == "RECLAIM_3"].iloc[0]
    new_only = model_comparison.loc[model_comparison.model == "NEW_RECLAIM_ONLY"].iloc[0]
    lines = [
        "# Retest Structure-Failure Forensics",
        "",
        f"Baseline reproduced: {'PASS' if reproduced else 'FAIL'}",
        "",
        "## Current retest invalidation rule",
        "",
        f"- Tolerance: `{rule['tolerance']}`",
        f"- LONG touch: `{rule['long_touch']}`",
        f"- LONG invalidate: `{rule['long_invalidate']}`",
        f"- SHORT touch: `{rule['short_touch']}`",
        f"- SHORT invalidate: `{rule['short_invalidate']}`",
        f"- Evaluation order: {rule['order']}",
        f"- Immediate termination: {rule['immediate_termination']}",
        f"- Later reclaim allowed: {rule['later_reclaim_allowed']}",
        "",
        "## Failure classification",
        "",
    ]
    for row in classification_df.itertuples():
        lines.append(f"- {row.failure_class}: N={int(row.N)} ({row.pct:.1f}%)")
    lines.extend(
        [
            "",
            "## Model comparison (recovered BOS population)",
            "",
            f"- CURRENT: N={int(current.N)}, Net AvgR={current.net_AvgR:.4f}, TotalR={current.net_TotalR:.2f}, PF={current.net_PF:.3f}, MaxDD={current.MaxDD:.2f}R",
            f"- RECLAIM-3: N={int(reclaim.N)}, Net AvgR={reclaim.net_AvgR:.4f}, TotalR={reclaim.net_TotalR:.2f}, PF={reclaim.net_PF:.3f}, MaxDD={reclaim.MaxDD:.2f}R",
            f"- NEW RECLAIM ONLY: N={int(new_only.N)}, Net AvgR={new_only.net_AvgR:.4f}, TotalR={new_only.net_TotalR:.2f}, PF={new_only.net_PF:.3f}, MaxDD={new_only.MaxDD:.2f}R",
            "",
            f"Temporary overshoots reclaiming within 3 bars: {overshoot_3}",
            f"Of those, existing confirm condition passes: {confirm_pass_3}",
            "",
            f"RECLAIM RULE VALUE: {reclaim_verdict}",
        ]
    )
    return "\n".join(lines) + "\n"
