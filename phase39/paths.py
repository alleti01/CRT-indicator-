"""Reconstruct complete post-entry price paths for frozen signals."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def max_hold_bars(signal_type: str) -> int:
    return 4 if signal_type in ("L", "S") else 3


def target_r(signal_type: str) -> float:
    return 3.0 if signal_type in ("L", "S") else 2.5


def reconstruct_path(sig, market: pd.DataFrame, pos: dict) -> Dict[str, float | str | int]:
    ts = pd.Timestamp(sig.marker_bar_timestamp)
    if ts not in pos:
        return {}
    entry_i = pos[ts]
    entry_px = float(sig.entry_price)
    stop = float(sig.stop)
    target = float(sig.target)
    st = str(sig.signal_type)
    direction = 1 if str(sig.direction).lower() == "long" else -1
    atr_entry = float(sig.atr) if hasattr(sig, "atr") and np.isfinite(sig.atr) else float(market.iloc[entry_i]["atr"])
    risk = abs(entry_px - stop)
    if risk <= 0:
        risk = 1e-9
    max_bars = max_hold_bars(st)
    tgt_r = target_r(st)

    mfe_r = mae_r = 0.0
    mfe_atr = mae_atr = 0.0
    max_fwd_range = 0.0
    net_dir = 0.0
    total_abs = 0.0
    dir_changes = 0
    consec_fav = consec_adv = 0
    max_consec_fav = max_consec_adv = 0
    near_entry_bars = 0
    prev_close = entry_px

    bars_to = {
        "bars_to_plus_0.25r": np.nan,
        "bars_to_plus_0.50r": np.nan,
        "bars_to_plus_1.00r": np.nan,
        "bars_to_plus_1.50r": np.nan,
        "bars_to_plus_2.00r": np.nan,
        "bars_to_target": np.nan,
        "bars_to_minus_0.25r": np.nan,
        "bars_to_minus_0.50r": np.nan,
        "bars_to_minus_1.00r": np.nan,
    }

    exit_type = "DATA_END"
    exit_ts = ts
    exit_px = entry_px
    realized_r = 0.0
    bars_held = 0

    for elapsed, j in enumerate(range(entry_i + 1, len(market)), start=1):
        bar = market.iloc[j]
        hi, lo, cl = float(bar.high), float(bar.low), float(bar.close)
        bar_atr = float(bar.atr) if np.isfinite(bar.atr) else atr_entry

        if direction == 1:
            bar_mfe_r = (hi - entry_px) / risk
            bar_mae_r = (entry_px - lo) / risk
            bar_mfe_atr = (hi - entry_px) / bar_atr if bar_atr > 0 else 0.0
            bar_mae_atr = (entry_px - lo) / bar_atr if bar_atr > 0 else 0.0
            hit_stop = lo <= stop
            hit_tgt = hi >= target
            bar_dir = cl - prev_close
            fav_bar = cl >= prev_close
        else:
            bar_mfe_r = (entry_px - lo) / risk
            bar_mae_r = (hi - entry_px) / risk
            bar_mfe_atr = (entry_px - lo) / bar_atr if bar_atr > 0 else 0.0
            bar_mae_atr = (hi - entry_px) / bar_atr if bar_atr > 0 else 0.0
            hit_stop = hi >= stop
            hit_tgt = lo <= target
            bar_dir = prev_close - cl
            fav_bar = cl <= prev_close

        mfe_r = max(mfe_r, bar_mfe_r)
        mae_r = max(mae_r, bar_mae_r)
        mfe_atr = max(mfe_atr, bar_mfe_atr)
        mae_atr = max(mae_atr, bar_mae_atr)
        max_fwd_range = max(max_fwd_range, hi - lo)
        net_dir += bar_dir * direction
        total_abs += abs(cl - prev_close)
        if elapsed > 1 and np.sign(bar_dir) != np.sign(prev_close - market.iloc[j - 1].close) and bar_dir != 0:
            dir_changes += 1
        if fav_bar:
            consec_fav += 1
            consec_adv = 0
        else:
            consec_adv += 1
            consec_fav = 0
        max_consec_fav = max(max_consec_fav, consec_fav)
        max_consec_adv = max(max_consec_adv, consec_adv)
        if abs(cl - entry_px) / risk < 0.15:
            near_entry_bars += 1

        for lvl, key in ((0.25, "bars_to_plus_0.25r"), (0.50, "bars_to_plus_0.50r"), (1.00, "bars_to_plus_1.00r"),
                         (1.50, "bars_to_plus_1.50r"), (2.00, "bars_to_plus_2.00r")):
            if np.isnan(bars_to[key]) and bar_mfe_r >= lvl:
                bars_to[key] = elapsed
        if np.isnan(bars_to["bars_to_target"]) and bar_mfe_r >= tgt_r:
            bars_to["bars_to_target"] = elapsed
        for lvl, key in ((0.25, "bars_to_minus_0.25r"), (0.50, "bars_to_minus_0.50r"), (1.00, "bars_to_minus_1.00r")):
            if np.isnan(bars_to[key]) and bar_mae_r >= lvl:
                bars_to[key] = elapsed

        prev_close = cl
        bars_held = elapsed

        if hit_stop:
            exit_type = "STOP"
            exit_ts = market.index[j]
            exit_px = stop
            realized_r = -1.0
            break
        if hit_tgt:
            exit_type = "TARGET"
            exit_ts = market.index[j]
            exit_px = target
            realized_r = tgt_r
            break
        if elapsed >= max_bars:
            exit_type = "TIME"
            exit_ts = market.index[j]
            exit_px = cl
            realized_r = (cl - entry_px) / risk * direction
            break

    fav_move = max(net_dir, 0.0)
    adv_move = max(-net_dir, 0.0)
    dir_eff = fav_move / total_abs if total_abs > 0 else 0.0
    move_eff = mfe_r / (mfe_r + mae_r) if (mfe_r + mae_r) > 0 else 0.0

    out = {
        "signal_id": sig.signal_id,
        "marker_bar_timestamp": ts,
        "signal_type": st,
        "direction": sig.direction,
        "entry_price": entry_px,
        "stop": stop,
        "target": target,
        "risk_points": risk,
        "atr_at_entry": atr_entry,
        "exit_type": exit_type,
        "exit_timestamp": exit_ts,
        "exit_price": exit_px,
        "realized_R": realized_r,
        "MFE_R": mfe_r,
        "MAE_R": mae_r,
        "MFE_ATR": mfe_atr,
        "MAE_ATR": mae_atr,
        "bars_held": bars_held,
        "max_forward_range": max_fwd_range,
        "net_directional_move": net_dir,
        "total_absolute_move": total_abs,
        "directional_efficiency": dir_eff,
        "movement_efficiency": move_eff,
        "fav_excursion_over_total": mfe_r * risk / total_abs if total_abs > 0 else 0.0,
        "adv_excursion_over_total": mae_r * risk / total_abs if total_abs > 0 else 0.0,
        "time_near_entry_bars": near_entry_bars,
        "direction_changes": dir_changes,
        "max_consec_favorable": max_consec_fav,
        "max_consec_adverse": max_consec_adv,
    }
    out.update(bars_to)
    return out


def build_signal_paths(signals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    pos = {ts: i for i, ts in enumerate(market.index)}
    rows = []
    for sig in signals.itertuples(index=False):
        row = reconstruct_path(sig, market, pos)
        if row:
            rows.append(row)
    return pd.DataFrame(rows)
