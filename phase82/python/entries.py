"""Build Phase82 entry sets from baseline stream."""
from __future__ import annotations

import pandas as pd

from phase69.python.sim_management import walk_trade
from phase82.python.config import EXT_ATR, M0
from phase82.python.engine import decide
from phase82.python.m15_causal import M15CausalArrays


def load_baseline() -> pd.DataFrame:
    from phase82.python.config import CANON_PARQUET

    df = pd.read_parquet(CANON_PARQUET)
    df = df.loc[df["h1_status"] == "KEEP"].copy()
    df = df.sort_values("entry_ts").reset_index(drop=True)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    return df


def apply_model(
    baseline: pd.DataFrame,
    arr: M15CausalArrays,
    model_id: str,
    *,
    allow_reversal: bool = False,
    use_memory: bool = False,
) -> pd.DataFrame:
    rows = []
    seen: set | None = set() if use_memory else None
    for _, r in baseline.iterrows():
        direction = r["direction_m1"]
        sig_i = int(r["entry_i_m1"]) - 1
        if sig_i < 15:
            continue
        d = decide(
            arr,
            sig_i,
            direction,
            model_id,
            ext_atr=EXT_ATR,
            allow_reversal=allow_reversal,
            use_memory=use_memory,
            seen_opps=seen,
        )
        if d.action != "TAKE" or d.entry_i is None:
            continue
        ei = d.entry_i
        use_baseline_r = (ei == int(r["entry_i_m1"]))
        if model_id == "P0":
            use_baseline_r = True
            ei = int(r["entry_i_m1"])

        if use_baseline_r:
            net_r = float(r["net_R_m1"])
            gross_r = float(r["gross_R_m1"])
            cost_r = float(r["cost_R_m1"])
            mfe = float(r["MFE_R_m1"])
            mae = float(r["MAE_R_m1"])
            dur = float(r["duration_min_m1"])
            exit_reason = r["exit_reason_m1"]
        else:
            ep = float(arr.op[ei])
            atr = float(arr.atr[ei]) if arr.atr[ei] > 0 else float(r["atr"])
            wt = walk_trade(
                arr.hi,
                arr.lo,
                arr.cl,
                arr.op,
                ei,
                direction,
                ep,
                atr,
                stop_atr=M0["stop_r"],
                target_r=M0["target_r"],
                max_hold=M0["max_hold_minutes"],
                mode="M0",
            )
            net_r = float(wt["net_R"])
            gross_r = float(wt.get("gross_R", net_r))
            cost_r = gross_r - net_r
            mfe = float(wt["MFE_R"])
            mae = float(wt["MAE_R"])
            dur = float(wt["duration"])
            exit_reason = wt["exit_reason"]

        from phase82.python.m15_state import m15_state_at
        from phase82.python.m1_state import m1_features_at

        m15 = m15_state_at(arr, sig_i, EXT_ATR)
        m1 = m1_features_at(arr, sig_i)

        rows.append(
            {
                "trade_id": r["trade_id"],
                "baseline_trade_id": r["trade_id"],
                "model_id": model_id,
                "direction": direction,
                "entry_ts": arr.idx[ei],
                "entry_i": ei,
                "sig_i": sig_i,
                "entry_type": d.entry_type,
                "reason_code": d.reason,
                "m15_state": m15["m15_state"],
                "m15_extension_atr": m15["m15_extension_atr"],
                "m1_extension_up_atr": m1.get("m1_extension_up_atr", 0),
                "m1_extension_down_atr": m1.get("m1_extension_down_atr", 0),
                "pullback_depth_atr": m1.get("pullback_from_low_atr", 0)
                if direction == "SHORT"
                else m1.get("pullback_from_high_atr", 0),
                "net_R": net_r,
                "gross_R": gross_r,
                "cost_R": cost_r,
                "net_R_2x_cost": net_r - cost_r,
                "MFE_R": mfe,
                "MAE_R": mae,
                "duration_min": dur,
                "exit_reason": exit_reason,
                "recovered": not use_baseline_r,
            }
        )
    return pd.DataFrame(rows)
