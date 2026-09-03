"""Shadow recomputation audit — compare replay vs append-only logs."""

from __future__ import annotations

import pandas as pd

from phase56.config import LOGS
from phase56.forward.metrics import events_df, signals_df, trades_df
from phase56.forward.logs import AppendOnlyLog, AUDIT_FIELDS


def audit_log_integrity() -> dict:
    """Verify append-only logs are internally consistent."""
    ev = events_df()
    sig = signals_df()
    tr = trades_df()
    issues = []
    if not sig.empty:
        missing = set(sig["initiating_event_id"]) - set(ev["event_id"])
        if missing:
            issues.append(f"signals_missing_events:{len(missing)}")
    if not tr.empty and not sig.empty:
        missing_sig = set(tr["signal_id"]) - set(sig["signal_id"])
        if missing_sig:
            issues.append(f"trades_missing_signals:{len(missing_sig)}")
    d10_new = ev.loc[ev["D10_pass"].astype(str).str.lower().eq("true") & ev["episode_status"].eq("NEW_EPISODE")] if not ev.empty else ev
    if not sig.empty and len(d10_new) != len(sig):
        issues.append(f"episode_count_mismatch:d10_new={len(d10_new)} signals={len(sig)}")
    return {
        "events": len(ev),
        "signals": len(sig),
        "trades": len(tr),
        "issues": issues,
        "pass": len(issues) == 0,
    }


def write_audit_record(detail: str, model_hash: str) -> None:
    log = AppendOnlyLog(LOGS / "audit_log.csv", AUDIT_FIELDS)
    log.append(
        {
            "timestamp_ct": pd.Timestamp.now(tz="America/Chicago"),
            "audit_type": "INTEGRITY",
            "detail": detail,
            "model_hash": model_hash,
        }
    )
