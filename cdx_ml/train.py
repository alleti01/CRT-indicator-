"""Train the take/skip + stop/target model with walk-forward testing.

The model scores every (signal, option) pair: given the market conditions and an
option (stop type, stop distance in ATR, target R), it predicts the R result.
For a new signal it takes the option with the best predicted R, or skips when
none clears `MIN_EDGE_R`.

Walk-forward: for each CDX trading day, train only on signals that resolved
before that day started (4-hour embargo), then test on that day. The model is
compared against two fixed rules on exactly the same days. A model is marked
PROMOTE only when it beats the best rule on the walk-forward days.

    python -m cdx_ml.train          # writes cdx_ml/reports/TRAINING_REPORT.md and cdx_ml/models/
"""
from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from cdx_ml.dataset import ET, HORIZON, OUT as DATA_DIR, STOP_KINDS, TARGETS

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"
REPORTS = HERE / "reports"

SIGNAL_FEATURES = [
    "side", "align_15m", "align_1h", "atr3", "atr_ratio", "hour_et", "weekday",
    "eff20", "overlap20", "range20_atr", "pos20", "room_day_atr", "ret15_atr",
    "ret60_atr", "mins_since_prev", "prev_same_side", "cdx_sl_pts", "cdx_tp1_r", "cdx_tp2_r",
]
SESSIONS = ["asia", "london", "ny_open", "ny_mid", "ny_pm", "close"]
MIN_EDGE_R = 0.10
MIN_TRAIN_ROWS = 60
RULES = {
    "take_all_fixed14_2R": (lambda r: True, "fixed14_t2"),
    "15m_agrees_atr1.5_2R": (lambda r: r["align_15m"] == 1, "atr1.5_t2"),
}


def load(path: Path = DATA_DIR / "dataset.csv") -> pd.DataFrame:
    df = pd.read_csv(path)
    df["t"] = pd.to_datetime(df["signal_time_utc"], utc=True)
    df["day"] = [_futures_day(t) for t in df["t"]]
    return df.sort_values("t").reset_index(drop=True)


def _futures_day(t: pd.Timestamp) -> str:
    et = t.tz_convert(ET)
    return (et + timedelta(hours=6)).strftime("%Y-%m-%d")  # 6 pm ET reopen starts the next day


def options() -> list[tuple[str, float]]:
    return [(k, t) for k in STOP_KINDS for t in TARGETS]


def stack(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (signal, option) that has a label."""
    parts = []
    for kind, tr in options():
        key = f"{kind}_t{tr:g}"
        d = df[df[f"r_{key}"].notna()].copy()
        if d.empty:
            continue
        d["opt"] = key
        d["opt_stop_atr"] = d[f"dist_{kind}"] / d["atr3"]
        d["opt_target_r"] = tr
        for k in STOP_KINDS:
            d[f"opt_is_{k}"] = int(k == kind)
        d["y"] = d[f"r_{key}"]
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def design(d: pd.DataFrame) -> np.ndarray:
    cols = [d[c].astype(float) for c in SIGNAL_FEATURES]
    cols += [(d["session"] == s).astype(float) for s in SESSIONS]
    cols += [(d["source"] == "cdx").astype(float)]
    cols += [d["opt_stop_atr"].astype(float), d["opt_target_r"].astype(float)]
    cols += [d[f"opt_is_{k}"].astype(float) for k in STOP_KINDS]
    return np.column_stack(cols)


def feature_names() -> list[str]:
    return SIGNAL_FEATURES + [f"session_{s}" for s in SESSIONS] + ["is_cdx", "opt_stop_atr", "opt_target_r"] + [f"opt_is_{k}" for k in STOP_KINDS]


def make_model() -> HistGradientBoostingRegressor:
    # Shallow trees, big leaves, strong L2: on a few hundred rows anything looser memorizes noise.
    return HistGradientBoostingRegressor(
        max_depth=3,
        max_iter=150,
        learning_rate=0.05,
        min_samples_leaf=40,
        l2_regularization=1.0,
        random_state=7,
    )


def fit(df: pd.DataFrame) -> HistGradientBoostingRegressor:
    s = stack(df)
    m = make_model()
    m.fit(design(s), s["y"].to_numpy())
    return m


@dataclass
class Pick:
    take: bool
    opt: str
    pred_r: float


def pick(model, rows: pd.DataFrame) -> list[Pick]:
    s = stack(rows)
    s["pred"] = model.predict(design(s))
    out = []
    for sid in rows["signal_id"]:
        g = s[s["signal_id"] == sid]
        best = g.loc[g["pred"].idxmax()]
        out.append(Pick(bool(best["pred"] >= MIN_EDGE_R), str(best["opt"]), float(best["pred"])))
    return out


def walk_forward(df: pd.DataFrame) -> pd.DataFrame:
    cdx_days = sorted(df.loc[df["source"] == "cdx", "day"].unique())
    rows = []
    for day in cdx_days:
        test = df[(df["day"] == day) & (df["source"] == "cdx")]
        day_start = test["t"].min().tz_convert(ET).replace(hour=18, minute=0, second=0) - timedelta(days=1)
        if test["t"].min().tz_convert(ET).hour >= 18:
            day_start += timedelta(days=1)
        train = df[df["t"] + HORIZON <= day_start]  # only signals whose 4h outcome was known before the day began
        if len(train) < MIN_TRAIN_ROWS:
            continue
        model = fit(train)
        for (_, r), p in zip(test.iterrows(), pick(model, test)):
            row = {"day": day, "signal_id": r["signal_id"], "train_rows": len(train),
                   "model_take": p.take, "model_opt": p.opt, "model_pred": p.pred_r,
                   "model_r": r[f"r_{p.opt}"] if p.take else 0.0}
            for name, (cond, opt) in RULES.items():
                take = bool(cond(r))
                row[f"{name}_take"] = take
                row[f"{name}_r"] = r[f"r_{opt}"] if take else 0.0
            rows.append(row)
    return pd.DataFrame(rows)


def summarize(wf: pd.DataFrame) -> pd.DataFrame:
    out = []
    for name in ["model"] + list(RULES):
        took = wf[wf[f"{name}_take"]]
        r = took[f"{name}_r"]
        by_day = wf.groupby("day")[f"{name}_r"].sum()
        out.append({
            "policy": name,
            "signals": len(wf),
            "trades": len(took),
            "win_rate": float((r > 0).mean()) if len(r) else 0.0,
            "avg_r": float(r.mean()) if len(r) else 0.0,
            "total_r": float(r.sum()),
            "green_days": int((by_day > 0).sum()),
            "red_days": int((by_day < 0).sum()),
            "worst_day_r": float(by_day.min()) if len(by_day) else 0.0,
        })
    return pd.DataFrame(out)


def importances(model, df: pd.DataFrame, top: int = 10) -> list[tuple[str, float]]:
    """How much predicted R moves when each input is shuffled. In-sample, so a rough guide only."""
    s = stack(df)
    X = design(s)
    base = model.predict(X)
    rng = np.random.default_rng(7)
    scores = []
    for j, name in enumerate(feature_names()):
        Xp = X.copy()
        Xp[:, j] = rng.permutation(Xp[:, j])
        scores.append((name, float(np.mean(np.abs(model.predict(Xp) - base)))))
    return sorted(scores, key=lambda x: -x[1])[:top]


def report(df: pd.DataFrame, wf: pd.DataFrame, summ: pd.DataFrame, imp, decision: str) -> str:
    cdx = df[df["source"] == "cdx"]
    fmt = lambda v: f"{v:+.2f}"
    lines = [
        "# CDX model training report",
        "",
        f"Trained {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC on {len(df)} signals ({len(cdx)} CDX). "
        f"Walk-forward tested on {wf['day'].nunique() if len(wf) else 0} CDX days, {len(wf)} signals.",
        "",
        f"## Decision: **{decision}**",
        "",
        "The model is promoted only when its walk-forward total R beats the best fixed rule on the same days.",
        "",
        "## Walk-forward results (each day tested on a model that never saw it)",
        "",
        "| Policy | Trades | Win rate | Avg R | Total R | Green / red days | Worst day R |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, r in summ.iterrows():
        lines.append(f"| {r['policy']} | {r['trades']} / {r['signals']} | {r['win_rate']:.0%} | {fmt(r['avg_r'])} | {fmt(r['total_r'])} | {r['green_days']} / {r['red_days']} | {fmt(r['worst_day_r'])} |")
    lines += ["", "## By day", "", "| Day | Signals | Train rows | Model trades | Model R | 15m rule R | Take-all R |", "|---|---|---|---|---|---|---|"]
    for day, g in wf.groupby("day"):
        lines.append(f"| {day} | {len(g)} | {g['train_rows'].iloc[0]} | {int(g['model_take'].sum())} | {fmt(g['model_r'].sum())} | {fmt(g['15m_agrees_atr1.5_2R_r'].sum())} | {fmt(g['take_all_fixed14_2R_r'].sum())} |")
    if len(wf):
        chosen = wf[wf["model_take"]]["model_opt"].value_counts()
        lines += ["", "## Options the model chose when it traded", ""] + [f"- `{k}`: {v}" for k, v in chosen.items()]
    lines += ["", "## What moves the model's prediction most (final model, in-sample)", ""]
    lines += [f"{i}. `{n}` ({v:.3f} R)" for i, (n, v) in enumerate(imp, 1)]
    lines += [
        "",
        "## Limits",
        "",
        "- Very small sample. With under ~300 CDX signals, a model beating the rule on a few days can be luck; treat a PROMOTE as a reason to shadow it, not to trade it.",
        "- Results are per signal and ignore the one-position-at-a-time and daily-limit rules.",
        "- Signals minutes apart share a price path, so per-signal results overstate independence.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    df = load()
    wf = walk_forward(df)
    summ = summarize(wf)
    best_rule = summ[summ["policy"] != "model"]["total_r"].max()
    model_total = float(summ.loc[summ["policy"] == "model", "total_r"].iloc[0])
    decision = "PROMOTE" if model_total > best_rule else "KEEP_RULE"
    final = fit(df)
    imp = importances(final, df)

    MODELS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    with (MODELS / "latest.pkl").open("wb") as fh:
        pickle.dump(final, fh)
    meta = {
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": len(df),
        "cdx_rows": int((df["source"] == "cdx").sum()),
        "last_signal_utc": df["t"].max().isoformat(),
        "features": feature_names(),
        "options": [f"{k}_t{t:g}" for k, t in options()],
        "min_edge_r": MIN_EDGE_R,
        "walk_forward": summ.to_dict(orient="records"),
        "decision": decision,
    }
    (MODELS / "latest.json").write_text(json.dumps(meta, indent=2))
    wf.to_csv(REPORTS / "walk_forward.csv", index=False)
    text = report(df, wf, summ, imp, decision)
    (REPORTS / "TRAINING_REPORT.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
