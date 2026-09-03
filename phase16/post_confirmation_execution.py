"""Post-confirmation entry execution study for recovered Confirm signals."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .backtest import validation_window
from .config import FrozenConfig
from .metrics import _drawdown
from .recovered_bos_gate_forensics import (
    FOCUS_CONFIG,
    _excel_safe,
    _finite,
    _robustness_rows,
    _summarize_sim,
    apply_sim_costs,
)
from .recovered_retest_structure_forensics import replay_retest_path
from .sequential_bos import _prepare_data, _summarize_with_costs, run_sequential_bos_backtest
from .sequential_bos_ignore_samebar import run_ignore_samebar_backtest
from .trade_archetype_decomposition import NQ_DOLLARS_PER_POINT, ROUND_TURN_COST_USD


LIMIT_WINDOW = 3
EXECUTION_MODELS = (
    "CURRENT",
    "NEXT_BAR_OPEN",
    "CONFIRM_MIDPOINT_50",
    "BOS_LEVEL_PULLBACK",
    "RETEST_CLOSE",
)
RISK_TREATMENTS = ("FROZEN_STOP", "FROZEN_RISK_LOGIC")
LIMIT_MODELS = {"CONFIRM_MIDPOINT_50", "BOS_LEVEL_PULLBACK", "RETEST_CLOSE"}


def current_execution_spec(config: FrozenConfig = FrozenConfig()) -> Dict[str, str]:
    return {
        "signal_known": "End of confirm bar close — confirm condition evaluated on closed bar",
        "entry_timestamp": "Same bar as confirmation (confirm bar timestamp)",
        "entry_bar": "confirm_bar (same bar as confirmation)",
        "entry_price": "Confirm bar close",
        "confirmation_close": "Same as entry_price",
        "entry_equals_confirm_close": "YES",
        "next_bar_information_used": "NO — entry uses only confirm bar OHLC including close",
        "stop_calculation_timestamp": "Confirm bar (ATR at confirm bar)",
        "stop_reference": f"entry_close ± {config.trade_stop_atr} × ATR(confirm bar)",
        "target_calculation": f"entry_close ± {config.trade_target_r}R where R = |entry - stop|",
        "execution_cost": f"${ROUND_TURN_COST_USD:.2f} round-turn / (risk_points × ${NQ_DOLLARS_PER_POINT:.0f}/pt)",
        "lookahead": "ZERO — confirm must close; entry at that close; exits from bar after entry",
        "ambiguous_bar_convention": "STOP checked before TARGET on ambiguous exit bars",
        "same_bar_exit_on_entry_bar": "NO for CURRENT (matches TradeEngine elapsed < 1 rule)",
        "limit_fill_same_bar_exit": "YES — conservative STOP-before-TARGET on limit fill bar",
    }


@dataclass(frozen=True)
class ExecutionResolution:
    filled: bool
    entry_bar: int
    entry_price: float
    bars_waited: int
    cancel_reason: str
    limit_price: Optional[float] = None


def _current_reference_prices(
    data: pd.DataFrame,
    *,
    confirm_bar: int,
    direction: int,
    config: FrozenConfig,
) -> Dict[str, float]:
    row = data.iloc[confirm_bar]
    entry_price = float(row.close)
    atr = float(row.atr) if _finite(row.atr) else 1.0
    risk = config.trade_stop_atr * atr
    stop = entry_price - risk if direction == 1 else entry_price + risk
    target = (
        entry_price + risk * config.trade_target_r
        if direction == 1
        else entry_price - risk * config.trade_target_r
    )
    return {
        "entry_price": entry_price,
        "stop_price": stop,
        "target_price": target,
        "risk_points": risk,
        "confirm_close": entry_price,
        "atr_at_confirm": atr,
    }


def _risk_prices_for_treatment(
    *,
    treatment: str,
    direction: int,
    entry_price: float,
    entry_bar: int,
    data: pd.DataFrame,
    config: FrozenConfig,
    frozen_ref: Dict[str, float],
) -> Optional[Dict[str, float]]:
    if treatment == "FROZEN_STOP":
        stop = float(frozen_ref["stop_price"])
        target = float(frozen_ref["target_price"])
        risk = abs(entry_price - stop)
        if risk <= 0:
            return None
        return {"stop_price": stop, "target_price": target, "risk_points": risk}
    row = data.iloc[entry_bar]
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
    return {"stop_price": stop, "target_price": target, "risk_points": risk}


def resolve_execution_model(
    model: str,
    *,
    data: pd.DataFrame,
    confirm_bar: int,
    retest_bar: int,
    bos_level: float,
    direction: int,
    end_exclusive: pd.Timestamp,
    config: FrozenConfig,
) -> ExecutionResolution:
    if confirm_bar < 0 or confirm_bar >= len(data):
        return ExecutionResolution(False, -1, float("nan"), 0, "invalid_confirm_bar")

    confirm = data.iloc[confirm_bar]
    confirm_ts = data.index[confirm_bar]

    if model == "CURRENT":
        return ExecutionResolution(
            filled=True,
            entry_bar=confirm_bar,
            entry_price=float(confirm.close),
            bars_waited=0,
            cancel_reason="",
        )

    if model == "NEXT_BAR_OPEN":
        entry_bar = confirm_bar + 1
        if entry_bar >= len(data):
            return ExecutionResolution(False, -1, float("nan"), 0, "no_next_bar")
        if data.index[entry_bar] >= end_exclusive:
            return ExecutionResolution(False, -1, float("nan"), 0, "next_bar_outside_window")
        entry_price = float(data.iloc[entry_bar].open)
        atr = float(data.iloc[entry_bar].atr) if _finite(data.iloc[entry_bar].atr) else 1.0
        risk = config.trade_stop_atr * atr
        if risk <= 0:
            return ExecutionResolution(False, -1, float("nan"), 0, "invalid_risk")
        return ExecutionResolution(
            filled=True,
            entry_bar=entry_bar,
            entry_price=entry_price,
            bars_waited=1,
            cancel_reason="",
        )

    if model == "CONFIRM_MIDPOINT_50":
        limit_price = (float(confirm.high) + float(confirm.low)) / 2.0
    elif model == "BOS_LEVEL_PULLBACK":
        limit_price = float(bos_level)
    elif model == "RETEST_CLOSE":
        if retest_bar < 0 or retest_bar >= len(data):
            return ExecutionResolution(False, -1, float("nan"), 0, "invalid_retest_bar")
        limit_price = float(data.iloc[retest_bar].close)
    else:
        raise ValueError(f"Unknown execution model: {model}")

    for offset in range(1, LIMIT_WINDOW + 1):
        pos = confirm_bar + offset
        if pos >= len(data):
            break
        ts = data.index[pos]
        if ts >= end_exclusive:
            break
        bar = data.iloc[pos]
        touched = (
            float(bar.low) <= limit_price
            if direction == 1
            else float(bar.high) >= limit_price
        )
        if touched:
            return ExecutionResolution(
                filled=True,
                entry_bar=pos,
                entry_price=limit_price,
                bars_waited=offset,
                cancel_reason="",
                limit_price=limit_price,
            )
    return ExecutionResolution(
        filled=False,
        entry_bar=-1,
        entry_price=float("nan"),
        bars_waited=LIMIT_WINDOW,
        cancel_reason="limit_not_filled_3_bars",
        limit_price=limit_price,
    )


def simulate_execution_trade(
    data: pd.DataFrame,
    *,
    entry_bar: int,
    entry_price: float,
    direction: int,
    stop_price: float,
    target_price: float,
    risk_points: float,
    config: FrozenConfig,
    end_exclusive: pd.Timestamp,
    check_entry_bar_exit: bool = False,
) -> Optional[Dict[str, Any]]:
    if entry_bar < 0 or entry_bar >= len(data) or risk_points <= 0:
        return None
    max_bars = config.trade_max_bars
    mfe_r = 0.0
    mae_r = 0.0
    start_offset = 0 if check_entry_bar_exit else 1

    for offset in range(start_offset, len(data) - entry_bar):
        pos = entry_bar + offset
        bar = data.iloc[pos]
        ts = data.index[pos]
        bar_end = ts + pd.Timedelta(config.chart_minutes, unit="m")
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)

        if direction == 1:
            mfe_r = max(mfe_r, (high - entry_price) / risk_points)
            mae_r = max(mae_r, (entry_price - low) / risk_points)
        else:
            mfe_r = max(mfe_r, (entry_price - low) / risk_points)
            mae_r = max(mae_r, (high - entry_price) / risk_points)

        if ts >= end_exclusive:
            gross_r = (
                (close - entry_price) / risk_points
                if direction == 1
                else (entry_price - close) / risk_points
            )
            return _trade_result(
                entry_bar,
                entry_price,
                stop_price,
                target_price,
                risk_points,
                direction,
                ts,
                close,
                gross_r,
                "WINDOW_END",
                mfe_r,
                mae_r,
            )

        if direction == 1:
            if low <= stop_price:
                return _trade_result(
                    entry_bar,
                    entry_price,
                    stop_price,
                    target_price,
                    risk_points,
                    direction,
                    ts,
                    stop_price,
                    -1.0,
                    "STOP",
                    mfe_r,
                    mae_r,
                )
            if high >= target_price:
                return _trade_result(
                    entry_bar,
                    entry_price,
                    stop_price,
                    target_price,
                    risk_points,
                    direction,
                    ts,
                    target_price,
                    config.trade_target_r,
                    "TARGET",
                    mfe_r,
                    mae_r,
                )
        else:
            if high >= stop_price:
                return _trade_result(
                    entry_bar,
                    entry_price,
                    stop_price,
                    target_price,
                    risk_points,
                    direction,
                    ts,
                    stop_price,
                    -1.0,
                    "STOP",
                    mfe_r,
                    mae_r,
                )
            if low <= target_price:
                return _trade_result(
                    entry_bar,
                    entry_price,
                    stop_price,
                    target_price,
                    risk_points,
                    direction,
                    ts,
                    target_price,
                    config.trade_target_r,
                    "TARGET",
                    mfe_r,
                    mae_r,
                )

        if offset >= max_bars or bar_end >= end_exclusive:
            gross_r = (
                (close - entry_price) / risk_points
                if direction == 1
                else (entry_price - close) / risk_points
            )
            return _trade_result(
                entry_bar,
                entry_price,
                stop_price,
                target_price,
                risk_points,
                direction,
                ts,
                close,
                gross_r,
                "TIME",
                mfe_r,
                mae_r,
            )
    return None


def _trade_result(
    entry_bar: int,
    entry_price: float,
    stop_price: float,
    target_price: float,
    risk_points: float,
    direction: int,
    exit_ts: pd.Timestamp,
    exit_price: float,
    gross_r: float,
    exit_reason: str,
    mfe_r: float,
    mae_r: float,
) -> Dict[str, Any]:
    return {
        "entry_bar": entry_bar,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "risk_points": risk_points,
        "direction": "Long" if direction == 1 else "Short",
        "exit_timestamp": exit_ts,
        "exit_price": exit_price,
        "gross_R": gross_r,
        "exit_reason": exit_reason,
        "MFE_R": mfe_r,
        "MAE_R": mae_r,
    }


def apply_execution_costs(trades: pd.DataFrame, *, cost_multiplier: float = 1.0) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    working = trades.copy()
    risk_points = (working.entry_price.astype(float) - working.stop_price.astype(float)).abs()
    cost_r = (ROUND_TURN_COST_USD * cost_multiplier) / (risk_points * NQ_DOLLARS_PER_POINT)
    working["gross_R"] = working.gross_R.astype(float)
    working["net_R"] = working.gross_R - cost_r
    working["cost_R"] = cost_r
    return working


def _entry_improvement_points(*, direction: int, current_entry: float, alt_entry: float) -> float:
    if direction == 1:
        return current_entry - alt_entry
    return alt_entry - current_entry


def _summarize_execution(trades: pd.DataFrame, *, eligible: int) -> Dict[str, Any]:
    base = _summarize_sim(trades)
    filled = int(len(trades))
    base["eligible_signals"] = eligible
    base["filled"] = filled
    base["unfilled"] = eligible - filled
    base["fill_rate"] = float(filled / eligible * 100.0) if eligible else 0.0
    if not trades.empty and "bars_waited" in trades.columns:
        base["median_bars_confirm_to_entry"] = float(trades.bars_waited.median())
    else:
        base["median_bars_confirm_to_entry"] = 0.0
    if not trades.empty and "entry_improvement_points" in trades.columns:
        base["mean_entry_improvement_points"] = float(trades.entry_improvement_points.mean())
        base["mean_entry_improvement_atr"] = float(trades.entry_improvement_atr.mean())
    else:
        base["mean_entry_improvement_points"] = 0.0
        base["mean_entry_improvement_atr"] = 0.0
    if not trades.empty and "MFE_R" in trades.columns:
        base["avg_MFE_R"] = float(trades.MFE_R.mean())
        base["avg_MAE_R"] = float(trades.MAE_R.mean())
    else:
        base["avg_MFE_R"] = 0.0
        base["avg_MAE_R"] = 0.0
    return base


def build_confirmed_signals(
    trace: pd.DataFrame,
    data: pd.DataFrame,
    *,
    end_exclusive: pd.Timestamp,
    config: FrozenConfig,
) -> pd.DataFrame:
    entries = trace.loc[trace.final_state == "ENTRY"].copy()
    rows: List[Dict[str, Any]] = []
    for row in entries.itertuples():
        direction = int(row.direction_int)
        bos_bar = int(row.bos_bar)
        bos_level = float(row.bos_level)
        confirm_bar_replay, outcome, _, _ = replay_retest_path(
            data,
            bos_bar=bos_bar,
            bos_level=bos_level,
            direction=direction,
            config=config,
            end_exclusive=end_exclusive,
            reclaim3=False,
        )
        confirm_bar = int(row.confirmation_bar)
        if confirm_bar_replay is not None and confirm_bar_replay != confirm_bar:
            confirm_bar = int(confirm_bar_replay)
        if outcome != "confirm_entry" and confirm_bar_replay is None:
            continue
        ref = _current_reference_prices(
            data, confirm_bar=confirm_bar, direction=direction, config=config
        )
        rows.append(
            {
                "signal_id": int(row.candidate_id),
                "population": "RECOVERED_54",
                "setup_timestamp": row.setup_timestamp,
                "bos_timestamp": row.bos_timestamp,
                "retest_timestamp": row.retest_timestamp,
                "confirm_timestamp": row.confirmation_timestamp,
                "confirm_bar": confirm_bar,
                "retest_bar": int(row.retest_bar),
                "bos_bar": bos_bar,
                "bos_level": bos_level,
                "direction": row.direction,
                "direction_int": direction,
                "confirm_close": ref["confirm_close"],
                "current_entry_price": ref["entry_price"],
                "current_stop_price": ref["stop_price"],
                "current_target_price": ref["target_price"],
                "current_risk_points": ref["risk_points"],
                "atr_at_confirm": ref["atr_at_confirm"],
            }
        )
    return pd.DataFrame(rows)


def run_post_confirmation_execution_study(
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

    gate_dir = output.parent / "recovered_bos_gate_forensics"
    trace_path = gate_dir / "recovered_bos_trace.csv"
    if not trace_path.exists():
        from .recovered_bos_gate_forensics import run_recovered_bos_gate_forensics

        run_recovered_bos_gate_forensics(frame, start=start, end=end, config=config, output=gate_dir)
    trace = pd.read_csv(trace_path)

    baseline_result, _ = run_ignore_samebar_backtest(
        frame, start=start, end=end, config=config, seq_config=FOCUS_CONFIG
    )
    recovered_trades = baseline_result.trades.loc[
        baseline_result.trades.get("recovered_samebar", False) == True
    ].copy()
    baseline_summary = _summarize_with_costs(recovered_trades)

    control_result, _ = run_sequential_bos_backtest(
        frame, start=start, end=end, config=config, seq_config=FOCUS_CONFIG
    )
    control_confirm = control_result.trades.loc[control_result.trades.model == "Confirm"].copy()
    control_summary = _summarize_with_costs(control_confirm)

    reproduced = (
        len(trace) == 158
        and int((trace.final_state == "ENTRY").sum()) == 54
        and baseline_summary["N"] == 54
        and abs(baseline_summary["net_TotalR"] - (-0.93)) < 0.2
        and abs(baseline_summary["net_PF"] - 0.97) < 0.05
        and abs(baseline_summary["MaxDD"] - 8.30) < 0.5
    )
    if not reproduced:
        raise RuntimeError(
            f"Baseline reproduction failed: N={baseline_summary['N']}, "
            f"TotalR={baseline_summary['net_TotalR']:.2f}, PF={baseline_summary['net_PF']:.2f}"
        )

    signals = build_confirmed_signals(trace, data, end_exclusive=end_exclusive, config=config)
    if len(signals) != 54:
        raise RuntimeError(f"Expected 54 confirmed signals, got {len(signals)}")

    trade_rows: List[Dict[str, Any]] = []
    eligible = len(signals)

    for signal in signals.itertuples():
        direction = int(signal.direction_int)
        confirm_bar = int(signal.confirm_bar)
        frozen_ref = {
            "stop_price": float(signal.current_stop_price),
            "target_price": float(signal.current_target_price),
            "entry_price": float(signal.current_entry_price),
            "risk_points": float(signal.current_risk_points),
        }
        current_entry = float(signal.current_entry_price)
        atr_confirm = float(signal.atr_at_confirm)

        for model in EXECUTION_MODELS:
            resolution = resolve_execution_model(
                model,
                data=data,
                confirm_bar=confirm_bar,
                retest_bar=int(signal.retest_bar),
                bos_level=float(signal.bos_level),
                direction=direction,
                end_exclusive=end_exclusive,
                config=config,
            )
            for treatment in RISK_TREATMENTS:
                row: Dict[str, Any] = {
                    "signal_id": int(signal.signal_id),
                    "population": signal.population,
                    "setup_timestamp": signal.setup_timestamp,
                    "bos_timestamp": signal.bos_timestamp,
                    "retest_timestamp": signal.retest_timestamp,
                    "confirm_timestamp": signal.confirm_timestamp,
                    "execution_model": model,
                    "risk_treatment": treatment,
                    "filled": resolution.filled,
                    "bars_waited": resolution.bars_waited,
                    "cancel_reason": resolution.cancel_reason,
                    "limit_price": resolution.limit_price,
                    "confirm_close": float(signal.confirm_close),
                    "direction": signal.direction,
                }
                if not resolution.filled:
                    row.update(
                        {
                            "entry_timestamp": pd.NaT,
                            "entry_bar": pd.NA,
                            "entry_price": float("nan"),
                            "stop_price": float("nan"),
                            "target_price": float("nan"),
                            "risk_points": float("nan"),
                            "entry_improvement_points": float("nan"),
                            "entry_improvement_atr": float("nan"),
                            "gross_R": float("nan"),
                            "net_R": float("nan"),
                            "MFE_R": float("nan"),
                            "MAE_R": float("nan"),
                        }
                    )
                    trade_rows.append(row)
                    continue

                risk_prices = _risk_prices_for_treatment(
                    treatment=treatment,
                    direction=direction,
                    entry_price=resolution.entry_price,
                    entry_bar=resolution.entry_bar,
                    data=data,
                    config=config,
                    frozen_ref=frozen_ref,
                )
                if risk_prices is None:
                    row.update(
                        {
                            "filled": False,
                            "cancel_reason": "invalid_risk_after_entry",
                            "entry_timestamp": pd.NaT,
                            "entry_bar": pd.NA,
                            "entry_price": resolution.entry_price,
                            "stop_price": float("nan"),
                            "target_price": float("nan"),
                            "risk_points": float("nan"),
                            "entry_improvement_points": float("nan"),
                            "entry_improvement_atr": float("nan"),
                            "gross_R": float("nan"),
                            "net_R": float("nan"),
                            "MFE_R": float("nan"),
                            "MAE_R": float("nan"),
                        }
                    )
                    trade_rows.append(row)
                    continue

                check_entry_bar = model in LIMIT_MODELS
                trade = simulate_execution_trade(
                    data,
                    entry_bar=resolution.entry_bar,
                    entry_price=resolution.entry_price,
                    direction=direction,
                    stop_price=risk_prices["stop_price"],
                    target_price=risk_prices["target_price"],
                    risk_points=risk_prices["risk_points"],
                    config=config,
                    end_exclusive=end_exclusive,
                    check_entry_bar_exit=check_entry_bar,
                )
                if trade is None:
                    row["filled"] = False
                    row["cancel_reason"] = "simulation_failed"
                    trade_rows.append(row)
                    continue

                improvement = _entry_improvement_points(
                    direction=direction,
                    current_entry=current_entry,
                    alt_entry=resolution.entry_price,
                )
                row.update(
                    {
                        "entry_timestamp": data.index[resolution.entry_bar],
                        "entry_bar": resolution.entry_bar,
                        "entry_price": resolution.entry_price,
                        "stop_price": risk_prices["stop_price"],
                        "target_price": risk_prices["target_price"],
                        "risk_points": risk_prices["risk_points"],
                        "entry_improvement_points": improvement,
                        "entry_improvement_atr": improvement / atr_confirm if atr_confirm > 0 else float("nan"),
                        **trade,
                    }
                )
                trade_rows.append(row)

    trace_df = pd.DataFrame(trade_rows)
    trace_df = apply_execution_costs(trace_df.loc[trace_df.filled == True].copy())

    summary_rows: List[Dict[str, Any]] = []
    for treatment in RISK_TREATMENTS:
        for model in EXECUTION_MODELS:
            subset = trace_df.loc[
                (trace_df.execution_model == model) & (trace_df.risk_treatment == treatment)
            ]
            summary_rows.append(
                {
                    "execution_model": model,
                    "risk_treatment": treatment,
                    **_summarize_execution(subset, eligible=eligible),
                }
            )
    summary_df = pd.DataFrame(summary_rows)

    primary_treatment = "FROZEN_RISK_LOGIC"
    current_filled = trace_df.loc[
        (trace_df.execution_model == "CURRENT") & (trace_df.risk_treatment == primary_treatment)
    ].copy()
    current_by_signal = current_filled.set_index("signal_id")

    matched_rows: List[Dict[str, Any]] = []
    for model in EXECUTION_MODELS:
        if model == "CURRENT":
            continue
        alt = trace_df.loc[
            (trace_df.execution_model == model) & (trace_df.risk_treatment == primary_treatment)
        ]
        alt_filled = alt.loc[alt.filled == True].set_index("signal_id")
        common_ids = sorted(set(current_by_signal.index) & set(alt_filled.index))
        if not common_ids:
            matched_rows.append(
                {
                    "execution_model": model,
                    "matched_N": 0,
                    "mean_entry_improvement_points": float("nan"),
                    "net_AvgR_delta": float("nan"),
                    "net_TotalR_delta": float("nan"),
                    "net_PF_delta": float("nan"),
                    "MaxDD_delta": float("nan"),
                    "avg_MAE_delta": float("nan"),
                    "avg_MFE_delta": float("nan"),
                }
            )
            continue
        cur = current_by_signal.loc[common_ids]
        alt_m = alt_filled.loc[common_ids]
        matched_rows.append(
            {
                "execution_model": model,
                "matched_N": len(common_ids),
                "mean_entry_improvement_points": float(alt_m.entry_improvement_points.mean()),
                "net_AvgR_delta": float(alt_m.net_R.mean() - cur.net_R.mean()),
                "net_TotalR_delta": float(alt_m.net_R.sum() - cur.net_R.sum()),
                "net_PF_delta": float(
                    _summarize_sim(alt_m)["net_PF"] - _summarize_sim(cur)["net_PF"]
                ),
                "MaxDD_delta": float(
                    _summarize_sim(alt_m)["MaxDD"] - _summarize_sim(cur)["MaxDD"]
                ),
                "avg_MAE_delta": float(alt_m.MAE_R.mean() - cur.MAE_R.mean()),
                "avg_MFE_delta": float(alt_m.MFE_R.mean() - cur.MFE_R.mean()),
            }
        )
    matched_df = pd.DataFrame(matched_rows)

    unfilled_rows: List[Dict[str, Any]] = []
    for model in LIMIT_MODELS:
        alt_all = pd.DataFrame(trade_rows).loc[
            (pd.DataFrame(trade_rows).execution_model == model)
            & (pd.DataFrame(trade_rows).risk_treatment == primary_treatment)
        ]
        unfilled_ids = alt_all.loc[alt_all.filled == False, "signal_id"].tolist()
        cur_subset = current_filled.loc[current_filled.signal_id.isin(unfilled_ids)]
        perf = _summarize_sim(cur_subset)
        unfilled_rows.append(
            {
                "execution_model": model,
                "unfilled_signals": len(unfilled_ids),
                "current_N": perf["N"],
                "current_WR": perf["WR"],
                "current_net_AvgR": perf["net_AvgR"],
                "current_net_TotalR": perf["net_TotalR"],
                "current_net_PF": perf["net_PF"],
            }
        )
    unfilled_df = pd.DataFrame(unfilled_rows)

    adverse_rows: List[Dict[str, Any]] = []
    for model in LIMIT_MODELS:
        alt_all = pd.DataFrame(trade_rows).loc[
            (pd.DataFrame(trade_rows).execution_model == model)
            & (pd.DataFrame(trade_rows).risk_treatment == primary_treatment)
        ]
        filled_ids = alt_all.loc[alt_all.filled == True, "signal_id"].tolist()
        unfilled_ids = alt_all.loc[alt_all.filled == False, "signal_id"].tolist()
        filled_cur = current_filled.loc[current_filled.signal_id.isin(filled_ids)]
        unfilled_cur = current_filled.loc[current_filled.signal_id.isin(unfilled_ids)]
        adverse_rows.append(
            {
                "execution_model": model,
                "limit_filled_current_net_AvgR": float(filled_cur.net_R.mean()) if len(filled_cur) else float("nan"),
                "limit_unfilled_current_net_AvgR": float(unfilled_cur.net_R.mean()) if len(unfilled_cur) else float("nan"),
                "limit_filled_current_net_TotalR": float(filled_cur.net_R.sum()) if len(filled_cur) else float("nan"),
                "limit_unfilled_current_net_TotalR": float(unfilled_cur.net_R.sum()) if len(unfilled_cur) else float("nan"),
                "limit_filled_N": len(filled_cur),
                "limit_unfilled_N": len(unfilled_cur),
            }
        )
    adverse_df = pd.DataFrame(adverse_rows)

    cost_rows: List[Dict[str, Any]] = []
    for multiplier in (1.0, 1.5, 2.0):
        for model in EXECUTION_MODELS:
            raw = pd.DataFrame(trade_rows).loc[
                (pd.DataFrame(trade_rows).execution_model == model)
                & (pd.DataFrame(trade_rows).risk_treatment == primary_treatment)
                & (pd.DataFrame(trade_rows).filled == True)
            ]
            if raw.empty:
                continue
            costed = apply_execution_costs(raw, cost_multiplier=multiplier)
            cost_rows.append(
                {
                    "execution_model": model,
                    "cost_multiplier": multiplier,
                    **_summarize_sim(costed),
                }
            )
    cost_df = pd.DataFrame(cost_rows)

    robustness_rows: List[Dict[str, Any]] = []
    current_perf = _summarize_execution(current_filled, eligible=eligible)
    for model in EXECUTION_MODELS:
        if model == "CURRENT":
            continue
        alt = trace_df.loc[
            (trace_df.execution_model == model) & (trace_df.risk_treatment == primary_treatment)
        ]
        perf = _summarize_execution(alt, eligible=eligible)
        if perf["net_AvgR"] > current_perf["net_AvgR"] and perf["net_PF"] > current_perf["net_PF"]:
            robustness_rows.extend(
                _robustness_rows(alt, config=config, prefix=f"{model.lower()}_")
            )
    robustness_df = pd.DataFrame(robustness_rows)

    verdict = _execution_verdict(
        summary_df=summary_df,
        matched_df=matched_df,
        adverse_df=adverse_df,
        unfilled_df=unfilled_df,
        treatment=primary_treatment,
    )

    full_trade_trace = pd.DataFrame(trade_rows)
    full_trade_trace = pd.concat(
        [
            apply_execution_costs(
                full_trade_trace.loc[full_trade_trace.filled == True].copy()
            ),
            full_trade_trace.loc[full_trade_trace.filled == False].copy(),
        ],
        ignore_index=True,
    )

    report = _build_report(
        spec=current_execution_spec(config),
        reproduced=reproduced,
        baseline_summary=baseline_summary,
        control_summary=control_summary,
        summary_df=summary_df,
        matched_df=matched_df,
        unfilled_df=unfilled_df,
        adverse_df=adverse_df,
        cost_df=cost_df,
        verdict=verdict,
        treatment=primary_treatment,
    )

    full_trade_trace.to_csv(output / "execution_trade_trace.csv", index=False)
    summary_df.to_csv(output / "execution_model_summary.csv", index=False)
    matched_df.to_csv(output / "matched_signal_comparison.csv", index=False)
    unfilled_df.to_csv(output / "unfilled_signal_analysis.csv", index=False)
    cost_df.to_csv(output / "cost_sensitivity.csv", index=False)
    robustness_df.to_csv(output / "robustness.csv", index=False)
    (output / "POST_CONFIRMATION_EXECUTION_REPORT.md").write_text(report)

    with pd.ExcelWriter(output / "POST_CONFIRMATION_EXECUTION.xlsx", engine="openpyxl") as writer:
        for name, df in (
            ("execution_trade_trace", full_trade_trace),
            ("execution_model_summary", summary_df),
            ("matched_signal_comparison", matched_df),
            ("unfilled_signal_analysis", unfilled_df),
            ("cost_sensitivity", cost_df),
            ("robustness", robustness_df),
        ):
            _excel_safe(df).to_excel(writer, sheet_name=name[:31], index=False)

    manifest = {
        "reproduced": reproduced,
        "population": "RECOVERED_54",
        "control_confirm_N": int(control_summary["N"]),
        "control_confirm_net_TotalR": float(control_summary["net_TotalR"]),
        "baseline": baseline_summary,
        "execution_spec": current_execution_spec(config),
        "verdict": verdict,
        "primary_treatment": primary_treatment,
        "summary": summary_df.to_dict(orient="records"),
        "matched": matched_df.to_dict(orient="records"),
    }
    (output / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return manifest


def _execution_verdict(
    *,
    summary_df: pd.DataFrame,
    matched_df: pd.DataFrame,
    adverse_df: pd.DataFrame,
    unfilled_df: pd.DataFrame,
    treatment: str,
) -> Dict[str, Any]:
    current = summary_df.loc[
        (summary_df.execution_model == "CURRENT") & (summary_df.risk_treatment == treatment)
    ].iloc[0]
    best_full = None
    best_full_score = float("-inf")
    best_matched = None
    best_matched_score = float("-inf")

    for model in EXECUTION_MODELS:
        if model == "CURRENT":
            continue
        row = summary_df.loc[
            (summary_df.execution_model == model) & (summary_df.risk_treatment == treatment)
        ].iloc[0]
        score = float(row.net_AvgR)
        if score > best_full_score:
            best_full_score = score
            best_full = model
        matched = matched_df.loc[matched_df.execution_model == model]
        if not matched.empty and matched.iloc[0]["matched_N"] > 0:
            mscore = float(matched.iloc[0]["net_AvgR_delta"])
            if mscore > best_matched_score:
                best_matched_score = mscore
                best_matched = model

    adverse_selection = "INCONCLUSIVE"
    if not adverse_df.empty:
        filled_worse = 0
        for row in adverse_df.itertuples():
            if (
                _finite(row.limit_filled_current_net_AvgR)
                and _finite(row.limit_unfilled_current_net_AvgR)
                and row.limit_filled_current_net_AvgR < row.limit_unfilled_current_net_AvgR
            ):
                filled_worse += 1
        if filled_worse >= 2:
            adverse_selection = "YES"
        elif filled_worse == 0:
            adverse_selection = "NO"

    current_beaten = False
    for model in EXECUTION_MODELS:
        if model == "CURRENT":
            continue
        row = summary_df.loc[
            (summary_df.execution_model == model) & (summary_df.risk_treatment == treatment)
        ].iloc[0]
        matched = matched_df.loc[matched_df.execution_model == model]
        matched_ok = (
            not matched.empty
            and matched.iloc[0]["matched_N"] > 0
            and matched.iloc[0]["net_AvgR_delta"] > 0
            and matched.iloc[0]["net_PF_delta"] > 0
        )
        if (
            row.net_AvgR > current.net_AvgR
            and row.net_PF > current.net_PF
            and row.MaxDD <= current.MaxDD * 1.1
            and matched_ok
        ):
            current_beaten = True
            break

    unfilled_skips_winners = False
    if not unfilled_df.empty:
        for row in unfilled_df.itertuples():
            if row.current_net_TotalR > 2.0 and row.unfilled_signals >= 10:
                unfilled_skips_winners = True
                break

    if current_beaten and not unfilled_skips_winners and adverse_selection != "YES":
        edge = "PROMISING"
        recommendation = best_matched or best_full or "KEEP CURRENT"
    elif current_beaten and (unfilled_skips_winners or adverse_selection == "YES"):
        edge = "WEAK"
        recommendation = "KEEP CURRENT"
    elif best_full_score > current.net_AvgR + 0.02:
        edge = "WEAK"
        recommendation = "KEEP CURRENT"
    else:
        edge = "NONE"
        recommendation = "KEEP CURRENT"

    return {
        "best_full_book": best_full or "CURRENT",
        "best_matched_signal": best_matched or "CURRENT",
        "adverse_selection": adverse_selection,
        "entry_execution_edge": edge,
        "recommended_entry_model": recommendation,
    }


def _build_report(
    *,
    spec: Dict[str, str],
    reproduced: bool,
    baseline_summary: Dict[str, Any],
    control_summary: Dict[str, Any],
    summary_df: pd.DataFrame,
    matched_df: pd.DataFrame,
    unfilled_df: pd.DataFrame,
    adverse_df: pd.DataFrame,
    cost_df: pd.DataFrame,
    verdict: Dict[str, Any],
    treatment: str,
) -> str:
    lines = [
        "# Post-Confirmation Entry Execution Study",
        "",
        f"Baseline reproduced: {'PASS' if reproduced else 'FAIL'}",
        "",
        "## Populations",
        "",
        f"- **Recovered Confirm (primary):** N={baseline_summary['N']}, Net TotalR={baseline_summary['net_TotalR']:.2f}R, PF={baseline_summary['net_PF']:.3f}, MaxDD={baseline_summary['MaxDD']:.2f}R",
        f"- **Sequential control Confirm (reference only):** N={control_summary['N']}, Net TotalR={control_summary['net_TotalR']:.2f}R, PF={control_summary['net_PF']:.3f}",
        "",
        "## Current execution",
        "",
    ]
    for key, value in spec.items():
        lines.append(f"- **{key.replace('_', ' ')}:** {value}")

    lines.extend(["", f"## Model performance ({treatment})", ""])
    for model in EXECUTION_MODELS:
        row = summary_df.loc[
            (summary_df.execution_model == model) & (summary_df.risk_treatment == treatment)
        ].iloc[0]
        lines.append(
            f"- **{model}:** fill={row.fill_rate:.1f}%, N={int(row.N)}, Net AvgR={row.net_AvgR:.4f}, "
            f"TotalR={row.net_TotalR:.2f}, PF={row.net_PF:.3f}, MaxDD={row.MaxDD:.2f}R"
        )

    lines.extend(["", "## Matched-signal comparison", ""])
    for row in matched_df.itertuples():
        lines.append(
            f"- **{row.execution_model}:** matched N={int(row.matched_N)}, AvgR delta={row.net_AvgR_delta:.4f}, "
            f"TotalR delta={row.net_TotalR_delta:.2f}, PF delta={row.net_PF_delta:.3f}"
        )

    lines.extend(["", "## Unfilled signal analysis (CURRENT outcomes)", ""])
    for row in unfilled_df.itertuples():
        lines.append(
            f"- **{row.execution_model}:** unfilled={int(row.unfilled_signals)}, "
            f"CURRENT would-be N={int(row.current_N)}, AvgR={row.current_net_AvgR:.4f}, TotalR={row.current_net_TotalR:.2f}"
        )

    lines.extend(
        [
            "",
            f"**Adverse selection:** {verdict['adverse_selection']}",
            f"**Entry execution edge:** {verdict['entry_execution_edge']}",
            f"**Recommended entry model:** {verdict['recommended_entry_model']}",
        ]
    )
    return "\n".join(lines) + "\n"
