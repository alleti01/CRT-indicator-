"""Phase77 path metrics, random direction gate, matched controls."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (
    ENTRY_DELAY_BARS,
    LATE_CONFIRMATION_FRAC,
    MATCH_SEED,
    MAX_SMD_ACCEPT,
    MIN_EFFECT_FP11,
    MIN_N_SETUP,
    RANDOM_SEED_COUNT,
    RANDOM_SEED_START,
)

HORIZONS = (3, 5, 10, 15, 30, 60)
FP_PAIRS = (
    (0.5, 0.5), (1.0, 1.0), (1.5, 1.0), (2.0, 1.0), (2.5, 1.0), (3.0, 1.0),
    (1.0, 1.5), (2.0, 1.5), (2.5, 1.5),
)


def path_metrics(signals: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals
    idx = m1.index
    pos = {ts: i for i, ts in enumerate(idx)}
    highs = m1["high"].values
    lows = m1["low"].values
    closes = m1["close"].values
    opens = m1["open"].values

    rows = []
    for _, sig in signals.iterrows():
        ets = sig["entry_ts"]
        if ets not in pos:
            continue
        start = pos[ets]
        ep = float(sig["entry_price"])
        atr = float(sig["atr"])
        if atr <= 0:
            continue
        d = 1 if sig["direction"] == "LONG" else -1
        end = min(start + 60, len(m1) - 1)
        rec = sig.to_dict()

        sig_i = pos.get(sig["signal_ts"])
        pre_move = 0.0
        if sig_i is not None and sig_i < start:
            pre_move = abs(ep - closes[sig_i]) / atr

        h_slice = highs[start : end + 1]
        l_slice = lows[start : end + 1]
        if d == 1:
            fav = (np.maximum.accumulate(h_slice) - ep) / atr
            adv = (ep - np.minimum.accumulate(l_slice)) / atr
        else:
            fav = (ep - np.minimum.accumulate(l_slice)) / atr
            adv = (np.maximum.accumulate(h_slice) - ep) / atr

        for h in HORIZONS:
            w = min(h, len(fav))
            if w:
                rec[f"mfe_{h}m"] = float(np.max(fav[:w]))
                rec[f"mae_{h}m"] = float(np.max(adv[:w]))

        for tg, st in FP_PAIRS:
            hit_tg = hit_st = False
            for j in range(len(fav)):
                if fav[j] >= tg:
                    hit_tg = True
                if adv[j] >= st:
                    hit_st = True
                if hit_tg and not hit_st:
                    rec[f"fp_{tg}atr_before_{st}atr"] = 1.0
                    break
                if hit_st and not hit_tg:
                    rec[f"fp_{tg}atr_before_{st}atr"] = 0.0
                    break
            else:
                rec[f"fp_{tg}atr_before_{st}atr"] = 0.5 if hit_tg and hit_st else np.nan

        total_15 = float(np.max(fav[: min(15, len(fav))]) + np.max(adv[: min(15, len(adv))])) if len(fav) else 0
        rec["movement_before_confirmation_atr"] = pre_move
        rec["movement_after_confirmation_atr"] = float(np.max(fav[: min(15, len(fav))])) if len(fav) else 0
        rec["fraction_move_completed"] = pre_move / total_15 if total_15 > 0 else np.nan
        rec["confirmation_too_late"] = bool(pre_move / max(total_15, 0.01) > LATE_CONFIRMATION_FRAC)
        rec["entry_delay_bars"] = int(start - sig_i) if sig_i is not None else ENTRY_DELAY_BARS
        rec["chase_atr"] = abs(ep - closes[sig_i]) / atr if sig_i is not None else 0.0
        rows.append(rec)

    return pd.DataFrame(rows)


def aggregate_paths(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"n": 0}
    out: dict = {"n": len(df)}
    for h in HORIZONS:
        mfe = df[f"mfe_{h}m"].dropna()
        mae = df[f"mae_{h}m"].dropna()
        if len(mfe):
            out[f"mfe_{h}m"] = float(mfe.mean())
            out[f"mae_{h}m"] = float(mae.mean())
            out[f"das_{h}m"] = float(mfe.mean() / mae.mean()) if mae.mean() else np.nan
    for tg, st in ((1.0, 1.0), (2.0, 1.0), (2.0, 1.5)):
        col = f"fp_{tg}atr_before_{st}atr"
        if col in df:
            s = df[col].dropna()
            if len(s):
                out[col] = float(s.mean())
    if "confirmation_too_late" in df:
        out["pct_confirmation_too_late"] = float(df["confirmation_too_late"].mean())
    return out


def random_direction_eval(signals: pd.DataFrame, m1: pd.DataFrame) -> dict:
    if len(signals) < MIN_N_SETUP:
        return {"status": "N_TOO_SMALL", "n": len(signals)}
    real = path_metrics(signals, m1)
    real_agg = aggregate_paths(real)
    fp_real = real_agg.get("fp_1.0atr_before_1.0atr", np.nan)

    rand_fp = []
    for seed in range(RANDOM_SEED_START, RANDOM_SEED_START + RANDOM_SEED_COUNT):
        rng = np.random.RandomState(seed)
        flip = signals.copy()
        flip["direction"] = np.where(rng.rand(len(flip)) < 0.5, "LONG", "SHORT")
        flip_agg = aggregate_paths(path_metrics(flip, m1))
        v = flip_agg.get("fp_1.0atr_before_1.0atr")
        if v is not None and not np.isnan(v):
            rand_fp.append(v)

    flipped = signals.copy()
    flipped["direction"] = flipped["direction"].map({"LONG": "SHORT", "SHORT": "LONG"})
    flip_agg = aggregate_paths(path_metrics(flipped, m1))
    fp_flip = flip_agg.get("fp_1.0atr_before_1.0atr", np.nan)

    arr = np.array(rand_fp)
    result = {
        "status": "FAIL",
        "n": len(signals),
        "fp11_real": fp_real,
        "fp11_random_mean": float(arr.mean()) if len(arr) else np.nan,
        "fp11_random_median": float(np.median(arr)) if len(arr) else np.nan,
        "fp11_random_std": float(arr.std()) if len(arr) else np.nan,
        "fp11_random_p5": float(np.percentile(arr, 5)) if len(arr) else np.nan,
        "fp11_random_p95": float(np.percentile(arr, 95)) if len(arr) else np.nan,
        "fp11_real_percentile": float((arr < fp_real).mean() * 100) if len(arr) and not np.isnan(fp_real) else np.nan,
        "fp11_real_minus_random": float(fp_real - arr.mean()) if len(arr) and not np.isnan(fp_real) else np.nan,
        "fp11_flip": fp_flip,
    }
    if not np.isnan(fp_real) and len(arr) and (fp_real - arr.mean()) >= MIN_EFFECT_FP11 and fp_real > fp_flip:
        result["status"] = "PASS"
    return result


def confluence_gradient(signals: pd.DataFrame, m1: pd.DataFrame) -> list[dict]:
    rows = []
    for cc in range(3, 8):
        sub = signals[signals["confluence_count"] == cc]
        agg = aggregate_paths(path_metrics(sub, m1)) if len(sub) else {"n": 0}
        rows.append({"confluence": cc, **agg})
    return rows


def split_chronological(signals: pd.DataFrame) -> pd.Series:
    order = signals["entry_ts"].sort_values()
    n = len(order)
    t_end = int(n * 0.60)
    v_end = int(n * 0.80)
    split = pd.Series("PILOT_TEST", index=order.index)
    split.iloc[:t_end] = "TRAIN"
    split.iloc[t_end:v_end] = "VALIDATION"
    return split
