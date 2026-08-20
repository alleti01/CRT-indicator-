"""Preregistered H1/H2/H3 entry-quality tests on existing development data.

The module consumes the frozen backtest outputs and market data.  It does not
alter the strategy, Pine code, setup feed, funnel, entries, exits, or costs.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np
import pandas as pd

from .config import FrozenConfig
from .indicators import add_base_indicators
from .metrics import summarize_group
from .structure import StructureEngine


ROUND_TURN_COST_USD = 14.50
NQ_DOLLARS_PER_POINT = 20.0
H1_DISPLACEMENT_MINIMUMS = (0.00, 0.10, 0.20, 0.30, 0.40, 0.50)
H1_RELATIVE_VOLUME_MINIMUMS = (0.75, 1.00, 1.25, 1.50, 1.75, 2.00)
H2_RETEST_RANGE_MINIMUMS = (0.25, 0.50, 0.75, 1.00, 1.25, 1.50)
H2_RECLAIM_MINIMUMS = (0.00, 0.05, 0.10, 0.15, 0.20, 0.30)
VOLATILITY_STATES = ("LOW", "MID", "HIGH")
SESSION_NAMES = (
    "Overnight",
    "Premarket",
    "Open",
    "MidAM",
    "Midday",
    "PM",
    "After-hours",
)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _timestamp_series(values: pd.Series, timezone: str) -> pd.Series:
    return pd.to_datetime(values, errors="raise", utc=True).dt.tz_convert(timezone)


def _drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    equity = values.astype(float).cumsum().to_numpy()
    peaks = np.maximum.accumulate(np.r_[0.0, equity])[:-1]
    return float(np.max(np.maximum(0.0, peaks - equity), initial=0.0))


def _basis_metrics(frame: pd.DataFrame, column: str, prefix: str) -> Dict[str, Any]:
    if frame.empty:
        values = pd.Series(dtype=float)
    else:
        values = frame.sort_values("exit_timestamp", kind="stable")[column].astype(float)
    wins = int((values > 0).sum())
    losses = int((values < 0).sum())
    flats = int((values == 0).sum())
    profit = float(values[values > 0].sum())
    loss = float(-values[values < 0].sum())
    pf = profit / loss if loss > 0 else (99.9 if profit > 0 else 0.0)
    return {
        f"{prefix}_wins": wins,
        f"{prefix}_losses": losses,
        f"{prefix}_flats": flats,
        f"{prefix}_WR_pct": wins * 100.0 / len(values) if len(values) else 0.0,
        f"{prefix}_AvgR": float(values.mean()) if len(values) else 0.0,
        f"{prefix}_TotalR": float(values.sum()) if len(values) else 0.0,
        f"{prefix}_PF": float(pf),
        f"{prefix}_MaxDD_R": _drawdown(values),
        f"{prefix}_largest_win_R": float(values.max()) if len(values) else 0.0,
        f"{prefix}_largest_loss_R": float(values.min()) if len(values) else 0.0,
    }


def performance(frame: pd.DataFrame) -> Dict[str, Any]:
    return {
        "N": len(frame),
        **_basis_metrics(frame, "gross_R", "gross"),
        **_basis_metrics(frame, "net_R", "net"),
    }


def sample_classification(count: int) -> str:
    if count < 30:
        return "INSUFFICIENT"
    if count < 50:
        return "VERY WEAK"
    if count < 100:
        return "EXPLORATORY"
    return "BETTER SUPPORTED"


def add_costs(trades: pd.DataFrame) -> pd.DataFrame:
    result = trades.copy()
    result["risk_points"] = (result.entry_price.astype(float) - result.stop_price.astype(float)).abs()
    if bool((result.risk_points <= 0).any()):
        raise AssertionError("frozen trade has non-positive risk")
    result["gross_R"] = result.result_R.astype(float)
    result["cost_R"] = ROUND_TURN_COST_USD / (result.risk_points * NQ_DOLLARS_PER_POINT)
    result["net_R"] = result.gross_R - result.cost_R
    return result


def verify_reference_baseline(confirm_trades: pd.DataFrame) -> Dict[str, Any]:
    working = add_costs(confirm_trades)
    metrics = performance(working)
    expected = {
        "N": 42,
        "net_wins": 17,
        "net_losses": 25,
        "net_WR_pct": 40.476190476190474,
        "net_AvgR": -0.008455272926675063,
        "net_TotalR": -0.3551214629203526,
        "net_PF": 0.9836932374533185,
        "net_MaxDD_R": 8.371281287974549,
    }
    for field, value in expected.items():
        actual = metrics[field]
        tolerance = 0 if isinstance(value, int) else 1e-9
        if abs(float(actual) - float(value)) > tolerance:
            raise RuntimeError(f"REFERENCE BASELINE MISMATCH: {field}={actual}, expected {value}")
    metrics["status"] = "PASS"
    return metrics


def _session_name(bucket: int) -> str:
    return {
        0: "Overnight",
        1: "Premarket",
        2: "Open",
        3: "MidAM",
        4: "Midday",
        5: "PM",
        6: "After-hours",
    }[int(bucket)]


def build_large_development_features(
    frame: pd.DataFrame,
    confirm_trades: pd.DataFrame,
    *,
    config: FrozenConfig,
    start: str,
    end: str,
) -> pd.DataFrame:
    """Attach BOS/retest/confirm features using only information known by entry."""
    data = frame.tz_convert(config.exchange_timezone).sort_index().copy()
    data = add_base_indicators(data, config)
    data["prior20_volume_mean"] = data.volume.shift(1).rolling(20, min_periods=20).mean()
    trades = add_costs(confirm_trades)
    for column in [
        "setup_timestamp",
        "bos_timestamp",
        "retest_timestamp",
        "confirm_timestamp",
        "entry_timestamp",
        "exit_timestamp",
    ]:
        trades[column] = _timestamp_series(trades[column], config.exchange_timezone)

    bos_keys = {int(timestamp.value) for timestamp in trades.bos_timestamp}
    structure_engine = StructureEngine(config)
    bos_levels: Dict[int, float] = {}
    for bar_index, row in enumerate(data.itertuples()):
        structure = structure_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.structure_pivot_high),
            pivot_low=float(row.structure_pivot_low),
        )
        key = int(row.Index.value)
        if key in bos_keys:
            directions = trades.loc[trades.bos_timestamp == row.Index, "direction"].unique()
            for direction_name in directions:
                direction = 1 if direction_name == "Long" else -1
                prior = structure.previous_active_high if direction == 1 else structure.previous_active_low
                current = structure.active_high if direction == 1 else structure.active_low
                level = prior if _finite(prior) else current
                bos_levels[(key, direction)] = float(level)

    position_by_time = {int(timestamp.value): position for position, timestamp in enumerate(data.index)}
    start_ts = pd.Timestamp(start, tz=config.exchange_timezone)
    end_exclusive = pd.Timestamp(end, tz=config.exchange_timezone) + pd.Timedelta(days=1)
    midpoint = start_ts + (end_exclusive - start_ts) / 2
    rows: List[Dict[str, Any]] = []
    for number, trade in enumerate(trades.sort_values("entry_timestamp", kind="stable").itertuples(), start=1):
        direction = 1 if trade.direction == "Long" else -1
        bos_pos = position_by_time[int(trade.bos_timestamp.value)]
        retest_pos = position_by_time[int(trade.retest_timestamp.value)]
        confirm_pos = position_by_time[int(trade.confirm_timestamp.value)]
        entry_pos = position_by_time[int(trade.entry_timestamp.value)]
        if not (bos_pos < retest_pos < confirm_pos == entry_pos):
            raise AssertionError(f"non-causal Confirm sequence at {trade.entry_timestamp}")
        bos = data.iloc[bos_pos]
        retest = data.iloc[retest_pos]
        confirm = data.iloc[confirm_pos]
        level = bos_levels.get((int(trade.bos_timestamp.value), direction), float("nan"))
        if not _finite(level):
            raise AssertionError(f"missing frozen BOS level at {trade.bos_timestamp}")
        bos_atr = float(bos.atr)
        retest_atr = float(retest.atr)
        confirm_atr = float(confirm.atr)
        retest_range = float(retest.high) - float(retest.low)
        displacement_beyond = abs(float(bos.close) - level)
        reclaim_distance = direction * (float(confirm.close) - level)
        trailing_atr = data.atr.iloc[max(0, entry_pos - 100) : entry_pos].dropna()
        atr_percentile = float((trailing_atr <= confirm_atr).mean()) if len(trailing_atr) else np.nan
        volatility_state = "LOW" if atr_percentile <= 0.33 else "HIGH" if atr_percentile >= 0.67 else "MID"
        entry_year = int(trade.entry_timestamp.year)
        quarter = int((trade.entry_timestamp.month - 1) // 3 + 1)
        rows.append(
            {
                "trade_id": f"D{number:04d}",
                "direction": trade.direction,
                "setup_timestamp": trade.setup_timestamp,
                "bos_timestamp": trade.bos_timestamp,
                "retest_timestamp": trade.retest_timestamp,
                "confirm_timestamp": trade.confirm_timestamp,
                "entry_timestamp": trade.entry_timestamp,
                "exit_timestamp": trade.exit_timestamp,
                "bos_level": level,
                "bos_close_beyond_structure_atr": displacement_beyond / bos_atr,
                "bos_relative_volume_20": float(bos.volume) / float(bos.prior20_volume_mean),
                "retest_range_atr": retest_range / retest_atr,
                "reclaim_distance_beyond_bos_atr": reclaim_distance / confirm_atr,
                "bars_bos_to_retest": retest_pos - bos_pos,
                "bars_retest_to_confirm": confirm_pos - retest_pos,
                "entry_atr": confirm_atr,
                "entry_atr_percentile_100": atr_percentile,
                "volatility_state": volatility_state,
                "session": _session_name(int(trade.session_bucket)),
                "year": entry_year,
                "quarter": f"{entry_year}-Q{quarter}",
                "time_half": "First half" if trade.entry_timestamp < midpoint else "Second half",
                "score": float(trade.score),
                "gross_R": float(trade.gross_R),
                "cost_R": float(trade.cost_R),
                "net_R": float(trade.net_R),
                "exit_reason": trade.exit_reason,
            }
        )
    result = pd.DataFrame(rows)
    if len(result) != len(trades):
        raise AssertionError("feature reconstruction dropped trades")
    return result


def _period_detail(frame: pd.DataFrame, hypothesis: str, cell_id: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    dimensions: Sequence[tuple[str, str]] = (("year", "year"), ("quarter", "quarter"), ("half", "time_half"))
    for period_type, column in dimensions:
        for period, group in frame.groupby(column, sort=True):
            rows.append(
                {
                    "hypothesis": hypothesis,
                    "cell_id": cell_id,
                    "period_type": period_type,
                    "period": str(period),
                    **performance(group),
                }
            )
    return pd.DataFrame(rows)


def _stability_summary(frame: pd.DataFrame) -> Dict[str, Any]:
    yearly = {str(year): performance(group)["net_TotalR"] for year, group in frame.groupby("year", sort=True)}
    quarterly = {str(quarter): performance(group)["net_TotalR"] for quarter, group in frame.groupby("quarter", sort=True)}
    halves = {str(half): performance(group)["net_TotalR"] for half, group in frame.groupby("time_half", sort=True)}
    return {
        "positive_years": sum(value > 0 for value in yearly.values()),
        "total_years": len(yearly),
        "positive_quarters": sum(value > 0 for value in quarterly.values()),
        "total_quarters": len(quarterly),
        "positive_halves": sum(value > 0 for value in halves.values()),
        "total_halves": len(halves),
        "yearly_net_TotalR_json": json.dumps(yearly, separators=(",", ":")),
        "quarterly_net_TotalR_json": json.dumps(quarterly, separators=(",", ":")),
        "half_net_TotalR_json": json.dumps(halves, separators=(",", ":")),
        "survives_time_stability": bool(
            len(yearly) >= 2
            and sum(value > 0 for value in yearly.values()) >= math.ceil(len(yearly) * 2 / 3)
            and len(halves) == 2
            and all(value > 0 for value in halves.values())
            and len(quarterly) >= 4
            and sum(value > 0 for value in quarterly.values()) >= math.ceil(len(quarterly) / 2)
        ),
    }


def _cell_row(
    selected: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    hypothesis: str,
    cell_id: str,
) -> Dict[str, Any]:
    metrics = performance(selected)
    long_metrics = performance(selected.loc[selected.direction == "Long"])
    short_metrics = performance(selected.loc[selected.direction == "Short"])
    return {
        "hypothesis": hypothesis,
        "cell_id": cell_id,
        **metrics,
        "trade_retention_pct": len(selected) * 100.0 / len(baseline) if len(baseline) else 0.0,
        "sample_classification": sample_classification(len(selected)),
        "net_AvgR_improvement_vs_baseline": metrics["net_AvgR"] - performance(baseline)["net_AvgR"],
        "long_N": long_metrics["N"],
        "long_net_AvgR": long_metrics["net_AvgR"],
        "long_net_TotalR": long_metrics["net_TotalR"],
        "long_net_PF": long_metrics["net_PF"],
        "short_N": short_metrics["N"],
        "short_net_AvgR": short_metrics["net_AvgR"],
        "short_net_TotalR": short_metrics["net_TotalR"],
        "short_net_PF": short_metrics["net_PF"],
        **_stability_summary(selected),
    }


def build_h1_grid(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, Dict[str, pd.DataFrame]]:
    rows: List[Dict[str, Any]] = []
    stability: List[pd.DataFrame] = []
    selections: Dict[str, pd.DataFrame] = {}
    for displacement in H1_DISPLACEMENT_MINIMUMS:
        for relative_volume in H1_RELATIVE_VOLUME_MINIMUMS:
            cell_id = f"H1_D{displacement:.2f}_V{relative_volume:.2f}"
            selected = trades.loc[
                (trades.bos_close_beyond_structure_atr >= displacement)
                & (trades.bos_relative_volume_20 >= relative_volume)
            ].copy()
            row = _cell_row(selected, trades, hypothesis="H1", cell_id=cell_id)
            row.update({"bos_displacement_atr_min": displacement, "relative_volume_20_min": relative_volume})
            rows.append(row)
            stability.append(_period_detail(selected, "H1", cell_id))
            selections[cell_id] = selected
    return pd.DataFrame(rows), pd.concat(stability, ignore_index=True), selections


def build_h2_grid(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, Dict[str, pd.DataFrame]]:
    rows: List[Dict[str, Any]] = []
    stability: List[pd.DataFrame] = []
    selections: Dict[str, pd.DataFrame] = {}
    for retest_range in H2_RETEST_RANGE_MINIMUMS:
        for reclaim in H2_RECLAIM_MINIMUMS:
            cell_id = f"H2_R{retest_range:.2f}_C{reclaim:.2f}"
            selected = trades.loc[
                (trades.retest_range_atr >= retest_range)
                & (trades.reclaim_distance_beyond_bos_atr >= reclaim)
            ].copy()
            row = _cell_row(selected, trades, hypothesis="H2", cell_id=cell_id)
            row.update(
                {
                    "retest_range_atr_min": retest_range,
                    "reclaim_distance_atr_min": reclaim,
                    "avg_bars_BOS_to_Retest": float(selected.bars_bos_to_retest.mean()) if len(selected) else np.nan,
                    "avg_bars_Retest_to_Confirm": float(selected.bars_retest_to_confirm.mean()) if len(selected) else np.nan,
                }
            )
            rows.append(row)
            stability.append(_period_detail(selected, "H2", cell_id))
            selections[cell_id] = selected
    return pd.DataFrame(rows), pd.concat(stability, ignore_index=True), selections


def build_h3_matrix(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, Dict[str, pd.DataFrame]]:
    rows: List[Dict[str, Any]] = []
    stability: List[pd.DataFrame] = []
    selections: Dict[str, pd.DataFrame] = {}
    for state in VOLATILITY_STATES:
        for session in SESSION_NAMES:
            cell_id = f"H3_{state}_{session.replace('-', '').replace(' ', '')}"
            selected = trades.loc[(trades.volatility_state == state) & (trades.session == session)].copy()
            row = _cell_row(selected, trades, hypothesis="H3", cell_id=cell_id)
            row.update({"volatility_state": state, "session": session})
            rows.append(row)
            stability.append(_period_detail(selected, "H3", cell_id))
            selections[cell_id] = selected
    detail = pd.concat([frame for frame in stability if not frame.empty], ignore_index=True) if any(not frame.empty for frame in stability) else pd.DataFrame()
    return pd.DataFrame(rows), detail, selections


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    maximum_iterations, epsilon, floor = 200, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    d = floor if abs(d) < floor else d
    d = 1.0 / d
    result = d
    for iteration in range(1, maximum_iterations + 1):
        m2 = 2 * iteration
        aa = iteration * (b - iteration) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = floor if abs(d) < floor else d
        c = 1.0 + aa / c
        c = floor if abs(c) < floor else c
        d = 1.0 / d
        result *= d * c
        aa = -(a + iteration) * (qab + iteration) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = floor if abs(d) < floor else d
        c = 1.0 + aa / c
        c = floor if abs(c) < floor else c
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < epsilon:
            break
    return result


def _regularized_beta(x: float, a: float, b: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    log_term = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    front = math.exp(log_term)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def _student_t_cdf(value: float, degrees_freedom: float) -> float:
    x = degrees_freedom / (degrees_freedom + value * value)
    tail = 0.5 * _regularized_beta(x, degrees_freedom / 2.0, 0.5)
    return 1.0 - tail if value >= 0 else tail


def welch_greater(selected: pd.Series, excluded: pd.Series) -> tuple[float, float, float]:
    a = selected.astype(float).dropna().to_numpy()
    b = excluded.astype(float).dropna().to_numpy()
    if len(a) < 2 or len(b) < 2:
        return np.nan, np.nan, np.nan
    va, vb = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    standard_error_sq = va / len(a) + vb / len(b)
    if standard_error_sq <= 0:
        return np.nan, np.nan, np.nan
    statistic = (float(np.mean(a)) - float(np.mean(b))) / math.sqrt(standard_error_sq)
    denominator = (va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1)
    degrees = standard_error_sq**2 / denominator if denominator > 0 else np.nan
    p_value = 1.0 - _student_t_cdf(statistic, degrees) if _finite(degrees) else np.nan
    return float(statistic), float(degrees), float(p_value)


def fdr_analysis(
    grids: Sequence[pd.DataFrame],
    selections: Dict[str, pd.DataFrame],
    baseline: pd.DataFrame,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for grid in grids:
        for cell in grid.itertuples():
            selected = selections[cell.cell_id]
            excluded = baseline.loc[~baseline.trade_id.isin(selected.trade_id)]
            if len(selected) < 30 or len(excluded) < 30:
                statistic = degrees = p_value = np.nan
                reason = "Not testable: selected or excluded group has N<30"
            else:
                statistic, degrees, p_value = welch_greater(selected.net_R, excluded.net_R)
                reason = "Welch one-sided selected mean > excluded mean"
            rows.append(
                {
                    "hypothesis": cell.hypothesis,
                    "cell_id": cell.cell_id,
                    "selected_N": len(selected),
                    "excluded_N": len(excluded),
                    "selected_net_AvgR": float(selected.net_R.mean()) if len(selected) else 0.0,
                    "excluded_net_AvgR": float(excluded.net_R.mean()) if len(excluded) else 0.0,
                    "difference_selected_minus_excluded": float(selected.net_R.mean() - excluded.net_R.mean()) if len(selected) and len(excluded) else np.nan,
                    "welch_t": statistic,
                    "degrees_freedom": degrees,
                    "raw_p_one_sided": p_value,
                    "raw_significant_0_05": bool(_finite(p_value) and p_value < 0.05),
                    "test_definition": reason,
                }
            )
    result = pd.DataFrame(rows)
    result["BH_FDR_q"] = np.nan
    valid = result.raw_p_one_sided.notna()
    ordered = result.loc[valid].sort_values("raw_p_one_sided").copy()
    count = len(ordered)
    if count:
        raw_q = ordered.raw_p_one_sided.to_numpy() * count / np.arange(1, count + 1)
        adjusted = np.minimum.accumulate(raw_q[::-1])[::-1]
        result.loc[ordered.index, "BH_FDR_q"] = np.minimum(1.0, adjusted)
    result["FDR_significant_0_05"] = result.BH_FDR_q.lt(0.05).fillna(False)
    result["predefined_cell_count"] = len(result)
    result["testable_cell_count"] = int(valid.sum())
    return result.sort_values(["hypothesis", "cell_id"], kind="stable").reset_index(drop=True)


def outlier_analysis(
    grids: Sequence[pd.DataFrame],
    selections: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for grid in grids:
        for cell in grid.itertuples():
            selected = selections[cell.cell_id]
            if len(selected) < 30 or cell.net_AvgR <= 0 or cell.net_PF <= 1:
                continue
            winners = selected.loc[selected.net_R > 0].sort_values("net_R", ascending=False)
            top_one_percent = max(1, math.ceil(len(selected) * 0.01))
            removals = {
                "none": [],
                "remove_best_trade": list(selected.nlargest(1, "net_R").trade_id),
                "remove_top3_winners": list(winners.head(3).trade_id),
                "remove_top1pct_winners": list(winners.head(top_one_percent).trade_id),
            }
            for removal, trade_ids in removals.items():
                remaining = selected.loc[~selected.trade_id.isin(trade_ids)]
                rows.append(
                    {
                        "hypothesis": cell.hypothesis,
                        "cell_id": cell.cell_id,
                        "removal": removal,
                        "removed_N": len(trade_ids),
                        **performance(remaining),
                    }
                )
    return pd.DataFrame(rows)


def _annotate_plateau(grid: pd.DataFrame, x_field: str, y_field: str, baseline_net_avg: float) -> pd.DataFrame:
    result = grid.copy()
    x_values = sorted(result[x_field].unique())
    y_values = sorted(result[y_field].unique())
    by_position = {(x_values.index(getattr(row, x_field)), y_values.index(getattr(row, y_field))): row for row in result.itertuples()}
    annotations: Dict[str, Dict[str, Any]] = {}
    for (x_position, y_position), row in by_position.items():
        neighbors = [
            by_position[position]
            for position in ((x_position - 1, y_position), (x_position + 1, y_position), (x_position, y_position - 1), (x_position, y_position + 1))
            if position in by_position
        ]
        neighbor_positive = [
            neighbor
            for neighbor in neighbors
            if neighbor.net_AvgR > 0
            and neighbor.net_PF > 1
            and neighbor.net_AvgR - baseline_net_avg >= 0.05
        ]
        rate = len(neighbor_positive) / len(neighbors) if neighbors else 0.0
        annotations[row.cell_id] = {
            "neighbor_count": len(neighbors),
            "neighbor_cost_positive_material_count": len(neighbor_positive),
            "neighbor_positive_rate": rate,
            "neighbor_median_net_AvgR": float(np.median([neighbor.net_AvgR for neighbor in neighbors])) if neighbors else np.nan,
            "broad_plateau": bool(
                row.net_AvgR > 0
                and row.net_PF > 1
                and row.net_AvgR - baseline_net_avg >= 0.05
                and len(neighbors) >= 2
                and rate >= 0.75
                and np.median([neighbor.net_AvgR for neighbor in neighbors]) > 0
            ),
        }
    return result.merge(pd.DataFrame.from_dict(annotations, orient="index").rename_axis("cell_id").reset_index(), on="cell_id", how="left")


def _outlier_survival(outliers: pd.DataFrame) -> Dict[str, bool]:
    if outliers.empty:
        return {}
    return {
        cell_id: bool((group.net_AvgR > 0).all() and (group.net_PF > 1).all())
        for cell_id, group in outliers.groupby("cell_id")
    }


def _select_representative(grid: pd.DataFrame, hypothesis: str) -> pd.Series:
    promising = grid.loc[grid.promising].copy() if "promising" in grid else pd.DataFrame()
    if not promising.empty:
        return promising.sort_values(
            ["net_AvgR", "trade_retention_pct"],
            ascending=[False, False],
            kind="stable",
        ).iloc[0]
    supported = grid.loc[grid.N >= 100].copy()
    pool = supported if not supported.empty else grid.loc[grid.N >= 30].copy()
    if pool.empty:
        return grid.sort_values("N", ascending=False, kind="stable").iloc[0]
    # When nothing qualifies, show the strongest adequately supported observation
    # in the summary. It remains explicitly non-promising unless it passes every
    # preregistered robustness gate below.
    sort_columns = ["broad_plateau", "survives_time_stability", "net_AvgR", "trade_retention_pct"] if hypothesis in {"H1", "H2"} else ["survives_time_stability", "net_AvgR", "trade_retention_pct"]
    available = [column for column in sort_columns if column in pool]
    return pool.sort_values(available, ascending=[False] * len(available), kind="stable").iloc[0]


def _fmt(value: Any, digits: int = 4) -> str:
    return "—" if not _finite(value) else f"{float(value):.{digits}f}"


def _candidate_row(row: pd.Series, hypothesis: str) -> Dict[str, Any]:
    return {
        "hypothesis": hypothesis,
        "summary_role": "qualified_candidate" if bool(row.get("promising", False)) else "strongest_supported_observation_not_qualified",
        "cell_id": row.cell_id,
        "N": int(row.N),
        "trade_retention_pct": row.trade_retention_pct,
        "sample_classification": row.sample_classification,
        "net_wins": int(row.net_wins),
        "net_losses": int(row.net_losses),
        "net_WR_pct": row.net_WR_pct,
        "gross_AvgR": row.gross_AvgR,
        "net_AvgR": row.net_AvgR,
        "gross_TotalR": row.gross_TotalR,
        "net_TotalR": row.net_TotalR,
        "gross_PF": row.gross_PF,
        "net_PF": row.net_PF,
        "net_MaxDD_R": row.net_MaxDD_R,
        "net_AvgR_improvement_vs_baseline": row.net_AvgR_improvement_vs_baseline,
        "long_N": int(row.long_N),
        "long_net_AvgR": row.long_net_AvgR,
        "long_net_TotalR": row.long_net_TotalR,
        "long_net_PF": row.long_net_PF,
        "short_N": int(row.short_N),
        "short_net_AvgR": row.short_net_AvgR,
        "short_net_TotalR": row.short_net_TotalR,
        "short_net_PF": row.short_net_PF,
        "positive_years": int(row.positive_years),
        "total_years": int(row.total_years),
        "positive_quarters": int(row.positive_quarters),
        "total_quarters": int(row.total_quarters),
        "positive_halves": int(row.positive_halves),
        "total_halves": int(row.total_halves),
        "avg_bars_BOS_to_Retest": row.get("avg_bars_BOS_to_Retest", np.nan),
        "avg_bars_Retest_to_Confirm": row.get("avg_bars_Retest_to_Confirm", np.nan),
        "broad_plateau": bool(row.get("broad_plateau", False)),
        "survives_realistic_costs": bool(row.net_AvgR > 0 and row.net_PF > 1),
        "outlier_test_applicable": bool(row.net_AvgR > 0 and row.net_PF > 1 and row.N >= 30),
        "survives_outlier_removal": bool(row.get("survives_outlier_removal", False)),
        "survives_time_stability": bool(row.survives_time_stability),
        "FDR_significant_0_05": bool(row.FDR_significant_0_05),
        "BH_FDR_q": row.BH_FDR_q,
        "promising": bool(row.get("promising", False)),
    }


def build_report(
    reference: Dict[str, Any],
    large_baseline: Dict[str, Any],
    candidates: pd.DataFrame,
    *,
    fdr_survivors: int,
    predefined_cells: int,
    testable_cells: int,
) -> str:
    indexed = candidates.set_index("hypothesis")
    any_promising = bool(candidates.promising.any())
    best = str(candidates.loc[candidates.promising, "hypothesis"].iloc[0]) if any_promising else "NONE"
    any_plateau = bool(candidates.broad_plateau.any())
    evidence = "PROMISING" if any_promising else "WEAK" if bool(candidates.survives_realistic_costs.any()) else "NONE"
    lines = [
        "# Focused Hypothesis Testing for Retest-Gated Entry Quality",
        "",
        "## Executive summary",
        "",
        f"The 42-trade reference baseline reproduced exactly (**{reference['status']}**). The three preregistered hypotheses were then evaluated on the already-downloaded 2024-01-01 through 2026-06-26 history, now classified as development data. No new data was downloaded, no unseen data was accessed, and no Pine or frozen strategy logic was changed.",
        "",
        f"Across {predefined_cells} predefined cells ({testable_cells} statistically testable), {fdr_survivors} survived Benjamini-Hochberg FDR at 5%. Entry-quality evidence is **{evidence}**. " + ("A candidate met every preregistered requirement." if any_promising else "**NO QUALITY FILTER SHOULD BE ADDED YET.**"),
        "",
        "## BASELINE",
        "",
        f"Reference reproduction: N {reference['N']}, wins {reference['net_wins']}, losses {reference['net_losses']}, WR {reference['net_WR_pct']:.2f}%, net AvgR {reference['net_AvgR']:.5f}, net TotalR {reference['net_TotalR']:.5f}, net PF {reference['net_PF']:.5f}, net MaxDD {reference['net_MaxDD_R']:.5f}R — PASS.",
        "",
        f"Larger development baseline: N {large_baseline['N']}, gross AvgR {large_baseline['gross_AvgR']:.5f}, gross TotalR {large_baseline['gross_TotalR']:.2f}, gross PF {large_baseline['gross_PF']:.4f}; net AvgR {large_baseline['net_AvgR']:.5f}, net TotalR {large_baseline['net_TotalR']:.2f}, net PF {large_baseline['net_PF']:.4f}, net MaxDD {large_baseline['net_MaxDD_R']:.2f}R.",
    ]
    for hypothesis in ("H1", "H2", "H3"):
        row = indexed.loc[hypothesis]
        outlier_text = "YES" if row.survives_outlier_removal else "NO" if row.outlier_test_applicable else "NOT APPLICABLE (failed cost-positive prerequisite)"
        lines.extend(
            [
                "",
                f"## {hypothesis} RESULT",
                "",
                f"Strongest adequately supported observation (not a selected rule unless every gate passes): **{row.cell_id}**. N {int(row.N)} ({row.trade_retention_pct:.1f}% retention; {row.sample_classification}), net AvgR {_fmt(row.net_AvgR)}, net TotalR {_fmt(row.net_TotalR, 2)}, net PF {_fmt(row.net_PF)}, net MaxDD {_fmt(row.net_MaxDD_R, 2)}R. Gross AvgR {_fmt(row.gross_AvgR)}, gross PF {_fmt(row.gross_PF)}.",
                "",
                f"Direction: Long N {int(row.long_N)}, net AvgR {_fmt(row.long_net_AvgR)}, PF {_fmt(row.long_net_PF)}; Short N {int(row.short_N)}, net AvgR {_fmt(row.short_net_AvgR)}, PF {_fmt(row.short_net_PF)}. Time: {int(row.positive_years)}/{int(row.total_years)} positive years, {int(row.positive_quarters)}/{int(row.total_quarters)} positive quarters, {int(row.positive_halves)}/{int(row.total_halves)} positive halves.",
                "",
                f"Plateau: {'YES' if row.broad_plateau else 'NO'}; realistic costs: {'YES' if row.survives_realistic_costs else 'NO'}; outlier removals: {outlier_text}; time stability: {'YES' if row.survives_time_stability else 'NO'}; FDR: {'PASS' if row.FDR_significant_0_05 else 'FAIL'} (q={_fmt(row.BH_FDR_q)}). Overall: {'PROMISING' if row.promising else 'NOT PROMISING'}.",
            ]
        )
        if hypothesis == "H2":
            lines.extend(
                [
                    "",
                    f"Average delays: BOS→Retest {_fmt(row.avg_bars_BOS_to_Retest, 2)} bars; Retest→Confirm {_fmt(row.avg_bars_Retest_to_Confirm, 2)} bars.",
                ]
            )
    lines.extend(
        [
            "",
            "## Final decision",
            "",
            f"- Best individual hypothesis: **{best}**",
            f"- Robust parameter plateau found: **{'YES' if any_plateau else 'NO'}**",
            f"- Survives realistic costs: **{'YES' if any_promising and bool(candidates.loc[candidates.promising, 'survives_realistic_costs'].all()) else 'NO'}**",
            f"- Survives outlier removal: **{'YES' if any_promising and bool(candidates.loc[candidates.promising, 'survives_outlier_removal'].all()) else 'NO'}**",
            f"- Survives time stability: **{'YES' if any_promising and bool(candidates.loc[candidates.promising, 'survives_time_stability'].all()) else 'NO'}**",
            f"- FDR survivors: **{fdr_survivors}**",
            f"- Entry quality improvement evidence: **{evidence}**",
            "",
            "No two-hypothesis combination was tested unless an individual hypothesis first met every preregistered success criterion. Quantile/session definitions, the 20-bar causal volume average, and the trailing-100-bar causal ATR percentile were fixed before examining cell outcomes.",
        ]
    )
    if not any_promising:
        lines.extend(["", "## Required conclusion", "", "**NO QUALITY FILTER SHOULD BE ADDED YET.**"])
    return "\n".join(lines) + "\n"


def run_focused_tests(
    *,
    large_frame: pd.DataFrame,
    large_confirm_trades: pd.DataFrame,
    reference_metrics: Dict[str, Any],
    output: Path,
    config: FrozenConfig,
    start: str = "2024-01-01",
    end: str = "2026-06-26",
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    features = build_large_development_features(
        large_frame,
        large_confirm_trades,
        config=config,
        start=start,
        end=end,
    )
    baseline_metrics = performance(features)
    h1, h1_stability, h1_selections = build_h1_grid(features)
    h2, h2_stability, h2_selections = build_h2_grid(features)
    h3, h3_stability, h3_selections = build_h3_matrix(features)
    selections = {**h1_selections, **h2_selections, **h3_selections}
    baseline_net_avg = baseline_metrics["net_AvgR"]
    h1 = _annotate_plateau(h1, "bos_displacement_atr_min", "relative_volume_20_min", baseline_net_avg)
    h2 = _annotate_plateau(h2, "retest_range_atr_min", "reclaim_distance_atr_min", baseline_net_avg)
    h3["neighbor_count"] = 0
    h3["neighbor_cost_positive_material_count"] = 0
    h3["neighbor_positive_rate"] = 0.0
    h3["neighbor_median_net_AvgR"] = np.nan
    h3["broad_plateau"] = False

    fdr = fdr_analysis((h1, h2, h3), selections, features)
    outliers = outlier_analysis((h1, h2, h3), selections)
    survival = _outlier_survival(outliers)
    fdr_fields = fdr[["cell_id", "raw_p_one_sided", "raw_significant_0_05", "BH_FDR_q", "FDR_significant_0_05"]]
    for name, grid in (("h1", h1), ("h2", h2), ("h3", h3)):
        merged = grid.merge(fdr_fields, on="cell_id", how="left")
        merged["survives_outlier_removal"] = merged.cell_id.map(survival).eq(True)
        merged["materially_better_than_baseline"] = merged.net_AvgR_improvement_vs_baseline >= 0.05
        merged["adequate_retention"] = merged.trade_retention_pct >= 20.0
        merged["promising"] = (
            (merged.net_AvgR > 0)
            & (merged.net_PF > 1)
            & merged.materially_better_than_baseline
            & (merged.N >= 100)
            & merged.adequate_retention
            & merged.survives_time_stability
            & merged.survives_outlier_removal
            & merged.FDR_significant_0_05
            & (merged.broad_plateau if name in {"h1", "h2"} else True)
        )
        if name == "h1":
            h1 = merged
        elif name == "h2":
            h2 = merged
        else:
            h3 = merged

    representative_rows = []
    for hypothesis, grid in (("H1", h1), ("H2", h2), ("H3", h3)):
        representative_rows.append(_candidate_row(_select_representative(grid, hypothesis), hypothesis))
    candidates = pd.DataFrame(representative_rows)
    promising = pd.concat([h1.loc[h1.promising], h2.loc[h2.promising], h3.loc[h3.promising]], ignore_index=True)
    if not promising.empty:
        promising_hypotheses = set(promising.hypothesis)
        candidates["promising"] = candidates.hypothesis.isin(promising_hypotheses)

    stability = pd.concat([h1_stability, h2_stability, h3_stability], ignore_index=True)
    h1.to_csv(output / "h1_grid.csv", index=False)
    h2.to_csv(output / "h2_grid.csv", index=False)
    h3.to_csv(output / "h3_volatility_session.csv", index=False)
    stability.to_csv(output / "stability_results.csv", index=False)
    outliers.to_csv(output / "outlier_results.csv", index=False)
    fdr.to_csv(output / "fdr_results.csv", index=False)
    candidates.to_csv(output / "candidate_summary.csv", index=False)
    features.to_csv(output / "development_confirm_trade_features.csv", index=False)
    pd.DataFrame([{"baseline": "42-trade reference", **reference_metrics}, {"baseline": "larger development", **baseline_metrics}]).to_csv(output / "baseline_reproduction.csv", index=False)
    fdr_survivors = int(fdr.FDR_significant_0_05.sum())
    report = build_report(
        reference_metrics,
        baseline_metrics,
        candidates,
        fdr_survivors=fdr_survivors,
        predefined_cells=len(fdr),
        testable_cells=int(fdr.raw_p_one_sided.notna().sum()),
    )
    (output / "focused_hypothesis_report.md").write_text(report)
    manifest = {
        "reference_baseline": reference_metrics,
        "larger_development_baseline": baseline_metrics,
        "development_range": {"start": start, "end": end},
        "new_data_downloaded": False,
        "unseen_data_accessed": False,
        "pine_modified": False,
        "predefined_cells": len(fdr),
        "testable_cells": int(fdr.raw_p_one_sided.notna().sum()),
        "FDR_survivors": fdr_survivors,
        "promising_cells": int(len(promising)),
        "combination_tested": False,
    }
    (output / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return manifest
