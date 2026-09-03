"""Phase68 — causal microstructure primitives on rolling trade windows."""
from __future__ import annotations

import numpy as np
import pandas as pd

WINDOWS_SEC = (15, 30, 60)


def _ns(ts: pd.Timestamp) -> int:
    return int(ts.value)


def build_minute_grid(trades: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    """Causal features at each 1m bar close from trades with ts <= bar close."""
    bars = m1.index.sort_values()
    ts_ns = trades["ts_local"].astype("int64").to_numpy()
    buy = trades["buy_vol"].to_numpy()
    sell = trades["sell_vol"].to_numpy()
    price = trades["price"].to_numpy()
    size = trades["size"].to_numpy()
    is_buy = trades["is_buy"].to_numpy()
    is_sell = trades["is_sell"].to_numpy()

    rows = []
    for bar_ts in bars:
        bar_ns = _ns(bar_ts)
        end = int(np.searchsorted(ts_ns, bar_ns, side="right"))
        if end < 10:
            continue
        atr = float(m1.loc[bar_ts, "atr"]) if "atr" in m1.columns else float(m1.loc[bar_ts, "high"] - m1.loc[bar_ts, "low"])
        atr = atr if atr > 0 else 1.0
        row = {"bar_ts": bar_ts, "atr": atr, "close": float(m1.loc[bar_ts, "close"])}
        for w in WINDOWS_SEC:
            w_ns = w * 1_000_000_000
            start = int(np.searchsorted(ts_ns, bar_ns - w_ns, side="left"))
            sl = slice(start, end)
            bv, sv = buy[sl].sum(), sell[sl].sum()
            tv = bv + sv
            delta = bv - sv
            row[f"delta_{w}s"] = delta
            row[f"delta_norm_{w}s"] = delta / tv if tv > 0 else 0
            row[f"buy_vol_{w}s"] = bv
            row[f"sell_vol_{w}s"] = sv
            row[f"trade_count_{w}s"] = end - start
            row[f"pace_{w}s"] = (end - start) / w
            row[f"vol_pace_{w}s"] = tv / w
            p0 = price[start] if start < end else price[end - 1]
            p1 = price[end - 1]
            disp = (p1 - p0) / atr
            row[f"price_disp_{w}s"] = disp
            row[f"response_{w}s"] = disp / (abs(delta) / max(tv, 1)) if tv > 0 else 0
            row[f"efficiency_{w}s"] = abs(disp) / max((price[sl].max() - price[sl].min()) / atr, 0.01) if end > start else 0
            # large trades: top 20% size in window (causal within window only)
            if end > start:
                thr = np.quantile(size[sl], 0.8)
                lb = size[sl] >= thr
                row[f"large_delta_{w}s"] = buy[sl][lb].sum() - sell[sl][lb].sum()
            else:
                row[f"large_delta_{w}s"] = 0
        rows.append(row)
    return pd.DataFrame(rows).set_index("bar_ts")


def train_quantiles(feat: pd.DataFrame, train_end: pd.Timestamp) -> dict:
    tr = feat.loc[feat.index <= train_end]
    q = {}
    for w in WINDOWS_SEC:
        for col in [f"delta_norm_{w}s", f"response_{w}s", f"pace_{w}s"]:
            if col in tr.columns:
                q[col] = {
                    "p70": float(tr[col].quantile(0.70)),
                    "p80": float(tr[col].quantile(0.80)),
                    "p30": float(tr[col].quantile(0.30)),
                    "p20": float(tr[col].quantile(0.20)),
                }
    # large trade threshold frozen from train
    q["large_size"] = float(tr.filter(like="buy_vol").stack().quantile(0.8)) if len(tr) else 0
    return q
