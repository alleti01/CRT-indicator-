"""Align CDX screenshot labels to a recovered 1-minute series."""
from __future__ import annotations

from typing import Any

import pandas as pd

from cdx_research.python.match import load_labels
from cdx_research.python.tzutil import ET, minute_floor_et

AUDIT_COLS = [
    "label_id",
    "screenshot_id",
    "direction",
    "confidence",
    "original_time_et",
    "matched_time_et",
    "delta_minutes",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "match_status",
    "notes",
]


def _bar_at(m1_et: pd.DataFrame, ts: pd.Timestamp) -> pd.Series | None:
    if ts in m1_et.index:
        row = m1_et.loc[ts]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        return row
    return None


def _fill_ohlcv(out: dict[str, Any], bar: pd.Series | None) -> None:
    if bar is None:
        out.update(open="", high="", low="", close="", volume="")
        return
    out["open"] = float(bar["open"])
    out["high"] = float(bar["high"])
    out["low"] = float(bar["low"])
    out["close"] = float(bar["close"])
    out["volume"] = float(bar["volume"]) if "volume" in bar.index and pd.notna(bar["volume"]) else ""


def align_labels(
    labels: pd.DataFrame,
    m1: pd.DataFrame,
    *,
    source: str,
) -> pd.DataFrame:
    """Match labels through America/New_York. m1 index must be tz-aware."""
    if m1.index.tz is None:
        raise ValueError("m1 index must be timezone-aware")
    m1_et = m1.copy()
    m1_et.index = m1.index.tz_convert(ET)
    data_min = m1_et.index.min()
    data_max = m1_et.index.max()
    rows: list[dict[str, Any]] = []

    for i, rec in enumerate(labels.itertuples(index=False), start=1):
        ts = minute_floor_et(pd.Timestamp(rec.signal_time_et))
        conf = str(rec.timestamp_confidence).upper()
        exact = _bar_at(m1_et, ts)
        minus = _bar_at(m1_et, ts - pd.Timedelta(minutes=1))
        plus = _bar_at(m1_et, ts + pd.Timedelta(minutes=1))
        in_range = bool(data_min <= ts <= data_max) if len(m1_et) else False

        out: dict[str, Any] = {
            "label_id": f"L{i:03d}",
            "screenshot_id": rec.screenshot_id,
            "direction": rec.direction,
            "confidence": conf,
            "original_time_et": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "matched_time_et": "",
            "delta_minutes": "",
            "source": source,
            "match_status": "UNMATCHED",
            "notes": "",
        }
        _fill_ohlcv(out, None)

        if conf == "LOW":
            # Broad contextual only — never used for the 7/10 strict gate.
            ctx = exact if exact is not None else minus if minus is not None else plus
            if ctx is not None:
                chosen_ts = ts if exact is not None else (ts - pd.Timedelta(minutes=1) if minus is not None else ts + pd.Timedelta(minutes=1))
                delta = int((chosen_ts - ts).total_seconds() // 60)
                out["match_status"] = "CONTEXT_ONLY"
                out["matched_time_et"] = chosen_ts.strftime("%Y-%m-%d %H:%M:%S")
                out["delta_minutes"] = delta
                _fill_ohlcv(out, ctx)
                out["notes"] = "LOW confidence; contextual bar only; excluded from strict parity"
            else:
                out["notes"] = (
                    f"LOW unmatched; in_range={in_range} data_et={data_min}..{data_max}"
                    if len(m1_et)
                    else "LOW unmatched; no recovered 1m series"
                )
            rows.append(out)
            continue

        if exact is not None:
            out["match_status"] = "EXACT"
            out["matched_time_et"] = ts.strftime("%Y-%m-%d %H:%M:%S")
            out["delta_minutes"] = 0
            _fill_ohlcv(out, exact)
            out["notes"] = "exact minute"
        elif minus is not None and plus is not None:
            # Both neighbors exist — do not guess.
            out["match_status"] = "AMBIGUOUS"
            out["notes"] = "both T-1 and T+1 exist; no exact bar; not counted as aligned"
        elif minus is not None or plus is not None:
            chosen = minus if minus is not None else plus  # one neighbor only; both-neighbor case handled above
            chosen_ts = ts - pd.Timedelta(minutes=1) if minus is not None else ts + pd.Timedelta(minutes=1)
            delta = int((chosen_ts - ts).total_seconds() // 60)
            out["match_status"] = "PLUS_MINUS_1"
            out["matched_time_et"] = chosen_ts.strftime("%Y-%m-%d %H:%M:%S")
            out["delta_minutes"] = delta
            _fill_ohlcv(out, chosen)
            out["notes"] = "MEDIUM timestamp ambiguity; single ±1 neighbor used"
        else:
            out["notes"] = (
                f"no exact or ±1 bar; in_range={in_range} data_et={data_min}..{data_max}"
                if len(m1_et)
                else "no recovered 1m series"
            )
        rows.append(out)

    return pd.DataFrame(rows, columns=AUDIT_COLS)


def medium_gate(audit: pd.DataFrame) -> dict[str, Any]:
    med = audit[audit["confidence"] == "MEDIUM"]
    exact = int((med["match_status"] == "EXACT").sum())
    pm1 = int((med["match_status"] == "PLUS_MINUS_1").sum())
    amb = int((med["match_status"] == "AMBIGUOUS").sum())
    unmatched = int((med["match_status"] == "UNMATCHED").sum())
    aligned = exact + pm1
    passed = aligned >= 7
    return {
        "medium_labels": int(len(med)),
        "exact": exact,
        "plus_minus_1": pm1,
        "ambiguous": amb,
        "unmatched": unmatched,
        "aligned": aligned,
        "gate_pass": passed,
        "long_matched": int(((med["direction"] == "LONG") & med["match_status"].isin(["EXACT", "PLUS_MINUS_1"])).sum()),
        "short_matched": int(((med["direction"] == "SHORT") & med["match_status"].isin(["EXACT", "PLUS_MINUS_1"])).sum()),
    }


def matched_medium_frame(audit: pd.DataFrame) -> pd.DataFrame:
    med = audit[audit["confidence"] == "MEDIUM"]
    return med[med["match_status"].isin(["EXACT", "PLUS_MINUS_1"])].copy()
