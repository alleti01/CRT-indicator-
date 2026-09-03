"""Phase68 — microstructure setup families A–H."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class MicroSignal:
    family: str
    direction: str
    bar_ts: pd.Timestamp
    entry_i: int
    window: int
    reason: str
    delta_norm: float
    price_disp: float
    response: float


def _strong(row, w: int, q: dict, side: str) -> bool:
    dn = row[f"delta_norm_{w}s"]
    if side == "LONG":
        return dn >= q.get(f"delta_norm_{w}s", {}).get("p70", 0.15)
    return dn <= q.get(f"delta_norm_{w}s", {}).get("p30", -0.15)


def _response_ok(row, w: int, direction: str) -> bool:
    disp = row[f"price_disp_{w}s"]
    if direction == "LONG":
        return disp > 0.05 and row[f"response_{w}s"] > 0
    return disp < -0.05 and row[f"response_{w}s"] < 0


def scan_a(feat: pd.DataFrame, q: dict, w: int = 60) -> list[MicroSignal]:
    """Delta continuation."""
    out = []
    for i, (ts, row) in enumerate(feat.iterrows()):
        if _strong(row, w, q, "LONG") and _response_ok(row, w, "LONG"):
            out.append(MicroSignal("A", "LONG", ts, i + 1, w, "A_DELTA_CONT_LONG",
                                   row[f"delta_norm_{w}s"], row[f"price_disp_{w}s"], row[f"response_{w}s"]))
        elif _strong(row, w, q, "SHORT") and _response_ok(row, w, "SHORT"):
            out.append(MicroSignal("A", "SHORT", ts, i + 1, w, "A_DELTA_CONT_SHORT",
                                   row[f"delta_norm_{w}s"], row[f"price_disp_{w}s"], row[f"response_{w}s"]))
    return out


def scan_b(feat: pd.DataFrame, q: dict, w: int = 60) -> list[MicroSignal]:
    """Absorption reversal: large delta, poor price response."""
    out = []
    for i, (ts, row) in enumerate(feat.iterrows()):
        dn = row[f"delta_norm_{w}s"]
        disp = row[f"price_disp_{w}s"]
        if dn >= q.get(f"delta_norm_{w}s", {}).get("p80", 0.2) and disp < 0.05:
            out.append(MicroSignal("B", "SHORT", ts, i + 1, w, "B_ABSORB_BUY_FAIL",
                                   dn, disp, row[f"response_{w}s"]))
        elif dn <= q.get(f"delta_norm_{w}s", {}).get("p20", -0.2) and disp > -0.05:
            out.append(MicroSignal("B", "LONG", ts, i + 1, w, "B_ABSORB_SELL_FAIL",
                                   dn, disp, row[f"response_{w}s"]))
    return out


def scan_c(feat: pd.DataFrame, m1: pd.DataFrame, w: int = 60) -> list[MicroSignal]:
    """Delta/price divergence vs 5-bar level."""
    out = []
    hi5 = m1["high"].rolling(5).max().shift(1)
    lo5 = m1["low"].rolling(5).min().shift(1)
    for i, (ts, row) in enumerate(feat.iterrows()):
        if ts not in m1.index:
            continue
        if m1.loc[ts, "close"] >= hi5.get(ts, 0) and row[f"delta_norm_{w}s"] < 0:
            out.append(MicroSignal("C", "SHORT", ts, i + 1, w, "C_DIV_HIGH_WEAK_DELTA",
                                   row[f"delta_norm_{w}s"], row[f"price_disp_{w}s"], row[f"response_{w}s"]))
        elif m1.loc[ts, "close"] <= lo5.get(ts, 999999) and row[f"delta_norm_{w}s"] > 0:
            out.append(MicroSignal("C", "LONG", ts, i + 1, w, "C_DIV_LOW_WEAK_DELTA",
                                   row[f"delta_norm_{w}s"], row[f"price_disp_{w}s"], row[f"response_{w}s"]))
    return out


def scan_f(feat: pd.DataFrame, w: int = 60) -> list[MicroSignal]:
    """Pressure flip: 15s vs 60s delta sign change."""
    out = []
    for i, (ts, row) in enumerate(feat.iterrows()):
        d15 = row.get("delta_norm_15s", 0)
        d60 = row.get(f"delta_norm_{w}s", 0)
        if d15 > 0.1 and d60 < -0.1:
            out.append(MicroSignal("F", "SHORT", ts, i + 1, w, "F_PRESSURE_FLIP_SHORT", d60, row[f"price_disp_{w}s"], 0))
        elif d15 < -0.1 and d60 > 0.1:
            out.append(MicroSignal("F", "LONG", ts, i + 1, w, "F_PRESSURE_FLIP_LONG", d60, row[f"price_disp_{w}s"], 0))
    return out


def scan_g(feat: pd.DataFrame, q: dict, w: int = 60) -> list[MicroSignal]:
    """Pace + imbalance."""
    out = []
    pace_thr = q.get(f"pace_{w}s", {}).get("p80", 5)
    for i, (ts, row) in enumerate(feat.iterrows()):
        if row[f"pace_{w}s"] < pace_thr:
            continue
        if _strong(row, w, q, "LONG") and _response_ok(row, w, "LONG"):
            out.append(MicroSignal("G", "LONG", ts, i + 1, w, "G_PACE_IMB_LONG", row[f"delta_norm_{w}s"], row[f"price_disp_{w}s"], 0))
        elif _strong(row, w, q, "SHORT") and _response_ok(row, w, "SHORT"):
            out.append(MicroSignal("G", "SHORT", ts, i + 1, w, "G_PACE_IMB_SHORT", row[f"delta_norm_{w}s"], row[f"price_disp_{w}s"], 0))
    return out


def scan_h(feat: pd.DataFrame, q: dict, w: int = 60) -> list[MicroSignal]:
    """Large-trade pressure."""
    out = []
    for i, (ts, row) in enumerate(feat.iterrows()):
        ld = row.get(f"large_delta_{w}s", 0)
        tv = row.get(f"buy_vol_{w}s", 0) + row.get(f"sell_vol_{w}s", 0)
        if tv <= 0:
            continue
        lnorm = ld / tv
        if lnorm >= 0.25 and _response_ok(row, w, "LONG"):
            out.append(MicroSignal("H", "LONG", ts, i + 1, w, "H_LARGE_TRADE_LONG", lnorm, row[f"price_disp_{w}s"], 0))
        elif lnorm <= -0.25 and _response_ok(row, w, "SHORT"):
            out.append(MicroSignal("H", "SHORT", ts, i + 1, w, "H_LARGE_TRADE_SHORT", lnorm, row[f"price_disp_{w}s"], 0))
    return out


def scan_delta_only(feat: pd.DataFrame, q: dict, w: int = 60) -> list[MicroSignal]:
    out = []
    for i, (ts, row) in enumerate(feat.iterrows()):
        if _strong(row, w, q, "LONG"):
            out.append(MicroSignal("DELTA", "LONG", ts, i + 1, w, "DELTA_ONLY_LONG", row[f"delta_norm_{w}s"], 0, 0))
        elif _strong(row, w, q, "SHORT"):
            out.append(MicroSignal("DELTA", "SHORT", ts, i + 1, w, "DELTA_ONLY_SHORT", row[f"delta_norm_{w}s"], 0, 0))
    return out


SCANNERS = {
    "A": scan_a,
    "B": scan_b,
    "C": scan_c,
    "F": scan_f,
    "G": scan_g,
    "H": scan_h,
}
