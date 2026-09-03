"""Failure definitions and reversal signal generation."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from phase29.config import BOS_RETEST_TOLERANCE_ATR

from .config import ARCHITECTURE, FAILURE_WINDOWS, OPP_BOS_MAX_BARS
from .displacements import first_opposite_bos, precompute_opposite_bos, reversal_direction, scan_displacements


def _reclaim_level(disp: pd.Series, reclaim_type: str) -> float:
    return float(disp["midpoint"] if reclaim_type == "midpoint" else disp["open"])


def _reclaim_hit(disp_dir: str, close: float, level: float) -> bool:
    if disp_dir == "Short":
        return close > level
    return close < level


def _midpoint_reclaim(
    disp: pd.Series,
    market: pd.DataFrame,
    window: int,
) -> Optional[Tuple[int, pd.Timestamp, str]]:
    i = int(disp["bar_index"])
    level = float(disp["midpoint"])
    for w in range(1, window + 1):
        j = i + w
        if j >= len(market):
            break
        if _reclaim_hit(str(disp["displacement_direction"]), float(market["close"].iloc[j]), level):
            return j, market.index[j], "midpoint"
    return None


def _open_reclaim(
    disp: pd.Series,
    market: pd.DataFrame,
    window: int,
) -> Optional[Tuple[int, pd.Timestamp, str]]:
    i = int(disp["bar_index"])
    level = float(disp["open"])
    for w in range(1, window + 1):
        j = i + w
        if j >= len(market):
            break
        if _reclaim_hit(str(disp["displacement_direction"]), float(market["close"].iloc[j]), level):
            return j, market.index[j], "open"
    return None


def _extreme_failure(
    disp: pd.Series,
    market: pd.DataFrame,
    window: int,
    reclaim_type: str,
) -> Optional[Tuple[int, pd.Timestamp, str, int]]:
    i = int(disp["bar_index"])
    disp_dir = str(disp["displacement_direction"])
    level = _reclaim_level(disp, reclaim_type)
    continuation_bar = None
    for w in range(1, window + 1):
        j = i + w
        if j >= len(market):
            break
        bar = market.iloc[j]
        if disp_dir == "Short":
            if float(bar["low"]) < float(disp["low"]):
                continuation_bar = j
            if continuation_bar is not None and _reclaim_hit(disp_dir, float(bar["close"]), level):
                return j, market.index[j], reclaim_type, continuation_bar
        else:
            if float(bar["high"]) > float(disp["high"]):
                continuation_bar = j
            if continuation_bar is not None and _reclaim_hit(disp_dir, float(bar["close"]), level):
                return j, market.index[j], reclaim_type, continuation_bar
    return None


def build_failure_events(
    displacements: pd.DataFrame,
    market: pd.DataFrame,
    bos_events: pd.DataFrame,
) -> pd.DataFrame:
    rows: List[dict] = []
    for _, disp in displacements.iterrows():
        disp_dir = str(disp["displacement_direction"])
        rev_dir = reversal_direction(disp_dir)
        base = {
            "displacement_id": int(disp["displacement_id"]),
            "displacement_timestamp": disp["displacement_timestamp"],
            "displacement_direction": disp_dir,
            "reversal_direction": rev_dir,
            "body_ratio": disp["body_ratio"],
            "close_location": disp["close_location"],
            "atr": disp["atr"],
        }
        for window in FAILURE_WINDOWS:
            hit = _midpoint_reclaim(disp, market, window)
            if hit:
                j, ts, rtype = hit
                rows.append(
                    base
                    | {
                        "failure_definition": f"A_MID_{window}",
                        "failure_window": window,
                        "confirm_bar_index": j,
                        "confirm_timestamp": ts,
                        "reclaim_type": rtype,
                        "reclaim_level": float(disp["midpoint"]),
                        "bos_timestamp": ts,
                        "bos_level": float(disp["midpoint"]),
                        "continuation_bar_index": np.nan,
                    }
                )
            hit = _open_reclaim(disp, market, window)
            if hit:
                j, ts, rtype = hit
                rows.append(
                    base
                    | {
                        "failure_definition": f"B_OPEN_{window}",
                        "failure_window": window,
                        "confirm_bar_index": j,
                        "confirm_timestamp": ts,
                        "reclaim_type": rtype,
                        "reclaim_level": float(disp["open"]),
                        "bos_timestamp": ts,
                        "bos_level": float(disp["open"]),
                        "continuation_bar_index": np.nan,
                    }
                )
            for rtype in ("midpoint", "open"):
                ext = _extreme_failure(disp, market, window, rtype)
                if ext:
                    j, ts, rt, cont = ext
                    rows.append(
                        base
                        | {
                            "failure_definition": f"C_EXT_{'MID' if rtype == 'midpoint' else 'OPEN'}_{window}",
                            "failure_window": window,
                            "confirm_bar_index": j,
                            "confirm_timestamp": ts,
                            "reclaim_type": rt,
                            "reclaim_level": _reclaim_level(disp, rtype),
                            "bos_timestamp": ts,
                            "bos_level": _reclaim_level(disp, rtype),
                            "continuation_bar_index": int(cont),
                        }
                    )
        opp = first_opposite_bos(int(disp["bar_index"]), disp_dir, bos_events, max_bars=OPP_BOS_MAX_BARS)
        if opp:
            rows.append(
                base
                | {
                    "failure_definition": "D_OPP_BOS",
                    "failure_window": opp["bos_bar_index"] - int(disp["bar_index"]),
                    "confirm_bar_index": int(opp["bos_bar_index"]),
                    "confirm_timestamp": opp["bos_timestamp"],
                    "reclaim_type": "opposite_bos",
                    "reclaim_level": float(opp["bos_level"]),
                    "bos_timestamp": opp["bos_timestamp"],
                    "bos_level": float(opp["bos_level"]),
                    "continuation_bar_index": np.nan,
                }
            )
            for rtype, prefix in (("midpoint", "E_MID_BOS"), ("open", "E_OPEN_BOS")):
                reclaim = _midpoint_reclaim(disp, market, 4) if rtype == "midpoint" else _open_reclaim(disp, market, 4)
                if reclaim is None:
                    continue
                rj, rts, _ = reclaim
                if int(opp["bos_bar_index"]) >= rj:
                    rows.append(
                        base
                        | {
                            "failure_definition": prefix,
                            "failure_window": int(opp["bos_bar_index"]) - int(disp["bar_index"]),
                            "confirm_bar_index": int(opp["bos_bar_index"]),
                            "confirm_timestamp": opp["bos_timestamp"],
                            "reclaim_type": rtype,
                            "reclaim_level": _reclaim_level(disp, rtype),
                            "bos_timestamp": opp["bos_timestamp"],
                            "bos_level": float(opp["bos_level"]),
                            "continuation_bar_index": np.nan,
                            "reclaim_bar_index": rj,
                            "reclaim_timestamp": rts,
                        }
                    )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["failure_event_id"] = out.apply(
        lambda r: f"{r['failure_definition']}_{r['displacement_timestamp']}_{r['reversal_direction']}",
        axis=1,
    )
    return out


def failure_signals(
    failures: pd.DataFrame,
    failure_definition: str,
) -> pd.DataFrame:
    sub = failures.loc[failures.failure_definition == failure_definition].copy()
    if sub.empty:
        return sub
    sub = sub.sort_values("confirm_timestamp").drop_duplicates(subset=["failure_event_id"], keep="first")
    sub["direction"] = sub["reversal_direction"]
    sub["entry_timestamp"] = sub["confirm_timestamp"]
    sub["architecture"] = ARCHITECTURE
    sub["signal_id"] = np.arange(1, len(sub) + 1)
    sub["event_id"] = sub["failure_event_id"]
    keep = [
        "signal_id",
        "direction",
        "entry_timestamp",
        "bos_timestamp",
        "architecture",
        "event_id",
        "failure_definition",
        "displacement_timestamp",
        "displacement_direction",
        "reclaim_level",
        "reclaim_type",
        "confirm_timestamp",
    ]
    return sub[keep].reset_index(drop=True)


def all_failure_definitions(failures: pd.DataFrame) -> List[str]:
    return sorted(failures["failure_definition"].unique().tolist())


def classify_continuation_vs_failure(
    displacements: pd.DataFrame,
    failures: pd.DataFrame,
    market: pd.DataFrame,
    *,
    horizon: int = 8,
) -> pd.DataFrame:
    """Classify each displacement as CONTINUATION, FAILURE_REVERSAL, or UNRESOLVED."""
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    fail_by_disp: Dict[int, pd.DataFrame] = {}
    if not failures.empty:
        for did, grp in failures.groupby("displacement_id"):
            fail_by_disp[int(did)] = grp.sort_values("confirm_bar_index")
    rows = []
    for _, disp in displacements.iterrows():
        i = int(disp["bar_index"])
        disp_dir = str(disp["displacement_direction"])
        end = min(len(market) - 1, i + horizon)
        continuation_bar = None
        failure_bar = None
        failure_def = None
        # Phase 31 continuation: same-direction BOS retest fill within 2 bars after displacement
        tol = BOS_RETEST_TOLERANCE_ATR * float(disp["atr"]) if np.isfinite(disp["atr"]) else 0.0
        bos_level = float(disp["high"]) if disp_dir == "Long" else float(disp["low"])
        for j in range(i + 1, min(i + 3, len(market))):
            bar = market.iloc[j]
            if disp_dir == "Long" and float(bar["low"]) <= bos_level + tol:
                continuation_bar = j
                break
            if disp_dir == "Short" and float(bar["high"]) >= bos_level - tol:
                continuation_bar = j
                break
        grp = fail_by_disp.get(int(disp["displacement_id"]))
        if grp is not None and not grp.empty:
            early = grp.loc[grp.confirm_bar_index <= end]
            if not early.empty:
                row = early.iloc[0]
                failure_bar = int(row["confirm_bar_index"])
                failure_def = str(row["failure_definition"])
        label = "UNRESOLVED"
        if continuation_bar is not None and (failure_bar is None or continuation_bar <= failure_bar):
            label = "CONTINUATION"
        elif failure_bar is not None and (continuation_bar is None or failure_bar < continuation_bar):
            label = "FAILURE_REVERSAL"
        elif continuation_bar is not None and failure_bar is not None and continuation_bar == failure_bar:
            label = "CONTINUATION"
        rows.append(
            {
                "displacement_id": int(disp["displacement_id"]),
                "displacement_timestamp": disp["displacement_timestamp"],
                "displacement_direction": disp_dir,
                "classification": label,
                "continuation_bar_index": continuation_bar,
                "failure_bar_index": failure_bar,
                "failure_definition": failure_def,
                "horizon_bars": horizon,
            }
        )
    return pd.DataFrame(rows)


def build_failure_strength(
    failures: pd.DataFrame,
    market: pd.DataFrame,
    displacements: pd.DataFrame,
) -> pd.DataFrame:
    if failures.empty:
        return pd.DataFrame()
    disp_map = displacements.set_index("displacement_id")
    rows = []
    for _, row in failures.iterrows():
        disp_i = int(market.index.get_loc(row["displacement_timestamp"]))
        conf_i = int(row["confirm_bar_index"])
        disp = market.iloc[disp_i]
        conf = market.iloc[conf_i]
        disp_meta = disp_map.loc[int(row["displacement_id"])]
        disp_rng = float(disp["high"] - disp["low"])
        reclaim_depth = abs(float(conf["close"]) - float(row["reclaim_level"])) / disp_rng if disp_rng > 0 else np.nan
        bars_reclaim = conf_i - disp_i
        cont_i = row.get("continuation_bar_index")
        bars_cont = float(cont_i - disp_i) if pd.notna(cont_i) else np.nan
        ext_beyond = np.nan
        if pd.notna(cont_i):
            ci = int(cont_i)
            if row["displacement_direction"] == "Short":
                ext_beyond = float(disp["low"] - market.iloc[ci]["low"])
            else:
                ext_beyond = float(market.iloc[ci]["high"] - disp["high"])
        rev_body = abs(float(conf["close"]) - float(conf["open"]))
        rev_rng = float(conf["high"] - conf["low"])
        rev_cl = (float(conf["close"]) - float(conf["low"])) / rev_rng if rev_rng > 0 else np.nan
        vol_ratio = np.nan
        if "volume" in market.columns:
            vol = market["volume"].astype(float)
            avg24 = vol.rolling(24, min_periods=24).mean().iloc[conf_i]
            if np.isfinite(avg24) and avg24 > 0:
                vol_ratio = float(vol.iloc[conf_i] / avg24)
        body = float(disp_meta["body"])
        atr = float(row["atr"]) if np.isfinite(row["atr"]) else np.nan
        rows.append(
            {
                "failure_event_id": row["failure_event_id"],
                "failure_definition": row["failure_definition"],
                "displacement_direction": row["displacement_direction"],
                "reversal_direction": row["reversal_direction"],
                "body_ratio": row["body_ratio"],
                "body_atr_ratio": float(body / atr) if np.isfinite(atr) and atr > 0 else np.nan,
                "reclaim_depth": reclaim_depth,
                "bars_until_reclaim": bars_reclaim,
                "bars_until_opposite_bos": conf_i - disp_i,
                "extreme_beyond_disp": ext_beyond,
                "reversal_body": rev_body,
                "reversal_close_location": rev_cl,
                "volume_ratio24": vol_ratio,
            }
        )
    return pd.DataFrame(rows)
