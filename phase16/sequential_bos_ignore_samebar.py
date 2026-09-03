"""Experimental SEQUENTIAL_BOS variant: ignore same-bar BOS, keep setup armed."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .backtest import BacktestResult, TRADE_COLUMNS, run_backtest, validation_window
from .bos_semantic_audit import CausalSwingEngine, SwingBreak
from .config import FrozenConfig
from .liquidity import LiquidityEngine
from .models import EntryEvent, SetupEvent, StructureEvent
from .sequential_bos import (
    BosDefinition,
    FunnelCounters,
    SequentialBosConfig,
    SETUP_BOS_EXPIRY_OPTIONS,
    _prepare_data,
    _summarize_with_costs,
    apply_costs,
    assert_strict_order,
    run_sequential_bos_backtest,
    summarize_architecture,
    verify_completed_trade_ordering,
    verify_retest_gated_parity,
)
from .sequential_bos import SequentialBosFunnel as ControlSequentialBosFunnel
from .setup_engine import SetupEngine
from .structure import StructureEngine
from .trade_engine import TradeEngine


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


@dataclass
class IgnoreSameBarFunnelCounters(FunnelCounters):
    same_bar_bos_ignored: int = 0
    same_bar_hard_invalidations: int = 0
    recovered_setups: int = 0
    recovered_later_bos: int = 0
    recovered_retest: int = 0
    recovered_confirm: int = 0
    recovered_entries: int = 0
    stale_setup_bar_bos_reuse: int = 0
    candidate_collisions: List[str] = field(default_factory=list)

    def export(self) -> Dict[str, Any]:
        base = super().export()
        base.update(
            {
                "same_bar_bos_ignored": self.same_bar_bos_ignored,
                "same_bar_hard_invalidations": self.same_bar_hard_invalidations,
                "recovered_setups": self.recovered_setups,
                "recovered_later_bos": self.recovered_later_bos,
                "recovered_retest": self.recovered_retest,
                "recovered_confirm": self.recovered_confirm,
                "recovered_entries": self.recovered_entries,
                "stale_setup_bar_bos_reuse": self.stale_setup_bar_bos_reuse,
                "candidate_collisions": list(self.candidate_collisions),
            }
        )
        return base


@dataclass
class IgnoreSameBarFunnel(ControlSequentialBosFunnel):
    counters: IgnoreSameBarFunnelCounters = field(default_factory=IgnoreSameBarFunnelCounters)
    had_same_bar_ignored: bool = False
    ignored_samebar_swing_bar: int = -1
    ignored_samebar_swing_level: float = float("nan")
    ignored_samebar_pivot_bar: int = -1
    setup_identity: int = 0
    recovered_candidate_rows: List[Dict[str, Any]] = field(default_factory=list)
    entry_audit_rows: List[Dict[str, Any]] = field(default_factory=list)
    _recovered_progress: Dict[str, bool] = field(default_factory=dict)

    def _reset(self, reason: str = "") -> None:
        if reason == "same_bar_setup_bos":
            self.counters.same_bar_hard_invalidations += 1
            raise AssertionError("ignore-and-wait funnel must not hard-reset on same_bar_setup_bos")
        self._recovered_progress = {}
        super()._reset(reason)

    def _setup_direction_swing(
        self,
        swing_22: tuple[Optional[SwingBreak], Optional[SwingBreak]],
        swing_33: tuple[Optional[SwingBreak], Optional[SwingBreak]],
    ) -> Optional[SwingBreak]:
        definition = self.seq_config.bos_definition
        if definition == BosDefinition.SWING_2_2:
            bull, bear = swing_22
            return bull if self.direction == 1 else bear
        if definition == BosDefinition.SWING_3_3:
            bull, bear = swing_33
            return bull if self.direction == 1 else bear
        return None

    def _same_bar_qualifying_bos(
        self,
        *,
        bar_index: int,
        structure: StructureEvent,
        swing_22: tuple[Optional[SwingBreak], Optional[SwingBreak]],
        swing_33: tuple[Optional[SwingBreak], Optional[SwingBreak]],
    ) -> tuple[bool, Optional[SwingBreak]]:
        if bar_index != self.setup_bar:
            return False, None
        same_bar_structure = (self.direction == 1 and structure.bull_bos) or (
            self.direction == -1 and structure.bear_bos
        )
        swing = self._setup_direction_swing(swing_22, swing_33)
        same_bar_swing = swing is not None and swing.bar_index == bar_index
        if self.seq_config.bos_definition in {BosDefinition.SWING_2_2, BosDefinition.SWING_3_3}:
            return same_bar_swing or same_bar_structure, swing
        return same_bar_structure, None

    def _ignore_same_bar_bos(self, *, bar_index: int, swing: Optional[SwingBreak]) -> None:
        self.counters.same_bar_bos_ignored += 1
        self.had_same_bar_ignored = True
        self.counters.recovered_setups += 1
        if swing is not None:
            self.ignored_samebar_swing_bar = swing.bar_index
            self.ignored_samebar_swing_level = float(swing.level)
            self.ignored_samebar_pivot_bar = int(swing.pivot_bar)
        self.recovered_candidate_rows.append(
            {
                "setup_identity": self.setup_identity,
                "setup_bar": self.setup_bar,
                "setup_timestamp": self.setup_timestamp,
                "direction": "Long" if self.direction == 1 else "Short",
                "ignored_on_bar": bar_index,
                "ignored_swing_level": self.ignored_samebar_swing_level,
                "ignored_pivot_bar": self.ignored_samebar_pivot_bar,
                "later_bos": False,
                "later_retest": False,
                "later_confirm": False,
                "later_entry": False,
            }
        )

    def _mark_recovered(self, key: str, **kwargs: Any) -> None:
        if not self.had_same_bar_ignored or self._recovered_progress.get(key):
            return
        self._recovered_progress[key] = True
        if not self.recovered_candidate_rows:
            return
        self.recovered_candidate_rows[-1].update(kwargs)
        counter_map = {
            "later_bos": "recovered_later_bos",
            "later_retest": "recovered_retest",
            "later_confirm": "recovered_confirm",
            "later_entry": "recovered_entries",
        }
        if key in counter_map:
            setattr(self.counters, counter_map[key], getattr(self.counters, counter_map[key]) + 1)

    def _record_entry_audit(self, *, bar_index: int, timestamp: pd.Timestamp) -> None:
        stale = self.bos_bar <= self.setup_bar or (
            _finite(self.ignored_samebar_swing_level)
            and _finite(self.bos_level)
            and self.bos_bar == self.ignored_samebar_swing_bar
            and float(self.bos_level) == float(self.ignored_samebar_swing_level)
        )
        if stale:
            self.counters.stale_setup_bar_bos_reuse += 1
        self.entry_audit_rows.append(
            {
                "setup_identity": self.setup_identity,
                "setup_bar": self.setup_bar,
                "bos_bar": self.bos_bar,
                "retest_bar": self.retest_bar,
                "confirm_bar": self.confirm_bar,
                "entry_bar": bar_index,
                "entry_timestamp": timestamp,
                "recovered_samebar": self.had_same_bar_ignored,
                "ignored_samebar_swing_bar": self.ignored_samebar_swing_bar,
                "ignored_samebar_swing_level": self.ignored_samebar_swing_level,
                "bos_level": self.bos_level,
                "stale_setup_bar_bos_reuse": stale,
            }
        )

    def step(
        self,
        *,
        bar_index: int,
        timestamp: pd.Timestamp,
        open_price: float,
        high: float,
        low: float,
        close: float,
        atr: float,
        setup: SetupEvent,
        structure: StructureEvent,
        swing_22: tuple[Optional[SwingBreak], Optional[SwingBreak]],
        swing_33: tuple[Optional[SwingBreak], Optional[SwingBreak]],
    ) -> List[EntryEvent]:
        entries: List[EntryEvent] = []

        if setup.canonical and self.state == 0:
            self.setup_identity += 1
            self.had_same_bar_ignored = False
            self.ignored_samebar_swing_bar = -1
            self.ignored_samebar_swing_level = float("nan")
            self.ignored_samebar_pivot_bar = -1
            self._recovered_progress = {}
            self.state = 1
            self.direction = setup.canonical_direction
            self.setup_bar = bar_index
            self.bos_bar = -1
            self.retest_bar = -1
            self.confirm_bar = -1
            self.score = setup.canonical_score
            self.bos_level = float("nan")
            self.bos_type = ""
            self.setup_timestamp = timestamp
            self.bos_timestamp = None
            self.retest_timestamp = None
            self.confirm_timestamp = None
            self.htf_regime = setup.htf_regime
            self.session_bucket = setup.session_bucket
            self.counters.qualified_setups += 1
        elif setup.canonical and self.state > 0:
            self.counters.candidate_collisions.append(
                f"setup_while_armed:bar={bar_index}:state={self.state}:identity={self.setup_identity}"
            )

        if self.state == 1:
            if self._opposite_bos(structure):
                self._reset("opposite_bos_before_retest")
                return entries

            same_bar, swing = self._same_bar_qualifying_bos(
                bar_index=bar_index,
                structure=structure,
                swing_22=swing_22,
                swing_33=swing_33,
            )
            if same_bar:
                self._ignore_same_bar_bos(bar_index=bar_index, swing=swing)
                return entries

            bos_ok, level, bos_type = self._matching_bos_event(
                bar_index=bar_index,
                structure=structure,
                swing_22=swing_22,
                swing_33=swing_33,
            )
            if bos_ok:
                if bar_index <= self.setup_bar:
                    self.counters.same_bar_hard_invalidations += 1
                    raise AssertionError("later BOS must satisfy bos_bar > setup_bar")
                if (
                    _finite(self.ignored_samebar_swing_level)
                    and float(level) == float(self.ignored_samebar_swing_level)
                    and bar_index == self.ignored_samebar_swing_bar
                ):
                    self.counters.stale_setup_bar_bos_reuse += 1
                    raise AssertionError("stale setup-bar BOS level reused as later BOS")
                self.bos_level = level
                self.bos_bar = bar_index
                self.bos_timestamp = timestamp
                self.bos_type = bos_type
                self.counters.reached_bos += 1
                self.counters.setup_to_bos_bars.append(bar_index - self.setup_bar)
                self.state = 2
                self._mark_recovered("later_bos", later_bos=True, bos_bar=bar_index)
            elif self._setup_bos_expired(bar_index):
                self._reset("setup_bos_expiry")

        elif self.state == 2 and _finite(self.bos_level):
            tolerance = (atr if _finite(float(atr)) else 1.0) * self.config.p12_retest_atr_tolerance
            eligible = self.bos_bar >= 0 and bar_index > self.bos_bar
            would_touch = (
                low <= self.bos_level + tolerance
                if self.direction == 1
                else high >= self.bos_level - tolerance
            )
            if not eligible and would_touch:
                self.counters.same_bar_bos_retest += 1
                self._reset("same_bar_bos_retest")
                return entries
            touched = eligible and would_touch
            invalid = eligible and (
                close < self.bos_level - tolerance
                if self.direction == 1
                else close > self.bos_level + tolerance
            )
            if invalid:
                self._reset("retest_structure_failed")
            elif touched:
                self.retest_bar = bar_index
                self.retest_timestamp = timestamp
                self.counters.reached_retest += 1
                self.counters.bos_to_retest_bars.append(bar_index - self.bos_bar)
                self.state = 3
                self._mark_recovered("later_retest", later_retest=True, retest_bar=bar_index)
            elif self.bos_bar >= 0 and bar_index - self.bos_bar > self.config.p12_expiry_bars:
                self._reset("bos_retest_expiry")

        elif self.state == 3 and _finite(self.bos_level) and self.retest_bar >= 0:
            tolerance = (atr if _finite(float(atr)) else 1.0) * self.config.p12_retest_atr_tolerance
            eligible = bar_index > self.retest_bar
            would_confirm = (close > open_price and close > self.bos_level) if self.direction == 1 else (
                close < open_price and close < self.bos_level
            )
            if not eligible and would_confirm:
                self.counters.same_bar_retest_confirm += 1
                self._reset("same_bar_retest_confirm")
                return entries
            confirmed = eligible and would_confirm
            invalid = eligible and (
                close < self.bos_level - tolerance
                if self.direction == 1
                else close > self.bos_level + tolerance
            )
            if confirmed:
                self.confirm_bar = bar_index
                self.confirm_timestamp = timestamp
                self.counters.reached_confirmation += 1
                self.counters.retest_to_confirm_bars.append(bar_index - self.retest_bar)
                assert self.setup_timestamp is not None
                assert self.bos_timestamp is not None
                assert self.retest_timestamp is not None
                assert_strict_order(
                    setup_bar=self.setup_bar,
                    bos_bar=self.bos_bar,
                    retest_bar=self.retest_bar,
                    confirm_bar=self.confirm_bar,
                    entry_bar=bar_index,
                )
                entries.append(
                    EntryEvent(
                        model="Confirm",
                        direction=self.direction,
                        score=self.score,
                        entry_timestamp=timestamp,
                        setup_timestamp=self.setup_timestamp,
                        bos_timestamp=self.bos_timestamp,
                        retest_timestamp=self.retest_timestamp,
                        confirm_timestamp=self.confirm_timestamp,
                        htf_regime=self.htf_regime,
                        session_bucket=self.session_bucket,
                    )
                )
                self.counters.reached_entry += 1
                self._record_entry_audit(bar_index=bar_index, timestamp=timestamp)
                self._mark_recovered("later_confirm", later_confirm=True)
                self._mark_recovered("later_entry", later_entry=True, entry_bar=bar_index)
                self._reset()
            elif invalid or bar_index - self.retest_bar > self.config.p12_expiry_bars:
                self._reset("confirm_failed_or_expiry")
        return entries


def run_ignore_samebar_backtest(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    config: FrozenConfig = FrozenConfig(),
    seq_config: SequentialBosConfig = SequentialBosConfig(),
) -> tuple[BacktestResult, IgnoreSameBarFunnel]:
    if frame.empty:
        raise ValueError("market data is empty")
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)
    data = _prepare_data(frame, config)
    first_bar = data.index[0]
    last_bar_end = data.index[-1] + pd.Timedelta(config.chart_minutes, unit="m")
    coverage = (
        "FULL DATA"
        if first_bar <= start_ts and last_bar_end >= end_exclusive
        else "PARTIAL DATA"
    )

    structure_engine = StructureEngine(config)
    swing_22_engine = CausalSwingEngine(2, 2)
    swing_33_engine = CausalSwingEngine(3, 3)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)
    funnel = IgnoreSameBarFunnel(config, seq_config)
    trades = TradeEngine(config)

    previous_close: Optional[float] = None
    previous_timestamp: Optional[pd.Timestamp] = None
    last_processed_close: Optional[float] = None
    last_processed_timestamp: Optional[pd.Timestamp] = None

    for bar_index, row in enumerate(data.itertuples()):
        timestamp = row.Index
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

        if start_ts <= timestamp < end_exclusive:
            entry_events = funnel.step(
                bar_index=bar_index,
                timestamp=timestamp,
                open_price=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                atr=float(row.atr),
                setup=setup_event,
                structure=structure_event,
                swing_22=swing_22,
                swing_33=swing_33,
            )
            for entry in entry_events:
                trades.try_open(entry, bar_index=bar_index, close=float(row.close), atr=float(row.atr))

        bar_end = timestamp + pd.Timedelta(config.chart_minutes, unit="m")
        trades.manage_bar(
            bar_index=bar_index,
            timestamp=timestamp,
            bar_end=bar_end,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            end_exclusive=end_exclusive,
            previous_close=previous_close,
            previous_timestamp=previous_timestamp,
        )
        previous_close = float(row.close)
        previous_timestamp = timestamp
        last_processed_close = float(row.close)
        last_processed_timestamp = timestamp
        if timestamp >= end_exclusive and not trades.active:
            break

    if trades.active and last_processed_close is not None and last_processed_timestamp is not None:
        trades.close_remaining(
            timestamp=last_processed_timestamp,
            close=last_processed_close,
            reason="DATA_END" if coverage == "PARTIAL DATA" else "WINDOW_END",
        )

    trade_frame = (
        pd.DataFrame([trade.export_dict() for trade in trades.completed])
        if trades.completed
        else pd.DataFrame(columns=TRADE_COLUMNS)
    )
    if not trade_frame.empty:
        trade_frame = trade_frame.sort_values(["exit_timestamp", "model"], kind="stable").reset_index(drop=True)
        audit = pd.DataFrame(funnel.entry_audit_rows)
        if not audit.empty:
            trade_frame = trade_frame.merge(
                audit[
                    [
                        "entry_timestamp",
                        "setup_identity",
                        "recovered_samebar",
                        "setup_bar",
                        "bos_bar",
                        "retest_bar",
                        "confirm_bar",
                    ]
                ],
                on="entry_timestamp",
                how="left",
            )

    result = BacktestResult(
        trades=trade_frame,
        events=pd.DataFrame(),
        diagnostics={
            "architecture": "SEQUENTIAL_BOS_IGNORE_SAMEBAR",
            "bos_definition": seq_config.bos_definition.value,
            "setup_bos_expiry_bars": seq_config.setup_bos_expiry_bars,
            **funnel.counters.export(),
        },
        coverage=coverage,
        start_timestamp=start_ts,
        end_exclusive=end_exclusive,
    )
    return result, funnel


def _conversion_pct(numerator: int, denominator: int) -> float:
    return float(numerator / denominator * 100.0) if denominator > 0 else 0.0


def _robustness_rows(trades: pd.DataFrame, *, config: FrozenConfig, label_prefix: str = "") -> List[Dict[str, Any]]:
    if trades.empty:
        return []
    enriched = apply_costs(trades.sort_values("exit_timestamp"))
    rows: List[Dict[str, Any]] = []
    entry_ts = pd.to_datetime(enriched.entry_timestamp, utc=True).dt.tz_convert(config.exchange_timezone)
    enriched = enriched.copy()
    enriched["year"] = entry_ts.dt.year
    for year, group in enriched.groupby("year"):
        rows.append({"slice": f"{label_prefix}year_{year}", **summarize_architecture(group, direction_split=False)})
    split = len(enriched) // 2
    for label, group in (("first_half", enriched.iloc[:split]), ("second_half", enriched.iloc[split:])):
        rows.append({"slice": f"{label_prefix}{label}", **summarize_architecture(group, direction_split=False)})
    rows.append(
        {
            "slice": f"{label_prefix}exclude_best_trade",
            **summarize_architecture(enriched.drop(enriched.net_R.idxmax()), direction_split=False),
        }
    )
    top3 = enriched.nlargest(3, "net_R").index
    rows.append(
        {
            "slice": f"{label_prefix}exclude_top_3_winners",
            **summarize_architecture(enriched.drop(top3), direction_split=False),
        }
    )
    cutoff = enriched.net_R.quantile(0.99)
    rows.append(
        {
            "slice": f"{label_prefix}exclude_top_1pct_winners",
            **summarize_architecture(enriched.loc[enriched.net_R <= cutoff], direction_split=False),
        }
    )
    return rows


def verify_control_parity(*, counters: FunnelCounters, summary: Dict[str, Any]) -> bool:
    return (
        counters.qualified_setups == 3033
        and counters.reached_bos == 88
        and counters.reached_retest == 43
        and counters.reached_confirmation == 29
        and counters.reached_entry == 29
        and counters.same_bar_setup_bos == 1958
        and summary["N"] == 29
        and abs(summary["net_AvgR"] - 0.2156) < 0.01
        and abs(summary["net_TotalR"] - 6.25) < 0.2
        and abs(summary["net_PF"] - 1.52) < 0.05
        and abs(summary["MaxDD"] - 2.87) < 0.2
    )


def run_ignore_samebar_study(
    frame: pd.DataFrame,
    *,
    start: str = "2024-01-01",
    end: str = "2026-06-26",
    config: FrozenConfig = FrozenConfig(),
    archived_trade_path: Path,
    output: Path,
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    prepared = _prepare_data(frame, config)
    frozen = run_backtest(frame, start=start, end=end, config=config)
    verify_retest_gated_parity(frozen.trades, archived_trade_path)

    focus = SequentialBosConfig(bos_definition=BosDefinition.SWING_2_2, setup_bos_expiry_bars=3)
    control_result, control_counters = run_sequential_bos_backtest(
        frame, start=start, end=end, config=config, seq_config=focus
    )
    baseline_parity = verify_control_parity(
        counters=control_counters,
        summary=_summarize_with_costs(control_result.trades),
    )

    comparison_rows: List[Dict[str, Any]] = []
    funnel_rows: List[Dict[str, Any]] = []
    recovered_frames: List[pd.DataFrame] = []
    recovered_entry_frames: List[pd.DataFrame] = []
    audit_frames: List[pd.DataFrame] = []
    robustness_rows: List[Dict[str, Any]] = []
    experiment_cache: Dict[int, tuple[BacktestResult, IgnoreSameBarFunnel]] = {}

    for expiry in SETUP_BOS_EXPIRY_OPTIONS:
        seq_config = SequentialBosConfig(
            bos_definition=BosDefinition.SWING_2_2,
            setup_bos_expiry_bars=expiry,
        )
        control, control_count = run_sequential_bos_backtest(
            frame, start=start, end=end, config=config, seq_config=seq_config
        )
        experiment, experiment_funnel = run_ignore_samebar_backtest(
            frame, start=start, end=end, config=config, seq_config=seq_config
        )
        experiment_cache[expiry] = (experiment, experiment_funnel)
        control_trades = control.trades.loc[control.trades.model == "Confirm"].copy()
        experiment_trades = experiment.trades.loc[experiment.trades.model == "Confirm"].copy()
        verify_completed_trade_ordering(control_trades, data_index=prepared.index)
        verify_completed_trade_ordering(experiment_trades, data_index=prepared.index)

        control_perf = summarize_architecture(control_trades)
        experiment_perf = summarize_architecture(experiment_trades)
        for mode, perf, counters in (
            ("CONTROL", control_perf, control_count),
            ("EXPERIMENT", experiment_perf, experiment_funnel.counters),
        ):
            comparison_rows.append(
                {
                    "expiry": expiry,
                    "mode": mode,
                    **perf,
                    "qualified_setups": counters.qualified_setups,
                    "reached_bos": counters.reached_bos,
                    "reached_retest": counters.reached_retest,
                    "reached_confirmation": counters.reached_confirmation,
                    "reached_entry": counters.reached_entry,
                }
            )
            funnel_rows.append(
                {
                    "expiry": expiry,
                    "mode": mode,
                    "qualified_setups": counters.qualified_setups,
                    "same_bar_bos_events": counters.same_bar_setup_bos
                    if mode == "CONTROL"
                    else counters.same_bar_bos_ignored,
                    "same_bar_hard_invalidations": counters.same_bar_setup_bos
                    if mode == "CONTROL"
                    else counters.same_bar_hard_invalidations,
                    "same_bar_ignored_events": counters.same_bar_bos_ignored if mode == "EXPERIMENT" else 0,
                    "later_bos": counters.reached_bos,
                    "retest": counters.reached_retest,
                    "confirm": counters.reached_confirmation,
                    "entry": counters.reached_entry,
                    "setup_to_bos_pct": _conversion_pct(counters.reached_bos, counters.qualified_setups),
                    "bos_to_retest_pct": _conversion_pct(counters.reached_retest, counters.reached_bos),
                    "retest_to_confirm_pct": _conversion_pct(
                        counters.reached_confirmation, counters.reached_retest
                    ),
                    "setup_to_entry_pct": _conversion_pct(counters.reached_entry, counters.qualified_setups),
                    "recovered_setups": counters.recovered_setups if mode == "EXPERIMENT" else 0,
                    "recovered_later_bos": counters.recovered_later_bos if mode == "EXPERIMENT" else 0,
                    "recovered_retest": counters.recovered_retest if mode == "EXPERIMENT" else 0,
                    "recovered_confirm": counters.recovered_confirm if mode == "EXPERIMENT" else 0,
                    "recovered_entries": counters.recovered_entries if mode == "EXPERIMENT" else 0,
                    "stale_setup_bar_bos_reuse": counters.stale_setup_bar_bos_reuse if mode == "EXPERIMENT" else 0,
                    "candidate_collisions": len(counters.candidate_collisions) if mode == "EXPERIMENT" else 0,
                }
            )

        recovered = pd.DataFrame(experiment_funnel.recovered_candidate_rows)
        audit = pd.DataFrame(experiment_funnel.entry_audit_rows)
        if not recovered.empty:
            recovered["expiry"] = expiry
            recovered_frames.append(recovered)
        if not audit.empty:
            audit["expiry"] = expiry
            audit_frames.append(audit)

        if not experiment_trades.empty and "recovered_samebar" in experiment_trades.columns:
            recovered_entries = experiment_trades.loc[experiment_trades.recovered_samebar == True].copy()
            original_entries = experiment_trades.loc[experiment_trades.recovered_samebar != True].copy()
        else:
            recovered_entries = experiment_trades.iloc[0:0].copy()
            original_entries = experiment_trades.copy()
        for label, subset in (
            ("original_survivors", original_entries),
            ("recovered_samebar", recovered_entries),
            ("combined", experiment_trades),
        ):
            comparison_rows.append({"expiry": expiry, "mode": label, **summarize_architecture(subset)})
        if not recovered_entries.empty:
            recovered_entries = recovered_entries.copy()
            recovered_entries["expiry"] = expiry
            recovered_entry_frames.append(recovered_entries)

        if expiry == 3:
            robustness_rows.extend(_robustness_rows(experiment_trades, config=config, label_prefix="experiment_exp3_"))
            robustness_rows.extend(_robustness_rows(recovered_entries, config=config, label_prefix="recovered_exp3_"))

    for expiry, (experiment, _) in experiment_cache.items():
        perf = summarize_architecture(experiment.trades)
        if perf["net_TotalR"] > 0 and expiry != 3:
            robustness_rows.extend(
                _robustness_rows(experiment.trades, config=config, label_prefix=f"experiment_exp{expiry}_")
            )

    comparison = pd.DataFrame(comparison_rows)
    funnel_comparison = pd.DataFrame(funnel_rows)
    recovered_candidates = pd.concat(recovered_frames, ignore_index=True) if recovered_frames else pd.DataFrame()
    recovered_entries = pd.concat(recovered_entry_frames, ignore_index=True) if recovered_entry_frames else pd.DataFrame()
    event_order_audit = pd.concat(audit_frames, ignore_index=True) if audit_frames else pd.DataFrame()
    robustness = pd.DataFrame(robustness_rows)

    comparison.to_csv(output / "comparison.csv", index=False)
    funnel_comparison.to_csv(output / "funnel_comparison.csv", index=False)
    recovered_candidates.to_csv(output / "recovered_candidates.csv", index=False)
    recovered_entries.to_csv(output / "recovered_entries.csv", index=False)
    event_order_audit.to_csv(output / "event_order_audit.csv", index=False)
    robustness.to_csv(output / "robustness.csv", index=False)

    exp3 = comparison.loc[(comparison["expiry"] == 3) & (comparison["mode"] == "EXPERIMENT")].iloc[0]
    ctl3 = comparison.loc[(comparison["expiry"] == 3) & (comparison["mode"] == "CONTROL")].iloc[0]
    rec3 = comparison.loc[(comparison["expiry"] == 3) & (comparison["mode"] == "recovered_samebar")]
    rec_perf = rec3.iloc[0].to_dict() if not rec3.empty else {}
    funnel3 = funnel_comparison.loc[
        (funnel_comparison["expiry"] == 3) & (funnel_comparison["mode"] == "EXPERIMENT")
    ].iloc[0]
    stale = int(
        funnel_comparison.loc[funnel_comparison["mode"] == "EXPERIMENT", "stale_setup_bar_bos_reuse"].sum()
    )
    strict_order_pass = stale == 0 and (
        event_order_audit.empty or not bool(event_order_audit.stale_setup_bar_bos_reuse.any())
    )

    if exp3["net_TotalR"] > ctl3["net_TotalR"] and exp3["N"] >= ctl3["N"] and strict_order_pass:
        classification = "A"
    elif exp3["net_TotalR"] > 0 and exp3["N"] > ctl3["N"]:
        classification = "B"
    elif abs(exp3["N"] - ctl3["N"]) <= 5 and abs(exp3["net_TotalR"] - ctl3["net_TotalR"]) <= 1.0:
        classification = "C"
    else:
        classification = "D"

    report = _build_report(
        baseline_parity=baseline_parity,
        control=ctl3,
        experiment=exp3,
        funnel3=funnel3,
        recovered_perf=rec_perf,
        funnel_comparison=funnel_comparison,
        comparison=comparison,
        classification=classification,
        strict_order_pass=strict_order_pass,
        stale=stale,
        robustness=robustness,
    )
    (output / "SEQUENTIAL_BOS_IGNORE_SAMEBAR_REPORT.md").write_text(report)
    try:
        with pd.ExcelWriter(output / "SEQUENTIAL_BOS_IGNORE_SAMEBAR.xlsx", engine="openpyxl") as writer:
            for name, frame in {
                "comparison": comparison,
                "funnel_comparison": funnel_comparison,
                "recovered_candidates": recovered_candidates,
                "recovered_entries": recovered_entries,
                "event_order_audit": event_order_audit,
                "robustness": robustness,
            }.items():
                _excel_safe(frame).to_excel(writer, sheet_name=name[:31], index=False)
    except ImportError:
        pass

    manifest = {
        "baseline_parity": baseline_parity,
        "control_sequential_parity": baseline_parity,
        "ignore_and_wait_implemented": True,
        "classification": classification,
        "strict_order_pass": strict_order_pass,
        "stale_setup_bar_bos_reuse": stale,
        "experiment_exp3": exp3.to_dict(),
        "control_exp3": ctl3.to_dict(),
        "recovered_exp3": rec_perf,
        "funnel_exp3": funnel3.to_dict(),
    }
    (output / "study_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return manifest


def _build_report(
    *,
    baseline_parity: bool,
    control: pd.Series,
    experiment: pd.Series,
    funnel3: pd.Series,
    recovered_perf: Dict[str, Any],
    funnel_comparison: pd.DataFrame,
    comparison: pd.DataFrame,
    classification: str,
    strict_order_pass: bool,
    stale: int,
    robustness: pd.DataFrame,
) -> str:
    class_map = {
        "A": "ignore-and-wait clearly improves sequential architecture",
        "B": "promising but needs further validation",
        "C": "neutral / little effect",
        "D": "recovered candidates degrade strategy",
    }
    lines = [
        "# SEQUENTIAL_BOS Ignore Same-Bar Experiment",
        "",
        f"Baseline parity: {'PASS' if baseline_parity else 'FAIL'}",
        f"Strict order: {'PASS' if strict_order_pass else 'FAIL'}",
        f"Stale setup-bar BOS reuse: {stale}",
        "",
        f"CONTROL expiry=3: N={int(control.N)}, Net AvgR={control.net_AvgR:.4f}, TotalR={control.net_TotalR:.2f}, PF={control.net_PF:.3f}, MaxDD={control.MaxDD:.2f}R",
        f"EXPERIMENT expiry=3: N={int(experiment.N)}, Net AvgR={experiment.net_AvgR:.4f}, TotalR={experiment.net_TotalR:.2f}, PF={experiment.net_PF:.3f}, MaxDD={experiment.MaxDD:.2f}R",
        "",
        f"Recovered setups={int(funnel3.recovered_setups)}, later BOS={int(funnel3.recovered_later_bos)}, entries={int(funnel3.recovered_entries)}",
    ]
    if recovered_perf:
        lines.append(
            f"Recovered entry performance: N={int(recovered_perf.get('N', 0))}, WR={recovered_perf.get('WR', 0):.2f}, "
            f"Net AvgR={recovered_perf.get('net_AvgR', 0):.4f}, TotalR={recovered_perf.get('net_TotalR', 0):.2f}, "
            f"PF={recovered_perf.get('net_PF', 0):.3f}, MaxDD={recovered_perf.get('MaxDD', 0):.2f}R"
        )
    lines.extend(["", "## Funnel comparison", ""])
    for row in funnel_comparison.itertuples():
        lines.append(
            f"- expiry={int(row.expiry)} {row.mode}: setups={int(row.qualified_setups)}, hard_inv={int(row.same_bar_hard_invalidations)}, "
            f"ignored={int(row.same_bar_ignored_events)}, BOS={int(row.later_bos)}, entry={int(row.entry)}, setup→entry={row.setup_to_entry_pct:.2f}%"
        )
    lines.extend(["", f"## Classification: {classification} — {class_map[classification]}", ""])
    if not robustness.empty:
        lines.extend(["", "## Robustness", ""])
        for row in robustness.itertuples():
            lines.append(f"- {row.slice}: N={int(row.N)}, TotalR={row.net_TotalR:.2f}, AvgR={row.net_AvgR:.4f}, PF={row.net_PF:.3f}")
    return "\n".join(lines) + "\n"
