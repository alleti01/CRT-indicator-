"""Aggregate ledger rows by blocking / enabling gates."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from signal_ledger.config import GATE_NAMES
from signal_ledger.gate_evaluator import blocking_gates_for_direction


def _parse_gate_state(s: str) -> dict[str, bool]:
    return json.loads(s)


def _best_direction(row: pd.Series) -> str:
    hl = float(row["hyp_long_R"]) if pd.notna(row["hyp_long_R"]) else -999
    hs = float(row["hyp_short_R"]) if pd.notna(row["hyp_short_R"]) else -999
    return "long" if hl >= hs else "short"


def aggregate_gates(ledger: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (missed_reversal_table, false_positive_table).
    Each table: gate_name, count, fraction_of_class.
    """
    missed = ledger[ledger["classification"] == "missed_reversal"]
    false_pos = ledger[ledger["classification"] == "false_positive"]

    mr_counts: dict[str, int] = {g: 0 for g in GATE_NAMES}
    for _, row in missed.iterrows():
        gs = _parse_gate_state(row["gate_state"])
        direction = _best_direction(row)
        for g in blocking_gates_for_direction(gs, direction):
            if g in mr_counts:
                mr_counts[g] += 1

    fp_counts: dict[str, int] = {g: 0 for g in GATE_NAMES}
    for _, row in false_pos.iterrows():
        gs = _parse_gate_state(row["gate_state"])
        direction = row.get("direction_fired") or _best_direction(row)
        side = str(direction).lower()
        for g in GATE_NAMES:
            if g.endswith(f"_{side}") or g in ("gate_open", "not_in_cooldown"):
                if gs.get(g, False):
                    fp_counts[g] += 1

    n_mr = max(len(missed), 1)
    n_fp = max(len(false_pos), 1)

    mr_df = pd.DataFrame(
        [{"gate": g, "count": c, "fraction_of_missed_reversal": c / len(missed) if len(missed) else 0.0} for g, c in mr_counts.items() if c > 0]
    ).sort_values("count", ascending=False)

    fp_df = pd.DataFrame(
        [{"gate": g, "count": c, "fraction_of_false_positive": c / len(false_pos) if len(false_pos) else 0.0} for g, c in fp_counts.items() if c > 0]
    ).sort_values("count", ascending=False)

    if mr_df.empty:
        mr_df = pd.DataFrame(columns=["gate", "count", "fraction_of_missed_reversal"])
    if fp_df.empty:
        fp_df = pd.DataFrame(columns=["gate", "count", "fraction_of_false_positive"])

    return mr_df, fp_df


TRUST_WARNING = (
    "WARNING: Ledger gate rankings are PENDING_REPLAY_CONFIRMATION until "
    "manual TradingView bar-replay checklist (Phase 2 item 3) is completed."
)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Rank gates from a built signal quality ledger")
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--out-missed", type=Path, default=Path("signal_ledger/output/gates_missed_reversal.csv"))
    p.add_argument("--out-fp", type=Path, default=Path("signal_ledger/output/gates_false_positive.csv"))
    args = p.parse_args(argv)

    if args.ledger.suffix == ".parquet":
        df = pd.read_parquet(args.ledger)
    else:
        df = pd.read_csv(args.ledger)

    if "trust_status" in df.columns and (df["trust_status"] == "PENDING_REPLAY_CONFIRMATION").any():
        print(TRUST_WARNING)

    mr, fp = aggregate_gates(df)
    args.out_missed.parent.mkdir(parents=True, exist_ok=True)
    mr.to_csv(args.out_missed, index=False)
    fp.to_csv(args.out_fp, index=False)
    print(f"Missed-reversal gates → {args.out_missed} ({len(mr)} rows)")
    print(f"False-positive gates → {args.out_fp} ({len(fp)} rows)")
    print("NOT FINAL — pending TV bar-replay confirmation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
