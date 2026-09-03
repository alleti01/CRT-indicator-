"""Bootstrap reference from historical OOS B1/M0 trades."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase17.analysis_core import max_drawdown
from phase31.metrics import performance

from phase48.entries import load_frozen_entries

from .config import BOOTSTRAP_SAMPLE_SIZES, BOOTSTRAP_SEED


def _bootstrap_metrics(r: np.ndarray, n_boot: int = 2000, seed: int = BOOTSTRAP_SEED) -> dict:
    rng = np.random.default_rng(seed)
    avgrs, totals, pfs, wrs, dds = [], [], [], [], []
    for _ in range(n_boot):
        sample = rng.choice(r, size=len(r), replace=True)
        p = performance(pd.DataFrame({"x": sample}), col="x")
        avgrs.append(p["AvgR"])
        totals.append(p["TotalR"])
        pfs.append(p["PF"])
        wrs.append(p["WinRate"])
        dds.append(max_drawdown(sample))
    return {
        "AvgR_p5": float(np.percentile(avgrs, 5)),
        "AvgR_p50": float(np.percentile(avgrs, 50)),
        "AvgR_p95": float(np.percentile(avgrs, 95)),
        "TotalR_p5": float(np.percentile(totals, 5)),
        "TotalR_p95": float(np.percentile(totals, 95)),
        "PF_p5": float(np.percentile(pfs, 5)),
        "PF_p95": float(np.percentile(pfs, 95)),
        "WinRate_p5": float(np.percentile(wrs, 5)),
        "WinRate_p95": float(np.percentile(wrs, 95)),
        "MaxDD_p5": float(np.percentile(dds, 5)),
        "MaxDD_p95": float(np.percentile(dds, 95)),
    }


def build_bootstrap_reference() -> pd.DataFrame:
    hist = load_frozen_entries()
    r = hist["control_net_R"].astype(float).to_numpy()
    rows = []
    for n in BOOTSTRAP_SAMPLE_SIZES:
        if n > len(r):
            continue
        sub = r[:n] if n == len(r) else r[-n:]
        p = performance(pd.DataFrame({"x": sub}), col="x")
        boot = _bootstrap_metrics(r, seed=BOOTSTRAP_SEED + n)
        rows.append({"sample_size": n, "historical_N": len(r), **p, **boot})
    return pd.DataFrame(rows)


def forward_percentile(forward_r: np.ndarray, historical_r: np.ndarray) -> dict:
    if len(forward_r) == 0:
        return {"AvgR_percentile": np.nan, "status": "INSUFFICIENT SAMPLE"}
    fwd_avgr = float(forward_r.mean())
    boot = [float(np.mean(np.random.default_rng(BOOTSTRAP_SEED + i).choice(historical_r, size=len(forward_r), replace=True)))
            for i in range(1000)]
    pct = float((np.array(boot) <= fwd_avgr).mean() * 100)
    status = "WITHIN EXPECTED RANGE"
    if pct < 25:
        status = "WEAKER THAN EXPECTED"
    elif pct > 75:
        status = "STRONGER THAN EXPECTED"
    if len(forward_r) < 20:
        status = "INSUFFICIENT SAMPLE"
    return {"AvgR_percentile": pct, "status": status}
