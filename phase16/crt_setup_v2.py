"""CRT Setup V2 experimental architecture — separate from frozen baselines."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from math import erfc, sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .backtest import run_backtest, validation_window
from .bos_semantic_audit import CausalSwingEngine
from .config import FrozenConfig
from .indicators import htf_regime_name, session_bucket_name
from .liquidity import LiquidityEngine
from .metrics import _drawdown
from .models import EntryEvent, SetupEvent, StructureEvent
from .sequential_bos import (
    BosDefinition,
    FunnelCounters,
    SequentialBosConfig,
    SequentialBosFunnel,
    _prepare_data,
    apply_costs,
    assert_strict_order,
    summarize_architecture,
    verify_retest_gated_parity,
)
from .setup_engine import SetupEngine
from .structure import StructureEngine
from .trade_engine import TradeEngine


CRT_LIQUIDITY_REFERENCE = "CRT_PRIOR_BAR_RANGE"
SETUP_V2_EXPIRY_OPTIONS = (3, 6, 12)


class SetupV2Archetype(str, Enum):
    SAME_BAR = "A"
    NEXT_BAR = "B"
    SAME_OR_NEXT = "C"


class SetupV2Qualification(str, Enum):
    STRUCTURE_ONLY = "structure_only"
    LEGACY_QUALIFIED = "legacy_qualified"


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


def current_crt_setup_thesis() -> Dict[str, str]:
    return {
        "A_range_reference": (
            "Chart-timeframe CRT uses prior bar high/low (crt_high/crt_low). "
            "Phase 4 liquidity uses confirmed 5/5 pivot highs (BSL) and lows (SSL)."
        ),
        "B_liquidity_swept": (
            "Long: SSL sweep (low pierces sell-side pivot, close reclaims) or bull BOS. "
            "Short: BSL sweep or bear BOS."
        ),
        "C_direction": (
            "Long setup on bull_bos or ssl_sweep with score≥70. "
            "Short on bear_bos or bsl_sweep with score≥70. Variant-C adds HTF≠0 and session≠after-hours."
        ),
        "D_setup_trigger": (
            "Same-bar Phase 3 bull/bear BOS OR Phase 4 BSL/SSL sweep, plus score≥70, cooldown, anti-chase filters."
        ),
        "E_htf_role": (
            "Prior closed 60m regime gates Variant-C canonical feed; neutral HTF blocks canonical setups."
        ),
        "F_score_role": (
            "0–100 composite: liquidity 25, structure 30, bias 20, displacement 15, session 10. "
            "Minimum 70 required for raw setup; canonical requires Variant-C on top."
        ),
        "G_structural_vs_heuristic": (
            "Structural: BOS/sweep event, cooldown, opposite invalidation downstream. "
            "Heuristic: score components, anti-chase, session preference, HTF Variant-C filter."
        ),
        "H_bos_overlap": (
            "Setup trigger includes structure.bull_bos/bear_bos on the same bar. "
            "RETEST_GATED funnel then accepts that identical same-bar structural break as BOS (664/705 same-bar). "
            "Setup and BOS are not separate causal events in the legacy architecture."
        ),
    }


def liquidity_reference_definition() -> Dict[str, str]:
    return {
        "primary_reference": CRT_LIQUIDITY_REFERENCE,
        "liquidity_high": "crt_high = prior completed bar high (shift(1) on chart timeframe)",
        "liquidity_low": "crt_low = prior completed bar low (shift(1) on chart timeframe)",
        "causal_availability": "Reference known before current bar opens; sweep evaluated on current bar OHLC",
        "alternatives_not_used_primary": (
            "Phase4 BSL/SSL pivot levels (buy_side/sell_side in LiquidityEngine); "
            "StructureEngine active_high/active_low (5/5 pivots for BOS, not CRT range)"
        ),
        "long_sweep": "low < crt_low",
        "long_reclaim": "close > crt_low",
        "short_sweep": "high > crt_high",
        "short_reclaim": "close < crt_high",
    }


def passes_legacy_qualification(setup: SetupEvent, direction: int, config: FrozenConfig) -> bool:
    live_filter = setup.htf_regime != 0 and setup.session_bucket != 6
    score = setup.long_score if direction == 1 else setup.short_score
    return live_filter and score >= config.se_min_score


@dataclass
class PendingSweep:
    direction: int
    sweep_bar: int
    sweep_timestamp: pd.Timestamp
    liquidity_level: float
    liquidity_reference: str
    sweep_distance: float
    wick_beyond: float
    atr: float


@dataclass
class SetupV2Candidate:
    direction: int
    setup_bar: int
    setup_timestamp: pd.Timestamp
    sweep_bar: int
    sweep_timestamp: pd.Timestamp
    reclaim_mode: str
    liquidity_level: float
    liquidity_reference: str
    sweep_distance: float
    wick_beyond_atr: float
    range_atr: float
    body_atr: float
    reclaim_distance_atr: float
    close_location: float
    volume_ratio: float
    atr_percentile: float
    session: str
    htf_regime: str
    legacy_score: int
    legacy_qualified: bool


@dataclass
class SetupV2Counters(FunnelCounters):
    liquidity_references: int = 0
    sweeps: int = 0
    reclaims: int = 0
    qualified_setups_v2: int = 0
    sweep_to_setup_bars: List[int] = field(default_factory=list)

    def export_v2(self) -> Dict[str, Any]:
        base = self.export()
        base.update(
            {
                "liquidity_references_observed": self.liquidity_references,
                "sweeps": self.sweeps,
                "reclaims": self.reclaims,
                "qualified_setup_v2": self.qualified_setups_v2,
                "median_bars_sweep_to_setup": _median(self.sweep_to_setup_bars),
                "conversion_sweep_to_setup": (
                    self.qualified_setups_v2 / self.sweeps if self.sweeps else float("nan")
                ),
                "conversion_setup_to_bos": (
                    self.reached_bos / self.qualified_setups_v2 if self.qualified_setups_v2 else float("nan")
                ),
                "conversion_bos_to_retest": (
                    self.reached_retest / self.reached_bos if self.reached_bos else float("nan")
                ),
                "conversion_retest_to_confirm": (
                    self.reached_confirmation / self.reached_retest if self.reached_retest else float("nan")
                ),
                "conversion_setup_to_entry": (
                    self.reached_entry / self.qualified_setups_v2 if self.qualified_setups_v2 else float("nan")
                ),
            }
        )
        return base


def _median(values: List[int]) -> float:
    if not values:
        return float("nan")
    return float(np.median(values))


def _atr_percentile(data: pd.DataFrame, bar_index: int, atr: float) -> float:
    if bar_index <= 0 or not _finite(atr):
        return float("nan")
    history = data.iloc[: bar_index + 1].atr.astype(float)
    history = history[history.map(_finite)]
    if history.empty:
        return float("nan")
    return float((history <= atr).mean())


def _volume_ratio(data: pd.DataFrame, bar_index: int, volume: float) -> float:
    start = max(0, bar_index - 20)
    history = data.iloc[start:bar_index].volume.astype(float)
    history = history[history > 0]
    if history.empty or volume <= 0:
        return float("nan")
    return float(volume / history.mean())


class SetupV2Detector:
    def __init__(
        self,
        *,
        archetype: SetupV2Archetype,
        qualification: SetupV2Qualification,
        config: FrozenConfig,
        data: pd.DataFrame,
    ) -> None:
        self.archetype = archetype
        self.qualification = qualification
        self.config = config
        self.data = data
        self.pending: Optional[PendingSweep] = None
        self.counters = SetupV2Counters()

    def _build_candidate(
        self,
        *,
        direction: int,
        setup_bar: int,
        setup_timestamp: pd.Timestamp,
        pending: PendingSweep,
        reclaim_mode: str,
        setup_event: SetupEvent,
    ) -> Optional[SetupV2Candidate]:
        row = self.data.iloc[setup_bar]
        atr = float(row.atr) if _finite(row.atr) else 1.0
        rng = float(row.high) - float(row.low)
        body = abs(float(row.close) - float(row.open))
        reclaim_distance = (
            float(row.close) - pending.liquidity_level
            if direction == 1
            else pending.liquidity_level - float(row.close)
        )
        close_loc = (float(row.close) - float(row.low)) / rng if rng > 0 else 0.5
        legacy_ok = passes_legacy_qualification(setup_event, direction, self.config)
        if self.qualification == SetupV2Qualification.LEGACY_QUALIFIED and not legacy_ok:
            return None
        self.counters.reclaims += 1
        self.counters.qualified_setups_v2 += 1
        self.counters.sweep_to_setup_bars.append(setup_bar - pending.sweep_bar)
        return SetupV2Candidate(
            direction=direction,
            setup_bar=setup_bar,
            setup_timestamp=setup_timestamp,
            sweep_bar=pending.sweep_bar,
            sweep_timestamp=pending.sweep_timestamp,
            reclaim_mode=reclaim_mode,
            liquidity_level=pending.liquidity_level,
            liquidity_reference=pending.liquidity_reference,
            sweep_distance=pending.sweep_distance,
            wick_beyond_atr=pending.wick_beyond / atr if atr > 0 else float("nan"),
            range_atr=rng / atr if atr > 0 else float("nan"),
            body_atr=body / atr if atr > 0 else float("nan"),
            reclaim_distance_atr=reclaim_distance / atr if atr > 0 else float("nan"),
            close_location=close_loc,
            volume_ratio=_volume_ratio(self.data, setup_bar, float(row.volume)),
            atr_percentile=_atr_percentile(self.data, setup_bar, atr),
            session=session_bucket_name(int(setup_event.session_bucket)),
            htf_regime=htf_regime_name(int(setup_event.htf_regime)),
            legacy_score=int(setup_event.long_score if direction == 1 else setup_event.short_score),
            legacy_qualified=legacy_ok,
        )

    def _record_sweep(
        self,
        *,
        direction: int,
        bar_index: int,
        timestamp: pd.Timestamp,
        liquidity_level: float,
        low: float,
        high: float,
        atr: float,
    ) -> PendingSweep:
        self.counters.sweeps += 1
        wick = (liquidity_level - low) if direction == 1 else (high - liquidity_level)
        sweep_distance = wick
        return PendingSweep(
            direction=direction,
            sweep_bar=bar_index,
            sweep_timestamp=timestamp,
            liquidity_level=liquidity_level,
            liquidity_reference=CRT_LIQUIDITY_REFERENCE,
            sweep_distance=sweep_distance,
            wick_beyond=wick,
            atr=atr,
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
        crt_high: float,
        crt_low: float,
        setup_event: SetupEvent,
        funnel_idle: bool,
    ) -> Optional[SetupV2Candidate]:
        if not funnel_idle:
            return None
        if _finite(crt_high) and _finite(crt_low):
            self.counters.liquidity_references += 1

        resolved_atr = float(atr) if _finite(atr) else 1.0

        if self.pending is not None and bar_index == self.pending.sweep_bar + 1:
            pending = self.pending
            self.pending = None
            if self.archetype in {SetupV2Archetype.NEXT_BAR, SetupV2Archetype.SAME_OR_NEXT}:
                reclaimed = (
                    pending.direction == 1 and close > pending.liquidity_level
                ) or (pending.direction == -1 and close < pending.liquidity_level)
                if reclaimed:
                    candidate = self._build_candidate(
                        direction=pending.direction,
                        setup_bar=bar_index,
                        setup_timestamp=timestamp,
                        pending=pending,
                        reclaim_mode="next_bar",
                        setup_event=setup_event,
                    )
                    if candidate is not None:
                        return candidate

        if not _finite(crt_low) or not _finite(crt_high):
            return None

        long_sweep = low < crt_low
        short_sweep = high > crt_high
        long_same = long_sweep and close > crt_low
        short_same = short_sweep and close < crt_high

        if self.archetype in {SetupV2Archetype.SAME_BAR, SetupV2Archetype.SAME_OR_NEXT}:
            if long_same:
                pending = self._record_sweep(
                    direction=1,
                    bar_index=bar_index,
                    timestamp=timestamp,
                    liquidity_level=crt_low,
                    low=low,
                    high=high,
                    atr=resolved_atr,
                )
                candidate = self._build_candidate(
                    direction=1,
                    setup_bar=bar_index,
                    setup_timestamp=timestamp,
                    pending=pending,
                    reclaim_mode="same_bar",
                    setup_event=setup_event,
                )
                if candidate is not None:
                    return candidate
            if short_same:
                pending = self._record_sweep(
                    direction=-1,
                    bar_index=bar_index,
                    timestamp=timestamp,
                    liquidity_level=crt_high,
                    low=low,
                    high=high,
                    atr=resolved_atr,
                )
                candidate = self._build_candidate(
                    direction=-1,
                    setup_bar=bar_index,
                    setup_timestamp=timestamp,
                    pending=pending,
                    reclaim_mode="same_bar",
                    setup_event=setup_event,
                )
                if candidate is not None:
                    return candidate

        if self.archetype in {SetupV2Archetype.NEXT_BAR, SetupV2Archetype.SAME_OR_NEXT}:
            if long_sweep and not long_same:
                self.pending = self._record_sweep(
                    direction=1,
                    bar_index=bar_index,
                    timestamp=timestamp,
                    liquidity_level=crt_low,
                    low=low,
                    high=high,
                    atr=resolved_atr,
                )
            elif short_sweep and not short_same:
                self.pending = self._record_sweep(
                    direction=-1,
                    bar_index=bar_index,
                    timestamp=timestamp,
                    liquidity_level=crt_high,
                    low=low,
                    high=high,
                    atr=resolved_atr,
                )
        return None


@dataclass
class SetupV2Funnel(SequentialBosFunnel):
    active_candidate: Optional[SetupV2Candidate] = None
    active_setup_identity: int = 0

    def arm_setup(self, candidate: SetupV2Candidate, setup_event: SetupEvent, setup_identity: int) -> None:
        if self.state != 0:
            return
        self.state = 1
        self.direction = candidate.direction
        self.setup_bar = candidate.setup_bar
        self.bos_bar = -1
        self.retest_bar = -1
        self.confirm_bar = -1
        self.score = float(candidate.legacy_score)
        self.bos_level = float("nan")
        self.bos_type = ""
        self.setup_timestamp = candidate.setup_timestamp
        self.bos_timestamp = None
        self.retest_timestamp = None
        self.confirm_timestamp = None
        self.active_candidate = candidate
        self.active_setup_identity = setup_identity
        self.htf_regime = setup_event.htf_regime
        self.session_bucket = setup_event.session_bucket
        self.counters.qualified_setups += 1

    def step_v2(
        self,
        *,
        bar_index: int,
        timestamp: pd.Timestamp,
        open_price: float,
        high: float,
        low: float,
        close: float,
        atr: float,
        structure: StructureEvent,
        swing_22: tuple,
        swing_33: tuple,
    ) -> List[EntryEvent]:
        setup_stub = SetupEvent(
            long_setup=False,
            short_setup=False,
            long_score=int(self.active_candidate.legacy_score) if self.active_candidate else 0,
            short_score=int(self.active_candidate.legacy_score) if self.active_candidate else 0,
            canonical_long=False,
            canonical_short=False,
            canonical_score=int(self.active_candidate.legacy_score) if self.active_candidate else 0,
            htf_regime=self.htf_regime,
            session_bucket=self.session_bucket,
        )
        return self.step(
            bar_index=bar_index,
            timestamp=timestamp,
            open_price=open_price,
            high=high,
            low=low,
            close=close,
            atr=atr,
            setup=setup_stub,
            structure=structure,
            swing_22=swing_22,
            swing_33=swing_33,
        )

    def _reset(self, reason: str = "") -> None:
        super()._reset(reason)
        self.active_candidate = None
        self.active_setup_identity = 0


def _one_sample_pvalue_positive(values: np.ndarray) -> float:
    values = values.astype(float)
    n = len(values)
    if n < 2:
        return 1.0 if values.mean() <= 0 else 0.0
    mean = float(values.mean())
    std = float(values.std(ddof=1))
    if std <= 0:
        return 0.0 if mean > 0 else 1.0
    t = mean / (std / sqrt(n))
    if t <= 0:
        return 1.0
    return 0.5 * erfc(t / sqrt(2))


def _benjamini_hochberg(p_values: List[float]) -> List[float]:
    m = len(p_values)
    order = np.argsort(p_values)
    adjusted = [1.0] * m
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        idx = order[rank]
        q = min(prev, p_values[idx] * m / (rank + 1))
        adjusted[idx] = q
        prev = q
    return adjusted


@dataclass(frozen=True)
class SetupV2Variant:
    archetype: SetupV2Archetype
    qualification: SetupV2Qualification
    setup_bos_expiry_bars: int

    @property
    def variant_id(self) -> str:
        qual = "STRUCT" if self.qualification == SetupV2Qualification.STRUCTURE_ONLY else "LEGACY"
        return f"V2-{self.archetype.value}-{qual}-EXP{self.setup_bos_expiry_bars}"


def run_setup_v2_backtest(
    frame: pd.DataFrame,
    *,
    variant: SetupV2Variant,
    start: str,
    end: str,
    config: FrozenConfig = FrozenConfig(),
    prepared: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, SetupV2Counters, List[Dict[str, Any]], List[Dict[str, Any]]]:
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)
    data = prepared if prepared is not None else _prepare_data(frame, config)
    seq_config = SequentialBosConfig(
        bos_definition=BosDefinition.SWING_2_2,
        setup_bos_expiry_bars=variant.setup_bos_expiry_bars,
    )

    structure_engine = StructureEngine(config)
    swing_22_engine = CausalSwingEngine(2, 2)
    swing_33_engine = CausalSwingEngine(3, 3)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)
    detector = SetupV2Detector(
        archetype=variant.archetype,
        qualification=variant.qualification,
        config=config,
        data=data,
    )
    funnel = SetupV2Funnel(config, seq_config)
    trades = TradeEngine(config)

    trace_rows: List[Dict[str, Any]] = []
    trade_feature_rows: List[Dict[str, Any]] = []
    setup_identity = 0

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

        candidate = None
        if start_ts <= timestamp < end_exclusive:
            candidate = detector.step(
                bar_index=bar_index,
                timestamp=timestamp,
                open_price=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                atr=float(row.atr),
                crt_high=float(row.crt_high),
                crt_low=float(row.crt_low),
                setup_event=setup_event,
                funnel_idle=funnel.state == 0,
            )
            if candidate is not None:
                setup_identity += 1
                trace_rows.append(
                    {
                        "variant_id": variant.variant_id,
                        "setup_identity": setup_identity,
                        **asdict(candidate),
                    }
                )
                funnel.arm_setup(candidate, setup_event, setup_identity)

            entry_events = funnel.step_v2(
                bar_index=bar_index,
                timestamp=timestamp,
                open_price=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                atr=float(row.atr),
                structure=structure_event,
                swing_22=swing_22,
                swing_33=swing_33,
            )
            for entry in entry_events:
                if entry.model != "Confirm":
                    continue
                trades.try_open(
                    entry,
                    bar_index=bar_index,
                    close=float(row.close),
                    atr=float(row.atr),
                )
                if funnel.active_candidate is not None:
                    trade_feature_rows.append(
                        {
                            "variant_id": variant.variant_id,
                            "setup_identity": funnel.active_setup_identity,
                            **asdict(funnel.active_candidate),
                        }
                    )

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

    if trades.active and last_processed_close is not None and last_processed_timestamp is not None:
        trades.close_remaining(
            timestamp=last_processed_timestamp,
            close=last_processed_close,
            reason="DATA_END",
        )

    trade_frame = pd.DataFrame([trade.export_dict() for trade in trades.completed])
    if not trade_frame.empty:
        trade_frame["variant_id"] = variant.variant_id
    counters = detector.counters
    counters.same_bar_setup_bos = funnel.counters.same_bar_setup_bos
    counters.same_bar_bos_retest = funnel.counters.same_bar_bos_retest
    counters.same_bar_retest_confirm = funnel.counters.same_bar_retest_confirm
    counters.reached_bos = funnel.counters.reached_bos
    counters.reached_retest = funnel.counters.reached_retest
    counters.reached_confirmation = funnel.counters.reached_confirmation
    counters.reached_entry = funnel.counters.reached_entry
    counters.setup_to_bos_bars = funnel.counters.setup_to_bos_bars
    counters.bos_to_retest_bars = funnel.counters.bos_to_retest_bars
    counters.retest_to_confirm_bars = funnel.counters.retest_to_confirm_bars
    counters.invalidations = funnel.counters.invalidations
    return trade_frame, counters, trace_rows, trade_feature_rows


@dataclass
class _VariantRuntime:
    variant: SetupV2Variant
    detector: SetupV2Detector
    funnel: SetupV2Funnel
    trades: TradeEngine
    setup_identity: int = 0
    trace_rows: List[Dict[str, Any]] = field(default_factory=list)
    feature_rows: List[Dict[str, Any]] = field(default_factory=list)


def run_all_setup_v2_variants(
    frame: pd.DataFrame,
    *,
    variants: List[SetupV2Variant],
    start: str,
    end: str,
    config: FrozenConfig = FrozenConfig(),
    prepared: Optional[pd.DataFrame] = None,
) -> Dict[str, Tuple[pd.DataFrame, SetupV2Counters, List[Dict[str, Any]], List[Dict[str, Any]]]]:
    """Run all predefined variants in one shared bar loop."""
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)
    data = prepared if prepared is not None else _prepare_data(frame, config)

    structure_engine = StructureEngine(config)
    swing_22_engine = CausalSwingEngine(2, 2)
    swing_33_engine = CausalSwingEngine(3, 3)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)

    runtimes: List[_VariantRuntime] = []
    for variant in variants:
        seq_config = SequentialBosConfig(
            bos_definition=BosDefinition.SWING_2_2,
            setup_bos_expiry_bars=variant.setup_bos_expiry_bars,
        )
        runtimes.append(
            _VariantRuntime(
                variant=variant,
                detector=SetupV2Detector(
                    archetype=variant.archetype,
                    qualification=variant.qualification,
                    config=config,
                    data=data,
                ),
                funnel=SetupV2Funnel(config, seq_config),
                trades=TradeEngine(config),
            )
        )

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

        in_window = start_ts <= timestamp < end_exclusive
        bar_end = timestamp + pd.Timedelta(config.chart_minutes, unit="m")
        past_window = timestamp >= end_exclusive

        for runtime in runtimes:
            active_trade = bool(runtime.trades.active)
            active_funnel = runtime.funnel.state != 0
            if not (in_window or active_trade or active_funnel):
                continue

            if in_window:
                candidate = runtime.detector.step(
                    bar_index=bar_index,
                    timestamp=timestamp,
                    open_price=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    atr=float(row.atr),
                    crt_high=float(row.crt_high),
                    crt_low=float(row.crt_low),
                    setup_event=setup_event,
                    funnel_idle=runtime.funnel.state == 0,
                )
                if candidate is not None:
                    runtime.setup_identity += 1
                    runtime.trace_rows.append(
                        {
                            "variant_id": runtime.variant.variant_id,
                            "setup_identity": runtime.setup_identity,
                            **asdict(candidate),
                        }
                    )
                    runtime.funnel.arm_setup(candidate, setup_event, runtime.setup_identity)

            if in_window or active_funnel:
                entry_events = runtime.funnel.step_v2(
                    bar_index=bar_index,
                    timestamp=timestamp,
                    open_price=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    atr=float(row.atr),
                    structure=structure_event,
                    swing_22=swing_22,
                    swing_33=swing_33,
                )
                for entry in entry_events:
                    if entry.model != "Confirm":
                        continue
                    runtime.trades.try_open(
                        entry,
                        bar_index=bar_index,
                        close=float(row.close),
                        atr=float(row.atr),
                    )
                    if runtime.funnel.active_candidate is not None:
                        runtime.feature_rows.append(
                            {
                                "variant_id": runtime.variant.variant_id,
                                "setup_identity": runtime.funnel.active_setup_identity,
                                **asdict(runtime.funnel.active_candidate),
                            }
                        )

            if active_trade or in_window:
                runtime.trades.manage_bar(
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

        if past_window and not any(rt.trades.active for rt in runtimes) and all(
            rt.funnel.state == 0 for rt in runtimes
        ):
            break

    if last_processed_close is not None and last_processed_timestamp is not None:
        for runtime in runtimes:
            if runtime.trades.active:
                runtime.trades.close_remaining(
                    timestamp=last_processed_timestamp,
                    close=last_processed_close,
                    reason="DATA_END",
                )

    results: Dict[str, Tuple[pd.DataFrame, SetupV2Counters, List[Dict[str, Any]], List[Dict[str, Any]]]] = {}
    for runtime in runtimes:
        trade_frame = pd.DataFrame([trade.export_dict() for trade in runtime.trades.completed])
        if not trade_frame.empty:
            trade_frame["variant_id"] = runtime.variant.variant_id
        counters = runtime.detector.counters
        counters.same_bar_setup_bos = runtime.funnel.counters.same_bar_setup_bos
        counters.same_bar_bos_retest = runtime.funnel.counters.same_bar_bos_retest
        counters.same_bar_retest_confirm = runtime.funnel.counters.same_bar_retest_confirm
        counters.reached_bos = runtime.funnel.counters.reached_bos
        counters.reached_retest = runtime.funnel.counters.reached_retest
        counters.reached_confirmation = runtime.funnel.counters.reached_confirmation
        counters.reached_entry = runtime.funnel.counters.reached_entry
        counters.setup_to_bos_bars = runtime.funnel.counters.setup_to_bos_bars
        counters.bos_to_retest_bars = runtime.funnel.counters.bos_to_retest_bars
        counters.retest_to_confirm_bars = runtime.funnel.counters.retest_to_confirm_bars
        counters.invalidations = runtime.funnel.counters.invalidations
        results[runtime.variant.variant_id] = (
            trade_frame,
            counters,
            runtime.trace_rows,
            runtime.feature_rows,
        )
    return results


def _robustness_slices(trades: pd.DataFrame, *, config: FrozenConfig, variant_id: str) -> List[Dict[str, Any]]:
    if trades.empty:
        return []
    enriched = apply_costs(trades.sort_values("entry_timestamp"))
    rows: List[Dict[str, Any]] = []
    entry_ts = pd.to_datetime(enriched.entry_timestamp, utc=True).dt.tz_convert(config.exchange_timezone)
    enriched = enriched.copy()
    enriched["year"] = entry_ts.dt.year
    for year, group in enriched.groupby("year"):
        rows.append({"variant_id": variant_id, "slice": f"year_{year}", **summarize_architecture(group)})
    split = len(enriched) // 2
    for label, group in (("first_half", enriched.iloc[:split]), ("second_half", enriched.iloc[split:])):
        rows.append({"variant_id": variant_id, "slice": label, **summarize_architecture(group)})
    for label, frame in (
        ("exclude_best_trade", enriched.drop(enriched.net_R.idxmax())),
        ("exclude_top_3_winners", enriched.drop(enriched.nlargest(3, "net_R").index)),
        ("exclude_top_1pct_winners", enriched.loc[enriched.net_R <= enriched.net_R.quantile(0.99)]),
    ):
        rows.append({"variant_id": variant_id, "slice": label, **summarize_architecture(frame)})
    for direction in ("Long", "Short"):
        group = enriched.loc[enriched.direction == direction]
        rows.append({"variant_id": variant_id, "slice": direction.lower(), **summarize_architecture(group)})
    return rows


def run_crt_setup_v2_study(
    frame: pd.DataFrame,
    *,
    start: str = "2024-01-01",
    end: str = "2026-06-26",
    config: FrozenConfig = FrozenConfig(),
    archived_trade_path: Path,
    output: Path,
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)

    frozen = run_backtest(frame, start=start, end=end, config=config)
    verify_retest_gated_parity(frozen.trades, archived_trade_path)
    baseline_parity = True

    original_trades = frozen.trades.loc[frozen.trades.model == "Control"].copy()
    retest_trades = frozen.trades.loc[frozen.trades.model == "Confirm"].copy()
    baselines = {
        "ORIGINAL": summarize_architecture(original_trades),
        "RETEST_GATED": summarize_architecture(retest_trades),
    }

    from .sequential_bos import run_sequential_bos_backtest

    control_result, _ = run_sequential_bos_backtest(
        frame,
        start=start,
        end=end,
        config=config,
        seq_config=SequentialBosConfig(
            bos_definition=BosDefinition.SWING_2_2,
            setup_bos_expiry_bars=3,
        ),
    )
    control_confirm = control_result.trades.loc[control_result.trades.model == "Confirm"].copy()
    baselines["SEQUENTIAL_BOS_CONTROL"] = summarize_architecture(control_confirm)

    variants = [
        SetupV2Variant(arch, qual, expiry)
        for arch in SetupV2Archetype
        for qual in SetupV2Qualification
        for expiry in SETUP_V2_EXPIRY_OPTIONS
    ]
    prepared = _prepare_data(frame, config)

    variant_rows: List[Dict[str, Any]] = []
    funnel_rows: List[Dict[str, Any]] = []
    trace_rows_all: List[Dict[str, Any]] = []
    trade_features_all: List[Dict[str, Any]] = []
    time_rows: List[Dict[str, Any]] = []
    outlier_rows: List[Dict[str, Any]] = []
    ordering_pass = True
    p_values: List[float] = []
    p_variant_ids: List[str] = []

    all_results = run_all_setup_v2_variants(
        frame,
        variants=variants,
        start=start,
        end=end,
        config=config,
        prepared=prepared,
    )

    for variant in variants:
        trades, counters, trace_rows, feature_rows = all_results[variant.variant_id]
        perf = summarize_architecture(trades)
        variant_rows.append({"variant_id": variant.variant_id, **asdict(variant), **perf})
        funnel_row = {"variant_id": variant.variant_id, **counters.export_v2()}
        variant_rows[-1]["qualified_setup_v2"] = funnel_row.get("qualified_setup_v2", 0)
        funnel_rows.append(funnel_row)
        trace_rows_all.extend(trace_rows)
        trade_features_all.extend(feature_rows)

        if counters.same_bar_bos_retest or counters.same_bar_retest_confirm:
            ordering_pass = False
        if not trades.empty:
            from .sequential_bos import verify_completed_trade_ordering

            try:
                verify_completed_trade_ordering(trades, data_index=prepared.index)
            except AssertionError:
                ordering_pass = False

        if not trades.empty:
            enriched = apply_costs(trades)
            p_values.append(_one_sample_pvalue_positive(enriched.net_R.to_numpy()))
            p_variant_ids.append(variant.variant_id)
            if perf["N"] >= 50 and perf["net_AvgR"] > 0 and perf["net_PF"] > 1:
                time_rows.extend(_robustness_slices(trades, config=config, variant_id=variant.variant_id))
                outlier_rows.extend(
                    row
                    for row in _robustness_slices(trades, config=config, variant_id=variant.variant_id)
                    if row["slice"]
                    in {
                        "exclude_best_trade",
                        "exclude_top_3_winners",
                        "exclude_top_1pct_winners",
                    }
                )

    adjusted = _benjamini_hochberg(p_values) if p_values else []
    mt_rows = [
        {
            "variant_id": vid,
            "raw_p_value_positive_mean": p,
            "bh_adjusted_p": adj,
            "fdr_survivor_005": adj <= 0.05,
        }
        for vid, p, adj in zip(p_variant_ids, p_values, adjusted)
    ]

    structure_legacy_rows: List[Dict[str, Any]] = []
    for arch in SetupV2Archetype:
        for expiry in SETUP_V2_EXPIRY_OPTIONS:
            struct = next(
                r
                for r in variant_rows
                if r["archetype"] == arch.value
                and r["qualification"] == SetupV2Qualification.STRUCTURE_ONLY.value
                and r["setup_bos_expiry_bars"] == expiry
            )
            legacy = next(
                r
                for r in variant_rows
                if r["archetype"] == arch.value
                and r["qualification"] == SetupV2Qualification.LEGACY_QUALIFIED.value
                and r["setup_bos_expiry_bars"] == expiry
            )
            structure_legacy_rows.append(
                {
                    "archetype": arch.value,
                    "setup_bos_expiry_bars": expiry,
                    "structure_setups": struct.get("qualified_setup_v2", float("nan")),
                    "legacy_setups": legacy.get("qualified_setup_v2", float("nan")),
                    "structure_entries": struct["N"],
                    "legacy_entries": legacy["N"],
                    "net_AvgR_delta": legacy["net_AvgR"] - struct["net_AvgR"],
                    "net_PF_delta": legacy["net_PF"] - struct["net_PF"],
                    "net_TotalR_delta": legacy["net_TotalR"] - struct["net_TotalR"],
                    "MaxDD_delta": legacy["MaxDD"] - struct["MaxDD"],
                }
            )

    verdict = _classify_study(variant_rows, mt_rows, baselines)

    pd.DataFrame(trace_rows_all).to_csv(output / "setup_v2_trace.csv", index=False)
    pd.DataFrame(funnel_rows).to_csv(output / "setup_v2_funnel.csv", index=False)
    pd.DataFrame(variant_rows).to_csv(output / "setup_v2_variant_results.csv", index=False)
    pd.DataFrame(time_rows).to_csv(output / "setup_v2_time_stability.csv", index=False)
    pd.DataFrame(outlier_rows).to_csv(output / "setup_v2_outlier_robustness.csv", index=False)
    pd.DataFrame(mt_rows).to_csv(output / "setup_v2_multiple_testing.csv", index=False)
    pd.DataFrame(trade_features_all).to_csv(output / "setup_v2_trade_features.csv", index=False)

    report = _build_report(
        thesis=current_crt_setup_thesis(),
        liquidity=liquidity_reference_definition(),
        baselines=baselines,
        variant_rows=variant_rows,
        mt_rows=mt_rows,
        verdict=verdict,
        baseline_parity=baseline_parity,
        ordering_pass=ordering_pass,
    )
    (output / "CRT_SETUP_V2_REPORT.md").write_text(report)

    with pd.ExcelWriter(output / "CRT_SETUP_V2.xlsx", engine="openpyxl") as writer:
        for name, df in (
            ("setup_v2_trace", pd.DataFrame(trace_rows_all)),
            ("setup_v2_funnel", pd.DataFrame(funnel_rows)),
            ("setup_v2_variant_results", pd.DataFrame(variant_rows)),
            ("setup_v2_time_stability", pd.DataFrame(time_rows)),
            ("setup_v2_outlier_robustness", pd.DataFrame(outlier_rows)),
            ("setup_v2_multiple_testing", pd.DataFrame(mt_rows)),
            ("setup_v2_trade_features", pd.DataFrame(trade_features_all)),
        ):
            _excel_safe(df).to_excel(writer, sheet_name=name[:31], index=False)

    manifest = {
        "baseline_parity": baseline_parity,
        "ordering_pass": ordering_pass,
        "baselines": baselines,
        "thesis": current_crt_setup_thesis(),
        "liquidity_reference": liquidity_reference_definition(),
        "variants": variant_rows,
        "multiple_testing": mt_rows,
        "verdict": verdict,
    }
    (output / "study_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return manifest


def _classify_study(
    variant_rows: List[Dict[str, Any]],
    mt_rows: List[Dict[str, Any]],
    baselines: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    df = pd.DataFrame(variant_rows)
    positive = df.loc[(df.net_AvgR > 0) & (df.net_PF > 1)]
    fdr_survivors = [row["variant_id"] for row in mt_rows if row.get("fdr_survivor_005")]

    best_row = df.sort_values(["net_TotalR", "net_AvgR"], ascending=False).iloc[0] if len(df) else None

    def best_for_archetype(letter: str) -> Dict[str, Any]:
        subset = df.loc[df.archetype == letter]
        if subset.empty:
            return {}
        row = subset.sort_values("net_TotalR", ascending=False).iloc[0]
        return {
            "variant_id": row.variant_id,
            "N": int(row.N),
            "net_AvgR": float(row.net_AvgR),
            "net_TotalR": float(row.net_TotalR),
            "net_PF": float(row.net_PF),
            "MaxDD": float(row.MaxDD),
        }

    struct = df.loc[df.qualification == SetupV2Qualification.STRUCTURE_ONLY.value]
    legacy = df.loc[df.qualification == SetupV2Qualification.LEGACY_QUALIFIED.value]
    struct_best = struct.sort_values("net_TotalR", ascending=False).iloc[0] if len(struct) else None
    legacy_best = legacy.sort_values("net_TotalR", ascending=False).iloc[0] if len(legacy) else None

    evidence = "NONE"
    classification = "D"
    if len(positive) >= 3 and len(fdr_survivors) >= 1:
        evidence = "PROMISING"
        classification = "B"
    elif len(positive) >= 1:
        evidence = "WEAK"
        classification = "C"
    elif best_row is not None and float(best_row.net_TotalR) > float(baselines["RETEST_GATED"]["net_TotalR"]):
        evidence = "WEAK"
        classification = "C"

    robust_positive = int((positive["N"] >= 50).sum()) if len(positive) else 0

    return {
        "best_architecture": _pick_best_architecture(df),
        "best_expiry_region": _pick_best_expiry(df),
        "archetype_best": {
            "A": best_for_archetype("A"),
            "B": best_for_archetype("B"),
            "C": best_for_archetype("C"),
        },
        "structure_vs_legacy": {
            "structure_best_totalR": float(struct_best.net_TotalR) if struct_best is not None else float("nan"),
            "legacy_best_totalR": float(legacy_best.net_TotalR) if legacy_best is not None else float("nan"),
            "better": (
                "structure_only"
                if struct_best is not None
                and legacy_best is not None
                and struct_best.net_TotalR > legacy_best.net_TotalR
                else "legacy_qualified"
                if legacy_best is not None
                and struct_best is not None
                and legacy_best.net_TotalR > struct_best.net_TotalR
                else "mixed"
            ),
        },
        "robust_positive_variants": robust_positive,
        "fdr_survivors": fdr_survivors,
        "evidence": evidence,
        "classification": classification,
        "recommendation": _recommendation(classification),
    }


def _pick_best_architecture(df: pd.DataFrame) -> str:
    if df.empty:
        return "NONE"
    grouped = df.groupby("archetype")["net_TotalR"].median()
    best = grouped.idxmax()
    if grouped[best] <= 0:
        return "NONE"
    return str(best)


def _pick_best_expiry(df: pd.DataFrame) -> str:
    if df.empty:
        return "NONE"
    grouped = df.groupby("setup_bos_expiry_bars")["net_TotalR"].median()
    best = grouped.idxmax()
    if grouped[best] <= 0:
        return "NONE"
    return str(int(best))


def _recommendation(classification: str) -> str:
    if classification in {"A", "B"}:
        return "Validate the best V2 archetype on fresh OOS data before any Pine implementation."
    if classification == "C":
        return "Keep frozen downstream pipeline; revisit CRT liquidity reference or setup thesis before further variants."
    return "Do not replace upstream setup with V2; current CRT setup thesis is not supported by this implementation."


def _build_report(
    *,
    thesis: Dict[str, str],
    liquidity: Dict[str, str],
    baselines: Dict[str, Dict[str, Any]],
    variant_rows: List[Dict[str, Any]],
    mt_rows: List[Dict[str, Any]],
    verdict: Dict[str, Any],
    baseline_parity: bool,
    ordering_pass: bool,
) -> str:
    lines = [
        "# CRT Setup V2 Study",
        "",
        f"Baseline parity: {'PASS' if baseline_parity else 'FAIL'}",
        f"Strict event ordering: {'PASS' if ordering_pass else 'FAIL'}",
        "",
        "## Current CRT setup thesis",
        "",
    ]
    for key, value in thesis.items():
        lines.append(f"- **{key}:** {value}")
    lines.extend(["", "## V2 liquidity reference", ""])
    for key, value in liquidity.items():
        lines.append(f"- **{key}:** {value}")
    lines.extend(["", "## Baselines", ""])
    for name, perf in baselines.items():
        lines.append(
            f"- **{name}:** N={perf['N']}, Net AvgR={perf['net_AvgR']:.4f}, "
            f"TotalR={perf['net_TotalR']:.2f}, PF={perf['net_PF']:.3f}, MaxDD={perf['MaxDD']:.2f}R"
        )
    lines.extend(["", "## Variant results", ""])
    for row in sorted(variant_rows, key=lambda r: r["net_TotalR"], reverse=True):
        lines.append(
            f"- **{row['variant_id']}:** N={int(row['N'])}, Net AvgR={row['net_AvgR']:.4f}, "
            f"TotalR={row['net_TotalR']:.2f}, PF={row['net_PF']:.3f}, MaxDD={row['MaxDD']:.2f}R"
        )
    lines.extend(
        [
            "",
            f"**Evidence:** {verdict['evidence']}",
            f"**Classification:** {verdict['classification']}",
            f"**FDR survivors:** {verdict['fdr_survivors']}",
        ]
    )
    return "\n".join(lines) + "\n"
