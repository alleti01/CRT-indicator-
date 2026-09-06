"""Component ablation scanners — frozen Phase78 logic with gates toggled."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from phase78.python.config import (
    DISPLACEMENT_MAX_BARS,
    DISPLACEMENT_PRIMARY,
    ENTRY_DELAY_BARS,
    ENTRY_PRIMARY,
    FVG_MAX_BARS_AFTER_MSS,
    MSS_MAX_BARS_AFTER_DISP,
    MSS_PRIMARY,
)
from phase78.python.liquidity import LiquidityMap
from phase78.python.sequence import (
    SetupRecord,
    SetupState,
    _detect_fvg,
    _detect_sweep,
    _displacement_ok,
    _mss_ok,
)

Direction = Literal["LONG", "SHORT"]


@dataclass
class AblationSpec:
    name: str
    require_sweep: bool = True
    require_displacement: bool = True
    require_mss: bool = True
    require_fvg_retrace: bool = True


ABLATIONS = {
    "FULL": AblationSpec("FULL", True, True, True, True),
    "A1_NO_SWEEP": AblationSpec("A1_NO_SWEEP", False, True, True, True),
    "A2_NO_DISPLACEMENT": AblationSpec("A2_NO_DISPLACEMENT", True, False, True, True),
    "A3_NO_MSS": AblationSpec("A3_NO_MSS", True, True, False, True),
    "A4_NO_FVG_RETRACE": AblationSpec("A4_NO_FVG_RETRACE", True, True, True, False),
}

DIAGNOSTICS = {
    "SWEEP_ONLY": "sweep_only",
    "MSS_ONLY": "mss_only",
    "FVG_ONLY": "fvg_only",
}


def scan_ablation(
    df_slice: pd.DataFrame,
    liq_map: LiquidityMap,
    calendar_date: object,
    window_id: str,
    window_end: pd.Timestamp,
    spec: AblationSpec,
    entry_mode: str = ENTRY_PRIMARY,
) -> list[SetupRecord]:
    entries: list[SetupRecord] = []
    if len(df_slice) == 0:
        return entries

    highs = df_slice["high"].values
    lows = df_slice["low"].values
    closes = df_slice["close"].values
    opens = df_slice["open"].values
    atrs = df_slice["atr"].values
    index = df_slice.index

    active: SetupRecord | None = None
    swept_levels: set[tuple[str, float]] = set()

    for local_i in range(len(df_slice)):
        ts = index[local_i]
        if ts > window_end:
            break
        h, l, c, atr = highs[local_i], lows[local_i], closes[local_i], atrs[local_i]

        if spec.require_sweep:
            if active is None or active.state in (SetupState.WAIT_SWEEP, SetupState.EXPIRED, SetupState.INVALIDATED):
                for liq in liq_map.levels:
                    key = (liq.level_type, liq.level_price)
                    if key in swept_levels:
                        continue
                    swept, extreme, dist = _detect_sweep(h, l, liq)
                    if not swept:
                        continue
                    swept_levels.add(key)
                    direction: Direction = "SHORT" if liq.side == "BUY_SIDE" else "LONG"
                    active = SetupRecord(
                        calendar_date=calendar_date,
                        window_id=window_id,
                        state=SetupState.SWEEP_DETECTED,
                        direction=direction,
                        liquidity_type=liq.level_type,
                        liquidity_price=liq.level_price,
                        sweep_time=ts,
                        sweep_extreme=extreme,
                        sweep_distance_points=dist,
                    )
                    break
        else:
            # A1: infer direction from first qualifying displacement bar
            if active is None:
                for direction in ("LONG", "SHORT"):
                    ref = l if direction == "LONG" else h
                    pseudo_extreme = h if direction == "SHORT" else l
                    ok, disp_atr = _displacement_ok(direction, pseudo_extreme, c, atr)
                    if ok:
                        active = SetupRecord(
                            calendar_date=calendar_date,
                            window_id=window_id,
                            state=SetupState.WAIT_MSS if spec.require_mss else SetupState.WAIT_FVG,
                            direction=direction,
                            liquidity_type="NO_SWEEP",
                            displacement_time=ts,
                            displacement_atr=disp_atr,
                            sweep_extreme=pseudo_extreme,
                        )
                        break

        if active is None:
            continue

        bars_since_sweep = local_i
        if active.sweep_time is not None:
            bars_since_sweep = local_i - int(np.searchsorted(index, active.sweep_time))

        # Displacement gate
        if spec.require_displacement and active.state in (SetupState.SWEEP_DETECTED, SetupState.WAIT_DISPLACEMENT):
            active.state = SetupState.WAIT_DISPLACEMENT
            ok, disp_atr = _displacement_ok(active.direction, active.sweep_extreme, c, atr)
            if ok:
                active.state = SetupState.WAIT_MSS if spec.require_mss else SetupState.WAIT_FVG
                active.displacement_time = ts
                active.displacement_atr = disp_atr
            elif bars_since_sweep > DISPLACEMENT_MAX_BARS:
                active = None
                continue

        if not spec.require_displacement and active.state == SetupState.SWEEP_DETECTED:
            active.state = SetupState.WAIT_MSS if spec.require_mss else SetupState.WAIT_FVG

        # MSS
        if spec.require_mss and active.state == SetupState.WAIT_MSS:
            ok, mss_lvl = _mss_ok(active.direction, c, lows, highs, local_i)
            disp_bars = 0
            if active.displacement_time is not None:
                disp_bars = local_i - int(np.searchsorted(index, active.displacement_time))
            elif active.sweep_time is not None:
                disp_bars = local_i - int(np.searchsorted(index, active.sweep_time))
            if ok:
                active.state = SetupState.WAIT_FVG if spec.require_fvg_retrace else SetupState.ENTERED
                active.mss_time = ts
                active.mss_level = mss_lvl
            elif disp_bars > MSS_MAX_BARS_AFTER_DISP:
                active = None
                continue

        if not spec.require_mss and active.state in (SetupState.WAIT_MSS, SetupState.WAIT_DISPLACEMENT, SetupState.SWEEP_DETECTED):
            if active.state != SetupState.WAIT_FVG:
                active.state = SetupState.WAIT_FVG if spec.require_fvg_retrace else SetupState.ENTERED

        # FVG + retrace
        if spec.require_fvg_retrace and active.state == SetupState.WAIT_FVG:
            fvg = _detect_fvg(active.direction, highs, lows, local_i)
            mss_bars = 0
            if active.mss_time is not None:
                mss_bars = local_i - int(np.searchsorted(index, active.mss_time))
            if fvg is not None:
                fvg.created_at = ts
                active.fvg = fvg
                active.state = SetupState.WAIT_RETRACE
            elif mss_bars > FVG_MAX_BARS_AFTER_MSS:
                active = None
                continue

        if spec.require_fvg_retrace and active.state == SetupState.WAIT_RETRACE and active.fvg is not None:
            fvg = active.fvg
            touched = False
            if active.direction == "LONG" and l <= fvg.high:
                touched = True
            elif active.direction == "SHORT" and h >= fvg.low:
                touched = True
            if touched:
                exec_i = local_i + ENTRY_DELAY_BARS
                if exec_i < len(df_slice):
                    active.entry_time = index[exec_i]
                    active.entry_price = float(opens[exec_i])
                    active.stop = active.sweep_extreme
                    active.state = SetupState.ENTERED
                    entries.append(active)
                    active = None
                    continue
                active = None
                continue

        if active is None:
            continue

        # A4: entry at MSS without FVG retrace
        if not spec.require_fvg_retrace and active.state == SetupState.WAIT_MSS:
            ok, mss_lvl = _mss_ok(active.direction, c, lows, highs, local_i)
            if ok:
                exec_i = local_i + ENTRY_DELAY_BARS
                if exec_i < len(df_slice):
                    rec = SetupRecord(
                        calendar_date=calendar_date,
                        window_id=window_id,
                        direction=active.direction,
                        sweep_time=active.sweep_time,
                        sweep_extreme=active.sweep_extreme,
                        mss_time=ts,
                        mss_level=mss_lvl,
                        entry_time=index[exec_i],
                        entry_price=float(opens[exec_i]),
                        stop=active.sweep_extreme,
                        liquidity_type=active.liquidity_type,
                    )
                    entries.append(rec)
                    active = None
                    continue

    return entries
