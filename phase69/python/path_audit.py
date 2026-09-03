"""Phase69 — path diagnostics without changing exit."""
from __future__ import annotations

import numpy as np
import pandas as pd


HORIZONS = [1, 2, 3, 5, 10, 15, 20, 30, 45, 60, 90, 120]
THRESHOLDS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 10.0]


def path_diagnostics(execs: pd.DataFrame, m) -> pd.DataFrame:
    rows = []
    for _, ex in execs.iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 125:
            continue
        d = 1 if ex["direction"] == "LONG" else -1
        ep = float(ex["entry_price"])
        atr = float(ex["atr_entry"]) if ex["atr_entry"] > 0 else float(m.atr[ei])
        risk = atr
        stop = ep - d * risk
        end = min(ei + 121, m.n)
        hs, ls = m.hi[ei:end], m.lo[ei:end]
        if d == 1:
            fav = (np.maximum.accumulate(hs) - ep) / risk
            adv = (ep - np.minimum.accumulate(ls)) / risk
        else:
            fav = (ep - np.minimum.accumulate(ls)) / risk
            adv = (np.maximum.accumulate(hs) - ep) / risk

        row = {"trade_id": ex["trade_id"], "direction": ex["direction"], "entry_ts": ex["entry_ts"],
               "atr": atr, "mfe_60m": float(np.max(fav)), "mae_60m": float(np.max(adv))}
        for h in HORIZONS:
            sl = min(h, len(fav))
            row[f"mfe_{h}m"] = float(np.max(fav[:sl])) if sl else 0
            row[f"mae_{h}m"] = float(np.max(adv[:sl])) if sl else 0
        rows.append(row)
    return pd.DataFrame(rows)


def first_touch(fav, adv, level: float) -> int | None:
    hit = np.where(fav >= level)[0]
    return int(hit[0]) if len(hit) else None


def counterfactual_after_r(execs: pd.DataFrame, m, trigger_r: float = 2.5) -> dict:
    """After first +trigger_r, prob of higher R before giveback."""
    reached = 0
    later = {t: 0 for t in [3, 4, 5, 6, 7, 10]}
    add_mfe = []
    for _, ex in execs.iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 65:
            continue
        d = 1 if ex["direction"] == "LONG" else -1
        ep = float(ex["entry_price"])
        risk = float(ex["atr_entry"]) if ex["atr_entry"] > 0 else float(m.atr[ei])
        end = min(ei + 121, m.n)
        hs, ls = m.hi[ei:end], m.lo[ei:end]
        if d == 1:
            fav = (np.maximum.accumulate(hs) - ep) / risk
            adv = (ep - np.minimum.accumulate(ls)) / risk
        else:
            fav = (ep - np.minimum.accumulate(ls)) / risk
            adv = (np.maximum.accumulate(hs) - ep) / risk
        ti = first_touch(fav, adv, trigger_r)
        if ti is None:
            continue
        reached += 1
        post_fav = fav[ti:]
        post_adv = adv[ti:]
        add_mfe.append(float(np.max(post_fav)))
        for t in later:
            # reach t before dropping to trigger-0.5
            hit_t = np.where(post_fav >= t)[0]
            hit_back = np.where(post_adv >= 0.5)[0]
            if len(hit_t) and (not len(hit_back) or hit_t[0] < hit_back[0]):
                later[t] += 1
    out = {"reached": reached, "pct_reached": reached / len(execs) if len(execs) else 0}
    for t, c in later.items():
        out[f"p_reach_{t}R_after_{trigger_r}R"] = c / reached if reached else 0
    if add_mfe:
        out["median_add_mfe_after"] = float(np.median(add_mfe))
        out["p75_add_mfe"] = float(np.quantile(add_mfe, 0.75))
        out["p90_add_mfe"] = float(np.quantile(add_mfe, 0.90))
    return out


def fixed_target_frontier(execs: pd.DataFrame, m, targets: list[float]) -> pd.DataFrame:
    from phase69.python.sim_management import simulate_batch
    rows = []
    for t in targets:
        sim = simulate_batch(execs, m, mode="M0", target_r=t, max_hold=60)
        if sim.empty:
            continue
        rows.append({
            "target_r": t,
            "N": len(sim),
            "win_rate": float((sim["gross_R"] > 0).mean()),
            "AvgR": float(sim["net_R"].mean()),
            "PF": float(sim["gross_R"].clip(lower=0).sum() / max(abs(sim["gross_R"].clip(upper=0).sum()), 1e-9)),
            "TotalR": float(sim["net_R"].sum()),
            "target_pct": float((sim["exit_reason"] == "FIXED_TARGET").mean()),
            "stop_pct": float((sim["exit_reason"] == "INITIAL_STOP").mean()),
            "median_hold": float(sim["duration"].median()),
            "avg_winner": float(sim.loc[sim["gross_R"] > 0, "gross_R"].mean()) if (sim["gross_R"] > 0).any() else 0,
            "avg_loser": float(sim.loc[sim["gross_R"] <= 0, "gross_R"].mean()) if (sim["gross_R"] <= 0).any() else 0,
        })
    return pd.DataFrame(rows)
