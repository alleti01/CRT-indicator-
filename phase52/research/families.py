"""S52 structure families A–G — causal 1M signal generation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session
from phase52.config import ATR_BREAK_MULTS, DEFAULT_SWING, DISPLACEMENT_BODY_MULT, RTH_SESSION
from phase52.research.swings import (
    causal_swing_high,
    causal_swing_low,
    precompute_swing_highs,
    precompute_swing_lows,
    precompute_last2_swing_highs,
    precompute_last2_swing_lows,
    recent_swing_highs,
    recent_swing_lows,
)


def _body_series(open_: np.ndarray, close: np.ndarray) -> np.ndarray:
    return np.abs(close - open_)


def generate_family_signals(
    market: pd.DataFrame,
    family: str,
    *,
    swing: int = DEFAULT_SWING,
    atr_mult: float = 0.0,
    rth_only: bool = False,
    start_i: int = 500,
) -> pd.DataFrame:
    """Scan 1M bars; return raw causal signals before dedupe/context."""
    hi = market["high"].values.astype(float)
    lo = market["low"].values.astype(float)
    cl = market["close"].values.astype(float)
    op = market["open"].values.astype(float)
    atr = market["atr"].values.astype(float) if "atr" in market.columns else np.full(len(market), np.nan)
    idx = market.index
    rows: list[dict] = []
    avg_body = pd.Series(_body_series(op, cl)).rolling(20, min_periods=20).mean().values
    sh_arr = precompute_swing_highs(hi, swing)
    sl_arr = precompute_swing_lows(lo, swing)
    sh1, sh2 = precompute_last2_swing_highs(hi, swing)
    sl1, sl2 = precompute_last2_swing_lows(lo, swing)

    # Event state — one signal per structural break (not every bar beyond level)
    armed_long: float | None = None
    armed_short: float | None = None
    beyond_sh = False
    beyond_sl = False
    last_rh = last_rl = np.nan
    in_range = True

    for i in range(start_i, len(market) - 1):
        ts = idx[i]
        if rth_only and not is_in_session(ts, RTH_SESSION):
            continue
        sh = sh_arr[i]
        sl = sl_arr[i]
        if not np.isfinite(sh) and not np.isfinite(sl):
            continue
        a = float(atr[i]) if np.isfinite(atr[i]) else np.nan

        def emit(direction: int, level: float, tag: str) -> None:
            rows.append(
                {
                    "entry_i": i,
                    "entry_timestamp": ts,
                    "direction": "LONG" if direction == 1 else "SHORT",
                    "entry_price": float(cl[i]),
                    "family": family,
                    "family_tag": tag,
                    "structure_level": level,
                    "swing": swing,
                    "atr_mult": atr_mult,
                }
            )

        # ── A: Micro BOS ──
        if family in ("A1", "A2", "A3"):
            if np.isfinite(sh):
                if cl[i] <= sh:
                    beyond_sh = False
                elif not beyond_sh:
                    ok = True
                    if family == "A3" and np.isfinite(a) and (cl[i] - sh) < atr_mult * a:
                        ok = False
                    if family == "A2" and cl[i] <= op[i]:
                        ok = False
                    if ok:
                        emit(1, sh, "bos_high")
                        beyond_sh = True
            if np.isfinite(sl):
                if cl[i] >= sl:
                    beyond_sl = False
                elif not beyond_sl:
                    ok = True
                    if family == "A3" and np.isfinite(a) and (sl - cl[i]) < atr_mult * a:
                        ok = False
                    if family == "A2" and cl[i] >= op[i]:
                        ok = False
                    if ok:
                        emit(-1, sl, "bos_low")
                        beyond_sl = True

        # ── B: CHoCH ──
        elif family in ("B1", "B2"):
            if np.isfinite(sh1[i]) and np.isfinite(sh2[i]) and sh1[i] < sh2[i]:
                lvl = sh1[i]
                if cl[i] <= lvl:
                    armed_long = None
                elif armed_long != lvl:
                    if family == "B2" and cl[i] <= op[i]:
                        pass
                    else:
                        emit(1, lvl, "choch_long")
                        armed_long = lvl
            if np.isfinite(sl1[i]) and np.isfinite(sl2[i]) and sl1[i] > sl2[i]:
                lvl = sl1[i]
                if cl[i] >= lvl:
                    armed_short = None
                elif armed_short != lvl:
                    if family == "B2" and cl[i] >= op[i]:
                        pass
                    else:
                        emit(-1, lvl, "choch_short")
                        armed_short = lvl

        # ── C: Failed break / reclaim ──
        elif family == "C1":
            if i >= 2 and np.isfinite(sl):
                if lo[i - 1] < sl and cl[i] > sl and cl[i] > op[i]:
                    emit(1, sl, "reclaim_long")
            if i >= 2 and np.isfinite(sh):
                if hi[i - 1] > sh and cl[i] < sh and cl[i] < op[i]:
                    emit(-1, sh, "reclaim_short")

        # ── D: Displacement + BOS ──
        elif family == "D1":
            body = abs(cl[i] - op[i])
            ab = avg_body[i]
            if np.isfinite(ab) and body > DISPLACEMENT_BODY_MULT * ab:
                if np.isfinite(sh) and cl[i] > sh:
                    emit(1, sh, "disp_bos_long")
                if np.isfinite(sl) and cl[i] < sl:
                    emit(-1, sl, "disp_bos_short")

        # ── E: Pullback continuation (simplified) ──
        elif family == "E1":
            if np.isfinite(sh1[i]) and np.isfinite(sh2[i]) and sh1[i] > sh2[i] and np.isfinite(sl1[i]) and np.isfinite(sh):
                mid = (sh1[i] + sl1[i]) / 2.0
                if lo[i] <= mid <= hi[i] and cl[i] > sh:
                    emit(1, sh, "pullback_long")
            if np.isfinite(sl1[i]) and np.isfinite(sl2[i]) and sl1[i] < sl2[i] and np.isfinite(sh1[i]) and np.isfinite(sl):
                mid = (sh1[i] + sl1[i]) / 2.0
                if lo[i] <= mid <= hi[i] and cl[i] < sl:
                    emit(-1, sl, "pullback_short")

        # ── F: Reversal after extension ──
        elif family == "F1":
            if i >= 5 and np.isfinite(a) and a > 0:
                ext_dn = (cl[i - 5] - cl[i]) / a
                if ext_dn >= 1.5 and np.isfinite(sh) and cl[i] > sh:
                    emit(1, sh, "rev_long")
                ext_up = (cl[i] - cl[i - 5]) / a
                if ext_up >= 1.5 and np.isfinite(sl) and cl[i] < sl:
                    emit(-1, sl, "rev_short")

        # ── G: Range break / failed break ──
        elif family in ("G1", "G3"):
            lb = min(30, i)
            if i < lb:
                continue
            rh = np.max(hi[i - lb : i])
            rl = np.min(lo[i - lb : i])
            if family == "G1":
                if rl <= cl[i] <= rh:
                    in_range = True
                elif cl[i] > rh and in_range:
                    emit(1, rh, "range_break_up")
                    in_range = False
                elif cl[i] < rl and in_range:
                    emit(-1, rl, "range_break_dn")
                    in_range = False
            else:
                if hi[i] > rh and cl[i] < rh and last_rh != rh:
                    emit(-1, rh, "failed_break_short")
                    last_rh = rh
                if lo[i] < rl and cl[i] > rl and last_rl != rl:
                    emit(1, rl, "failed_break_long")
                    last_rl = rl

    return pd.DataFrame(rows)


def dedupe_signals(raw: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """One signal per structural event; opposite direction resets."""
    if raw.empty:
        return raw, 0
    raw = raw.sort_values("entry_timestamp").reset_index(drop=True)
    kept: list[dict] = []
    last_dir = 0
    last_level: dict[int, float] = {1: -np.inf, -1: np.inf}
    removed = 0
    for _, r in raw.iterrows():
        d = 1 if r["direction"] == "LONG" else -1
        lvl = float(r["structure_level"])
        if d == last_dir and d == 1 and lvl <= last_level[1]:
            removed += 1
            continue
        if d == last_dir and d == -1 and lvl >= last_level[-1]:
            removed += 1
            continue
        kept.append(r.to_dict())
        last_dir = d
        last_level[d] = lvl
        last_level[-d] = np.inf if d == 1 else -np.inf
    return pd.DataFrame(kept), removed
