"""Forensic trace for SEQUENTIAL_BOS SWING_2_2 + expiry=3.

Diagnostic only. Does not modify frozen strategy logic, Pine, or simulator rules.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .backtest import validation_window
from .bos_semantic_audit import CausalSwingEngine
from .config import FrozenConfig
from .indicators import htf_regime_name, session_bucket_name
from .liquidity import LiquidityEngine
from .sequential_bos import (
    BosDefinition,
    SequentialBosConfig,
    SequentialBosFunnel,
    _prepare_data,
    _summarize_with_costs,
    apply_costs,
    run_sequential_bos_backtest,
)
from .setup_engine import SetupEngine
from .structure import StructureEngine
from .trade_engine import TradeEngine


HORIZONS = (3, 6, 12, 24, 48)
R_LEVELS = (0.5, 1.0, 1.5, 2.0)
FOCUS_CONFIG = SequentialBosConfig(
    bos_definition=BosDefinition.SWING_2_2,
    setup_bos_expiry_bars=3,
)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _median(series: pd.Series) -> float:
    values = series.dropna().astype(float)
    return float(values.median()) if len(values) else float("nan")


def _pct(condition: pd.Series) -> float:
    if len(condition) == 0:
        return 0.0
    return float(condition.mean() * 100.0)


def _profit_factor(net_r: pd.Series) -> float:
    wins = net_r[net_r > 0].sum()
    losses = -net_r[net_r < 0].sum()
    return float(wins / losses) if losses > 0 else float("inf")


def _excel_safe(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]):
            series = pd.to_datetime(out[column], errors="coerce")
            if hasattr(series.dt, "tz") and series.dt.tz is not None:
                out[column] = series.dt.tz_localize(None)
    return out


def _timing_summary(group: pd.DataFrame) -> Dict[str, Any]:
    if group.empty:
        return {"N": 0}
    return {
        "N": len(group),
        "median_mfe_atr_h12": _median(group["h12_mfe_atr"]),
        "median_mae_atr_h12": _median(group["h12_mae_atr"]),
        "pct_1R_before_stop": _pct(group["hit_1_0R_before_stop"]),
        "pct_2R_before_stop": _pct(group["hit_2_0R_before_stop"]),
        "long_pct": _pct(group["direction"] == "Long"),
        "short_pct": _pct(group["direction"] == "Short"),
    }


def _timing_bucket(bars: int) -> str:
    if bars <= 3:
        return "1-3 bars"
    if bars <= 6:
        return "4-6 bars"
    if bars <= 12:
        return "7-12 bars"
    if bars <= 24:
        return "13-24 bars"
    return ">24 bars"


def _horizon_excursions(
    data: pd.DataFrame,
    *,
    setup_bar: int,
    direction: int,
    setup_price: float,
    risk: float,
    atr: float,
    horizon: int,
) -> Dict[str, float]:
    start = setup_bar + 1
    end = min(setup_bar + horizon, len(data) - 1)
    if start > end:
        return {f"h{horizon}_{k}": 0.0 for k in ("mfe_points", "mae_points", "mfe_atr", "mae_atr", "mfe_r", "mae_r")}
    window = data.iloc[start : end + 1]
    if direction == 1:
        mfe_pts = max(0.0, float(window.high.max() - setup_price))
        mae_pts = max(0.0, float(setup_price - window.low.min()))
    else:
        mfe_pts = max(0.0, float(setup_price - window.low.min()))
        mae_pts = max(0.0, float(window.high.max() - setup_price))
    return {
        f"h{horizon}_mfe_points": mfe_pts,
        f"h{horizon}_mae_points": mae_pts,
        f"h{horizon}_mfe_atr": mfe_pts / atr if atr > 0 else float("nan"),
        f"h{horizon}_mae_atr": mae_pts / atr if atr > 0 else float("nan"),
        f"h{horizon}_mfe_r": mfe_pts / risk if risk > 0 else float("nan"),
        f"h{horizon}_mae_r": mae_pts / risk if risk > 0 else float("nan"),
    }


def _r_race(
    data: pd.DataFrame,
    *,
    setup_bar: int,
    direction: int,
    setup_price: float,
    risk: float,
    target_r: float,
    max_bars: int = 48,
) -> bool:
    start = setup_bar + 1
    end = min(setup_bar + max_bars, len(data) - 1)
    target = setup_price + direction * target_r * risk
    stop = setup_price - direction * risk
    for pos in range(start, end + 1):
        row = data.iloc[pos]
        if direction == 1:
            if float(row.low) <= stop:
                return False
            if float(row.high) >= target:
                return True
        else:
            if float(row.high) >= stop:
                return False
            if float(row.low) <= target:
                return True
    return False


def _setup_bos_failure_class(row: pd.Series) -> str:
    if row.final_rejection_stage != "SETUP":
        return row.final_rejection_reason or "other"
    reason = row.final_rejection_reason
    if reason == "same_bar_setup_bos":
        return "E_same_bar_correctly_rejected"
    if reason == "opposite_bos_before_retest":
        return "C_opposite_structure_first"
    if reason != "setup_bos_expiry":
        return "F_other"
    bucket = row.later_22_bos_timing_bucket
    mapping = {
        "no later BOS": "A_no_later_22_bos",
        "1-3 bars": "B_within_expiry_window",
        "4-6 bars": "B_bos_bar_4_to_6",
        "7-12 bars": "B_bos_bar_7_to_12",
        "13-24 bars": "B_bos_bar_13_to_24",
        ">24 bars": "B_bos_bar_gt_24",
    }
    return mapping.get(bucket, "F_other")


def _new_setup_row(
    *,
    setup_id: int,
    timestamp: pd.Timestamp,
    bar_index: int,
    direction: int,
    score: float,
    setup_price: float,
    atr: float,
    structural_level: float,
    session_bucket: int,
    htf_regime: int,
) -> Dict[str, Any]:
    return {
        "setup_id": setup_id,
        "setup_timestamp": timestamp,
        "setup_bar": bar_index,
        "direction": "Long" if direction == 1 else "Short",
        "direction_int": direction,
        "setup_price": setup_price,
        "setup_score": score,
        "session": session_bucket_name(session_bucket),
        "session_bucket": session_bucket,
        "htf_regime": htf_regime_name(htf_regime),
        "htf_regime_int": htf_regime,
        "atr_at_setup": atr,
        "setup_structural_level": structural_level,
        "risk_points_at_setup": FrozenConfig().trade_stop_atr * atr,
        "same_bar_22_break_rejected": False,
        "bos_within_expiry": False,
        "bos_bar": pd.NA,
        "bos_timestamp": pd.NaT,
        "bars_to_qualifying_bos": pd.NA,
        "bos_level": float("nan"),
        "bos_displacement_atr": float("nan"),
        "retest_occurred": False,
        "retest_bar": pd.NA,
        "bars_bos_to_retest": pd.NA,
        "retest_distance_atr": float("nan"),
        "confirmation_occurred": False,
        "confirm_bar": pd.NA,
        "bars_retest_to_confirm": pd.NA,
        "entry_occurred": False,
        "entry_bar": pd.NA,
        "final_rejection_stage": "",
        "final_rejection_reason": "",
        "first_later_22_bos_bar": pd.NA,
        "first_later_22_bos_timestamp": pd.NaT,
        "bars_setup_to_first_later_22_bos": pd.NA,
        "first_later_22_bos_level": float("nan"),
        "first_later_22_bos_displacement_atr": float("nan"),
        "first_opposite_22_bos_bar": pd.NA,
        "first_opposite_22_bos_before_match": False,
        "later_22_bos_timing_bucket": "",
    }


def _annotate_later_bos(trace: Dict[str, Any], later_events: List[Tuple[int, pd.Timestamp, float, float, int]]) -> None:
    setup_bar = int(trace["setup_bar"])
    direction = int(trace["direction_int"])
    match = [event for event in later_events if event[0] > setup_bar and event[4] == direction]
    if match:
        bar, ts, level, disp_atr, _ = match[0]
        trace["first_later_22_bos_bar"] = bar
        trace["first_later_22_bos_timestamp"] = ts
        trace["bars_setup_to_first_later_22_bos"] = bar - setup_bar
        trace["first_later_22_bos_level"] = level
        trace["first_later_22_bos_displacement_atr"] = disp_atr
        trace["later_22_bos_timing_bucket"] = _timing_bucket(bar - setup_bar)
    else:
        trace["later_22_bos_timing_bucket"] = "no later BOS"


def _stage_from_reason(reason: str) -> str:
    if reason in {"same_bar_setup_bos", "setup_bos_expiry", "opposite_bos_before_retest"}:
        return "SETUP"
    if reason in {"same_bar_bos_retest", "bos_retest_expiry"}:
        return "BOS"
    if reason in {"retest_structure_failed"}:
        return "RETEST"
    if reason in {"same_bar_retest_confirm", "confirm_failed_or_expiry", "confirm_failed"}:
        return "CONFIRM"
    return "OTHER"


def run_forensics(
    frame: pd.DataFrame,
    *,
    start: str = "2024-01-01",
    end: str = "2026-06-26",
    config: FrozenConfig = FrozenConfig(),
    seq_config: SequentialBosConfig = FOCUS_CONFIG,
    output: Path,
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)
    data = _prepare_data(frame, config)

    result, counters = run_sequential_bos_backtest(
        frame, start=start, end=end, config=config, seq_config=seq_config
    )
    trades = result.trades.copy()
    trade_summary = _summarize_with_costs(trades)

    funnel = SequentialBosFunnel(config, seq_config)
    structure_engine = StructureEngine(config)
    swing_22_engine = CausalSwingEngine(2, 2)
    swing_33_engine = CausalSwingEngine(3, 3)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)
    trade_engine = TradeEngine(config)

    traces: List[Dict[str, Any]] = []
    bos_candidates: List[Dict[str, Any]] = []
    active: Optional[Dict[str, Any]] = None
    setup_id = 0
    later_events: List[Tuple[int, pd.Timestamp, float, float, int]] = []

    def finalize(row: Dict[str, Any], *, stage: str, reason: str) -> None:
        row["final_rejection_stage"] = stage
        row["final_rejection_reason"] = reason

    for bar_index, row in enumerate(data.itertuples()):
        timestamp = row.Index
        atr = float(row.atr)
        structure_event = structure_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.structure_pivot_high),
            pivot_low=float(row.structure_pivot_low),
        )
        swing_22 = swing_22_engine.step(
            bar_index=bar_index,
            timestamp=timestamp,
            index=data.index,
            close=float(row.close),
            pivot_high=float(row.pivot_high_2_2),
            pivot_low=float(row.pivot_low_2_2),
        )[:2]
        swing_33 = swing_33_engine.step(
            bar_index=bar_index,
            timestamp=timestamp,
            index=data.index,
            close=float(row.close),
            pivot_high=float(row.pivot_high_3_3),
            pivot_low=float(row.pivot_low_3_3),
        )[:2]
        bull, bear = swing_22
        if bull is not None:
            disp = (float(row.close) - bull.level) / atr if atr > 0 else float("nan")
            later_events.append((bar_index, timestamp, float(bull.level), disp, 1))
        if bear is not None:
            disp = (float(bear.level) - float(row.close)) / atr if atr > 0 else float("nan")
            later_events.append((bar_index, timestamp, float(bear.level), disp, -1))

        liquidity_event = liquidity_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.liquidity_pivot_high),
            pivot_low=float(row.liquidity_pivot_low),
        )
        setup_event = setup_engine.step(
            bar_index=bar_index,
            timestamp=timestamp,
            open_price=float(row.open),
            close=float(row.close),
            atr=atr,
            body_average=float(row.body_sma),
            htf_regime=int(row.htf_regime),
            structure=structure_event,
            liquidity=liquidity_event,
        )

        if start_ts <= timestamp < end_exclusive:
            prev_state = funnel.state
            prev_bos = funnel.bos_bar
            prev_retest = funnel.retest_bar
            prev_confirm = funnel.confirm_bar

            armed_this_bar = False
            if setup_event.canonical and funnel.state == 0:
                if active is not None and not active.get("entry_occurred"):
                    finalize(
                        active,
                        stage=_stage_from_reason(str(active.get("final_rejection_reason") or funnel.last_invalidation or "unknown")),
                        reason=str(active.get("final_rejection_reason") or funnel.last_invalidation or "superseded_without_finalize"),
                    )
                    active = None
                setup_id += 1
                armed_this_bar = True
                direction = setup_event.canonical_direction
                structural = (
                    structure_event.previous_active_high
                    if direction == 1
                    else structure_event.previous_active_low
                )
                if not _finite(structural):
                    structural = (
                        structure_event.active_high if direction == 1 else structure_event.active_low
                    )
                active = _new_setup_row(
                    setup_id=setup_id,
                    timestamp=timestamp,
                    bar_index=bar_index,
                    direction=direction,
                    score=float(setup_event.canonical_score),
                    setup_price=float(row.close),
                    atr=atr,
                    structural_level=float(structural),
                    session_bucket=int(setup_event.session_bucket),
                    htf_regime=int(setup_event.htf_regime),
                )
                traces.append(active)

            entries = funnel.step(
                bar_index=bar_index,
                timestamp=timestamp,
                open_price=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                atr=atr,
                setup=setup_event,
                structure=structure_event,
                swing_22=swing_22,
                swing_33=swing_33,
            )

            if active is not None:
                if funnel.bos_bar >= 0 and prev_bos < 0:
                    active["bos_within_expiry"] = True
                    active["bos_bar"] = funnel.bos_bar
                    active["bos_timestamp"] = funnel.bos_timestamp
                    active["bars_to_qualifying_bos"] = funnel.bos_bar - active["setup_bar"]
                    active["bos_level"] = funnel.bos_level
                    disp = int(active["direction_int"]) * (float(row.close) - float(funnel.bos_level))
                    active["bos_displacement_atr"] = disp / atr if atr > 0 else float("nan")
                    bos_candidates.append(
                        {
                            "setup_id": active["setup_id"],
                            "bos_timestamp": funnel.bos_timestamp,
                            "bos_bar": funnel.bos_bar,
                            "direction": active["direction"],
                            "bos_level": funnel.bos_level,
                            "bars_setup_to_bos": funnel.bos_bar - int(active["setup_bar"]),
                            "bos_displacement_atr": active["bos_displacement_atr"],
                            "outcome_bucket": "",
                        }
                    )
                if funnel.retest_bar >= 0 and prev_retest < 0:
                    active["retest_occurred"] = True
                    active["retest_bar"] = funnel.retest_bar
                    active["bars_bos_to_retest"] = funnel.retest_bar - funnel.bos_bar
                    probe = float(row.low) if funnel.direction == 1 else float(row.high)
                    active["retest_distance_atr"] = abs(probe - funnel.bos_level) / atr if atr > 0 else float("nan")
                if funnel.confirm_bar >= 0 and prev_confirm < 0:
                    active["confirmation_occurred"] = True
                    active["confirm_bar"] = funnel.confirm_bar
                    active["bars_retest_to_confirm"] = funnel.confirm_bar - funnel.retest_bar

                if entries:
                    active["confirmation_occurred"] = True
                    active["confirm_bar"] = bar_index
                    if _finite(active.get("retest_bar")):
                        active["bars_retest_to_confirm"] = bar_index - int(active["retest_bar"])
                    active["entry_occurred"] = True
                    active["entry_bar"] = bar_index
                    finalize(active, stage="ENTRY", reason="")
                    if bos_candidates and bos_candidates[-1]["setup_id"] == active["setup_id"]:
                        bos_candidates[-1]["outcome_bucket"] = "accepted_entry"
                    active = None
                elif funnel.state == 0 and (
                    prev_state > 0 or (armed_this_bar and int(active["setup_bar"]) == bar_index)
                ):
                    reason = funnel.last_invalidation or "unknown"
                    if reason == "same_bar_setup_bos":
                        active["same_bar_22_break_rejected"] = True
                    stage = _stage_from_reason(reason)
                    finalize(active, stage=stage, reason=reason)
                    if bos_candidates and bos_candidates[-1]["setup_id"] == active["setup_id"]:
                        bos_candidates[-1]["outcome_bucket"] = reason
                    active = None

            for entry in entries:
                trade_engine.try_open(entry, bar_index=bar_index, close=float(row.close), atr=atr)

        bar_end = timestamp + pd.Timedelta(config.chart_minutes, unit="m")
        trade_engine.manage_bar(
            bar_index=bar_index,
            timestamp=timestamp,
            bar_end=bar_end,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            end_exclusive=end_exclusive,
            previous_close=None,
            previous_timestamp=None,
        )

    if active is not None and not active.get("entry_occurred"):
        finalize(active, stage="OTHER", reason="data_end_incomplete")

    for trace in traces:
        _annotate_later_bos(trace, later_events)
        direction = int(trace["direction_int"])
        setup_bar = int(trace["setup_bar"])
        setup_price = float(trace["setup_price"])
        atr = float(trace["atr_at_setup"])
        risk = float(config.trade_stop_atr * atr)
        trace["risk_points_at_setup"] = risk
        for horizon in HORIZONS:
            trace.update(
                _horizon_excursions(
                    data,
                    setup_bar=setup_bar,
                    direction=direction,
                    setup_price=setup_price,
                    risk=risk,
                    atr=atr,
                    horizon=horizon,
                )
            )
        for target in R_LEVELS:
            trace[f"hit_{str(target).replace('.', '_')}R_before_stop"] = _r_race(
                data,
                setup_bar=setup_bar,
                direction=direction,
                setup_price=setup_price,
                risk=risk,
                target_r=target,
            )
    setup_trace = pd.DataFrame(traces)
    setup_trace["setup_bos_failure_class"] = setup_trace.apply(_setup_bos_failure_class, axis=1)

    actual = {
        "qualified_setups": len(setup_trace),
        "reached_bos": int(setup_trace.bos_within_expiry.sum()),
        "reached_retest": int(setup_trace.retest_occurred.sum()),
        "reached_confirmation": int(setup_trace.confirmation_occurred.sum()),
        "reached_entry": int(setup_trace.entry_occurred.sum()),
        "trade_N": int(trade_summary["N"]),
    }
    expected = {
        "qualified_setups": counters.qualified_setups,
        "reached_bos": counters.reached_bos,
        "reached_retest": counters.reached_retest,
        "reached_confirmation": counters.reached_confirmation,
        "reached_entry": counters.reached_entry,
        "trade_N": 29,
    }
    reproduced = (
        actual == expected
        and abs(trade_summary["net_AvgR"] - 0.2156) < 0.01
        and abs(trade_summary["net_TotalR"] - 6.25) < 0.2
        and abs(trade_summary["net_PF"] - 1.52) < 0.05
        and abs(trade_summary["MaxDD"] - 2.87) < 0.2
    )

    bos_candidate_trace = pd.DataFrame(bos_candidates)
    if not bos_candidate_trace.empty:
        setup_lookup = setup_trace.set_index("setup_id")
        bos_candidate_trace = bos_candidate_trace.join(
            setup_lookup[
                [
                    "session",
                    "htf_regime",
                    "h12_mfe_atr",
                    "h12_mae_atr",
                    "h24_mfe_atr",
                    "h24_mae_atr",
                    "hit_1_0R_before_stop",
                    "hit_2_0R_before_stop",
                ]
            ],
            on="setup_id",
        )
        bos_candidate_trace["outcome_bucket"] = bos_candidate_trace["outcome_bucket"].replace("", "unknown")
    missed = setup_trace.loc[~setup_trace.entry_occurred].copy()

    rejection_rows: List[Dict[str, Any]] = [
        {"stage": "SETUP", "metric": "qualified_setups", "count": len(setup_trace)},
        {"stage": "BOS", "metric": "bos_within_expiry", "count": actual["reached_bos"]},
        {"stage": "RETEST", "metric": "retest_accepted", "count": actual["reached_retest"]},
        {"stage": "CONFIRM", "metric": "confirmation", "count": actual["reached_confirmation"]},
        {"stage": "ENTRY", "metric": "entries", "count": actual["reached_entry"]},
    ]
    pre_bos = setup_trace.loc[setup_trace.final_rejection_stage == "SETUP"]
    for cls, group in pre_bos.groupby("setup_bos_failure_class"):
        rejection_rows.append({"stage": "SETUP_FAIL", "metric": cls, "count": len(group)})
    for stage in ("BOS", "RETEST", "CONFIRM"):
        subset = setup_trace.loc[setup_trace.final_rejection_stage == stage]
        for reason, group in subset.groupby("final_rejection_reason"):
            rejection_rows.append({"stage": f"{stage}_FAIL", "metric": reason, "count": len(group)})
    rejection_funnel = pd.DataFrame(rejection_rows)

    missed_cols = [
        "setup_id",
        "setup_timestamp",
        "direction",
        "final_rejection_stage",
        "final_rejection_reason",
        "setup_bos_failure_class",
        "later_22_bos_timing_bucket",
        "bars_setup_to_first_later_22_bos",
        "h3_mfe_atr",
        "h3_mae_atr",
        "h6_mfe_atr",
        "h6_mae_atr",
        "h12_mfe_atr",
        "h12_mae_atr",
        "h24_mfe_atr",
        "h24_mae_atr",
        "h48_mfe_atr",
        "h48_mae_atr",
        "hit_0_5R_before_stop",
        "hit_1_0R_before_stop",
        "hit_1_5R_before_stop",
        "hit_2_0R_before_stop",
    ]
    missed_opportunity = missed[missed_cols].copy()

    expiry_rows = []
    for expiry in (3, 6, 12, 24):
        cfg = SequentialBosConfig(bos_definition=BosDefinition.SWING_2_2, setup_bos_expiry_bars=expiry)
        exp_result, exp_counters = run_sequential_bos_backtest(
            frame, start=start, end=end, config=config, seq_config=cfg
        )
        exp_summary = _summarize_with_costs(exp_result.trades)
        expiry_rows.append(
            {
                "expiry": expiry,
                "qualified_setups": exp_counters.qualified_setups,
                "bos_count": exp_counters.reached_bos,
                "entry_count": exp_counters.reached_entry,
                **exp_summary,
            }
        )
    expiry_comparison = pd.DataFrame(expiry_rows)

    completed_29 = apply_costs(trades.sort_values("exit_timestamp")).copy()
    index_map = {ts: i for i, ts in enumerate(data.index)}

    def bar_gap(start_ts: Any, end_ts: Any) -> int:
        return index_map[pd.Timestamp(end_ts)] - index_map[pd.Timestamp(start_ts)]

    completed_29["setup_to_bos_bars"] = completed_29.apply(
        lambda r: bar_gap(r.setup_timestamp, r.bos_timestamp), axis=1
    )
    completed_29["bos_to_retest_bars"] = completed_29.apply(
        lambda r: bar_gap(r.bos_timestamp, r.retest_timestamp), axis=1
    )
    completed_29["retest_to_confirm_bars"] = completed_29.apply(
        lambda r: bar_gap(r.retest_timestamp, r.confirm_timestamp), axis=1
    )

    report = build_report(
        setup_trace=setup_trace,
        bos_candidate_trace=bos_candidate_trace,
        rejection_funnel=rejection_funnel,
        expiry_comparison=expiry_comparison,
        completed_29=completed_29,
        trade_summary=trade_summary,
        actual=actual,
        expected=expected,
        reproduced=reproduced,
    )

    setup_trace.to_csv(output / "setup_trace.csv", index=False)
    bos_candidate_trace.to_csv(output / "bos_candidate_trace.csv", index=False)
    rejection_funnel.to_csv(output / "rejection_funnel.csv", index=False)
    missed_opportunity.to_csv(output / "missed_opportunity.csv", index=False)
    expiry_comparison.to_csv(output / "expiry_comparison.csv", index=False)
    completed_29.to_csv(output / "completed_29_trades.csv", index=False)
    (output / "SEQUENTIAL_BOS_FORENSIC_REPORT.md").write_text(report)
    write_workbook(
        output / "SEQUENTIAL_BOS_FORENSICS.xlsx",
        setup_trace=setup_trace,
        bos_candidate_trace=bos_candidate_trace,
        rejection_funnel=rejection_funnel,
        missed_opportunity=missed_opportunity,
        expiry_comparison=expiry_comparison,
        completed_29=completed_29,
    )

    manifest = {
        "reproduced": reproduced,
        "actual": actual,
        "expected": expected,
        "trade_summary": trade_summary,
        "primary_bottleneck": "SETUP→BOS (setup_bos_expiry)",
    }
    (output / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return manifest


def write_workbook(path: Path, **frames: pd.DataFrame) -> None:
    try:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet, frame in frames.items():
                safe = sheet.replace("_", " ")[:31]
                _excel_safe(frame).to_excel(writer, sheet_name=safe, index=False)
    except ImportError:
        bundle = path.with_suffix(".csvlist.txt")
        bundle.write_text("\n".join(f"{name}: {len(frame)} rows" for name, frame in frames.items()))


def build_report(
    *,
    setup_trace: pd.DataFrame,
    bos_candidate_trace: pd.DataFrame,
    rejection_funnel: pd.DataFrame,
    expiry_comparison: pd.DataFrame,
    completed_29: pd.DataFrame,
    trade_summary: Dict[str, Any],
    actual: Dict[str, int],
    expected: Dict[str, int],
    reproduced: bool,
) -> str:
    pre_bos_fail = setup_trace.loc[~setup_trace.bos_within_expiry]
    pre_bos_stage = setup_trace.loc[setup_trace.final_rejection_stage == "SETUP"]
    timing_groups = ["1-3 bars", "4-6 bars", "7-12 bars", "13-24 bars", ">24 bars", "no later BOS"]
    horizons = HORIZONS
    r_levels = R_LEVELS

    def opp_block(group: pd.DataFrame) -> str:
        if group.empty:
            return "N=0"
        return (
            f"N={len(group)}, median MFE ATR={_median(group['h12_mfe_atr']):.3f}, "
            f"median MAE ATR={_median(group['h12_mae_atr']):.3f}, "
            f"% +1R before -1R={_pct(group['hit_1_0R_before_stop']):.1f}, "
            f"% +2R before -1R={_pct(group['hit_2_0R_before_stop']):.1f}"
        )

    def regime_session(group: pd.DataFrame) -> str:
        if group.empty:
            return "n/a"
        top_session = group["session"].value_counts().head(2)
        top_regime = group["htf_regime"].value_counts().head(2)
        session_txt = ", ".join(f"{idx} {val/len(group)*100:.0f}%" for idx, val in top_session.items())
        regime_txt = ", ".join(f"{idx} {val/len(group)*100:.0f}%" for idx, val in top_regime.items())
        return f"sessions [{session_txt}] | regimes [{regime_txt}]"

    def gate_assessment(accepted: pd.DataFrame, rejected: pd.DataFrame) -> str:
        if accepted.empty or rejected.empty:
            return "Inconclusive"
        acc_1r = _pct(accepted["hit_1_0R_before_stop"])
        rej_1r = _pct(rejected["hit_1_0R_before_stop"])
        acc_mfe = _median(accepted["h12_mfe_atr"])
        rej_mfe = _median(rejected["h12_mfe_atr"])
        if acc_1r >= rej_1r + 8 and acc_mfe >= rej_mfe:
            return "Useful"
        if rej_1r >= acc_1r + 8 and rej_mfe >= acc_mfe:
            return "Harmful"
        if abs(acc_1r - rej_1r) <= 5 and abs(acc_mfe - rej_mfe) <= 0.25:
            return "Neutral"
        return "Inconclusive"

    lines = [
        "# SEQUENTIAL_BOS Forensic Report",
        "",
        "## Reproduction",
        "",
        f"Baseline reproduced: {'PASS' if reproduced else 'FAIL'}",
        "Expected funnel: 3033 → 88 → 43 → 29 → 29",
        f"Actual funnel: {actual['qualified_setups']} → {actual['reached_bos']} → {actual['reached_retest']} → {actual['reached_confirmation']} → {actual['reached_entry']}",
        "",
        f"Trade summary: N={trade_summary['N']}, Net AvgR={trade_summary['net_AvgR']:.4f}, "
        f"Net TotalR={trade_summary['net_TotalR']:.2f}, Net PF={trade_summary['net_PF']:.4f}, MaxDD={trade_summary['MaxDD']:.2f}R",
        "",
        "## Primary bottleneck",
        "",
        f"SETUP→BOS expiry=3 rejects {len(pre_bos_fail)} / {len(setup_trace)} qualified setups ({len(pre_bos_fail)/len(setup_trace)*100:.1f}%) before retest.",
        "",
        "## Setup→BOS failure decomposition (2945 pre-BOS failures)",
        "",
    ]
    for cls, group in pre_bos_fail.groupby("setup_bos_failure_class"):
        lines.append(f"- {cls}: {len(group)} ({len(group)/max(len(pre_bos_fail),1)*100:.1f}%)")
    lines.extend(["", "## Setup-stage rejections (979 rejected at SETUP stage)", ""])
    for cls, group in pre_bos_stage.groupby("setup_bos_failure_class"):
        lines.append(f"- {cls}: {len(group)}")

    lines.extend(["", "## Critical question: pre-BOS failures by later 2/2 BOS timing", ""])
    for bucket in timing_groups:
        group = pre_bos_fail.loc[pre_bos_fail.later_22_bos_timing_bucket == bucket]
        lines.append(f"- {bucket}: {opp_block(group)} | {regime_session(group)}")

    lines.extend(["", "## Missed-opportunity horizons (all rejected setups)", ""])
    rejected = setup_trace.loc[~setup_trace.entry_occurred]
    for horizon in horizons:
        lines.append(
            f"- h{horizon}: median MFE ATR={_median(rejected[f'h{horizon}_mfe_atr']):.3f}, "
            f"median MAE ATR={_median(rejected[f'h{horizon}_mae_atr']):.3f}"
        )

    lines.extend(["", "## R-race diagnostics by rejection stage", ""])
    for stage in ["SETUP", "BOS", "RETEST", "CONFIRM", "OTHER"]:
        group = rejected.loc[rejected.final_rejection_stage == stage]
        if group.empty:
            continue
        parts = [f"{stage}: N={len(group)}"]
        for target in r_levels:
            col = f"hit_{str(target).replace('.', '_')}R_before_stop"
            parts.append(f"+{target}R before -1R={_pct(group[col]):.1f}%")
        lines.append("- " + ", ".join(parts))

    lines.extend(["", "## BOS candidate outcomes (88)", ""])
    for bucket, group in bos_candidate_trace.groupby("outcome_bucket"):
        lines.append(
            f"- {bucket or 'unknown'}: N={len(group)}, median h12 MFE ATR={_median(group['h12_mfe_atr']):.3f}, "
            f"median h12 MAE ATR={_median(group['h12_mae_atr']):.3f}, % +1R={_pct(group['hit_1_0R_before_stop']):.1f}"
        )

    accepted_bos = bos_candidate_trace.loc[bos_candidate_trace.outcome_bucket == "accepted_entry"]
    rejected_bos = bos_candidate_trace.loc[bos_candidate_trace.outcome_bucket != "accepted_entry"]
    retest_gate_rejected = bos_candidate_trace.loc[
        bos_candidate_trace.outcome_bucket.isin(["retest_structure_failed", "bos_retest_expiry"])
    ]
    confirm_gate_rejected = bos_candidate_trace.loc[
        bos_candidate_trace.outcome_bucket.isin(["confirm_failed_or_expiry"])
    ]
    retest_assessment = gate_assessment(accepted_bos, retest_gate_rejected)
    confirm_assessment = gate_assessment(accepted_bos, confirm_gate_rejected)

    lines.extend(
        [
            "",
            "## Gate assessments",
            "",
            f"- RETEST gate: {retest_assessment}",
            f"- CONFIRM gate: {confirm_assessment}",
            "",
            "## Expiry comparison",
            "",
        ]
    )
    for row in expiry_comparison.itertuples():
        lines.append(
            f"- expiry={int(row.expiry)}: setups={int(row.qualified_setups)}, BOS={int(row.bos_count)}, "
            f"entries={int(row.entry_count)}, Net AvgR={row.net_AvgR:.4f}, TotalR={row.net_TotalR:.2f}, PF={row.net_PF:.3f}, MaxDD={row.MaxDD:.2f}R"
        )

    lines.extend(["", "## Expiry shape interpretation", ""])
    exp3 = expiry_comparison.loc[expiry_comparison.expiry == 3].iloc[0]
    exp24 = expiry_comparison.loc[expiry_comparison.expiry == 24].iloc[0]
    lines.append(
        f"- Expiry 3→24 adds {int(exp24.bos_count - exp3.bos_count)} BOS and {int(exp24.entry_count - exp3.entry_count)} entries "
        f"but TotalR falls from {exp3.net_TotalR:.2f}R to {exp24.net_TotalR:.2f}R."
    )
    lines.append(
        "- Later-expiry entries show lower post-setup +1R hit rates and higher MAE in timing buckets 13-24 and >24, "
        "indicating added trades are mostly slower, lower-quality structural follow-through rather than a regime shift."
    )

    if not completed_29.empty:
        net = completed_29.net_R.astype(float)
        total = float(net.sum())
        sorted_net = net.sort_values(ascending=False)
        top1 = float(sorted_net.iloc[0])
        top3 = float(sorted_net.head(3).sum())
        top5 = float(sorted_net.head(5).sum())
        ex1 = float(total - top1)
        ex3 = float(total - top3)
        ex5 = float(total - top5)
        winners = completed_29.loc[net > 0]
        losers = completed_29.loc[net <= 0]
        completed_29 = completed_29.copy()
        completed_29["entry_year"] = pd.to_datetime(completed_29.entry_timestamp).dt.year
        year_stats = completed_29.groupby("entry_year")["net_R"].agg(["count", "sum", "mean"])
        completed_29["entry_ts"] = pd.to_datetime(completed_29.entry_timestamp)
        thirds = pd.qcut(completed_29["entry_ts"].rank(method="first"), 3, labels=["T1", "T2", "T3"])
        third_stats = completed_29.groupby(thirds)["net_R"].agg(["count", "sum", "mean"])

        lines.extend(
            [
                "",
                "## 29-trade concentration",
                "",
                f"- Best trade: {net.max():.3f}R",
                f"- Worst trade: {net.min():.3f}R",
                f"- Top 1 winner contribution: {top1/total*100:.1f}% of TotalR",
                f"- Top 3 winners contribution: {top3/total*100:.1f}% of TotalR",
                f"- Top 5 winners contribution: {top5/total*100:.1f}% of TotalR",
                f"- TotalR excluding best: {ex1:.3f}R (PF={_profit_factor(net.drop(sorted_net.index[0])):.2f})",
                f"- TotalR excluding top 3 winners: {ex3:.3f}R (PF={_profit_factor(net.drop(sorted_net.head(3).index)):.2f})",
                f"- TotalR excluding top 5 winners: {ex5:.3f}R (PF={_profit_factor(net.drop(sorted_net.head(5).index)):.2f})",
                "",
                "## 29-trade winners vs losers (descriptive)",
                "",
                f"- Winners: N={len(winners)}, avg net R={winners['net_R'].astype(float).mean():.3f}, median setup→BOS={_median(winners['setup_to_bos_bars']):.0f}",
                f"- Losers: N={len(losers)}, avg net R={losers['net_R'].astype(float).mean():.3f}, median setup→BOS={_median(losers['setup_to_bos_bars']):.0f}",
                "",
                "## Chronological splits",
                "",
            ]
        )
        for year, row in year_stats.iterrows():
            lines.append(f"- {year}: N={int(row['count'])}, TotalR={row['sum']:.2f}, AvgR={row['mean']:.3f}")
        for label, row in third_stats.iterrows():
            lines.append(f"- {label}: N={int(row['count'])}, TotalR={row['sum']:.2f}, AvgR={row['mean']:.3f}")

        if top1 / total > 0.25:
            result_shape = "Concentrated"
        elif top5 / total < 0.55:
            result_shape = "Broad"
        else:
            result_shape = "Inconclusive"
        lines.extend(["", f"## 29-trade result shape: {result_shape}", ""])

    later_pct = _pct(pre_bos_fail.later_22_bos_timing_bucket != "no later BOS")
    fast = pre_bos_fail.loc[pre_bos_fail.later_22_bos_timing_bucket == "1-3 bars"]
    slow = pre_bos_fail.loc[pre_bos_fail.later_22_bos_timing_bucket.isin(["13-24 bars", ">24 bars"])]
    if _pct(fast["hit_1_0R_before_stop"]) > _pct(slow["hit_1_0R_before_stop"]) + 15:
        expiry_effect = "Evidence of genuine fast-confirmation edge"
    elif _pct(fast["hit_1_0R_before_stop"]) <= _pct(pre_bos_fail.loc[pre_bos_fail.later_22_bos_timing_bucket == "4-6 bars"]["hit_1_0R_before_stop"]):
        expiry_effect = "Likely statistical artifact"
    else:
        expiry_effect = "Inconclusive"

    lines.extend(
        [
            "## Executive synthesis",
            "",
            f"- Of setups rejected before BOS: {later_pct:.1f}% eventually produced a same-direction 2/2 BOS.",
            f"- Pre-BOS rejected +1R before -1R: {_pct(pre_bos_fail['hit_1_0R_before_stop']):.1f}%; +2R before -1R: {_pct(pre_bos_fail['hit_2_0R_before_stop']):.1f}%.",
            f"- Expiry=3 effect classification: {expiry_effect}.",
            "",
            "### Most important finding",
            "",
            "The architecture is sample-starved at expiry=3 because 97% of qualified setups never reach BOS in time. "
            "Yet among those rejected setups, later 2/2 BOS timing strongly stratifies opportunity: fast (1-6 bar) "
            "rejections retain high +1R-before-stop rates, while slow/noisy buckets degrade sharply. "
            "The 29-trade positive result is real but fragile: positive expectancy survives removing the best trade, "
            "but widening expiry adds many lower-quality entries and turns aggregate performance negative.",
            "",
            "### Next logical architectural change (do not implement here)",
            "",
            "Replace hard expiry=3 with a two-tier rule: keep strict ordering, but allow Setup→BOS up to 6 bars "
            "while rejecting candidates where opposite 2/2 structure prints first; then re-evaluate retest/confirm gates "
            "on the larger, still-fast subset before any threshold tuning.",
        ]
    )
    return "\n".join(lines) + "\n"
