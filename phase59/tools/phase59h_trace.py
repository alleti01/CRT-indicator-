#!/usr/bin/env python3
"""Phase59H — bar-by-bar Python vs TV-HTF (lookahead_off) take-timing trace."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58.research.context import compute_context
from phase58.research.instrument import NQ
from phase58.research.location import compute_location
from phase58.research.reaction import compute_all_reactions
from phase58.research.trader_engine import TraderEngine
from phase58.research.trader_state import State
from phase58d.research.evidence import compute_evidence, decide
from phase58f.research.confidence import compute_confidence
from phase58f.research.policies import apply_policy
from phase58g.research.forensics import enrich
from phase58h.research.filters import apply_h_model
from phase58j.research.lw_data import build_market_arrays_lw, build_mtf_arrays_lw, load_markets_lw
from phase53.research.data import align_htf_to_1m, htf_bar_index
from phase59.tools.phase59_parity import _load_cfg

TZ = NQ.timezone
OUT = ROOT / "phase59" / "reports"
WIN = ("2026-08-26 13:35:00", "2026-08-26 13:45:00")


def _st(v: State) -> str:
    return {
        State.WATCH: "WATCH",
        State.ARMED_LONG: "ARMED_LONG",
        State.ARMED_SHORT: "ARMED_SHORT",
        State.IN_LONG: "IN_LONG",
        State.IN_SHORT: "IN_SHORT",
        State.COOLDOWN: "COOLDOWN",
    }[v]


def tv_confirmed_label(ts: pd.Timestamp) -> pd.Timestamp:
    """TV request.security(lookahead_off): last confirmed HTF bucket at 1M close."""
    if ts.minute % 5 == 4:
        return ts.floor("5min")
    return ts.floor("5min") - pd.Timedelta(minutes=5)


def tv_confirmed_label_15(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.minute % 15 == 14:
        return ts.floor("15min")
    return ts.floor("15min") - pd.Timedelta(minutes=15)


def _score(ma, i: int, direction: str, cfg: dict) -> dict:
    ctx = compute_context(ma, i)
    loc = compute_location(ma, i, direction)
    react = compute_all_reactions(ma, i, direction, cfg)
    ctx_sc = min(2, ctx["bull_score"] if direction == "LONG" else ctx["bear_score"])
    contra = 0
    if direction == "LONG" and ctx["direction"] == "NEUTRAL" and ctx["bear_score"] >= 2:
        contra = -1
    elif direction == "SHORT" and ctx["direction"] == "NEUTRAL" and ctx["bull_score"] >= 2:
        contra = -1
    total = ctx_sc + loc["score"] + react["score"] + contra
    return {
        "ctxDir": ctx["direction"],
        "ctxConf": ctx["confidence"],
        "bullSc": ctx["bull_score"],
        "bearSc": ctx["bear_score"],
        "ctxRs": "|".join(ctx["reasons"]),
        "locSc": loc["score"],
        "locRs": "|".join(loc["reasons"]),
        "reactSc": react["score"],
        "reactRs": "|".join(react["reasons"]),
        "contra": contra,
        "ctxSc": ctx_sc,
        "total": total,
        "rawTake": total >= cfg.get("take_threshold", 4),
    }


def _patch_tv_htf(ma, m1_index, m5, m15, i: int):
    ts = ma.idx[i]
    lab5 = tv_confirmed_label(ts)
    lab15 = tv_confirmed_label_15(ts)
    j5 = int(m5.index.searchsorted(lab5))
    if j5 >= len(m5) or m5.index[j5] != lab5:
        j5 = max(0, int(m5.index.searchsorted(lab5, side="right") - 1))
    j15 = int(m15.index.searchsorted(lab15))
    if j15 >= len(m15) or m15.index[j15] != lab15:
        j15 = max(0, int(m15.index.searchsorted(lab15, side="right") - 1))
    ma.m5_op[i] = float(m5.iloc[j5]["open"])
    ma.m5_hi[i] = float(m5.iloc[j5]["high"])
    ma.m5_lo[i] = float(m5.iloc[j5]["low"])
    ma.m5_cl[i] = float(m5.iloc[j5]["close"])
    if "atr" in m5.columns:
        ma.m5_atr[i] = float(m5.iloc[j5]["atr"])
    ma.m15_cl[i] = float(m15.iloc[j15]["close"])
    ma.m15_op[i] = float(m15.iloc[j15]["open"])
    ma.m15_hi[i] = float(m15.iloc[j15]["high"])
    ma.m15_lo[i] = float(m15.iloc[j15]["low"])
    if "atr" in m15.columns:
        ma.m15_atr[i] = float(m15.iloc[j15]["atr"])
    return j5, j15


def main() -> None:
    cfg = _load_cfg()
    ma = build_market_arrays_lw(swing=cfg.get("swing_period", 5))
    m_mtf = build_mtf_arrays_lw(swing_5m=cfg.get("swing_period", 5))
    m1, m5, m15 = load_markets_lw()
    m5a = align_htf_to_1m(m1, m5)
    idx5 = htf_bar_index(m1.index, m5.index)
    idx15 = htf_bar_index(m1.index, m15.index)

    start = int(np.where(ma.idx == pd.Timestamp(WIN[0], tz=TZ))[0][0])
    end = int(np.where(ma.idx == pd.Timestamp(WIN[1], tz=TZ))[0][0])
    warm = int(np.where(ma.idx == pd.Timestamp("2026-08-26 13:20:00", tz=TZ))[0][0])

    eng = TraderEngine(ma, cfg)
    for b in range(warm, end + 1):
        eng.on_bar_close(b)

    import copy

    ma_tv = copy.deepcopy(ma)
    rows: list[dict] = []
    first_div = None

    for b in range(start, end + 1):
        ts = ma.idx[b]
        j5_py = int(idx5[b])
        j15_py = int(idx15[b])
        j5_tv, j15_tv = _patch_tv_htf(ma_tv, m1.index, m5, m15, b)

        dec = None
        eng2 = TraderEngine(ma, cfg)
        for bb in range(warm, b + 1):
            dec = eng2.on_bar_close(bb)

        py_l = _score(ma, b, "LONG", cfg)
        tv_l = _score(ma_tv, b, "LONG", cfg)

        ev = {}
        p58d = p4 = h1 = ""
        if py_l["rawTake"] and dec and dec.decision.value in ("TAKE_LONG", "TAKE_SHORT"):
            ev = compute_evidence(m_mtf, b, "LONG", cfg)
            p58d, _ = decide(ev, "E", cfg, 0)
            conf = compute_confidence(m_mtf, b, "LONG", cfg)
            row = pd.DataFrame([{**conf, "original_direction": "LONG", "15m_state": ev["15m_state"]}])
            row = enrich(row)
            p4 = str(apply_policy(row, "P4").iloc[0])
            h1 = str(apply_h_model(row, "H1").iloc[0])

        row = {
            "ts_chicago": str(ts),
            "ts_ny": str(ts.tz_convert("America/New_York")),
            "unix_ms": int(ts.tz_convert("UTC").timestamp() * 1000),
            "open": ma.op[b],
            "high": ma.hi[b],
            "low": ma.lo[b],
            "close": ma.cl[b],
            "atr": ma.atr[b],
            "py_p58State": _st(eng2.st.state),
            "py_p58Dir": eng2.st.direction,
            "py_p58InTrade": eng2.st.trade is not None,
            "py_decision": dec.decision.value if dec else "",
            "py_m5_src": str(m5.index[j5_py]),
            "py_m5_OHLC": f"{ma.m5_op[b]:.2f}/{ma.m5_hi[b]:.2f}/{ma.m5_lo[b]:.2f}/{ma.m5_cl[b]:.2f}",
            "py_m15_src": str(m15.index[j15_py]),
            "py_ctxSc": py_l["ctxSc"],
            "py_locSc": py_l["locSc"],
            "py_reactSc": py_l["reactSc"],
            "py_contra": py_l["contra"],
            "py_total": py_l["total"],
            "py_rawTake": py_l["rawTake"],
            "py_ctxRs": py_l["ctxRs"],
            "py_reactRs": py_l["reactRs"],
            "tv_m5_src": str(m5.index[j5_tv]),
            "tv_m5_OHLC": f"{ma_tv.m5_op[b]:.2f}/{ma_tv.m5_hi[b]:.2f}/{ma_tv.m5_lo[b]:.2f}/{ma_tv.m5_cl[b]:.2f}",
            "tv_m15_src": str(m15.index[j15_tv]),
            "tv_ctxSc": tv_l["ctxSc"],
            "tv_locSc": tv_l["locSc"],
            "tv_reactSc": tv_l["reactSc"],
            "tv_contra": tv_l["contra"],
            "tv_total": tv_l["total"],
            "tv_rawTake": tv_l["rawTake"],
            "tv_ctxRs": tv_l["ctxRs"],
            "m5_src_match": j5_py == j5_tv,
            "total_match": py_l["total"] == tv_l["total"],
            "rawTake_match": py_l["rawTake"] == tv_l["rawTake"],
        }
        rows.append(row)

        if first_div is None and (j5_py != j5_tv or py_l["total"] != tv_l["total"]):
            first_div = {
                "ts": str(ts),
                "field": "m5_src" if j5_py != j5_tv else "total",
                "py": row["py_m5_src"] if j5_py != j5_tv else py_l["total"],
                "tv": row["tv_m5_src"] if j5_py != j5_tv else tv_l["total"],
            }

    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "phase59h_bar_by_bar_diff.csv"
    df.to_csv(csv_path, index=False)

    # 13:40 snapshot
    t40 = pd.Timestamp("2026-08-26 13:40:00", tz=TZ)
    b40 = int(np.where(ma.idx == t40)[0][0])
    py40 = _score(ma, b40, "LONG", cfg)
    ma_tv40 = copy.deepcopy(ma)
    _patch_tv_htf(ma_tv40, m1.index, m5, m15, b40)
    tv40 = _score(ma_tv40, b40, "LONG", cfg)
    ev40 = compute_evidence(m_mtf, b40, "LONG", cfg)
    d40, dr40 = decide(ev40, "E", cfg, 0)
    conf40 = compute_confidence(m_mtf, b40, "LONG", cfg)
    r40 = pd.DataFrame([{**conf40, "original_direction": "LONG", "15m_state": ev40["15m_state"]}])
    r40 = enrich(r40)
    p4_40 = str(apply_policy(r40, "P4").iloc[0])
    h1_40 = str(apply_h_model(r40, "H1").iloc[0])

    print(f"Wrote {csv_path}")
    print(f"FIRST_DIVERGENCE: {first_div}")
    print("\n=== PYTHON @ 13:40 ===")
    print(py40)
    print(f"evTotal={ev40['total_evidence']} evLoc={ev40['location_score']} evDir={ev40['direction_score']} evReact={ev40['reaction_score']}")
    print(f"decision={d40} P4={p4_40} H1={h1_40} FINAL={d40=='TAKE' and p4_40=='KEEP' and h1_40=='KEEP'}")
    print("\n=== TV lookahead_off @ 13:40 ===")
    print(tv40)
    print(f"m5_src_py={m5.index[int(idx5[b40])]} m5_src_tv={m5.index[int(m5.index.searchsorted(tv_confirmed_label(t40)))]}")


if __name__ == "__main__":
    main()
