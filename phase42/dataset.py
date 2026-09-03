"""Build sparse training dataset: missed positives + matched negatives."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session

from .config import P41_CAPTURE, P41_MISSED, P41_OPPORTUNITIES, RTH_SESSION

FEATURE_COLS = [
    "ret_3_atr", "ret_6_atr", "ret_8_atr", "dist_ema8_atr", "dist_ema20_atr",
    "dist_session_high_atr", "dist_session_low_atr", "body_atr", "upper_wick_ratio",
    "lower_wick_ratio", "close_loc", "range_atr", "rel_volume", "atr_expansion",
    "atr_percentile", "impulse_3bar", "micro_higher_low", "micro_lower_high",
    "reclaim_prior_mid", "failed_new_low", "failed_new_high", "directional_efficiency",
    "pre_entry_efficiency_5", "overlap_density_5", "alternating_bars_8",
]


def verify_phase41_parity() -> pd.DataFrame:
    cap = pd.read_csv(P41_CAPTURE)
    opp = pd.read_csv(P41_OPPORTUNITIES)
    n_total = len(opp)
    n_miss = int((cap["capture_status"] == "MISSED").sum())
    n_p33 = int((cap["capture_status"] == "CAPTURED_PHASE33").sum())
    n_p40 = int((cap["capture_status"] == "CAPTURED_PHASE40").sum())
    n_any = int((cap["capture_status"] != "MISSED").sum())
    return pd.DataFrame(
        [
            {"metric": "total_major_reversals", "value": n_total},
            {"metric": "phase33_captured", "value": n_p33},
            {"metric": "phase40_captured_rev", "value": n_p40},
            {"metric": "captured_any", "value": n_any},
            {"metric": "completely_missed", "value": n_miss},
            {"metric": "missed_pct", "value": n_miss / n_total if n_total else 0},
        ]
    )


def load_missed() -> pd.DataFrame:
    m = pd.read_csv(P41_MISSED)
    m["extreme_timestamp"] = pd.to_datetime(m["extreme_timestamp"], utc=True)
    return m


def _causal_decision_ts(market: pd.DataFrame, extreme_ts: pd.Timestamp):
    """Use turn-bar close (extreme bar) as causal decision timestamp."""
    if extreme_ts in market.index:
        return extreme_ts
    # nearest prior bar if exact timestamp missing
    prior = market.index[market.index <= extreme_ts]
    return prior[-1] if len(prior) else None


def build_matched_negatives(
    market: pd.DataFrame,
    feats: pd.DataFrame,
    missed: pd.DataFrame,
    opportunities: pd.DataFrame,
) -> pd.DataFrame:
    """Sample negatives from RTH bars similar to positives but not major reversal windows."""
    rng_seed = np.random.default_rng(42)
    opp_ts = set(pd.to_datetime(opportunities["extreme_timestamp"], utc=True))
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    exclude: set[pd.Timestamp] = set()
    for ts in opp_ts:
        if ts not in pos_map:
            continue
        i = pos_map[ts]
        for j in range(max(0, i - 3), min(len(market), i + 4)):
            exclude.add(market.index[j])

    rth_idx = [ts for ts in market.index if is_in_session(ts, RTH_SESSION) and ts not in exclude]
    rth_df = feats.loc[rth_idx].copy()
    rth_df["hour_bucket"] = [t.hour for t in rth_df.index]
    atr_pct = rth_df["atr_percentile"].fillna(0.5)
    rth_df["atr_q"] = pd.qcut(atr_pct, 4, labels=False, duplicates="drop")

    pos_rows: list[dict] = []
    for opp in missed.itertuples(index=False):
        ts = _causal_decision_ts(market, pd.Timestamp(opp.extreme_timestamp))
        if ts is None or ts not in feats.index:
            continue
        pos_rows.append({"timestamp": ts, "direction": opp.direction, "label": 1, "event_id": opp.event_id})

    neg_rows: list[dict] = []
    ret_col = "ret_6_atr"
    for pr in pos_rows:
        ts = pr["timestamp"]
        direction = pr["direction"]
        if ts not in rth_df.index:
            continue
        ref = rth_df.loc[ts]
        hb, aq = ref["hour_bucket"], ref["atr_q"]
        ref_ret = float(ref.get(ret_col, 0))
        pool = rth_df.loc[(rth_df["hour_bucket"] == hb) & (rth_df["atr_q"] == aq)]
        if direction == "Long":
            pool = pool.loc[pool[ret_col] <= ref_ret + 0.35]
        else:
            pool = pool.loc[pool[ret_col] >= ref_ret - 0.35]
        pos_ts = {p["timestamp"] for p in pos_rows}
        pool = pool.loc[~pool.index.isin(pos_ts)]
        if len(pool) < 5:
            pool = rth_df.loc[~rth_df.index.isin(pos_ts)]
        n_pick = min(5, len(pool))
        picks = pool.sample(n=n_pick, random_state=int(rng_seed.integers(0, 1_000_000)))
        for pts in picks.index:
            neg_rows.append({"timestamp": pts, "direction": direction, "label": 0, "event_id": ""})

    # Broad false-reversal pool (phase41-style) to ensure negatives in every era
    atr = market["atr"].astype(float)
    ret6 = (market["close"] - market["close"].shift(6)) / atr
    bar_rng = market["high"] - market["low"]
    upper_wick = (market["high"] - market[["open", "close"]].max(axis=1)) / bar_rng.replace(0, np.nan)
    lower_wick = (market[["open", "close"]].min(axis=1) - market["low"]) / bar_rng.replace(0, np.nan)
    bull_fake = (ret6 < -0.8) & (lower_wick > 0.30) & (~market.index.isin(exclude))
    bear_fake = (ret6 > 0.8) & (upper_wick > 0.30) & (~market.index.isin(exclude))
    for mask, direction in ((bull_fake, "Long"), (bear_fake, "Short")):
        idxs = [ts for ts in market.index[mask] if is_in_session(ts, RTH_SESSION)]
        if not idxs:
            continue
        pick = rng_seed.choice(len(idxs), size=min(len(idxs), len(pos_rows)), replace=False)
        for pi in pick:
            neg_rows.append({"timestamp": idxs[pi], "direction": direction, "label": 0, "event_id": ""})

    pos_df = pd.DataFrame(pos_rows)
    neg_df = pd.DataFrame(neg_rows).drop_duplicates(subset=["timestamp", "direction"])
    return pd.concat([pos_df, neg_df], ignore_index=True)


def attach_features(dataset: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in dataset.itertuples(index=False):
        ts = pd.Timestamp(row.timestamp)
        if ts not in feats.index:
            continue
        d = feats.loc[ts].to_dict()
        d.update({"timestamp": ts, "direction": row.direction, "label": row.label, "event_id": row.event_id})
        rows.append(d)
    return pd.DataFrame(rows)
