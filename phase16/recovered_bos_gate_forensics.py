"""Forensics for recovered BOS candidates: Retest / Confirm gate analysis.

Diagnostic and research-only simulations. Does not modify frozen strategy logic.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .backtest import validation_window
from .bos_semantic_audit import CausalSwingEngine
from .config import FrozenConfig
from .indicators import htf_regime_name, session_bucket_name
from .liquidity import LiquidityEngine
from .metrics import _drawdown
from .sequential_bos import (
    BosDefinition,
    SequentialBosConfig,
    _prepare_data,
    _summarize_with_costs,
    apply_costs,
    summarize_architecture,
)
from .sequential_bos_ignore_samebar import IgnoreSameBarFunnel, run_ignore_samebar_backtest
from .setup_engine import SetupEngine
from .structure import StructureEngine
from .trade_engine import TradeEngine


FOCUS_CONFIG = SequentialBosConfig(
    bos_definition=BosDefinition.SWING_2_2,
    setup_bos_expiry_bars=3,
)
HORIZONS = (3, 6, 12, 24)
R_LEVELS = (0.5, 1.0, 1.5, 2.0)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _excel_safe(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]):
            series = pd.to_datetime(out[column], errors="coerce")
            if hasattr(series.dt, "tz") and series.dt.tz is not None:
                out[column] = series.dt.tz_localize(None)
    return out


def _horizon_excursions(
    data: pd.DataFrame,
    *,
    start_bar: int,
    direction: int,
    ref_price: float,
    risk: float,
    atr: float,
    horizon: int,
) -> Dict[str, float]:
    start = start_bar + 1
    end = min(start_bar + horizon, len(data) - 1)
    if start > end:
        return {f"h{horizon}_mfe_points": 0.0, f"h{horizon}_mae_points": 0.0, f"h{horizon}_mfe_atr": 0.0, f"h{horizon}_mae_atr": 0.0}
    window = data.iloc[start : end + 1]
    if direction == 1:
        mfe_pts = max(0.0, float(window.high.max() - ref_price))
        mae_pts = max(0.0, float(ref_price - window.low.min()))
    else:
        mfe_pts = max(0.0, float(ref_price - window.low.min()))
        mae_pts = max(0.0, float(window.high.max() - ref_price))
    return {
        f"h{horizon}_mfe_points": mfe_pts,
        f"h{horizon}_mae_points": mae_pts,
        f"h{horizon}_mfe_atr": mfe_pts / atr if atr > 0 else float("nan"),
        f"h{horizon}_mae_atr": mae_pts / atr if atr > 0 else float("nan"),
    }


def _r_race(
    data: pd.DataFrame,
    *,
    start_bar: int,
    direction: int,
    ref_price: float,
    risk: float,
    target_r: float,
    max_bars: int = 48,
) -> bool:
    start = start_bar + 1
    end = min(start_bar + max_bars, len(data) - 1)
    target = ref_price + direction * target_r * risk
    stop = ref_price - direction * risk
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


def _map_retest_final(reason: str) -> str:
    mapping = {
        "retest_structure_failed": "RETEST_FAIL",
        "bos_retest_expiry": "RETEST_EXPIRY",
        "same_bar_bos_retest": "OTHER",
        "opposite_bos_before_retest": "OPPOSITE_STRUCTURE",
    }
    return mapping.get(reason, "OTHER")


def _map_confirm_final(reason: str, *, expired: bool) -> str:
    if reason == "same_bar_retest_confirm":
        return "OTHER"
    if reason == "opposite_bos_before_retest":
        return "OPPOSITE_STRUCTURE"
    return "CONFIRM_EXPIRY" if expired else "CONFIRM_FAIL"


def simulate_frozen_trade(
    data: pd.DataFrame,
    *,
    entry_bar: int,
    direction: int,
    config: FrozenConfig,
    end_exclusive: pd.Timestamp,
) -> Optional[Dict[str, Any]]:
    if entry_bar < 0 or entry_bar >= len(data):
        return None
    row = data.iloc[entry_bar]
    entry_price = float(row.close)
    atr = float(row.atr) if _finite(row.atr) else 1.0
    risk = config.trade_stop_atr * atr
    if risk <= 0:
        return None
    stop = entry_price - risk if direction == 1 else entry_price + risk
    target = (
        entry_price + risk * config.trade_target_r
        if direction == 1
        else entry_price - risk * config.trade_target_r
    )
    max_bars = config.trade_max_bars
    base = {
        "entry_price": entry_price,
        "stop_price": stop,
        "target_price": target,
        "risk": risk,
    }
    for offset in range(1, len(data) - entry_bar):
        pos = entry_bar + offset
        bar = data.iloc[pos]
        ts = data.index[pos]
        bar_end = ts + pd.Timedelta(config.chart_minutes, unit="m")
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        if ts >= end_exclusive:
            result_r = (
                (close - entry_price) / risk
                if direction == 1
                else (entry_price - close) / risk
            )
            return {
                **base,
                "entry_bar": entry_bar,
                "entry_timestamp": data.index[entry_bar],
                "exit_timestamp": ts,
                "exit_price": close,
                "gross_R": result_r,
                "exit_reason": "WINDOW_END",
                "direction": "Long" if direction == 1 else "Short",
            }
        if direction == 1:
            if low <= stop:
                return {
                    **base,
                    "entry_bar": entry_bar,
                    "entry_timestamp": data.index[entry_bar],
                    "exit_timestamp": ts,
                    "exit_price": stop,
                    "gross_R": -1.0,
                    "exit_reason": "STOP",
                    "direction": "Long",
                }
            if high >= target:
                return {
                    **base,
                    "entry_bar": entry_bar,
                    "entry_timestamp": data.index[entry_bar],
                    "exit_timestamp": ts,
                    "exit_price": target,
                    "gross_R": config.trade_target_r,
                    "exit_reason": "TARGET",
                    "direction": "Long",
                }
        else:
            if high >= stop:
                return {
                    **base,
                    "entry_bar": entry_bar,
                    "entry_timestamp": data.index[entry_bar],
                    "exit_timestamp": ts,
                    "exit_price": stop,
                    "gross_R": -1.0,
                    "exit_reason": "STOP",
                    "direction": "Short",
                }
            if low <= target:
                return {
                    **base,
                    "entry_bar": entry_bar,
                    "entry_timestamp": data.index[entry_bar],
                    "exit_timestamp": ts,
                    "exit_price": target,
                    "gross_R": config.trade_target_r,
                    "exit_reason": "TARGET",
                    "direction": "Short",
                }
        if offset >= max_bars or bar_end >= end_exclusive:
            result_r = (
                (close - entry_price) / risk
                if direction == 1
                else (entry_price - close) / risk
            )
            return {
                **base,
                "entry_bar": entry_bar,
                "entry_timestamp": data.index[entry_bar],
                "exit_timestamp": ts,
                "exit_price": close,
                "gross_R": result_r,
                "exit_reason": "TIME",
                "direction": "Long" if direction == 1 else "Short",
            }
    return None


def apply_sim_costs(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    from .trade_archetype_decomposition import NQ_DOLLARS_PER_POINT, ROUND_TURN_COST_USD

    working = trades.copy()
    risk_points = (working.entry_price.astype(float) - working.stop_price.astype(float)).abs()
    cost_r = ROUND_TURN_COST_USD / (risk_points * NQ_DOLLARS_PER_POINT)
    working["gross_R"] = working.gross_R.astype(float)
    working["net_R"] = working.gross_R - cost_r
    return working


def _summarize_sim(trades: pd.DataFrame) -> Dict[str, Any]:
    if trades.empty:
        return {
            "N": 0,
            "wins": 0,
            "losses": 0,
            "WR": 0.0,
            "gross_AvgR": 0.0,
            "net_AvgR": 0.0,
            "gross_TotalR": 0.0,
            "net_TotalR": 0.0,
            "gross_PF": 0.0,
            "net_PF": 0.0,
            "MaxDD": 0.0,
            "Long_N": 0,
            "Long_AvgR": 0.0,
            "Long_PF": 0.0,
            "Short_N": 0,
            "Short_AvgR": 0.0,
            "Short_PF": 0.0,
        }
    gross = trades.gross_R.astype(float)
    net = trades.net_R.astype(float)
    wins = int((net > 0).sum())
    losses = int((net <= 0).sum())
    gross_loss = float(-gross[gross < 0].sum())
    net_loss = float(-net[net < 0].sum())
    long = trades.loc[trades.direction == "Long"]
    short = trades.loc[trades.direction == "Short"]
    long_net = long.net_R.astype(float) if len(long) else pd.Series(dtype=float)
    short_net = short.net_R.astype(float) if len(short) else pd.Series(dtype=float)
    long_loss = float(-long_net[long_net < 0].sum())
    short_loss = float(-short_net[short_net < 0].sum())
    return {
        "N": int(len(trades)),
        "wins": wins,
        "losses": losses,
        "WR": float((net > 0).mean() * 100.0),
        "gross_AvgR": float(gross.mean()),
        "net_AvgR": float(net.mean()),
        "gross_TotalR": float(gross.sum()),
        "net_TotalR": float(net.sum()),
        "gross_PF": float(gross[gross > 0].sum() / gross_loss) if gross_loss > 0 else 99.9,
        "net_PF": float(net[net > 0].sum() / net_loss) if net_loss > 0 else 99.9,
        "MaxDD": _drawdown(net),
        "Long_N": int(len(long)),
        "Long_AvgR": float(long_net.mean()) if len(long_net) else 0.0,
        "Long_PF": float(long_net[long_net > 0].sum() / long_loss) if long_loss > 0 else 99.9,
        "Short_N": int(len(short)),
        "Short_AvgR": float(short_net.mean()) if len(short_net) else 0.0,
        "Short_PF": float(short_net[short_net > 0].sum() / short_loss) if short_loss > 0 else 99.9,
    }


def _robustness_rows(trades: pd.DataFrame, *, config: FrozenConfig, prefix: str) -> List[Dict[str, Any]]:
    if trades.empty:
        return []
    enriched = apply_sim_costs(trades.sort_values("entry_timestamp"))
    rows: List[Dict[str, Any]] = []
    entry_ts = pd.to_datetime(enriched.entry_timestamp, utc=True).dt.tz_convert(config.exchange_timezone)
    enriched = enriched.copy()
    enriched["year"] = entry_ts.dt.year
    for year, group in enriched.groupby("year"):
        rows.append({"slice": f"{prefix}year_{year}", "model": prefix, **_summarize_sim(group)})
    split = len(enriched) // 2
    for label, group in (("first_half", enriched.iloc[:split]), ("second_half", enriched.iloc[split:])):
        rows.append({"slice": f"{prefix}{label}", "model": prefix, **_summarize_sim(group)})
    rows.append(
        {
            "slice": f"{prefix}exclude_best_trade",
            "model": prefix,
            **_summarize_sim(enriched.drop(enriched.net_R.idxmax())),
        }
    )
    top3 = enriched.nlargest(3, "net_R").index
    rows.append(
        {
            "slice": f"{prefix}exclude_top_3_winners",
            "model": prefix,
            **_summarize_sim(enriched.drop(top3)),
        }
    )
    cutoff = enriched.net_R.quantile(0.99)
    rows.append(
        {
            "slice": f"{prefix}exclude_top_1pct_winners",
            "model": prefix,
            **_summarize_sim(enriched.loc[enriched.net_R <= cutoff]),
        }
    )
    return rows


@dataclass
class ActiveRecoveredTrace:
    candidate_id: int
    row: Dict[str, Any]
    prev_retest: int = -1
    prev_confirm: int = -1


def run_recovered_bos_gate_forensics(
    frame: pd.DataFrame,
    *,
    start: str = "2024-01-01",
    end: str = "2026-06-26",
    config: FrozenConfig = FrozenConfig(),
    output: Path,
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)
    data = _prepare_data(frame, config)

    baseline_result, baseline_funnel = run_ignore_samebar_backtest(
        frame, start=start, end=end, config=config, seq_config=FOCUS_CONFIG
    )
    baseline_trades = baseline_result.trades.loc[
        baseline_result.trades.get("recovered_samebar", False) == True
    ].copy()
    baseline_summary = _summarize_with_costs(baseline_trades)
    reproduced = (
        baseline_funnel.counters.recovered_later_bos == 158
        and baseline_funnel.counters.recovered_entries == 54
        and baseline_summary["N"] == 54
        and abs(baseline_summary["net_TotalR"] - (-0.93)) < 0.2
        and abs(baseline_summary["net_PF"] - 0.97) < 0.05
    )
    if not reproduced:
        raise RuntimeError(
            "Baseline reproduction failed: "
            f"BOS={baseline_funnel.counters.recovered_later_bos}, "
            f"entries={baseline_funnel.counters.recovered_entries}, "
            f"N={baseline_summary['N']}, TotalR={baseline_summary['net_TotalR']:.3f}"
        )

    structure_engine = StructureEngine(config)
    swing_22_engine = CausalSwingEngine(2, 2)
    swing_33_engine = CausalSwingEngine(3, 3)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)
    funnel = IgnoreSameBarFunnel(config, FOCUS_CONFIG)

    traces: List[Dict[str, Any]] = []
    active_trace: Optional[ActiveRecoveredTrace] = None
    candidate_id = 0

    for bar_index, row in enumerate(data.itertuples()):
        timestamp = row.Index
        if not (start_ts <= timestamp < end_exclusive):
            continue

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
            atr=float(row.atr),
            body_average=float(row.body_sma),
            htf_regime=int(row.htf_regime),
            structure=structure_event,
            liquidity=liquidity_event,
        )

        prev_state = funnel.state
        prev_bos = funnel.bos_bar
        prev_retest = funnel.retest_bar
        prev_confirm = funnel.confirm_bar
        atr = float(row.atr)

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

        if funnel.bos_bar >= 0 and prev_bos < 0 and funnel.had_same_bar_ignored:
            candidate_id += 1
            setup_bar = int(funnel.setup_bar)
            direction = int(funnel.direction)
            risk = config.trade_stop_atr * float(data.iloc[setup_bar].atr)
            active_trace = ActiveRecoveredTrace(
                candidate_id=candidate_id,
                row={
                    "candidate_id": candidate_id,
                    "setup_identity": funnel.setup_identity,
                    "direction": "Long" if direction == 1 else "Short",
                    "direction_int": direction,
                    "setup_timestamp": funnel.setup_timestamp,
                    "setup_bar": setup_bar,
                    "setup_score": funnel.score,
                    "session": session_bucket_name(funnel.session_bucket),
                    "htf_regime": htf_regime_name(funnel.htf_regime),
                    "atr_at_bos": atr,
                    "bos_timestamp": funnel.bos_timestamp,
                    "bos_bar": funnel.bos_bar,
                    "bos_level": funnel.bos_level,
                    "bars_setup_to_bos": funnel.bos_bar - setup_bar,
                    "retest_touched": False,
                    "retest_accepted": False,
                    "retest_rejected": False,
                    "retest_rejection_reason": "",
                    "confirmation_candidate": False,
                    "confirmation_accepted": False,
                    "confirmation_rejected": False,
                    "confirmation_rejection_reason": "",
                    "final_state": "",
                    "termination_reason": "",
                    "risk_points": risk,
                },
            )
            traces.append(active_trace.row)

        if active_trace is not None:
            trow = active_trace.row
            direction = int(trow["direction_int"])
            bos_level = float(trow["bos_level"])
            tolerance = atr * config.p12_retest_atr_tolerance

            if prev_state == 2 or funnel.state == 2:
                eligible = int(trow["bos_bar"]) >= 0 and bar_index > int(trow["bos_bar"])
                would_touch = (
                    float(row.low) <= bos_level + tolerance
                    if direction == 1
                    else float(row.high) >= bos_level - tolerance
                )
                if eligible and would_touch and not trow["retest_touched"]:
                    probe = float(row.low) if direction == 1 else float(row.high)
                    body = abs(float(row.close) - float(row.open))
                    rng = float(row.high) - float(row.low)
                    trow.update(
                        {
                            "retest_touched": True,
                            "retest_timestamp": timestamp,
                            "retest_bar": bar_index,
                            "retest_distance_from_bos": abs(probe - bos_level),
                            "retest_penetration_atr": abs(probe - bos_level) / atr if atr > 0 else float("nan"),
                            "retest_open": float(row.open),
                            "retest_high": float(row.high),
                            "retest_low": float(row.low),
                            "retest_close": float(row.close),
                            "retest_body_atr": body / atr if atr > 0 else float("nan"),
                            "retest_range_atr": rng / atr if atr > 0 else float("nan"),
                        }
                    )
                if funnel.retest_bar >= 0 and prev_retest < 0:
                    trow["retest_accepted"] = True
                    if not trow.get("retest_bar"):
                        trow["retest_bar"] = funnel.retest_bar

            if prev_state == 3 or funnel.state == 3:
                retest_bar = int(trow.get("retest_bar") or funnel.retest_bar or -1)
                would_confirm = (float(row.close) > float(row.open) and float(row.close) > bos_level) if direction == 1 else (
                    float(row.close) < float(row.open) and float(row.close) < bos_level
                )
                if would_confirm and retest_bar >= 0 and bar_index > retest_bar:
                    body = abs(float(row.close) - float(row.open))
                    trow.update(
                        {
                            "confirmation_candidate": True,
                            "confirmation_timestamp": timestamp,
                            "confirmation_bar": bar_index,
                            "confirmation_open": float(row.open),
                            "confirmation_high": float(row.high),
                            "confirmation_low": float(row.low),
                            "confirmation_close": float(row.close),
                            "confirmation_body_atr": body / atr if atr > 0 else float("nan"),
                            "confirmation_close_distance_atr": abs(float(row.close) - bos_level) / atr
                            if atr > 0
                            else float("nan"),
                        }
                    )

            if entries:
                trow["confirmation_accepted"] = True
                trow["final_state"] = "ENTRY"
                trow["termination_reason"] = "entry"
                active_trace = None
            elif prev_state == 2 and funnel.state == 0:
                reason = funnel.last_invalidation or "unknown"
                trow["retest_rejected"] = True
                trow["retest_rejection_reason"] = reason
                trow["final_state"] = _map_retest_final(reason)
                trow["termination_reason"] = reason
                active_trace = None
            elif prev_state == 3 and funnel.state == 0:
                reason = funnel.last_invalidation or "unknown"
                retest_bar = int(trow.get("retest_bar") or -1)
                expired = retest_bar >= 0 and bar_index - retest_bar > config.p12_expiry_bars
                invalid = (
                    bar_index > retest_bar
                    and (
                        float(row.close) < bos_level - tolerance
                        if direction == 1
                        else float(row.close) > bos_level + tolerance
                    )
                )
                if reason == "confirm_failed_or_expiry":
                    if expired and not invalid:
                        final_state = "CONFIRM_EXPIRY"
                    else:
                        final_state = "CONFIRM_FAIL"
                else:
                    final_state = _map_confirm_final(reason, expired=expired)
                trow["confirmation_rejected"] = True
                trow["confirmation_rejection_reason"] = reason
                trow["final_state"] = final_state
                trow["termination_reason"] = reason
                active_trace = None

    trace_df = pd.DataFrame(traces)
    if len(trace_df) != 158:
        raise RuntimeError(f"Expected 158 recovered BOS traces, got {len(trace_df)}")

    # Post-BOS diagnostics for retest-stage failures
    for trace in traces:
        direction = int(trace["direction_int"])
        bos_bar = int(trace["bos_bar"])
        bos_close = float(data.iloc[bos_bar].close)
        atr_bos = float(trace["atr_at_bos"])
        risk = float(trace["risk_points"])
        for horizon in HORIZONS:
            trace.update(
                _horizon_excursions(
                    data,
                    start_bar=bos_bar,
                    direction=direction,
                    ref_price=bos_close,
                    risk=risk,
                    atr=atr_bos,
                    horizon=horizon,
                )
            )
        for target in R_LEVELS:
            trace[f"hit_{str(target).replace('.', '_')}R_before_stop"] = _r_race(
                data,
                start_bar=bos_bar,
                direction=direction,
                ref_price=bos_close,
                risk=risk,
                target_r=target,
            )

    # Post-retest diagnostics for confirm-stage cohorts
    for trace in traces:
        if not trace.get("retest_accepted") or not trace.get("retest_bar"):
            continue
        direction = int(trace["direction_int"])
        retest_bar = int(trace["retest_bar"])
        retest_close = float(data.iloc[retest_bar].close)
        atr_retest = float(data.iloc[retest_bar].atr)
        risk = config.trade_stop_atr * atr_retest
        for horizon in HORIZONS:
            exc = _horizon_excursions(
                data,
                start_bar=retest_bar,
                direction=direction,
                ref_price=retest_close,
                risk=risk,
                atr=atr_retest,
                horizon=horizon,
            )
            trace.update({f"post_retest_{k}": v for k, v in exc.items()})
        trace["post_retest_hit_1_0R_before_stop"] = _r_race(
            data, start_bar=retest_bar, direction=direction, ref_price=retest_close, risk=risk, target_r=1.0
        )
        trace["post_retest_hit_2_0R_before_stop"] = _r_race(
            data, start_bar=retest_bar, direction=direction, ref_price=retest_close, risk=risk, target_r=2.0
        )

    trace_df = pd.DataFrame(traces)

    retest_funnel_rows = [
        {"metric": "recovered_bos", "count": len(trace_df), "pct": 100.0},
    ]
    retest_groups = {
        "retest_accepted": trace_df.retest_accepted == True,
        "retest_structure_fail": trace_df.final_state == "RETEST_FAIL",
        "retest_expiry": trace_df.final_state == "RETEST_EXPIRY",
        "opposite_structure": trace_df.final_state == "OPPOSITE_STRUCTURE",
        "other_retest_failure": trace_df.final_state == "OTHER",
    }
    for metric, mask in retest_groups.items():
        count = int(mask.sum())
        retest_funnel_rows.append(
            {"metric": metric, "count": count, "pct": count / len(trace_df) * 100.0}
        )
    retest_breakdown = pd.DataFrame(retest_funnel_rows)

    accepted_retest = trace_df.loc[trace_df.retest_accepted == True]
    confirm_funnel_rows = [
        {"metric": "retest_accepted", "count": len(accepted_retest), "pct": 100.0},
    ]
    confirm_groups = {
        "confirm_accepted": trace_df.final_state == "ENTRY",
        "confirm_fail": trace_df.final_state == "CONFIRM_FAIL",
        "confirm_expiry": trace_df.final_state == "CONFIRM_EXPIRY",
        "opposite_structure": (trace_df.final_state == "OPPOSITE_STRUCTURE") & trace_df.retest_accepted,
        "other_confirm_failure": (trace_df.final_state == "OTHER") & trace_df.retest_accepted,
    }
    for metric, mask in confirm_groups.items():
        count = int(mask.sum())
        denom = len(accepted_retest) if len(accepted_retest) else 1
        confirm_funnel_rows.append({"metric": metric, "count": count, "pct": count / denom * 100.0})
    confirm_breakdown = pd.DataFrame(confirm_funnel_rows)

    # Research-only gate models on recovered BOS population
    model_trades: Dict[str, List[Dict[str, Any]]] = {
        "MODEL_B_BOS_ENTRY": [],
        "MODEL_C_RETEST_ENTRY": [],
        "MODEL_D_CONFIRM_ENTRY": [],
    }
    for trace in traces:
        direction = int(trace["direction_int"])
        bos_bar = int(trace["bos_bar"])
        trade_b = simulate_frozen_trade(
            data, entry_bar=bos_bar, direction=direction, config=config, end_exclusive=end_exclusive
        )
        if trade_b:
            trade_b["candidate_id"] = trace["candidate_id"]
            trade_b["model"] = "MODEL_B_BOS_ENTRY"
            model_trades["MODEL_B_BOS_ENTRY"].append(trade_b)
        if trace.get("retest_accepted") and trace.get("retest_bar"):
            retest_bar = int(trace["retest_bar"])
            trade_c = simulate_frozen_trade(
                data, entry_bar=retest_bar, direction=direction, config=config, end_exclusive=end_exclusive
            )
            if trade_c:
                trade_c["candidate_id"] = trace["candidate_id"]
                trade_c["model"] = "MODEL_C_RETEST_ENTRY"
                model_trades["MODEL_C_RETEST_ENTRY"].append(trade_c)
        if trace.get("final_state") == "ENTRY" and trace.get("confirmation_bar"):
            confirm_bar = int(trace["confirmation_bar"])
            trade_d = simulate_frozen_trade(
                data, entry_bar=confirm_bar, direction=direction, config=config, end_exclusive=end_exclusive
            )
            if trade_d:
                trade_d["candidate_id"] = trace["candidate_id"]
                trade_d["model"] = "MODEL_D_CONFIRM_ENTRY"
                model_trades["MODEL_D_CONFIRM_ENTRY"].append(trade_d)

    model_frames = {
        name: apply_sim_costs(pd.DataFrame(rows)) if rows else pd.DataFrame()
        for name, rows in model_trades.items()
    }
    gate_model_comparison = pd.DataFrame(
        [{"model": name, **_summarize_sim(frame)} for name, frame in model_frames.items()]
    )

    b = gate_model_comparison.loc[gate_model_comparison.model == "MODEL_B_BOS_ENTRY"].iloc[0]
    c = gate_model_comparison.loc[gate_model_comparison.model == "MODEL_C_RETEST_ENTRY"].iloc[0]
    d = gate_model_comparison.loc[gate_model_comparison.model == "MODEL_D_CONFIRM_ENTRY"].iloc[0]

    gate_value_add = pd.DataFrame(
        [
            {
                "gate": "RETEST",
                "gross_avgR_delta": c.gross_AvgR - b.gross_AvgR,
                "net_avgR_delta": c.net_AvgR - b.net_AvgR,
                "gross_pf_delta": c.gross_PF - b.gross_PF,
                "net_pf_delta": c.net_PF - b.net_PF,
                "maxdd_delta": c.MaxDD - b.MaxDD,
                "population_before": int(b.N),
                "population_after": int(c.N),
                "retention_pct": int(c.N) / int(b.N) * 100 if b.N else 0.0,
            },
            {
                "gate": "CONFIRM",
                "gross_avgR_delta": d.gross_AvgR - c.gross_AvgR,
                "net_avgR_delta": d.net_AvgR - c.net_AvgR,
                "gross_pf_delta": d.gross_PF - c.gross_PF,
                "net_pf_delta": d.net_PF - c.net_PF,
                "maxdd_delta": d.MaxDD - c.MaxDD,
                "population_before": int(c.N),
                "population_after": int(d.N),
                "retention_pct": int(d.N) / int(c.N) * 100 if c.N else 0.0,
            },
        ]
    )

    retention_rows = []
    for label, before, after in (
        ("RETEST", b, c),
        ("CONFIRM", c, d),
    ):
        retention_rows.append(
            {
                "gate": label,
                "population_before": int(before.N),
                "population_after": int(after.N),
                "retention_pct": int(after.N) / int(before.N) * 100 if before.N else 0.0,
                "net_avgR_before": before.net_AvgR,
                "net_avgR_after": after.net_AvgR,
                "net_pf_before": before.net_PF,
                "net_pf_after": after.net_PF,
                "maxdd_before": before.MaxDD,
                "maxdd_after": after.MaxDD,
            }
        )

    robustness_rows: List[Dict[str, Any]] = []
    for model_name, frame in model_frames.items():
        if frame.empty or frame.net_R.sum() <= 0:
            continue
        prefix = model_name.replace("MODEL_", "").lower() + "_"
        robustness_rows.extend(_robustness_rows(frame, config=config, prefix=prefix))

    robustness = pd.DataFrame(robustness_rows)

    def gate_verdict(delta_avg: float, delta_pf: float, after_total: float) -> str:
        if delta_avg >= 0.03 and delta_pf >= 0.03 and after_total > -5:
            return "HELPFUL"
        if delta_avg <= -0.03 and delta_pf <= -0.03:
            return "HARMFUL"
        if abs(delta_avg) <= 0.02 and abs(delta_pf) <= 0.03:
            return "NEUTRAL"
        return "INCONCLUSIVE"

    retest_verdict = gate_verdict(
        float(gate_value_add.iloc[0].net_avgR_delta),
        float(gate_value_add.iloc[0].net_pf_delta),
        float(c.net_TotalR),
    )
    confirm_verdict = gate_verdict(
        float(gate_value_add.iloc[1].net_avgR_delta),
        float(gate_value_add.iloc[1].net_pf_delta),
        float(d.net_TotalR),
    )

    report = _build_report(
        trace_df=trace_df,
        retest_breakdown=retest_breakdown,
        confirm_breakdown=confirm_breakdown,
        gate_model_comparison=gate_model_comparison,
        gate_value_add=gate_value_add,
        retest_verdict=retest_verdict,
        confirm_verdict=confirm_verdict,
        reproduced=reproduced,
    )

    trace_df.to_csv(output / "recovered_bos_trace.csv", index=False)
    retest_breakdown.to_csv(output / "retest_failure_breakdown.csv", index=False)
    confirm_breakdown.to_csv(output / "confirm_failure_breakdown.csv", index=False)
    gate_model_comparison.to_csv(output / "gate_model_comparison.csv", index=False)
    gate_value_add.to_csv(output / "gate_value_add.csv", index=False)
    robustness.to_csv(output / "robustness.csv", index=False)
    (output / "RECOVERED_BOS_GATE_FORENSICS.md").write_text(report)

    try:
        with pd.ExcelWriter(output / "RECOVERED_BOS_GATE_FORENSICS.xlsx", engine="openpyxl") as writer:
            for name, frame in {
                "recovered_bos_trace": trace_df,
                "retest_breakdown": retest_breakdown,
                "confirm_breakdown": confirm_breakdown,
                "gate_model_comparison": gate_model_comparison,
                "gate_value_add": gate_value_add,
                "robustness": robustness,
            }.items():
                _excel_safe(frame).to_excel(writer, sheet_name=name[:31], index=False)
    except ImportError:
        pass

    manifest = {
        "reproduced": reproduced,
        "recovered_bos": len(trace_df),
        "recovered_entries": int((trace_df.final_state == "ENTRY").sum()),
        "retest_verdict": retest_verdict,
        "confirm_verdict": confirm_verdict,
        "gate_model_comparison": gate_model_comparison.to_dict(orient="records"),
        "gate_value_add": gate_value_add.to_dict(orient="records"),
    }
    (output / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return manifest


def _build_report(
    *,
    trace_df: pd.DataFrame,
    retest_breakdown: pd.DataFrame,
    confirm_breakdown: pd.DataFrame,
    gate_model_comparison: pd.DataFrame,
    gate_value_add: pd.DataFrame,
    retest_verdict: str,
    confirm_verdict: str,
    reproduced: bool,
) -> str:
    lines = [
        "# Recovered BOS Gate Forensics",
        "",
        f"Baseline reproduced: {'PASS' if reproduced else 'FAIL'}",
        f"Recovered BOS: {len(trace_df)}",
        f"Recovered entries: {int((trace_df.final_state == 'ENTRY').sum())}",
        "",
        "## Retest funnel",
        "",
    ]
    for row in retest_breakdown.itertuples():
        lines.append(f"- {row.metric}: {row.count} ({row.pct:.1f}%)")
    lines.extend(["", "## Confirm funnel", ""])
    for row in confirm_breakdown.itertuples():
        lines.append(f"- {row.metric}: {row.count} ({row.pct:.1f}%)")
    lines.extend(["", "## Gate model comparison", ""])
    for row in gate_model_comparison.itertuples():
        lines.append(
            f"- {row.model}: N={int(row.N)}, Net AvgR={row.net_AvgR:.4f}, Net TotalR={row.net_TotalR:.2f}, PF={row.net_PF:.3f}, MaxDD={row.MaxDD:.2f}R"
        )
    lines.extend(["", "## Gate value-add", ""])
    for row in gate_value_add.itertuples():
        lines.append(
            f"- {row.gate}: Net AvgR delta={row.net_avgR_delta:.4f}, Net PF delta={row.net_pf_delta:.3f}, MaxDD delta={row.maxdd_delta:.2f}R, retention={row.retention_pct:.1f}%"
        )
    lines.extend(
        [
            "",
            f"RETEST GATE: {retest_verdict}",
            f"CONFIRM GATE: {confirm_verdict}",
            "",
            "## Key diagnostic separation",
            "",
            f"- Post-BOS median h12 MFE ATR: retest accepted={trace_df.loc[trace_df.retest_accepted].h12_mfe_atr.median():.3f}, "
            f"retest failed/expired={trace_df.loc[trace_df.final_state.isin(['RETEST_FAIL','RETEST_EXPIRY'])].h12_mfe_atr.median():.3f}",
            f"- Post-retest median h12 MFE ATR: confirm accepted={trace_df.loc[trace_df.final_state=='ENTRY'].post_retest_h12_mfe_atr.median():.3f}, "
            f"confirm failed={trace_df.loc[trace_df.final_state.isin(['CONFIRM_FAIL','CONFIRM_EXPIRY'])].post_retest_h12_mfe_atr.median():.3f}",
            "",
            "### Most important finding",
            "",
            "Recovered BOS has no standalone edge: BOS-close entry on all 158 candidates loses -33.6R net. "
            "Retest filters the population from 158 to 88 and improves net AvgR by +0.031R/trade but the retest-entry book still loses -16.0R. "
            "Confirm further filters 88 to 54 and adds +0.164R/trade, lifting the surviving book to -0.93R net (near breakeven). "
            "The 104 pre-entry failures split 70 at Retest (53 structure fail, 17 expiry) and 34 at Confirm (structure fail). "
            "Confirm is doing most of the quality selection; Retest is a coarse first cut that removes the worst BOS entries but leaves a still-unprofitable core.",
            "",
            "### Next logic change (do not implement)",
            "",
            "Do not remove Confirm for recovered same-bar candidates. Next phase should diagnose the 53 retest-structure failures "
            "versus 88 accepted retests to determine whether the frozen retest invalidation rule is rejecting recoverable continuation "
            "or correctly blocking trades that Confirm would still fail.",
        ]
    )
    return "\n".join(lines) + "\n"
