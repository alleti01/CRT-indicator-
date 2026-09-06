#!/usr/bin/env python3
"""Phase76 checkpoint 14 — randomized direction control gate (Families A–F)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(line_buffering=True)

from phase76.python.auction_engine import build_auction_features  # noqa: E402
from phase76.python.config import CHECKPOINTS, REPORTS  # noqa: E402
from phase76.python.data_loader import load_nq_1m  # noqa: E402
from phase76.python.market_states import classify_auction_states  # noqa: E402
from phase76.python.path_engine import precompute_signal_paths  # noqa: E402
from phase76.python.randomized_controls import FamilySpec, run_family_gate, summary_row  # noqa: E402
from phase76.python.signals import (  # noqa: E402
    family_a_upper_rejection,
    family_b_lower_rejection,
    family_c_initiative_acceptance,
    family_d_failed_acceptance,
    family_e_lvn_traversal,
    family_f_value_rotation,
)

FROZEN_DIR = ROOT / "phase76" / "data" / "frozen_signals"
FEAT_CACHE = ROOT / "phase76" / "data" / "auction_features.parquet"

FAMILIES = [
    FamilySpec("A", "UPPER_VALUE_REJECTION", lambda f: family_a_upper_rejection(f, value_source="developing")),
    FamilySpec("B", "LOWER_VALUE_REJECTION", lambda f: family_b_lower_rejection(f, value_source="developing")),
    FamilySpec("C", "INITIATIVE_ACCEPTANCE", lambda f: family_c_initiative_acceptance(f, value_source="developing")),
    FamilySpec("D", "FAILED_ACCEPTANCE", lambda f: family_d_failed_acceptance(f, value_source="developing")),
    FamilySpec("E", "LVN_TRAVERSAL", family_e_lvn_traversal),
    FamilySpec("F", "VALUE_ROTATION", lambda f: family_f_value_rotation(f, value_source="developing")),
]


def _load_or_build_features(ohlc: pd.DataFrame) -> pd.DataFrame:
    if FEAT_CACHE.exists():
        print(f"Loading cached features: {FEAT_CACHE}")
        feat = pd.read_parquet(FEAT_CACHE)
        feat.index = pd.to_datetime(feat.index, utc=True)
        return feat
    print("Building auction features (slow, will cache)...")
    feat = build_auction_features(ohlc)
    feat["auction_state"] = classify_auction_states(feat, value_source="developing")
    FEAT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    feat.to_parquet(FEAT_CACHE)
    return feat


def _freeze_signals(spec: FamilySpec, feat: pd.DataFrame) -> pd.DataFrame:
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    path = FROZEN_DIR / f"family_{spec.code}_signals.parquet"
    if path.exists():
        return pd.read_parquet(path)
    sigs = spec.generator(feat)
    if sigs.empty:
        sigs.to_parquet(path)
        return sigs
    sigs = sigs.dropna(subset=["entry_ts"]).copy()
    sigs["atr"] = [feat.loc[t, "atr"] if t in feat.index else None for t in sigs["signal_ts"]]
    sigs.to_parquet(path)
    return sigs


def _append_ledger(row: dict) -> None:
    ledger = REPORTS / "EXPERIMENT_LEDGER.csv"
    fields = list(row.keys())
    write_header = not ledger.exists() or ledger.stat().st_size < 10
    with ledger.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            w.writeheader()
        w.writerow(row)


def _fmt(v, nd=3):
    import numpy as np

    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{float(v):.{nd}f}"


def _write_reports(results: list[dict], summary: list[dict]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)

    # Main CSV
    pd.DataFrame(summary).to_csv(REPORTS / "PHASE76_RANDOMIZED_CONTROLS.csv", index=False)

    # Year stability
    year_rows = []
    for r in results:
        for yr, agg in r.get("years", {}).items():
            year_rows.append(
                {
                    "family": r["family"],
                    "year": yr,
                    "n": agg.get("n", 0),
                    "fp_1_1": agg.get("fp_1.0atr_before_1.0atr"),
                    "fp_2_1": agg.get("fp_2.0atr_before_1.0atr"),
                    "asym_15m": agg.get("asym_15m"),
                }
            )
    pd.DataFrame(year_rows).to_csv(REPORTS / "PHASE76_RANDOMIZED_YEAR_STABILITY.csv", index=False)

    # Split stability
    split_rows = []
    for r in results:
        for split, agg in r.get("splits", {}).items():
            split_rows.append(
                {
                    "family": r["family"],
                    "split": split,
                    "n": agg.get("n", 0),
                    "fp_1_1": agg.get("fp_1.0atr_before_1.0atr"),
                    "fp_2_1": agg.get("fp_2.0atr_before_1.0atr"),
                    "asym_15m": agg.get("asym_15m"),
                }
            )
    pd.DataFrame(split_rows).to_csv(REPORTS / "PHASE76_RANDOMIZED_SPLIT_STABILITY.csv", index=False)

    # Markdown
    lines = [
        "# Phase76 — Randomized Direction Controls",
        "",
        "Gate: 100 deterministic seeds (76001–76100). Fixed entry T+1 open.",
        "",
        "## Summary table",
        "",
        "| Family | N | Real +1/-1 | Rand +1/-1 | Real +2/-1 | Rand +2/-1 | Real MFE/MAE15 | Flip +2/-1 | Train +2/-1 | Val +2/-1 | Hist +2/-1 | Verdict |",
        "|--------|---|------------|------------|------------|------------|----------------|------------|-------------|-----------|------------|---------|",
    ]
    for s in summary:
        lines.append(
            f"| {s['family']} | {s['n']} | {_fmt(s.get('real_fp11'))} | {_fmt(s.get('rand_fp11_mean'))} | "
            f"{_fmt(s.get('real_fp21'))} | {_fmt(s.get('rand_fp21_mean'))} | {_fmt(s.get('real_asym_15'))} | "
            f"{_fmt(s.get('flip_fp21'))} | {_fmt(s.get('train_fp21'))} | {_fmt(s.get('val_fp21'))} | "
            f"{_fmt(s.get('hist_test_fp21'))} | {s.get('verdict', '')} |"
        )

    survivors = [r for r in results if r.get("passes_random_gate")]
    rejected = [r for r in results if r.get("verdict") == "NO_DIRECTIONAL_INFORMATION"]
    inverse = [r for r in results if r.get("verdict") == "INVERSE_INFORMATION"]

    lines.extend(
        [
            "",
            "## Gate outcomes",
            "",
            f"- **Survivors (pass to matched S/R):** {', '.join(r['family'] for r in survivors) or 'none'}",
            f"- **Rejected (NO_DIRECTIONAL_INFORMATION):** {', '.join(r['family'] for r in rejected) or 'none'}",
            f"- **Inverse flagged:** {', '.join(r['family'] for r in inverse) or 'none'}",
            "",
            "## Per-family detail",
            "",
        ]
    )

    for r in results:
        lines.append(f"### Family {r['family']} — {r['name']}")
        lines.append(f"- N: {r['n']}")
        lines.append(f"- Verdict: **{r['verdict']}**")
        fp11 = r.get("fp11_stats", {})
        fp21 = r.get("fp21_stats", {})
        lines.append(
            f"- +1/-1: real={_fmt(fp11.get('real'))} rand_mean={_fmt(fp11.get('rand_mean'))} "
            f"percentile={fp11.get('real_percentile', '—')} delta={fp11.get('real_minus_mean', '—')}"
        )
        lines.append(
            f"- +2/-1: real={_fmt(fp21.get('real'))} rand_mean={_fmt(fp21.get('rand_mean'))} "
            f"percentile={fp21.get('real_percentile', '—')} delta={fp21.get('real_minus_mean', '—')}"
        )
        flip = r.get("flip", {})
        lines.append(f"- Flip +2/-1: {_fmt(flip.get('fp_2.0atr_before_1.0atr'))}")
        lines.append("")

    (REPORTS / "PHASE76_RANDOMIZED_CONTROLS.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    if not (CHECKPOINTS / "02_causality_audit.json").exists():
        print("CAUSALITY audit missing — run run_causality_audit.py first")
        return 2

    print("Loading OHLC...")
    ohlc = load_nq_1m()
    feat = _load_or_build_features(ohlc)

    results = []
    summary = []

    for spec in FAMILIES:
        print(f"\n=== Family {spec.code}: {spec.name} ===")
        sigs = _freeze_signals(spec, feat)
        print(f"  frozen signals: {len(sigs)}")
        if sigs.empty:
            res = {"family": spec.code, "name": spec.name, "n": 0, "verdict": "DATA_INSUFFICIENT", "passes_random_gate": False}
            results.append(res)
            summary.append(summary_row(res))
            continue

        print("  precomputing paths...")
        path_cache = FROZEN_DIR / f"family_{spec.code}_paths.parquet"
        if path_cache.exists():
            pre = pd.read_parquet(path_cache)
        else:
            pre = precompute_signal_paths(sigs, feat)
            pre.to_parquet(path_cache)
        print(f"  executable: {len(pre)}")
        res = run_family_gate(spec, pre, feat)
        results.append(res)
        summary.append(summary_row(res))
        (CHECKPOINTS / f"14_family_{spec.code}_result.json").write_text(json.dumps(res, indent=2, default=str))
        print(f"  verdict: {res['verdict']}")

        _append_ledger(
            {
                "experiment_id": f"RAND_GATE_{spec.code}",
                "family": spec.code,
                "hypothesis": f"randomized direction control {spec.name}",
                "parameters": "100 seeds, developing value, frozen T+1 entry",
                "train_result": str(res.get("splits", {}).get("TRAIN", {})),
                "validation_result": str(res.get("splits", {}).get("VALIDATION", {})),
                "decision": res["verdict"],
                "reason": f"fp21 delta={res.get('fp21_stats', {}).get('real_minus_mean', '')}",
            }
        )

    _write_reports(results, summary)

    survivors = [r["family"] for r in results if r.get("passes_random_gate")]
    checkpoint = {
        "checkpoint_14": "PASS" if survivors else "FAIL",
        "survivors": survivors,
        "rejected": [r["family"] for r in results if r.get("verdict") == "NO_DIRECTIONAL_INFORMATION"],
        "inverse": [r["family"] for r in results if r.get("verdict") == "INVERSE_INFORMATION"],
        "all_failed": len(survivors) == 0,
    }
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / "14_randomized_controls.json").write_text(json.dumps(checkpoint, indent=2))
    manifest_path = CHECKPOINTS / "CHECKPOINT_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"phase": 76, "checkpoints": {}}
    manifest.setdefault("checkpoints", {})["14_randomized_controls"] = checkpoint["checkpoint_14"]
    manifest["random_gate_survivors"] = survivors
    manifest["verdict"] = "CONTINUE" if survivors else "PHASE76_NO_AUCTION_INFORMATION_PENDING_SR"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print("\n=== SUMMARY ===")
    for s in summary:
        print(
            f"  {s['family']} n={s['n']} real+2/-1={s.get('real_fp21', float('nan')):.3f} "
            f"rand={s.get('rand_fp21_mean', float('nan')):.3f} verdict={s.get('verdict')}"
        )
    print(f"\nReports: {REPORTS / 'PHASE76_RANDOMIZED_CONTROLS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
