"""Build per-bar signal quality ledger (offline batch) from Pine-native gate exports."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from phase58j.research.lw_data import load_markets_lw
from signal_ledger.config import GATE_NAMES, LedgerConfig
from signal_ledger.gate_evaluator import (
    blocking_gates_for_direction,
    gate_state_detail_from_export_row,
    gate_state_from_export_row,
)
from signal_ledger.gate_export import load_tv_gate_export
from signal_ledger.hypothetical_outcomes import hyp_m0_both
from signal_ledger.signal_loader import load_signal_log

Classification = str  # correct_take | false_positive | missed_reversal | correct_pass

TRUST_LABEL = "PENDING_REPLAY_CONFIRMATION"


def classify_row(
    signal_fired: bool,
    direction_fired: str | None,
    hyp_long_r: float,
    hyp_short_r: float,
    threshold_r: float,
) -> Classification:
    if signal_fired and direction_fired:
        outcome = hyp_long_r if direction_fired == "long" else hyp_short_r
        if np.isfinite(outcome) and outcome > 0:
            return "correct_take"
        return "false_positive"
    best = max(
        hyp_long_r if np.isfinite(hyp_long_r) else -999,
        hyp_short_r if np.isfinite(hyp_short_r) else -999,
    )
    if best >= threshold_r:
        return "missed_reversal"
    return "correct_pass"


def _atr_sma_range(hi: np.ndarray, lo: np.ndarray, period: int = 14) -> np.ndarray:
    tr = np.maximum(hi - lo, np.maximum(np.abs(hi - np.roll(hi, 1)), np.abs(lo - np.roll(lo, 1))))
    tr[0] = hi[0] - lo[0]
    out = np.full_like(tr, np.nan)
    for i in range(period - 1, len(tr)):
        out[i] = tr[i - period + 1 : i + 1].mean()
    return out


def build_ledger(cfg: LedgerConfig, gate_export_path: Path) -> pd.DataFrame:
    """
    Produce one row per bar present in the Pine GLD export within [cfg.start, cfg.end].

    Gate states come exclusively from TradingView data-window export (Part A).
    Output is labeled PENDING_REPLAY_CONFIRMATION until manual TV bar-replay checklist passes.
    """
    gates = load_tv_gate_export(gate_export_path)
    start = pd.Timestamp(cfg.start, tz="UTC")
    end = pd.Timestamp(cfg.end, tz="UTC")
    gates = gates[(gates["bar_time_utc"] >= start) & (gates["bar_time_utc"] <= end)].copy()
    if gates.empty:
        raise ValueError(f"No gate export rows in range {cfg.start} .. {cfg.end}")

    m1, _, _ = load_markets_lw()
    m1_utc = m1.copy()
    if m1_utc.index.tz is None:
        m1_utc.index = m1_utc.index.tz_localize("America/Chicago").tz_convert("UTC")
    else:
        m1_utc.index = m1_utc.index.tz_convert("UTC")

    fired = load_signal_log(cfg.signal_log_paths)

    rows = []
    for _, grow in gates.iterrows():
        bar_time = pd.Timestamp(grow["bar_time_utc"]).tz_convert("UTC")
        bar_key = bar_time.floor("min")

        # Align to local 1M OHLC for hyp_R (Chicago index floored to minute, converted UTC)
        loc_mask = m1_utc.index.floor("min") == bar_key
        if not loc_mask.any():
            continue
        bi = int(np.where(loc_mask)[0][0])
        if bi < 1 or bi >= len(m1) - 62:
            continue

        hi = m1["high"].values.astype(float)
        lo = m1["low"].values.astype(float)
        cl = m1["close"].values.astype(float)
        op = m1["open"].values.astype(float)
        atr = _atr_sma_range(hi, lo)
        signal_i = bi - 1  # signal evaluated at prior bar close convention if export is bar close time
        # Export bar_time is bar open time in TV; signal at T uses bar index bi-1 for T+1 entry from T
        # GLD export at bar close of bar bi → signal bar index = bi when take_* fires on that bar
        if bool(grow.get("take_long", False)) or bool(grow.get("take_short", False)):
            signal_i = bi

        log_sig = fired.get(bar_key)
        if log_sig is not None:
            signal_fired = True
            direction_fired = log_sig.direction
            event_id = log_sig.event_id
        else:
            signal_fired = bool(grow.get("take_long", False) or grow.get("take_short", False))
            direction_fired = "long" if grow.get("take_long", False) else ("short" if grow.get("take_short", False) else None)
            event_id = None

        gs = gate_state_from_export_row(grow)
        detail = gate_state_detail_from_export_row(grow)
        blocked = (
            blocking_gates_for_direction(gs, direction_fired, detail=detail)
            if direction_fired
            else []
        )
        hl, hs = hyp_m0_both(hi, lo, cl, op, atr, signal_i)
        cls = classify_row(signal_fired, direction_fired, hl, hs, cfg.missed_reversal_threshold_r)

        rows.append(
            {
                "bar_time_utc": bar_time.isoformat(),
                "signal_fired": signal_fired,
                "direction_fired": direction_fired,
                "event_id": event_id,
                "gate_state": json.dumps(gs),
                "gate_state_detail": json.dumps(detail),
                "blocking_gates": json.dumps(blocked),
                "evidence_threshold_long_state": detail["evidence_threshold_long_state"],
                "evidence_threshold_short_state": detail["evidence_threshold_short_state"],
                "arm_total_long_state": detail["arm_total_long_state"],
                "arm_total_short_state": detail["arm_total_short_state"],
                "hyp_long_R": hl,
                "hyp_short_R": hs,
                "classification": cls,
                "trust_status": TRUST_LABEL,
                "gate_source": "pine_gld_export",
            }
        )

    df = pd.DataFrame(rows)
    cfg.output_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg.output_path.suffix == ".parquet":
        df.to_parquet(cfg.output_path, index=False)
    else:
        df.to_csv(cfg.output_path, index=False)
    return df


def classification_counts(df: pd.DataFrame) -> dict[str, int]:
    return df["classification"].value_counts().to_dict()


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Build signal quality ledger from Pine GLD export")
    p.add_argument("--start", required=True, help="UTC start date YYYY-MM-DD")
    p.add_argument("--end", required=True, help="UTC end date YYYY-MM-DD")
    p.add_argument("--gate-export", type=Path, required=True, help="TradingView chart CSV with GLD_* plots")
    p.add_argument("--output", type=Path, default=Path("signal_ledger/output/signal_quality_ledger.parquet"))
    p.add_argument("--threshold-r", type=float, default=1.5, help="Missed-reversal M0 R threshold")
    p.add_argument(
        "--signals",
        type=Path,
        nargs="*",
        default=[],
        help="Phase72A signal jsonl paths with gate_state in payload",
    )
    args = p.parse_args(argv)
    cfg = LedgerConfig(
        start=args.start,
        end=args.end,
        output_path=args.output,
        missed_reversal_threshold_r=args.threshold_r,
        signal_log_paths=list(args.signals),
    )
    df = build_ledger(cfg, args.gate_export)
    counts = classification_counts(df)
    print(f"Wrote {len(df)} rows → {cfg.output_path}")
    print(f"trust_status={TRUST_LABEL} (all rows)")
    print(f"classification_counts={counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
