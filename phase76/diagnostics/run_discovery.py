#!/usr/bin/env python3
"""Phase76 discovery pipeline — checkpoints 00–03 + family A path preview."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase76.python.auction_engine import build_auction_features  # noqa: E402
from phase76.python.config import CHECKPOINTS, REPORTS  # noqa: E402
from phase76.python.data_loader import load_nq_1m  # noqa: E402
from phase76.python.market_states import classify_auction_states  # noqa: E402
from phase76.python.path_audit import path_audit, path_summary  # noqa: E402
from phase76.python.signals import (  # noqa: E402
    family_a_upper_rejection,
    family_b_lower_rejection,
)

EXPERIMENT_LEDGER = REPORTS / "EXPERIMENT_LEDGER.csv"


def _append_ledger(row: dict) -> None:
    import csv

    EXPERIMENT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    write_header = not EXPERIMENT_LEDGER.exists()
    with EXPERIMENT_LEDGER.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            w.writeheader()
        w.writerow(row)


def main() -> int:
    if not (CHECKPOINTS / "02_causality_audit.json").exists():
        print("Run run_causality_audit.py first.")
        return 2

    causality = json.loads((CHECKPOINTS / "02_causality_audit.json").read_text())
    if causality["verdict"] != "CAUSALITY_PASS":
        print("CAUSALITY_FAIL — stop.")
        return 2

    print("Loading data + building auction features...")
    df = load_nq_1m()
    feat = build_auction_features(df)
    feat["auction_state"] = classify_auction_states(feat, value_source="developing")

    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / "01_profile_engine.json").write_text(
        json.dumps({"checkpoint_01": "PASS", "bars": len(feat), "profile_type": feat["profile_type"].iloc[0]}, indent=2)
    )
    (CHECKPOINTS / "03_market_states.json").write_text(
        json.dumps(
            {
                "checkpoint_03": "PASS",
                "state_counts": feat["auction_state"].value_counts().head(15).to_dict(),
            },
            indent=2,
        )
    )

    # Family A/B developing — path preview on full sample (information only, not final verdict)
    results = {}
    for name, fn, vs in [
        ("A_dev", lambda f: family_a_upper_rejection(f, value_source="developing"), "developing"),
        ("A_prior", lambda f: family_a_upper_rejection(f, value_source="prior"), "prior"),
        ("B_dev", lambda f: family_b_lower_rejection(f, value_source="developing"), "developing"),
        ("B_prior", lambda f: family_b_lower_rejection(f, value_source="prior"), "prior"),
    ]:
        sigs = fn(feat)
        if not sigs.empty and "entry_ts" in sigs.columns:
            sigs = sigs.dropna(subset=["entry_ts"])
            sigs["atr"] = [feat.loc[t, "atr"] if t in feat.index else None for t in sigs["signal_ts"]]
            pathed = path_audit(sigs, feat)
            results[name] = path_summary(pathed)
            pathed.head(500).to_csv(REPORTS / f"phase76_preview_{name}.csv", index=False)
        else:
            results[name] = {"n": 0}
        _append_ledger(
            {
                "experiment_id": f"PREVIEW_{name}",
                "family": name[0],
                "hypothesis": f"upper/lower rejection {vs}",
                "parameters": "fixed preregistered",
                "train_result": str(results[name]),
                "validation_result": "NOT_RUN",
                "decision": "CONTINUE",
                "reason": "path preview only",
            }
        )

    preview_md = [
        "# Phase76 — Discovery Preview (Checkpoint 04–05 path audit sample)",
        "",
        "Full randomized controls and WF splits not run in this preview.",
        "",
        "| Config | Signals | MFE 15m | MAE 15m | Asym 15m |",
        "|--------|---------|---------|---------|----------|",
    ]
    for k, v in results.items():
        preview_md.append(
            f"| {k} | {v.get('n', 0)} | {v.get('mfe_15m_mean', '—')} | {v.get('mae_15m_mean', '—')} | {v.get('asym_15m', '—')} |"
        )
    (REPORTS / "PHASE76_DISCOVERY_PREVIEW.md").write_text("\n".join(preview_md) + "\n")
    print(json.dumps(results, indent=2))
    print(f"Preview: {REPORTS / 'PHASE76_DISCOVERY_PREVIEW.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
