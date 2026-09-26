"""Document data-extension stop + unmatched label audit. No fitting."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from cdx_research.python.match import load_labels
from phase58j.research.lw_data import load_market_1m_lw

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "2026-09-21_data_alignment"
ET = ZoneInfo("America/New_York")


def main() -> None:
    RUN.mkdir(parents=True, exist_ok=True)
    labels = load_labels()
    m1 = load_market_1m_lw()
    last_et = m1.index.max().tz_convert(ET)
    last_utc = m1.index.max().tz_convert(timezone.utc)

    rows = []
    for i, rec in enumerate(labels.itertuples(index=False), start=1):
        ts = rec.signal_time_et
        if ts.tzinfo is None:
            ts = ts.tz_localize(ET)
        else:
            ts = ts.tz_convert(ET)
        ts = ts.replace(second=0, microsecond=0)
        delta = (ts - last_et).total_seconds() / 60.0
        rows.append(
            {
                "label_id": f"L{i:03d}",
                "screenshot_id": rec.screenshot_id,
                "direction": rec.direction,
                "original_time_et": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "confidence": rec.timestamp_confidence,
                "matched_time_et": "",
                "timestamp_delta_minutes": "",
                "exact_match": False,
                "ohlcv_available": False,
                "match_status": "UNMATCHED",
                "notes": (
                    f"label_et={ts.isoformat()} last_ohlcv_et={last_et.isoformat()} "
                    f"label_is_{delta:.0f}min_after_data_end"
                ),
            }
        )
    audit = pd.DataFrame(rows)
    audit_path = ROOT / "parity" / "label_match_audit.csv"
    audit.to_csv(audit_path, index=False)
    audit.to_csv(RUN / "label_match_audit.csv", index=False)

    med = audit[audit["confidence"] == "MEDIUM"]
    empty_cols = [
        "label_id",
        "screenshot_id",
        "direction",
        "original_time_et",
        "matched_time_et",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "match_status",
    ]
    pd.DataFrame(columns=empty_cols).to_csv(ROOT / "parity" / "matched_medium_labels.csv", index=False)
    pd.DataFrame(columns=empty_cols).to_csv(RUN / "matched_medium_labels.csv", index=False)

    summary = {
        "prior_verdict": "CDX_RE_INSUFFICIENT_INFORMATION",
        "this_run_verdict": "CDX_RE_DATA_EXTENSION_FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows_before": int(len(m1)),
        "rows_after": int(len(m1)),
        "old_data_end_ct": str(m1.index.max()),
        "old_data_end_et": str(last_et),
        "old_data_end_utc": str(last_utc),
        "new_data_end": str(m1.index.max()),
        "medium_labels": int((labels.timestamp_confidence == "MEDIUM").sum()),
        "medium_exact": 0,
        "medium_pm1": 0,
        "medium_unmatched": int((med.match_status == "UNMATCHED").sum()),
        "low_used_for_strict_parity": False,
        "reason": "DATABENTO_API_KEY not available on this machine; no compatible NQ.v.0 bars after 2026-09-02",
    }
    (RUN / "run_summary.json").write_text(json.dumps(summary, indent=2))
    print("wrote", audit_path, "medium_unmatched", summary["medium_unmatched"])


if __name__ == "__main__":
    main()
