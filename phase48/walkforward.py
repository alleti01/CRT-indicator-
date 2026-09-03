"""Walk-forward management parameter selection."""

from __future__ import annotations

import itertools
from typing import Callable

import numpy as np
import pandas as pd

from phase31.metrics import performance
from phase45.execution.data_1m import load_market_1m

from .config import (
    ATR_STOP_MULTS,
    BE_DESTS,
    BE_TRIGGERS,
    FIXED_TARGET_R,
    OPPOSITE_BOS_MIN_R,
    PARTIAL_SCHEMES,
    P45_DATASET,
    PROFIT_LOCK_LEVELS,
    PROFIT_LOCK_TRIGGERS,
    STAGNATION_RULES,
    TIME_EXIT_MIN,
    TRAIL_ACTIVATE,
    TRAIL_ATR,
    TRAIL_GIVEBACK,
    WALK_FORWARD_FOLDS,
)
from .entries import build_train_entries, enrich_entry_row, load_frozen_entries
from .simulate_mgmt import MgmtSpec, simulate_managed
from .stops import compute_stop
from .variants import (
    run_spec_on_entry,
    spec_15m_invalidation,
    spec_breakeven,
    spec_fixed_target,
    spec_m0,
    spec_opposite_bos,
    spec_partial,
    spec_profit_lock,
    spec_stagnation,
    spec_structure_target,
    spec_time_exit,
    spec_trail,
)


def _summarize(results: list[dict]) -> dict:
    if not results:
        return {"N": 0, "AvgR": 0.0, "PF": 0.0, "TotalR": 0.0, "MaxDD": 0.0, "WinRate": 0.0}
    df = pd.DataFrame(results)
    p = performance(df, col="net_R")
    p["WinRate"] = float((df["net_R"] > 0).mean())
    p["MAE"] = float(df["MAE_R"].mean()) if "MAE_R" in df.columns else np.nan
    p["MFE"] = float(df["MFE_R"].mean()) if "MFE_R" in df.columns else np.nan
    p["MFE_Capture"] = float(df["mfe_capture"].mean()) if "mfe_capture" in df.columns else np.nan
    p["AvgHold"] = float(df["hold_bars"].mean()) if "hold_bars" in df.columns else np.nan
    return p


def _simulate_rows(rows: pd.DataFrame, market: pd.DataFrame, spec: MgmtSpec, *, stop_mode: str | None = None, stop_param: float | None = None) -> list[dict]:
    out = []
    for _, row in rows.iterrows():
        r = enrich_entry_row(row, market)
        stop, tgt = float(r["initial_stop"]), float(r["initial_target"])
        if stop_mode == "S3" and stop_param is not None:
            stop, tgt = compute_stop(market, int(r["entry_i"]), float(r["entry_price"]), r["direction"], r["signal_type"], mode="S3", frozen_stop=stop, atr_mult=stop_param)
        elif stop_mode == "S1":
            stop, tgt = compute_stop(market, int(r["entry_i"]), float(r["entry_price"]), r["direction"], r["signal_type"], mode="S1", frozen_stop=stop)
        elif stop_mode == "S2":
            stop, tgt = compute_stop(market, int(r["entry_i"]), float(r["entry_price"]), r["direction"], r["signal_type"], mode="S2", frozen_stop=stop, bos_level=row.get("bos_level"))
        sim = run_spec_on_entry(r, market, spec, stop_px=stop, tgt_px=tgt)
        out.append({**sim, "signal_id": row["signal_id"], "fold": row.get("fold"), "variant": spec.name})
    return out


def _pick_best(train_rows: pd.DataFrame, market: pd.DataFrame, candidates: list[tuple[MgmtSpec, dict]], *, min_n: int = 15) -> tuple[MgmtSpec, dict, float]:
    best_spec, best_kw, best_avgr = spec_m0(), {}, -999.0
    for spec, kw in candidates:
        res = _simulate_rows(train_rows, market, spec, **kw)
        if len(res) < min_n:
            continue
        avgr = float(pd.DataFrame(res)["net_R"].mean())
        if avgr > best_avgr:
            best_avgr, best_spec, best_kw = avgr, spec, kw
    return best_spec, best_kw, best_avgr


def walk_forward_management(market: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    mkt = market if market is not None else load_market_1m()
    ds = pd.read_csv(P45_DATASET, parse_dates=["marker_bar_timestamp", "actionable_timestamp"])
    for win in (5, 10, 15):
        c = f"B1_w{win}_entry_time"
        if c in ds.columns:
            ds[c] = pd.to_datetime(ds[c], utc=True).dt.tz_convert("America/Chicago")
    test_entries = load_frozen_entries()
    test_entries = test_entries.apply(lambda r: enrich_entry_row(r, mkt), axis=1)

    wf_parts: list[pd.DataFrame] = []
    param_rows: list[dict] = []
    family_best: dict[str, dict] = {}

    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, 1):
        train_rows = build_train_entries(ds, mkt, fold_i, tr_s, tr_e)
        test_rows = test_entries.loc[test_entries["fold"] == fold_i].copy()
        if test_rows.empty:
            continue

        families: list[tuple[str, list]] = [
            ("Stop_S3", [(spec_m0(), {"stop_mode": "S3", "stop_param": p}) for p in ATR_STOP_MULTS]),
            ("Fixed_Target", [(spec_fixed_target(r), {}) for r in FIXED_TARGET_R]),
            ("Break_Even", [(spec_breakeven(t, d), {}) for t in (0.5, 1.0, 1.5) for d in ("BE0", "BE1")]),
            ("Partials", [(spec_partial(p), {}) for p in PARTIAL_SCHEMES]),
            ("Trailing", [(spec_trail(a, m, p), {}) for a in (1.0, 1.5) for m, p in [("TR1", 0), ("TR2", 0), ("TR3", 0.75), ("TR4", 0.75)]]),
            ("Opposite_BOS", [(spec_opposite_bos(r), {}) for r in OPPOSITE_BOS_MIN_R]),
            ("Time_Exit", [(spec_time_exit(t), {}) for t in (10, 15, 30, 45, 60)]),
            ("Stagnation", [(spec_stagnation(s), {}) for s in ("ST1", "ST2", "ST3", "ST4")]),
            ("Profit_Lock", [(spec_profit_lock(t, l), {}) for t in (1.0, 1.5, 2.0) for l in (0.0, 0.5, 1.0)]),
            ("Structure_Target", [(spec_structure_target((1.0, 3.0)), {}), (spec_structure_target((1.5, 3.0)), {})]),
            ("INV_15M", [(spec_15m_invalidation(), {})]),
        ]

        for fam, cands in families:
            best_spec, best_kw, _ = _pick_best(train_rows, mkt, cands)
            res = _simulate_rows(test_rows, mkt, best_spec, **best_kw)
            df = pd.DataFrame(res)
            df["family"] = fam
            df["fold"] = fold_i
            wf_parts.append(df)
            param_rows.append({"fold": fold_i, "family": fam, "variant": best_spec.name, **best_kw})

    wf = pd.concat(wf_parts, ignore_index=True) if wf_parts else pd.DataFrame()
    params = pd.DataFrame(param_rows)

    # M0 control on same test entries
    m0_parts = []
    for fold_i in test_entries["fold"].unique():
        test_rows = test_entries.loc[test_entries["fold"] == fold_i]
        res = _simulate_rows(test_rows, mkt, spec_m0())
        m0_parts.append(pd.DataFrame(res))
    m0 = pd.concat(m0_parts, ignore_index=True) if m0_parts else pd.DataFrame()

    return m0, wf, params
