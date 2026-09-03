"""CRT signal-edge localization — event-level forward-return diagnostics."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .backtest import validation_window
from .bos_semantic_audit import CausalSwingEngine
from .config import FrozenConfig
from .crt_setup_v2 import (
    CRT_LIQUIDITY_REFERENCE,
    SetupV2Archetype,
    SetupV2Candidate,
    SetupV2Detector,
    SetupV2Funnel,
    SetupV2Qualification,
    _atr_percentile,
    _finite,
    _volume_ratio,
    passes_legacy_qualification,
)
from .indicators import htf_regime_name, is_in_session, session_bucket_name
from .resample import cme_session_date
from .liquidity import LiquidityEngine
from .models import SetupEvent, StructureEvent
from .sequential_bos import (
    BosDefinition,
    SequentialBosConfig,
    _prepare_data,
)
from .setup_engine import SetupEngine
from .structure import StructureEngine
HORIZONS = (3, 6, 12, 24, 48)
R_LEVELS = (0.5, 1.0, 1.5, 2.0)
SCORE_BIN_LABELS = ("<50", "50-59", "60-69", "70-79", "80-89", "90+")
COMPONENTS = (
    "setup_liquidity_component",
    "setup_structure_component",
    "setup_bias_component",
    "setup_displacement_component",
    "setup_session_component",
)
V2_FEATURES = (
    "wick_beyond_atr",
    "reclaim_distance_atr",
    "body_atr",
    "range_atr",
    "close_location",
    "sweep_to_setup_bars",
)
POPULATIONS = (
    "A_legacy_canonical",
    "B_v2_sweep_pre_qual",
    "C_v2b_reclaim_pre_qual",
    "D_v2b_reclaim_post_qual",
    "E_later_bos_from_D",
)
GATE_STAGES = ("setup", "bos", "retest", "confirm")
MIN_N_REPLICATED = 30


@dataclass
class RawEvent:
    population: str
    era: str
    event_id: int
    timestamp: pd.Timestamp
    bar_index: int
    direction: int
    direction_name: str
    close: float
    atr: float
    session: str
    htf_regime: str
    legacy_score: float
    setup_liquidity_component: float = float("nan")
    setup_structure_component: float = float("nan")
    setup_bias_component: float = float("nan")
    setup_displacement_component: float = float("nan")
    setup_session_component: float = float("nan")
    setup_component_sum: float = float("nan")
    liquidity_level: float = float("nan")
    sweep_bar: int = -1
    sweep_distance: float = float("nan")
    wick_beyond_atr: float = float("nan")
    reclaim_distance_atr: float = float("nan")
    body_atr: float = float("nan")
    range_atr: float = float("nan")
    close_location: float = float("nan")
    volume_ratio: float = float("nan")
    atr_percentile: float = float("nan")
    sweep_to_setup_bars: float = float("nan")
    setup_to_bos_bars: float = float("nan")
    bos_displacement_atr: float = float("nan")
    distance_active_structure: float = float("nan")
    distance_liquidity_level: float = float("nan")
    distance_session_high: float = float("nan")
    distance_session_low: float = float("nan")
    distance_prior_day_high: float = float("nan")
    distance_prior_day_low: float = float("nan")
    bars_since_bull_bos: float = float("nan")
    bars_since_bear_bos: float = float("nan")
    bars_since_ssl_sweep: float = float("nan")
    bars_since_bsl_sweep: float = float("nan")
    gate_stage: str = ""
    parent_setup_id: int = -1
    unavailable_features: str = ""


def score_bin(score: float) -> str:
    if not _finite(score):
        return "unknown"
    value = int(score)
    if value < 50:
        return "<50"
    if value < 60:
        return "50-59"
    if value < 70:
        return "60-69"
    if value < 80:
        return "70-79"
    if value < 90:
        return "80-89"
    return "90+"


def _component_attribution(
    *,
    direction: int,
    bar_index: int,
    row,
    setup_engine: SetupEngine,
    structure: StructureEvent,
    config: FrozenConfig,
) -> Dict[str, float]:
    recent_liquidity = (
        setup_engine.ssl_sweep_bar >= 0
        and bar_index - setup_engine.ssl_sweep_bar <= config.se_liquidity_lookback
        if direction == 1
        else setup_engine.bsl_sweep_bar >= 0
        and bar_index - setup_engine.bsl_sweep_bar <= config.se_liquidity_lookback
    )
    structure_bar = setup_engine.bull_structure_bar if direction == 1 else setup_engine.bear_structure_bar
    recent_structure = structure_bar >= 0 and bar_index - structure_bar <= config.se_liquidity_lookback
    choch = setup_engine.bull_is_choch if direction == 1 else setup_engine.bear_is_choch
    bias = int(structure.bias_after)
    favorable_bias = bias == direction
    liquidity_component = 25.0 if recent_liquidity else 0.0
    structure_component = (
        (30.0 if choch else (30.0 if favorable_bias else 20.0)) if recent_structure else 0.0
    )
    bias_component = 20.0 if favorable_bias else (10.0 if bias == 0 else 5.0)
    body_average = float(row.body_sma)
    directional_body = direction * (float(row.close) - float(row.open))
    displacement_component = (
        15.0
        if _finite(body_average)
        and body_average > 0
        and directional_body > config.se_displacement_multiplier * body_average
        else 0.0
    )
    session_component = 10.0 if is_in_session(row.Index, config.se_preferred_session) else 0.0
    total = min(
        liquidity_component + structure_component + bias_component + displacement_component + session_component,
        100.0,
    )
    return {
        "setup_liquidity_component": liquidity_component,
        "setup_structure_component": structure_component,
        "setup_bias_component": bias_component,
        "setup_displacement_component": displacement_component,
        "setup_session_component": session_component,
        "setup_component_sum": total,
    }


def _distance_features(
    *,
    direction: int,
    row,
    structure: StructureEvent,
    liquidity_level: float,
    session_high: float,
    session_low: float,
    prior_day_high: float,
    prior_day_low: float,
) -> Dict[str, float]:
    close = float(row.close)
    atr = float(row.atr) if _finite(row.atr) and float(row.atr) > 0 else float("nan")
    active = structure.active_high if direction == 1 else structure.active_low
    distance_active = (
        abs(close - float(active)) / atr if _finite(active) and _finite(atr) else float("nan")
    )
    distance_liq = (
        abs(close - liquidity_level) / atr if _finite(liquidity_level) and _finite(atr) else float("nan")
    )
    return {
        "distance_active_structure": distance_active,
        "distance_liquidity_level": distance_liq,
        "distance_session_high": (session_high - close) / atr if _finite(atr) else float("nan"),
        "distance_session_low": (close - session_low) / atr if _finite(atr) else float("nan"),
        "distance_prior_day_high": (prior_day_high - close) / atr if _finite(atr) else float("nan"),
        "distance_prior_day_low": (close - prior_day_low) / atr if _finite(atr) else float("nan"),
    }


def compute_forward_outcomes(data: pd.DataFrame, event: RawEvent) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    idx = int(event.bar_index)
    if idx >= len(data) - 1:
        return metrics
    atr = float(event.atr) if _finite(event.atr) and event.atr > 0 else float("nan")
    if not _finite(atr) or atr <= 0:
        return metrics
    highs = data["high"].to_numpy(dtype=float)
    lows = data["low"].to_numpy(dtype=float)
    closes = data["close"].to_numpy(dtype=float)
    event_close = float(event.close)
    direction = int(event.direction)
    risk = 1.5 * atr

    for horizon in HORIZONS:
        end_idx = min(idx + horizon, len(data) - 1)
        if end_idx <= idx:
            continue
        window_high = float(highs[idx + 1 : end_idx + 1].max())
        window_low = float(lows[idx + 1 : end_idx + 1].min())
        if direction == 1:
            metrics[f"mfe_{horizon}"] = (window_high - event_close) / atr
            metrics[f"mae_{horizon}"] = (event_close - window_low) / atr
            metrics[f"forward_return_{horizon}"] = (float(closes[end_idx]) - event_close) / atr
        else:
            metrics[f"mfe_{horizon}"] = (event_close - window_low) / atr
            metrics[f"mae_{horizon}"] = (window_high - event_close) / atr
            metrics[f"forward_return_{horizon}"] = (event_close - float(closes[end_idx])) / atr

    end_scan = min(len(data), idx + 49)
    hit_minus_one = False
    for level in R_LEVELS:
        metrics[f"plus_{str(level).replace('.', '_')}R_before_minus_1R"] = 0.0
    for i in range(idx + 1, end_scan):
        high = float(highs[i])
        low = float(lows[i])
        if direction == 1:
            favorable = high - event_close
            adverse = event_close - low
        else:
            favorable = event_close - low
            adverse = high - event_close
        if not hit_minus_one and adverse >= risk:
            hit_minus_one = True
        if not hit_minus_one:
            for level in R_LEVELS:
                key = f"plus_{str(level).replace('.', '_')}R_before_minus_1R"
                if metrics[key] == 0.0 and favorable >= level * risk:
                    metrics[key] = 1.0
        if hit_minus_one:
            break
    return metrics


def extract_events(
    frame: pd.DataFrame,
    *,
    era: str,
    start: str,
    end: str,
    config: FrozenConfig,
) -> Tuple[List[RawEvent], pd.DataFrame]:
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)
    data = _prepare_data(frame, config)
    structure_engine = StructureEngine(config)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)
    swing_22_engine = CausalSwingEngine(2, 2)
    swing_33_engine = CausalSwingEngine(3, 3)
    v2_detector = SetupV2Detector(
        archetype=SetupV2Archetype.NEXT_BAR,
        qualification=SetupV2Qualification.STRUCTURE_ONLY,
        config=config,
        data=data,
    )
    seq_config = SequentialBosConfig(bos_definition=BosDefinition.SWING_2_2, setup_bos_expiry_bars=6)
    v2_funnel = SetupV2Funnel(config, seq_config)
    events: List[RawEvent] = []
    event_id = 0
    setup_id = 0
    pending_gate_parent: Dict[str, int] = {}

    session_dates = pd.Series(cme_session_date(data.index), index=data.index)
    session_high = data.groupby(session_dates)["high"].cummax()
    session_low = data.groupby(session_dates)["low"].cummin()
    day_groups = data.groupby(session_dates)
    prior_day_high = day_groups["high"].shift(1).groupby(session_dates).transform("max")
    prior_day_low = day_groups["low"].shift(1).groupby(session_dates).transform("min")

    last_bull_bos = -1
    last_bear_bos = -1
    last_ssl = -1
    last_bsl = -1
    prev_state = 0

    for bar_index, row in enumerate(data.itertuples()):
        timestamp = row.Index
        structure = structure_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.structure_pivot_high),
            pivot_low=float(row.structure_pivot_low),
        )
        if structure.bull_bos:
            last_bull_bos = bar_index
        if structure.bear_bos:
            last_bear_bos = bar_index
        liquidity = liquidity_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.liquidity_pivot_high),
            pivot_low=float(row.liquidity_pivot_low),
        )
        if liquidity.ssl_sweep:
            last_ssl = bar_index
        if liquidity.bsl_sweep:
            last_bsl = bar_index
        setup_event = setup_engine.step(
            bar_index=bar_index,
            timestamp=timestamp,
            open_price=float(row.open),
            close=float(row.close),
            atr=float(row.atr),
            body_average=float(row.body_sma),
            htf_regime=int(row.htf_regime),
            structure=structure,
            liquidity=liquidity,
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

        if start_ts <= timestamp < end_exclusive:
            if setup_event.canonical:
                direction = setup_event.canonical_direction
                comps = _component_attribution(
                    direction=direction,
                    bar_index=bar_index,
                    row=row,
                    setup_engine=setup_engine,
                    structure=structure,
                    config=config,
                )
                dist = _distance_features(
                    direction=direction,
                    row=row,
                    structure=structure,
                    liquidity_level=float(row.crt_low if direction == 1 else row.crt_high),
                    session_high=float(session_high.iloc[bar_index]),
                    session_low=float(session_low.iloc[bar_index]),
                    prior_day_high=float(prior_day_high.iloc[bar_index])
                    if _finite(prior_day_high.iloc[bar_index])
                    else float("nan"),
                    prior_day_low=float(prior_day_low.iloc[bar_index])
                    if _finite(prior_day_low.iloc[bar_index])
                    else float("nan"),
                )
                event_id += 1
                setup_id += 1
                pending_gate_parent["legacy"] = setup_id
                events.append(
                    RawEvent(
                        population="A_legacy_canonical",
                        era=era,
                        event_id=event_id,
                        timestamp=timestamp,
                        bar_index=bar_index,
                        direction=direction,
                        direction_name="Long" if direction == 1 else "Short",
                        close=float(row.close),
                        atr=float(row.atr),
                        session=session_bucket_name(int(setup_event.session_bucket)),
                        htf_regime=htf_regime_name(int(setup_event.htf_regime)),
                        legacy_score=float(setup_event.canonical_score),
                        gate_stage="setup",
                        parent_setup_id=setup_id,
                        bars_since_bull_bos=bar_index - last_bull_bos if last_bull_bos >= 0 else float("nan"),
                        bars_since_bear_bos=bar_index - last_bear_bos if last_bear_bos >= 0 else float("nan"),
                        bars_since_ssl_sweep=bar_index - last_ssl if last_ssl >= 0 else float("nan"),
                        bars_since_bsl_sweep=bar_index - last_bsl if last_bsl >= 0 else float("nan"),
                        unavailable_features="VWAP_not_available",
                        **comps,
                        **dist,
                    )
                )

            crt_high = float(row.crt_high)
            crt_low = float(row.crt_low)
            long_sweep = _finite(crt_low) and float(row.low) < crt_low
            short_sweep = _finite(crt_high) and float(row.high) > crt_high
            long_same = long_sweep and float(row.close) > crt_low
            short_same = short_sweep and float(row.close) < crt_high
            if long_sweep and not long_same:
                event_id += 1
                atr_val = float(row.atr) if _finite(row.atr) else float("nan")
                wick = crt_low - float(row.low)
                events.append(
                    RawEvent(
                        population="B_v2_sweep_pre_qual",
                        era=era,
                        event_id=event_id,
                        timestamp=timestamp,
                        bar_index=bar_index,
                        direction=1,
                        direction_name="Long",
                        close=float(row.close),
                        atr=atr_val,
                        session=session_bucket_name(int(setup_event.session_bucket)),
                        htf_regime=htf_regime_name(int(setup_event.htf_regime)),
                        legacy_score=float(setup_event.long_score),
                        liquidity_level=crt_low,
                        sweep_bar=bar_index,
                        sweep_distance=wick,
                        wick_beyond_atr=wick / atr_val if _finite(atr_val) and atr_val > 0 else float("nan"),
                        volume_ratio=_volume_ratio(data, bar_index, float(row.volume)),
                        atr_percentile=_atr_percentile(data, bar_index, atr_val),
                        unavailable_features="reclaim_features_not_yet_known;VWAP_not_available",
                    )
                )
            if short_sweep and not short_same:
                event_id += 1
                atr_val = float(row.atr) if _finite(row.atr) else float("nan")
                wick = float(row.high) - crt_high
                events.append(
                    RawEvent(
                        population="B_v2_sweep_pre_qual",
                        era=era,
                        event_id=event_id,
                        timestamp=timestamp,
                        bar_index=bar_index,
                        direction=-1,
                        direction_name="Short",
                        close=float(row.close),
                        atr=atr_val,
                        session=session_bucket_name(int(setup_event.session_bucket)),
                        htf_regime=htf_regime_name(int(setup_event.htf_regime)),
                        legacy_score=float(setup_event.short_score),
                        liquidity_level=crt_high,
                        sweep_bar=bar_index,
                        sweep_distance=wick,
                        wick_beyond_atr=wick / atr_val if _finite(atr_val) and atr_val > 0 else float("nan"),
                        volume_ratio=_volume_ratio(data, bar_index, float(row.volume)),
                        atr_percentile=_atr_percentile(data, bar_index, atr_val),
                        unavailable_features="reclaim_features_not_yet_known;VWAP_not_available",
                    )
                )

            candidate = v2_detector.step(
                bar_index=bar_index,
                timestamp=timestamp,
                open_price=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                atr=float(row.atr),
                crt_high=crt_high,
                crt_low=crt_low,
                setup_event=setup_event,
                funnel_idle=v2_funnel.state == 0,
            )
            if candidate is not None and candidate.reclaim_mode == "next_bar":
                direction = candidate.direction
                comps = _component_attribution(
                    direction=direction,
                    bar_index=bar_index,
                    row=row,
                    setup_engine=setup_engine,
                    structure=structure,
                    config=config,
                )
                dist = _distance_features(
                    direction=direction,
                    row=row,
                    structure=structure,
                    liquidity_level=candidate.liquidity_level,
                    session_high=float(session_high.iloc[bar_index]),
                    session_low=float(session_low.iloc[bar_index]),
                    prior_day_high=float(prior_day_high.iloc[bar_index])
                    if _finite(prior_day_high.iloc[bar_index])
                    else float("nan"),
                    prior_day_low=float(prior_day_low.iloc[bar_index])
                    if _finite(prior_day_low.iloc[bar_index])
                    else float("nan"),
                )
                population = (
                    "D_v2b_reclaim_post_qual" if candidate.legacy_qualified else "C_v2b_reclaim_pre_qual"
                )
                event_id += 1
                setup_id += 1
                pending_gate_parent["v2"] = setup_id
                events.append(
                    RawEvent(
                        population=population,
                        era=era,
                        event_id=event_id,
                        timestamp=timestamp,
                        bar_index=bar_index,
                        direction=direction,
                        direction_name="Long" if direction == 1 else "Short",
                        close=float(row.close),
                        atr=float(row.atr),
                        session=candidate.session,
                        htf_regime=candidate.htf_regime,
                        legacy_score=float(candidate.legacy_score),
                        liquidity_level=candidate.liquidity_level,
                        sweep_bar=candidate.sweep_bar,
                        sweep_distance=candidate.sweep_distance,
                        wick_beyond_atr=candidate.wick_beyond_atr,
                        reclaim_distance_atr=candidate.reclaim_distance_atr,
                        body_atr=candidate.body_atr,
                        range_atr=candidate.range_atr,
                        close_location=candidate.close_location,
                        volume_ratio=candidate.volume_ratio,
                        atr_percentile=candidate.atr_percentile,
                        sweep_to_setup_bars=candidate.setup_bar - candidate.sweep_bar,
                        gate_stage="setup",
                        parent_setup_id=setup_id,
                        unavailable_features="VWAP_not_available",
                        **comps,
                        **dist,
                    )
                )
                if candidate.legacy_qualified:
                    v2_funnel.arm_setup(candidate, setup_event, setup_id)

            prev_state = v2_funnel.state
            active_before = v2_funnel.active_candidate
            entries = v2_funnel.step_v2(
                bar_index=bar_index,
                timestamp=timestamp,
                open_price=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                atr=float(row.atr),
                structure=structure,
                swing_22=swing_22,
                swing_33=swing_33,
            )
            if v2_funnel.state == 2 and prev_state == 1 and v2_funnel.active_candidate is not None:
                candidate = v2_funnel.active_candidate
                direction = candidate.direction
                atr_val = float(row.atr) if _finite(row.atr) else float("nan")
                displacement = abs(float(row.close) - v2_funnel.bos_level) / atr_val if _finite(atr_val) else float("nan")
                event_id += 1
                events.append(
                    RawEvent(
                        population="E_later_bos_from_D",
                        era=era,
                        event_id=event_id,
                        timestamp=timestamp,
                        bar_index=bar_index,
                        direction=direction,
                        direction_name="Long" if direction == 1 else "Short",
                        close=float(row.close),
                        atr=atr_val,
                        session=candidate.session,
                        htf_regime=candidate.htf_regime,
                        legacy_score=float(candidate.legacy_score),
                        liquidity_level=candidate.liquidity_level,
                        sweep_bar=candidate.sweep_bar,
                        wick_beyond_atr=candidate.wick_beyond_atr,
                        reclaim_distance_atr=candidate.reclaim_distance_atr,
                        body_atr=candidate.body_atr,
                        range_atr=candidate.range_atr,
                        close_location=candidate.close_location,
                        setup_to_bos_bars=bar_index - candidate.setup_bar,
                        bos_displacement_atr=displacement,
                        gate_stage="bos",
                        parent_setup_id=pending_gate_parent.get("v2", -1),
                        unavailable_features="VWAP_not_available",
                    )
                )
            if v2_funnel.state == 3 and prev_state == 2 and v2_funnel.active_candidate is not None:
                candidate = v2_funnel.active_candidate
                event_id += 1
                events.append(
                    RawEvent(
                        population="D_v2b_reclaim_post_qual",
                        era=era,
                        event_id=event_id,
                        timestamp=timestamp,
                        bar_index=bar_index,
                        direction=candidate.direction,
                        direction_name="Long" if candidate.direction == 1 else "Short",
                        close=float(row.close),
                        atr=float(row.atr),
                        session=candidate.session,
                        htf_regime=candidate.htf_regime,
                        legacy_score=float(candidate.legacy_score),
                        gate_stage="retest",
                        parent_setup_id=pending_gate_parent.get("v2", -1),
                        unavailable_features="VWAP_not_available",
                    )
                )
            if any(entry.model == "Confirm" for entry in entries) and active_before is not None:
                candidate = active_before
                event_id += 1
                events.append(
                    RawEvent(
                        population="D_v2b_reclaim_post_qual",
                        era=era,
                        event_id=event_id,
                        timestamp=timestamp,
                        bar_index=bar_index,
                        direction=candidate.direction,
                        direction_name="Long" if candidate.direction == 1 else "Short",
                        close=float(row.close),
                        atr=float(row.atr),
                        session=candidate.session,
                        htf_regime=candidate.htf_regime,
                        legacy_score=float(candidate.legacy_score),
                        gate_stage="confirm",
                        parent_setup_id=pending_gate_parent.get("v2", -1),
                        unavailable_features="VWAP_not_available",
                    )
                )

    return events, data


def events_to_frame(events: Sequence[RawEvent], data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for event in events:
        base = asdict(event)
        base["timestamp"] = event.timestamp
        forward = compute_forward_outcomes(data, event)
        base.update(forward)
        rows.append(base)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values(["era", "population", "timestamp"]).reset_index(drop=True)
    return frame


def _spearman(left: pd.Series, right: pd.Series) -> float:
    aligned = pd.concat([left.astype(float), right.astype(float)], axis=1).dropna()
    if len(aligned) < 5:
        return float("nan")
    ranked = aligned.rank(method="average")
    return float(ranked.iloc[:, 0].corr(ranked.iloc[:, 1]))


def _median_metric(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return float("nan")
    series = frame[column].astype(float)
    series = series[series.map(_finite)]
    return float(series.median()) if not series.empty else float("nan")


def _rate_metric(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return float("nan")
    series = frame[column].astype(float)
    series = series[series.map(_finite)]
    return float(series.mean()) if not series.empty else float("nan")


def bootstrap_ci(values: np.ndarray, *, stat: str = "median", n: int = 1000, seed: int = 42) -> Tuple[float, float]:
    values = values.astype(float)
    values = values[np.isfinite(values)]
    if len(values) < 5:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(n):
        draw = rng.choice(values, size=len(values), replace=True)
        samples.append(float(np.median(draw)) if stat == "median" else float(np.mean(draw)))
    return float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def classify_effect(dev: float, oos: float, *, dev_n: int, oos_n: int, dev_robust: float, oos_robust: float) -> str:
    if not (_finite(dev) and _finite(oos)):
        return "NO_INFORMATION"
    if dev_n < MIN_N_REPLICATED or oos_n < MIN_N_REPLICATED:
        return "WEAK_INFORMATION"
    same = (dev > 0 and oos > 0) or (dev < 0 and oos < 0)
    if not same:
        return "REVERSED" if abs(dev) > 0.01 and abs(oos) > 0.01 else "ERA_DEPENDENT"
    if abs(dev) < 0.02 and abs(oos) < 0.02:
        return "NO_INFORMATION"
    robust_same = (dev_robust > 0 and oos_robust > 0) or (dev_robust < 0 and oos_robust < 0)
    if same and robust_same:
        return "REPLICATED_INFORMATION"
    if same:
        return "WEAK_INFORMATION"
    return "ERA_DEPENDENT"


def build_edge_map(all_events: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    metrics = [f"mfe_{h}" for h in HORIZONS] + [f"mae_{h}" for h in HORIZONS] + [f"forward_return_{h}" for h in HORIZONS]
    metrics += [f"plus_{str(level).replace('.', '_')}R_before_minus_1R" for level in R_LEVELS]
    for population in POPULATIONS:
        for metric in metrics:
            dev = all_events.loc[(all_events.population == population) & (all_events.era == "development")]
            oos = all_events.loc[(all_events.population == population) & (all_events.era == "failed_oos")]
            dev_effect = _median_metric(dev, metric) if metric.startswith(("mfe", "mae", "forward")) else _rate_metric(dev, metric)
            oos_effect = _median_metric(oos, metric) if metric.startswith(("mfe", "mae", "forward")) else _rate_metric(oos, metric)
            dev_trim = dev.copy()
            oos_trim = oos.copy()
            if metric.startswith("mfe") and not dev.empty:
                cutoff = dev[metric].quantile(0.99)
                dev_trim = dev.loc[dev[metric] <= cutoff]
            if metric.startswith("mfe") and not oos.empty:
                cutoff = oos[metric].quantile(0.99)
                oos_trim = oos.loc[oos[metric] <= cutoff]
            dev_robust = _median_metric(dev_trim, metric) if metric.startswith(("mfe", "mae", "forward")) else _rate_metric(dev_trim, metric)
            oos_robust = _median_metric(oos_trim, metric) if metric.startswith(("mfe", "mae", "forward")) else _rate_metric(oos_trim, metric)
            classification = classify_effect(
                dev_effect,
                oos_effect,
                dev_n=len(dev),
                oos_n=len(oos),
                dev_robust=dev_robust,
                oos_robust=oos_robust,
            )
            rows.append(
                {
                    "feature": population,
                    "population": population,
                    "metric": metric,
                    "development_effect": dev_effect,
                    "oos_effect": oos_effect,
                    "same_direction": (dev_effect > 0 and oos_effect > 0) or (dev_effect < 0 and oos_effect < 0),
                    "development_N": len(dev),
                    "oos_N": len(oos),
                    "outlier_robust": classification == "REPLICATED_INFORMATION",
                    "classification": classification,
                }
            )
    for component in COMPONENTS + V2_FEATURES:
        for metric in ("mfe_12", "forward_return_12", "plus_1_0R_before_minus_1R"):
            if metric not in all_events.columns and component not in all_events.columns:
                continue
            for population in ("A_legacy_canonical", "C_v2b_reclaim_pre_qual", "D_v2b_reclaim_post_qual"):
                dev = all_events.loc[(all_events.population == population) & (all_events.era == "development")]
                oos = all_events.loc[(all_events.population == population) & (all_events.era == "failed_oos")]
                if component not in dev.columns:
                    continue
                dev_valid = dev.loc[dev[component].map(_finite)]
                oos_valid = oos.loc[oos[component].map(_finite)]
                if len(dev_valid) < MIN_N_REPLICATED or len(oos_valid) < MIN_N_REPLICATED:
                    continue
                corr_dev = _spearman(dev_valid[component], dev_valid[metric])
                corr_oos = _spearman(oos_valid[component], oos_valid[metric])
                classification = classify_effect(
                    float(corr_dev) if _finite(corr_dev) else float("nan"),
                    float(corr_oos) if _finite(corr_oos) else float("nan"),
                    dev_n=len(dev_valid),
                    oos_n=len(oos_valid),
                    dev_robust=float(corr_dev) if _finite(corr_dev) else 0.0,
                    oos_robust=float(corr_oos) if _finite(corr_oos) else 0.0,
                )
                rows.append(
                    {
                        "feature": component,
                        "population": population,
                        "metric": metric,
                        "development_effect": corr_dev,
                        "oos_effect": corr_oos,
                        "same_direction": (_finite(corr_dev) and _finite(corr_oos) and corr_dev * corr_oos > 0),
                        "development_N": len(dev_valid),
                        "oos_N": len(oos_valid),
                        "outlier_robust": classification == "REPLICATED_INFORMATION",
                        "classification": classification,
                    }
                )
    return pd.DataFrame(rows)


def population_summary(all_events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for era in ("development", "failed_oos"):
        for population in POPULATIONS:
            for direction in ("Long", "Short", "All"):
                subset = all_events.loc[(all_events.era == era) & (all_events.population == population)]
                if direction != "All":
                    subset = subset.loc[subset.direction_name == direction]
                rows.append(
                    {
                        "era": era,
                        "population": population,
                        "direction": direction,
                        "event_count": len(subset),
                    }
                )
    return pd.DataFrame(rows)


def forward_outcome_summary(all_events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    metrics = [("mfe", h) for h in HORIZONS] + [("mae", h) for h in HORIZONS] + [("forward_return", h) for h in HORIZONS]
    metrics += [("plus_1_0R_before_minus_1R", None), ("plus_2_0R_before_minus_1R", None)]
    for era in ("development", "failed_oos"):
        for population in POPULATIONS:
            for direction in ("Long", "Short", "All"):
                subset = all_events.loc[(all_events.era == era) & (all_events.population == population)]
                if direction != "All":
                    subset = subset.loc[subset.direction_name == direction]
                for name, horizon in metrics:
                    column = name if horizon is None else f"{name}_{horizon}"
                    if column not in subset.columns:
                        continue
                    value = _median_metric(subset, column) if horizon is not None or "plus" not in column else _rate_metric(subset, column)
                    rows.append(
                        {
                            "era": era,
                            "population": population,
                            "direction": direction,
                            "metric": column,
                            "value": value,
                            "N": len(subset),
                        }
                    )
    return pd.DataFrame(rows)


def direction_analysis(all_events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for population in POPULATIONS:
        for direction in ("Long", "Short"):
            dev = all_events.loc[
                (all_events.population == population)
                & (all_events.era == "development")
                & (all_events.direction_name == direction)
            ]
            oos = all_events.loc[
                (all_events.population == population)
                & (all_events.era == "failed_oos")
                & (all_events.direction_name == direction)
            ]
            dev_mfe = _median_metric(dev, "mfe_12")
            oos_mfe = _median_metric(oos, "mfe_12")
            dev_ret = _median_metric(dev, "forward_return_12")
            oos_ret = _median_metric(oos, "forward_return_12")
            if not (_finite(dev_mfe) and _finite(oos_mfe)):
                behavior = "WEAK"
            elif (dev_mfe > 0 and oos_mfe > 0) or (dev_mfe < 0 and oos_mfe < 0):
                behavior = "CONSISTENT"
            elif (dev_mfe > 0) != (oos_mfe > 0):
                behavior = "REVERSED"
            else:
                behavior = "ERA_DEPENDENT"
            rows.append(
                {
                    "population": population,
                    "direction": direction,
                    "development_mfe12": dev_mfe,
                    "failed_oos_mfe12": oos_mfe,
                    "development_return12": dev_ret,
                    "failed_oos_return12": oos_ret,
                    "development_N": len(dev),
                    "failed_oos_N": len(oos),
                    "behavior": behavior,
                }
            )
    return pd.DataFrame(rows)


def legacy_score_bins(all_events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for era in ("development", "failed_oos"):
        for population in POPULATIONS:
            subset = all_events.loc[(all_events.era == era) & (all_events.population == population)]
            if subset.empty:
                continue
            subset = subset.copy()
            subset["score_bin"] = subset["legacy_score"].map(score_bin)
            for bin_label in SCORE_BIN_LABELS:
                group = subset.loc[subset.score_bin == bin_label]
                rows.append(
                    {
                        "era": era,
                        "population": population,
                        "score_bin": bin_label,
                        "N": len(group),
                        "median_mfe_12": _median_metric(group, "mfe_12"),
                        "median_mae_12": _median_metric(group, "mae_12"),
                        "median_forward_return_12": _median_metric(group, "forward_return_12"),
                        "plus_1R_before_minus_1R": _rate_metric(group, "plus_1_0R_before_minus_1R"),
                        "plus_2R_before_minus_1R": _rate_metric(group, "plus_2_0R_before_minus_1R"),
                    }
                )
            valid = subset.loc[subset.legacy_score.map(_finite)]
            if len(valid) >= 5:
                for metric in ("mfe_12", "mae_12", "forward_return_12"):
                    corr = _spearman(valid["legacy_score"], valid[metric])
                    rows.append(
                        {
                            "era": era,
                            "population": population,
                            "score_bin": f"spearman_score_vs_{metric}",
                            "N": len(valid),
                            "median_mfe_12": float("nan"),
                            "median_mae_12": float("nan"),
                            "median_forward_return_12": float("nan"),
                            "plus_1R_before_minus_1R": float("nan"),
                            "plus_2R_before_minus_1R": float(corr),
                        }
                    )
    return pd.DataFrame(rows)


def legacy_component_analysis(all_events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    populations = ("A_legacy_canonical", "C_v2b_reclaim_pre_qual", "D_v2b_reclaim_post_qual")
    metrics = ("mfe_12", "mae_12", "forward_return_12", "plus_1_0R_before_minus_1R")
    for component in COMPONENTS:
        for population in populations:
            for era in ("development", "failed_oos"):
                subset = all_events.loc[(all_events.population == population) & (all_events.era == era)]
                valid = subset.loc[subset[component].map(_finite)]
                if len(valid) < 10:
                    continue
                for metric in metrics:
                    if metric not in valid.columns:
                        continue
                    values = valid[component].astype(float).to_numpy()
                    outcomes = valid[metric].astype(float).to_numpy()
                    mask = np.isfinite(values) & np.isfinite(outcomes)
                    if mask.sum() < 10:
                        continue
                    corr = _spearman(pd.Series(values[mask]), pd.Series(outcomes[mask]))
                    lo, hi = bootstrap_ci(outcomes[mask])
                    rows.append(
                        {
                            "component": component,
                            "population": population,
                            "era": era,
                            "metric": metric,
                            "N": int(mask.sum()),
                            "spearman": float(corr),
                            "median_outcome": float(np.median(outcomes[mask])),
                            "bootstrap_ci_low": lo,
                            "bootstrap_ci_high": hi,
                        }
                    )
    return pd.DataFrame(rows)


def v2_liquidity_analysis(all_events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    populations = ("B_v2_sweep_pre_qual", "C_v2b_reclaim_pre_qual", "D_v2b_reclaim_post_qual")
    for feature in V2_FEATURES:
        for population in populations:
            for era in ("development", "failed_oos"):
                subset = all_events.loc[(all_events.population == population) & (all_events.era == era)]
                valid = subset.loc[subset[feature].map(_finite)]
                if len(valid) < 20:
                    continue
                valid = valid.copy()
                valid["feature_quantile"] = pd.qcut(valid[feature], 4, duplicates="drop")
                for quantile, group in valid.groupby("feature_quantile", observed=False):
                    rows.append(
                        {
                            "feature": feature,
                            "population": population,
                            "era": era,
                            "quantile": str(quantile),
                            "N": len(group),
                            "median_mfe_12": _median_metric(group, "mfe_12"),
                            "median_mae_12": _median_metric(group, "mae_12"),
                            "median_forward_return_12": _median_metric(group, "forward_return_12"),
                            "plus_1R_before_minus_1R": _rate_metric(group, "plus_1_0R_before_minus_1R"),
                        }
                    )
    return pd.DataFrame(rows)


def bos_information_value(all_events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for era in ("development", "failed_oos"):
        setup = all_events.loc[
            (all_events.era == era)
            & (all_events.population == "D_v2b_reclaim_post_qual")
            & (all_events.gate_stage == "setup")
        ]
        bos = all_events.loc[(all_events.era == era) & (all_events.population == "E_later_bos_from_D")]
        rows.append(
            {
                "era": era,
                "stage": "setup_reclaim_close",
                "N": len(setup),
                "median_mfe_12": _median_metric(setup, "mfe_12"),
                "median_mae_12": _median_metric(setup, "mae_12"),
                "median_forward_return_12": _median_metric(setup, "forward_return_12"),
                "plus_1R_before_minus_1R": _rate_metric(setup, "plus_1_0R_before_minus_1R"),
                "plus_2R_before_minus_1R": _rate_metric(setup, "plus_2_0R_before_minus_1R"),
            }
        )
        rows.append(
            {
                "era": era,
                "stage": "later_bos_close",
                "N": len(bos),
                "median_mfe_12": _median_metric(bos, "mfe_12"),
                "median_mae_12": _median_metric(bos, "mae_12"),
                "median_forward_return_12": _median_metric(bos, "forward_return_12"),
                "plus_1R_before_minus_1R": _rate_metric(bos, "plus_1_0R_before_minus_1R"),
                "plus_2R_before_minus_1R": _rate_metric(bos, "plus_2_0R_before_minus_1R"),
            }
        )
        if len(setup):
            rows.append(
                {
                    "era": era,
                    "stage": "selection_rate_setup_to_bos",
                    "N": len(setup),
                    "median_mfe_12": len(bos) / len(setup),
                    "median_mae_12": float("nan"),
                    "median_forward_return_12": float("nan"),
                    "plus_1R_before_minus_1R": float("nan"),
                    "plus_2R_before_minus_1R": float("nan"),
                }
            )
    return pd.DataFrame(rows)


def gate_information_funnel(all_events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for era in ("development", "failed_oos"):
        setup = all_events.loc[
            (all_events.era == era)
            & (all_events.population == "D_v2b_reclaim_post_qual")
            & (all_events.gate_stage == "setup")
        ]
        bos = all_events.loc[(all_events.era == era) & (all_events.population == "E_later_bos_from_D")]
        retest = all_events.loc[
            (all_events.era == era)
            & (all_events.population == "D_v2b_reclaim_post_qual")
            & (all_events.gate_stage == "retest")
        ]
        confirm = all_events.loc[
            (all_events.era == era)
            & (all_events.population == "D_v2b_reclaim_post_qual")
            & (all_events.gate_stage == "confirm")
        ]
        total = len(setup)
        for stage, subset in (("setup", setup), ("bos", bos), ("retest", retest), ("confirm", confirm)):
            rows.append(
                {
                    "era": era,
                    "gate_stage": stage,
                    "N": len(subset),
                    "retention_vs_setup": len(subset) / total if total else float("nan"),
                    "median_mfe_12": _median_metric(subset, "mfe_12"),
                    "median_mae_12": _median_metric(subset, "mae_12"),
                    "median_forward_return_12": _median_metric(subset, "forward_return_12"),
                    "plus_1R_before_minus_1R": _rate_metric(subset, "plus_1_0R_before_minus_1R"),
                    "plus_2R_before_minus_1R": _rate_metric(subset, "plus_2_0R_before_minus_1R"),
                }
            )
    return pd.DataFrame(rows)


def regime_session_analysis(all_events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for era in ("development", "failed_oos"):
        for population in POPULATIONS:
            subset = all_events.loc[(all_events.era == era) & (all_events.population == population)]
            for column in ("session", "htf_regime"):
                for label, group in subset.groupby(column):
                    if len(group) < 20:
                        continue
                    rows.append(
                        {
                            "era": era,
                            "population": population,
                            "dimension": column,
                            "label": label,
                            "N": len(group),
                            "median_mfe_12": _median_metric(group, "mfe_12"),
                            "median_forward_return_12": _median_metric(group, "forward_return_12"),
                            "plus_1R_before_minus_1R": _rate_metric(group, "plus_1_0R_before_minus_1R"),
                        }
                    )
    return pd.DataFrame(rows)


def verify_trade_counts(config: FrozenConfig) -> Dict[str, Any]:
    dev_row = pd.read_csv(
        Path(__file__).resolve().parent / "results/crt_setup_v2/setup_v2_variant_results.csv"
    )
    dev_row = dev_row.loc[dev_row.variant_id == "V2-B-LEGACY-EXP6"].iloc[0]
    oos_manifest = json.loads(
        (Path(__file__).resolve().parent / "results/crt_setup_v2_oos/study_manifest.json").read_text()
    )
    dev_n = int(dev_row.N)
    oos_n = int(oos_manifest["result"]["N"])
    return {
        "development_trade_count": dev_n,
        "development_expected": 193,
        "development_pass": dev_n == 193,
        "failed_oos_trade_count": oos_n,
        "failed_oos_expected": 197,
        "failed_oos_pass": oos_n == 197,
    }


def population_classification(edge_map: pd.DataFrame, population: str, metric: str = "forward_return_12") -> str:
    rows = edge_map.loc[(edge_map.population == population) & (edge_map.metric == metric)]
    if rows.empty:
        return "NO_INFORMATION"
    return str(rows.iloc[0]["classification"])


def run_signal_edge_study(
    dev_frame: pd.DataFrame,
    oos_frame: pd.DataFrame,
    *,
    output: Path,
    config: FrozenConfig = FrozenConfig(),
    use_cached_events: bool = False,
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    validation = verify_trade_counts(config)

    dev_path = output / "event_dataset_development.csv"
    oos_path = output / "event_dataset_failed_oos.csv"
    if use_cached_events and dev_path.exists() and oos_path.exists():
        print("Loading cached event datasets...", flush=True)
        dev_df = pd.read_csv(dev_path)
        oos_df = pd.read_csv(oos_path)
    else:
        print("Extracting development events...", flush=True)
        dev_events, dev_data = extract_events(
            dev_frame, era="development", start="2024-01-01", end="2026-06-26", config=config
        )
        print(f"Development raw events: {len(dev_events)}", flush=True)
        print("Extracting failed-OOS observed events...", flush=True)
        oos_events, oos_data = extract_events(
            oos_frame, era="failed_oos", start="2018-01-01", end="2020-11-30", config=config
        )
        print(f"Failed-OOS raw events: {len(oos_events)}", flush=True)
        print("Computing forward outcomes (development)...", flush=True)
        dev_df = events_to_frame(dev_events, dev_data)
        print("Computing forward outcomes (failed-OOS)...", flush=True)
        oos_df = events_to_frame(oos_events, oos_data)
        dev_df.to_csv(dev_path, index=False)
        oos_df.to_csv(oos_path, index=False)
    all_events = pd.concat([dev_df, oos_df], ignore_index=True)

    lookahead_pass = True
    if not use_cached_events:
        for frame, data in ((dev_df, dev_data), (oos_df, oos_data)):
            for _, row in frame.iterrows():
                if int(row.bar_index) >= len(data) - 1:
                    continue
                if pd.Timestamp(row.timestamp) >= pd.Timestamp(data.index[int(row.bar_index) + 1]):
                    lookahead_pass = False
    else:
        for frame in (dev_df, oos_df):
            if "bar_index" not in frame.columns:
                continue
            if (frame["bar_index"].astype(int) < 0).any():
                lookahead_pass = False

    population_df = population_summary(all_events)
    forward_df = forward_outcome_summary(all_events)
    direction_df = direction_analysis(all_events)
    score_df = legacy_score_bins(all_events)
    component_df = legacy_component_analysis(all_events)
    v2_df = v2_liquidity_analysis(all_events)
    bos_df = bos_information_value(all_events)
    gate_df = gate_information_funnel(all_events)
    regime_df = regime_session_analysis(all_events)
    edge_map = build_edge_map(all_events)

    population_df.to_csv(output / "population_summary.csv", index=False)
    forward_df.to_csv(output / "forward_outcomes.csv", index=False)
    direction_df.to_csv(output / "direction_analysis.csv", index=False)
    score_df.to_csv(output / "legacy_score_bins.csv", index=False)
    component_df.to_csv(output / "legacy_component_analysis.csv", index=False)
    v2_df.to_csv(output / "v2_liquidity_analysis.csv", index=False)
    bos_df.to_csv(output / "bos_information_value.csv", index=False)
    gate_df.to_csv(output / "gate_information_funnel.csv", index=False)
    regime_df.to_csv(output / "regime_session_analysis.csv", index=False)
    edge_map.to_csv(output / "edge_map.csv", index=False)

    replicated_components = []
    for component in COMPONENTS:
        dev_rows = component_df.loc[
            (component_df.component == component) & (component_df.metric == "forward_return_12") & (component_df.era == "development")
        ]
        oos_rows = component_df.loc[
            (component_df.component == component) & (component_df.metric == "forward_return_12") & (component_df.era == "failed_oos")
        ]
        if dev_rows.empty or oos_rows.empty:
            continue
        dev_corr = float(dev_rows.iloc[0]["spearman"])
        oos_corr = float(oos_rows.iloc[0]["spearman"])
        if classify_effect(dev_corr, oos_corr, dev_n=int(dev_rows.iloc[0]["N"]), oos_n=int(oos_rows.iloc[0]["N"]), dev_robust=dev_corr, oos_robust=oos_corr) == "REPLICATED_INFORMATION":
            replicated_components.append(component)

    replicated_v2 = edge_map.loc[
        (edge_map.feature.isin(V2_FEATURES)) & (edge_map.classification == "REPLICATED_INFORMATION")
    ].feature.unique().tolist()

    def gate_stage_classification(stage: str) -> str:
        dev = gate_df.loc[(gate_df.era == "development") & (gate_df.gate_stage == stage)]
        oos = gate_df.loc[(gate_df.era == "failed_oos") & (gate_df.gate_stage == stage)]
        if dev.empty or oos.empty:
            return "NO_INFORMATION"
        return classify_effect(
            float(dev.iloc[0]["median_forward_return_12"]),
            float(oos.iloc[0]["median_forward_return_12"]),
            dev_n=int(dev.iloc[0]["N"]),
            oos_n=int(oos.iloc[0]["N"]),
            dev_robust=float(dev.iloc[0]["median_forward_return_12"]),
            oos_robust=float(oos.iloc[0]["median_forward_return_12"]),
        )

    long_short_behavior = direction_df.groupby("direction")["behavior"].apply(lambda s: s.mode().iloc[0] if not s.empty else "WEAK").to_dict()
    long_short_class = "CONSISTENT" if all(v == "CONSISTENT" for v in long_short_behavior.values()) else (
        "REVERSED" if any(v == "REVERSED" for v in long_short_behavior.values()) else "ERA_DEPENDENT"
    )

    classifications = {
        "original_crt": population_classification(edge_map, "A_legacy_canonical"),
        "liquidity_sweep": population_classification(edge_map, "B_v2_sweep_pre_qual"),
        "next_bar_reclaim": population_classification(edge_map, "C_v2b_reclaim_pre_qual"),
        "legacy_qualification": population_classification(edge_map, "D_v2b_reclaim_post_qual"),
        "later_bos": population_classification(edge_map, "E_later_bos_from_D"),
        "retest_gate": gate_stage_classification("retest"),
        "confirm_gate": gate_stage_classification("confirm"),
        "long_short": long_short_class,
    }

    edge_counts = edge_map.classification.value_counts().to_dict()
    forward_replicated = edge_map.loc[
        (edge_map.metric == "forward_return_12")
        & (edge_map.classification == "REPLICATED_INFORMATION")
        & (edge_map.development_N >= MIN_N_REPLICATED)
        & (edge_map.oos_N >= MIN_N_REPLICATED)
        & (edge_map.development_effect > 0.05)
        & (edge_map.oos_effect > 0.05)
    ]
    replicated_features = forward_replicated["feature"].unique().tolist()
    v3_justified = len(replicated_components) > 0 or (
        len(forward_replicated) > 0 and not forward_replicated.empty
    )

    manifest = {
        "validation": validation,
        "lookahead_audit": lookahead_pass,
        "datasets": {
            "development": "2024-01-01 to 2026-06-26",
            "failed_oos_observed": "2018-01-01 to 2020-11-30 (observed; not OOS)",
        },
        "population_counts": population_df.to_dict(orient="records"),
        "classifications": classifications,
        "edge_map_counts": edge_counts,
        "crt_v3_justified": v3_justified,
        "replicated_components": replicated_components,
        "replicated_v2_features": replicated_v2,
        "replicated_features": replicated_features,
        "unavailable_features": ["VWAP"],
    }

    report_lines = [
        "# CRT Signal-Edge Localization Report",
        "",
        "## Validation",
        f"- Development frozen trade count: {validation['development_trade_count']} (expected 193) — {'PASS' if validation['development_pass'] else 'FAIL'}",
        f"- Failed-OOS frozen trade count: {validation['failed_oos_trade_count']} (expected 197) — {'PASS' if validation['failed_oos_pass'] else 'FAIL'}",
        f"- Lookahead audit: {'PASS' if lookahead_pass else 'FAIL'}",
        "",
        "## Edge map counts",
    ]
    for label, count in edge_counts.items():
        report_lines.append(f"- {label}: {count}")
    report_lines.extend(
        [
            "",
            f"## CRT V3 justified: {'YES' if v3_justified else 'NO'}",
            "",
            "## Population forward return 12 (median, All directions)",
            "",
        ]
    )
    for population in POPULATIONS:
        dev = forward_df.loc[
            (forward_df.population == population)
            & (forward_df.era == "development")
            & (forward_df.direction == "All")
            & (forward_df.metric == "forward_return_12")
        ]
        oos = forward_df.loc[
            (forward_df.population == population)
            & (forward_df.era == "failed_oos")
            & (forward_df.direction == "All")
            & (forward_df.metric == "forward_return_12")
        ]
        if not dev.empty and not oos.empty:
            report_lines.append(
                f"- **{population}:** development={dev.iloc[0]['value']:.4f} (N={int(dev.iloc[0]['N'])}), "
                f"failed_oos={oos.iloc[0]['value']:.4f} (N={int(oos.iloc[0]['N'])})"
            )
    report_lines.extend(
        [
            "",
            "## Decision tree",
            f"1. Original CRT setup replicated information: {classifications['original_crt']}",
            f"2. Liquidity sweep alone: {classifications['liquidity_sweep']}",
            f"3. Next-bar reclaim adds information: {classifications['next_bar_reclaim']}",
            f"4. Legacy qualification adds information: {classifications['legacy_qualification']}",
            f"5. Later BOS adds information: {classifications['later_bos']}",
            f"6. Retest gate: {classifications['retest_gate']}",
            f"7. Confirm gate: {classifications['confirm_gate']}",
            f"8. Long/short asymmetry: {classifications['long_short']}",
            f"9. Replicated legacy components: {replicated_components or 'NONE'}",
            f"10. CRT V3 research justified: {'YES' if v3_justified else 'NO'}",
        ]
    )
    (output / "CRT_SIGNAL_EDGE_LOCALIZATION_REPORT.md").write_text("\n".join(report_lines) + "\n")

    with pd.ExcelWriter(output / "CRT_SIGNAL_EDGE_LOCALIZATION.xlsx", engine="openpyxl") as writer:
        for name, df in (
            ("population_summary", population_df),
            ("forward_outcomes", forward_df),
            ("direction_analysis", direction_df),
            ("legacy_score_bins", score_df),
            ("legacy_component_analysis", component_df),
            ("v2_liquidity", v2_df),
            ("bos_information", bos_df),
            ("gate_funnel", gate_df),
            ("regime_session", regime_df),
            ("edge_map", edge_map),
        ):
            df.to_excel(writer, sheet_name=name[:31], index=False)

    manifest["replicated_components"] = replicated_components
    manifest["replicated_v2_features"] = replicated_v2
    manifest["replicated_features"] = replicated_features
    (output / "study_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest
