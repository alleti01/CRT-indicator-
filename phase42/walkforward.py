"""Walk-forward sparse precision discovery."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session

from .config import MAX_TPD, PRECISION_TIERS, RTH_SESSION, TARGET_TPD_PREF, WALK_FORWARD_FOLDS
from .simulate import enrich_net, rth_days, simulate_trade


def _cols_available(df: pd.DataFrame) -> List[str]:
    pref = [
        "ret_3_atr", "ret_6_atr", "dist_ema8_atr", "dist_ema20_atr", "dist_session_low_atr",
        "dist_session_high_atr", "body_atr", "upper_wick_ratio", "lower_wick_ratio", "close_loc",
        "range_atr", "rel_volume", "atr_expansion", "atr_percentile", "impulse_3bar",
        "micro_higher_low", "micro_lower_high", "reclaim_prior_mid", "failed_new_low", "failed_new_high",
        "directional_efficiency", "overlap_density_5",
    ]
    return [c for c in pref if c in df.columns]


def _prep_xy(df: pd.DataFrame, cols: List[str]) -> Tuple[pd.DataFrame, np.ndarray]:
    x = df[cols].astype(float).replace([np.inf, -np.inf], np.nan)
    med = x.median()
    x = x.fillna(med)
    y = df["label"].astype(int).values
    return x, y


def _extension_mask(feats: pd.DataFrame, direction: str, thr: dict) -> pd.Series:
    if direction == "Long":
        return feats["ret_6_atr"] <= thr.get("ret_6_max", -0.8)
    return feats["ret_6_atr"] >= thr.get("ret_6_min", 0.8)


def walk_forward_sparse(
    market: pd.DataFrame,
    feats: pd.DataFrame,
    train_dataset: pd.DataFrame,
    *,
    entry_mode: str = "CURRENT",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    from sklearn.linear_model import LogisticRegression

    cols = _cols_available(feats)
    pos = {ts: i for i, ts in enumerate(market.index)}
    rth = pd.Series([is_in_session(ts, RTH_SESSION) for ts in feats.index], index=feats.index)
    all_rth = feats.loc[rth]

    wf_trades = []
    wf_preds = []
    wf_selections = []
    tier_rows = []

    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, start=1):
        tz = feats.index.tz
        tr_lo, tr_hi = pd.Timestamp(tr_s, tz=tz), pd.Timestamp(tr_e, tz=tz)
        te_lo, te_hi = pd.Timestamp(te_s, tz=tz), pd.Timestamp(te_e, tz=tz)

        for direction, dcode, stype in (("Long", 1, "MRL"), ("Short", -1, "MRS")):
            tr_data = train_dataset.loc[
                (train_dataset["timestamp"] >= tr_lo)
                & (train_dataset["timestamp"] <= tr_hi)
                & (train_dataset["direction"] == direction)
            ]
            if len(tr_data) < 30 or tr_data["label"].sum() < 5 or (tr_data["label"] == 0).sum() < 10:
                continue
            Xtr, ytr = _prep_xy(tr_data, cols)
            lr = LogisticRegression(max_iter=1000, class_weight="balanced", C=0.5)
            lr.fit(Xtr, ytr)

            ext_thr = {
                "ret_6_max": float(tr_data.loc[tr_data["label"] == 1, "ret_6_atr"].quantile(0.75)) if direction == "Long" else None,
                "ret_6_min": float(tr_data.loc[tr_data["label"] == 1, "ret_6_atr"].quantile(0.25)) if direction == "Short" else None,
            }
            tr_bars = all_rth.loc[(all_rth.index >= tr_lo) & (all_rth.index <= tr_hi)]
            tr_bars = tr_bars.loc[_extension_mask(tr_bars, direction, ext_thr)]
            if tr_bars.empty:
                continue
            Xtr_all = tr_bars[cols].astype(float).replace([np.inf, -np.inf], np.nan).fillna(tr_bars[cols].median())
            p_tr = lr.predict_proba(Xtr_all)[:, 1]

            te_bars = all_rth.loc[(all_rth.index >= te_lo) & (all_rth.index <= te_hi)]
            te_bars = te_bars.loc[_extension_mask(te_bars, direction, ext_thr)]
            if te_bars.empty:
                continue
            Xte = te_bars[cols].astype(float).replace([np.inf, -np.inf], np.nan).fillna(te_bars[cols].median())
            p_te = lr.predict_proba(Xte)[:, 1]

            tr_days = rth_days(tr_bars.index)
            te_days = rth_days(te_bars.index)
            best_thr = None
            best_tier = None
            for tier in PRECISION_TIERS:
                thr = float(np.quantile(p_tr, tier))
                n_tr = int((p_tr >= thr).sum())
                tpd_tr = n_tr / tr_days
                if tpd_tr > MAX_TPD:
                    continue
                if tpd_tr < 0.05:
                    continue
                best_thr = thr
                best_tier = tier
                break
            if best_thr is None:
                # fallback: threshold for ~0.3 tpd on train
                target_n = int(TARGET_TPD_PREF * tr_days)
                order = np.sort(p_tr)[::-1]
                best_thr = float(order[min(target_n, len(order) - 1)]) if len(order) else 1.0
                best_tier = 0.0

            fired = te_bars.loc[p_te >= best_thr]
            tpd_te = len(fired) / te_days
            score_map = dict(zip(fired.index, p_te[p_te >= best_thr]))

            wf_selections.append(
                {
                    "fold": fold_i,
                    "direction": direction,
                    "signal_type": stype,
                    "threshold": best_thr,
                    "tier": best_tier,
                    "train_days": tr_days,
                    "test_days": te_days,
                    "test_signals": len(fired),
                    "test_tpd": tpd_te,
                    "top_features": ",".join([cols[i] for i in np.argsort(np.abs(lr.coef_[0]))[::-1][:5]]),
                }
            )

            for ts in fired.index:
                if ts not in pos:
                    continue
                sim = simulate_trade(market, pos[ts], dcode, entry_mode=entry_mode)
                if not sim:
                    continue
                sc = float(score_map[ts])
                wf_trades.append(
                    {
                        "fold": fold_i,
                        "marker_bar_timestamp": ts,
                        "signal_type": stype,
                        "direction": direction,
                        "score": sc,
                        "threshold": best_thr,
                        **sim,
                    }
                )
                wf_preds.append({"fold": fold_i, "timestamp": ts, "direction": direction, "score": sc, "fired": 1})

            for tier in PRECISION_TIERS:
                thr = float(np.quantile(p_tr, tier))
                sub = te_bars.loc[p_te >= thr]
                tier_rows.append({"fold": fold_i, "direction": direction, "tier": tier, "threshold": thr, "N": len(sub), "tpd": len(sub) / te_days})

    trades = pd.DataFrame(wf_trades)
    if not trades.empty:
        trades = enrich_net(trades)
    meta = {
        "cols": cols,
        "entry_mode": entry_mode,
    }
    return pd.DataFrame(wf_preds), trades, pd.DataFrame(wf_selections), pd.DataFrame(tier_rows), meta


def rule_from_selections(selections: pd.DataFrame) -> dict:
    if selections.empty:
        return {}
    stable = selections.groupby("direction")["top_features"].apply(lambda s: s.mode().iloc[0] if len(s.mode()) else "").to_dict()
    return {
        "name": "SPARSE_LR_MISSED_REVERSAL",
        "description": "Walk-forward logistic regression on missed-reversal positives vs matched negatives; train-only score threshold for sparse firing",
        "stable_features": stable,
        "median_test_tpd": float(selections["test_tpd"].median()) if not selections.empty else np.nan,
    }
