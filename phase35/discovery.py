"""Walk-forward entry discovery, precision curves, and simple rule extraction."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, export_text

from phase29.config import WALK_FORWARD_FOLDS
from phase29.simulator import SimConfig, simulate_trade
from phase31.metrics import apply_costs, enrich_net, net_performance, performance

from .config import (
    DISCOVERY_ENTRY_MODEL,
    DISCOVERY_MAX_BARS,
    DISCOVERY_STOP_ATR,
    DISCOVERY_TARGET_R,
    FREQ_BANDS,
    PRECISION_TOP_PCTS,
    WF_MIN_TEST_STRONG,
    WF_MIN_TRAIN_STRONG,
)


FEATURE_COLS_LONG = (
    "body_atr", "close_loc", "lower_wick_ratio", "ret_1", "ret_3", "ret_4",
    "dist_low_8_atr", "break_high_8", "pullback_from_low_8", "disp_long",
    "price_vs_ema8", "ema8_slope", "atr_expansion", "rel_volume", "minutes_since_open",
)

FEATURE_COLS_SHORT = (
    "body_atr", "close_loc", "upper_wick_ratio", "ret_1", "ret_3", "ret_4",
    "dist_high_8_atr", "break_low_8", "pullback_from_high_8", "disp_short",
    "price_vs_ema8", "ema8_slope", "atr_expansion", "rel_volume", "minutes_since_open",
)


@dataclass
class SimpleRule:
    direction: str
    conditions: Tuple[Tuple[str, str, float], ...]
    description: str

    def mask(self, df: pd.DataFrame) -> pd.Series:
        if not self.conditions:
            return pd.Series(False, index=df.index)
        m = pd.Series(True, index=df.index)
        for col, op, val in self.conditions:
            if op == ">":
                m &= df[col] > val
            elif op == "<":
                m &= df[col] < val
            elif op == ">=":
                m &= df[col] >= val
            elif op == "<=":
                m &= df[col] <= val
        return m


def _merge_dataset(labels: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    return labels.merge(features, on=["timestamp", "bar_index"], how="inner", suffixes=("", "_feat"))


def _train_medians(train: pd.DataFrame, cols: Tuple[str, ...]) -> Dict[str, float]:
    return {c: float(train[c].median()) for c in cols if c in train.columns}


def _discover_rule(
    train: pd.DataFrame,
    *,
    direction: str,
    target_col: str,
    feature_cols: Tuple[str, ...],
    target_trades_day: float = 1.0,
) -> SimpleRule:
    """Extract a 2–3 condition rule from train data via greedy threshold search."""
    med = _train_medians(train, feature_cols)
    y = train[target_col].astype(bool)
    base_rate = float(y.mean()) if len(y) else 0.0
    best_rule = SimpleRule(direction, tuple(), f"{direction} NO_RULE")
    best_score = -1.0

    # univariate lifts
    candidates: List[Tuple[str, str, float, float]] = []
    for col in feature_cols:
        if col not in train.columns:
            continue
        for op, q in ((">", 0.70), (">", 0.80), ("<", 0.30), ("<", 0.20)):
            val = float(train[col].quantile(q))
            mask = train[col] > val if op == ">" else train[col] < val
            if mask.sum() < 30:
                continue
            prec = float(y[mask].mean())
            freq = mask.mean()
            lift = prec / base_rate if base_rate > 0 else prec
            candidates.append((col, op, val, lift * prec))

    candidates.sort(key=lambda x: x[3], reverse=True)
    top_feats = []
    seen = set()
    for col, op, val, _ in candidates:
        if col in seen:
            continue
        top_feats.append((col, op, val))
        seen.add(col)
        if len(top_feats) >= 3:
            break

    if not top_feats:
        return best_rule

    # try pairs and triples
    for r in (2, 3):
        for combo in combinations(top_feats, r):
            rule = SimpleRule(direction, combo, " AND ".join(f"{c}{o}{v:.4g}" for c, o, v in combo))
            mask = rule.mask(train)
            n = int(mask.sum())
            if n < 50:
                continue
            prec = float(y[mask].mean())
            days = train.loc[mask, "session_date"].nunique() if "session_date" in train.columns else max(n / 26, 1)
            tpd = n / max(days, 1)
            # prefer precision with frequency near target
            freq_pen = abs(tpd - target_trades_day) / max(target_trades_day, 0.25)
            score = prec - 0.05 * freq_pen
            if score > best_score:
                best_score = score
                best_rule = rule

    if best_rule.conditions:
        return best_rule
    # fallback: best single-feature rule
    if candidates:
        col, op, val, _ = candidates[0]
        return SimpleRule(direction, ((col, op, val),), f"{col}{op}{val:.4g}")
    return best_rule


def _tree_rules(train: pd.DataFrame, feature_cols: Tuple[str, ...], target_col: str, direction: str) -> str:
    cols = [c for c in feature_cols if c in train.columns]
    if not cols or train[target_col].sum() < WF_MIN_TRAIN_STRONG:
        return ""
    X = train[cols].fillna(0.0)
    y = train[target_col].astype(int)
    clf = DecisionTreeClassifier(max_depth=3, min_samples_leaf=50, class_weight="balanced", random_state=42)
    clf.fit(X, y)
    return export_text(clf, feature_names=cols)


def precision_curve(df: pd.DataFrame, score: pd.Series, target: pd.Series, direction: str) -> pd.DataFrame:
    base = float(target.mean()) if len(target) else 0.0
    order = score.rank(method="first", ascending=False)
    rows = []
    for pct in PRECISION_TOP_PCTS:
        cutoff = int(max(len(df) * pct / 100.0, 1))
        sel = order <= cutoff
        if sel.sum() == 0:
            continue
        prec = float(target[sel].mean())
        rows.append(
            {
                "direction": direction,
                "top_pct": pct,
                "n": int(sel.sum()),
                "precision": prec,
                "baseline_rate": base,
                "lift": prec / base if base > 0 else np.nan,
            }
        )
    return pd.DataFrame(rows)


def _ml_score(train: pd.DataFrame, test: pd.DataFrame, feature_cols: Tuple[str, ...], target_col: str) -> Tuple[pd.Series, pd.Series]:
    from sklearn.ensemble import GradientBoostingClassifier

    cols = [c for c in feature_cols if c in train.columns]
    X_tr = train[cols].fillna(0.0)
    y_tr = train[target_col].astype(int)
    X_te = test[cols].fillna(0.0)
    if y_tr.sum() < WF_MIN_TRAIN_STRONG:
        return pd.Series(0.0, index=test.index), pd.Series(0.0, index=train.index)
    model = GradientBoostingClassifier(
        n_estimators=100, max_depth=3, min_samples_leaf=50, random_state=42
    )
    model.fit(X_tr, y_tr)
    return pd.Series(model.predict_proba(X_te)[:, 1], index=test.index), pd.Series(
        model.predict_proba(X_tr)[:, 1], index=train.index
    )


def simulate_signals(
    signals: pd.DataFrame,
    market: pd.DataFrame,
    *,
    entry_model: str = DISCOVERY_ENTRY_MODEL,
) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    cfg = SimConfig(
        entry_model=entry_model,
        stop_atr=DISCOVERY_STOP_ATR,
        target_r=DISCOVERY_TARGET_R,
        max_bars=DISCOVERY_MAX_BARS,
        management="FIXED",
    )
    rows = []
    for i, row in enumerate(signals.itertuples(index=False), start=1):
        sig = pd.Series(
            {
                "signal_id": i,
                "direction": row.direction,
                "entry_timestamp": row.timestamp,
            }
        )
        res = simulate_trade(sig, market, pos_map, cfg)
        rows.append(
            {
                "timestamp": row.timestamp,
                "direction": row.direction,
                "entry_timestamp": res.entry_timestamp,
                "entry_price": res.entry_price,
                "stop_price": res.stop_price,
                "filled": res.filled,
                "result_R": res.result_R,
                "exit_reason": res.exit_reason,
                "mfe_r": res.mfe_r,
                "mae_r": res.mae_r,
                "entry_model": entry_model,
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["net_R"] = apply_costs(out.assign(entry_price=out["entry_price"], stop_price=out["stop_price"]))
    return out


def walk_forward_discovery(
    dataset: pd.DataFrame,
    market: pd.DataFrame,
    *,
    rth_days: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, SimpleRule, SimpleRule, pd.DataFrame]:
    """Returns predictions, trades, long/short precision curves, rule candidates, best rules."""
    all_preds = []
    all_trades = []
    long_curves = []
    short_curves = []
    rule_rows = []
    last_long_rule = SimpleRule("Long", tuple(), "")
    last_short_rule = SimpleRule("Short", tuple(), "")

    tz = dataset["timestamp"].dt.tz

    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, start=1):
        train = dataset[
            (dataset["timestamp"] >= pd.Timestamp(tr_s, tz=tz))
            & (dataset["timestamp"] <= pd.Timestamp(tr_e, tz=tz))
        ].copy()
        test = dataset[
            (dataset["timestamp"] >= pd.Timestamp(te_s, tz=tz))
            & (dataset["timestamp"] <= pd.Timestamp(te_e, tz=tz))
        ].copy()
        if train.empty or test.empty:
            continue

        long_rule = _discover_rule(train, direction="Long", target_col="long_strong", feature_cols=FEATURE_COLS_LONG)
        short_rule = _discover_rule(train, direction="Short", target_col="short_strong", feature_cols=FEATURE_COLS_SHORT)
        last_long_rule, last_short_rule = long_rule, short_rule

        tree_long = _tree_rules(train, FEATURE_COLS_LONG, "long_strong", "Long")
        tree_short = _tree_rules(train, FEATURE_COLS_SHORT, "short_strong", "Short")

        ml_score_te_l, ml_score_tr_l = _ml_score(train, test, FEATURE_COLS_LONG, "long_strong")
        ml_score_te_s, ml_score_tr_s = _ml_score(train, test, FEATURE_COLS_SHORT, "short_strong")

        long_curves.append(precision_curve(test, ml_score_te_l, test["long_strong"], "Long"))
        short_curves.append(precision_curve(test, ml_score_te_s, test["short_strong"], "Short"))

        rule_rows.append(
            {
                "fold": fold_i,
                "direction": "Long",
                "rule": long_rule.description,
                "tree_upper_bound": tree_long[:500],
            }
        )
        rule_rows.append(
            {
                "fold": fold_i,
                "direction": "Short",
                "rule": short_rule.description,
                "tree_upper_bound": tree_short[:500],
            }
        )

        for direction, rule, target_col in (
            ("Long", long_rule, "long_strong"),
            ("Short", short_rule, "short_strong"),
        ):
            mask = rule.mask(test)
            sigs = test.loc[mask, ["timestamp"]].copy()
            sigs["direction"] = direction
            sigs["fold"] = fold_i
            sigs["rule"] = rule.description
            sigs["label_strong"] = test.loc[mask, target_col].astype(bool).values
            sigs["ml_score"] = ml_score_te_l[mask].values if direction == "Long" else ml_score_te_s[mask].values
            all_preds.append(sigs)
            sim = simulate_signals(sigs, market)
            if not sim.empty:
                sim["fold"] = fold_i
                sim["rule"] = rule.description
                all_preds[-1] = sigs.merge(sim, on="timestamp", how="left")
                all_trades.append(sim)

    preds = pd.concat(all_preds, ignore_index=True) if all_preds else pd.DataFrame()
    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    long_pc = pd.concat(long_curves, ignore_index=True) if long_curves else pd.DataFrame()
    short_pc = pd.concat(short_curves, ignore_index=True) if short_curves else pd.DataFrame()
    rules = pd.DataFrame(rule_rows)

    # aggregate precision curves
    if not long_pc.empty:
        long_pc = long_pc.groupby("top_pct", as_index=False).agg(
            precision=("precision", "mean"), lift=("lift", "mean"), baseline_rate=("baseline_rate", "mean")
        )
        long_pc["direction"] = "Long"
    if not short_pc.empty:
        short_pc = short_pc.groupby("top_pct", as_index=False).agg(
            precision=("precision", "mean"), lift=("lift", "mean"), baseline_rate=("baseline_rate", "mean")
        )
        short_pc["direction"] = "Short"

    return preds, trades, long_pc, short_pc, rules, last_long_rule, last_short_rule


def entry_timing_comparison(
    dataset: pd.DataFrame,
    market: pd.DataFrame,
    *,
    sample_n: int = 2000,
) -> pd.DataFrame:
    """Matched-event timing on STRONG labels."""
    strong = dataset.loc[dataset["long_strong"] | dataset["short_strong"]].copy()
    if len(strong) > sample_n:
        strong = strong.sample(sample_n, random_state=42)
    models = ("CURRENT", "NEXT_OPEN", "NEXT_CLOSE", "RETRACE_25", "RETRACE_50")
    rows = []
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    for _, row in strong.iterrows():
        direction = "Long" if row["long_strong"] else "Short"
        for model in models:
            sig = pd.Series({"signal_id": 1, "direction": direction, "entry_timestamp": row["timestamp"]})
            cfg = SimConfig(
                entry_model=model,
                stop_atr=DISCOVERY_STOP_ATR,
                target_r=DISCOVERY_TARGET_R,
                max_bars=DISCOVERY_MAX_BARS,
            )
            res = simulate_trade(sig, market, pos_map, cfg)
            rows.append(
                {
                    "timestamp": row["timestamp"],
                    "direction": direction,
                    "entry_model": model,
                    "filled": res.filled,
                    "result_R": res.result_R if res.filled else np.nan,
                    "label_strong": True,
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    summary = (
        out.groupby(["direction", "entry_model"])
        .agg(
            N=("filled", "sum"),
            fill_rate=("filled", "mean"),
            AvgR=("result_R", "mean"),
        )
        .reset_index()
    )
    return summary
