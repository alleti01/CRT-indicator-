#!/usr/bin/env python3
"""Phase68 — programmatic data availability audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "phase68" / "reports"
CHECKPOINTS = ROOT / "phase68" / "checkpoints"


def _inspect_csv(path: Path, nrows: int = 3) -> dict:
    df = pd.read_csv(path, nrows=nrows)
    cols = {c.lower() for c in df.columns}
    has_ohlc = {"open", "high", "low", "close"}.issubset(cols)
    has_trade = ("price" in cols and "size" in cols and ("timestamp" in cols or "ts_event" in cols))
    has_aggressor = "side" in cols or "aggressor" in cols
    has_quote = bool(cols & {"bid_px", "ask_px", "bid", "ask", "bid_size", "ask_size"})
    level = 0
    if has_ohlc:
        level = 0
    if has_trade:
        level = max(level, 1)
    if has_trade and has_quote:
        level = 2
    if has_quote and any("depth" in c or "level" in c for c in cols):
        level = max(level, 3)
    return {
        "path": str(path.relative_to(ROOT)),
        "size_mb": round(path.stat().st_size / 1e6, 2),
        "columns": list(df.columns),
        "level": level,
        "has_ohlc": has_ohlc,
        "has_trades": has_trade,
        "has_aggressor": has_aggressor,
        "has_quotes": has_quote,
        "causal": "YES if event timestamps; OHLC bars are causal at bar close",
    }


def _date_range_csv(path: Path) -> tuple[str, str, int]:
    try:
        df = pd.read_csv(path, usecols=[pd.read_csv(path, nrows=0).columns[0]], parse_dates=[0])
        col = df.columns[0]
        return str(df[col].min()), str(df[col].max()), len(df)
    except Exception:
        return "unknown", "unknown", -1


def run_audit() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    key_paths = [
        ROOT / "phase27/data/raw/nq_trades_pilot_202401.csv",
        ROOT / "phase16/data/raw/nq_continuous_1m_20231201_20260626.csv",
        ROOT / "phase18/data/raw/nq_continuous_1m_raw.csv",
        ROOT / "phase16/data/raw/nq_continuous_1m_oos_20171001_20201201.csv",
        ROOT / "phase49/data/forward/nq_continuous_1m_forward.csv",
        ROOT / "phase58j/data/nq_continuous_1m_lw_extension.csv",
    ]

    datasets = []
    for p in key_paths:
        if p.exists():
            meta = _inspect_csv(p)
            start, end, n = _date_range_csv(p)
            meta.update({"start": start, "end": end, "rows_est": n})
            datasets.append(meta)

    # classify project-wide max level
    max_level = max((d["level"] for d in datasets), default=0)
    trades_full = [d for d in datasets if d.get("has_trades")]
    ohlc_full = [d for d in datasets if d.get("has_ohlc") and not d.get("has_trades")]

    # Primary research stack
    from phase58j.research.lw_data import load_market_1m_lw
    m1 = load_market_1m_lw()
    primary = {
        "bars": len(m1),
        "start": str(m1.index.min()),
        "end": str(m1.index.max()),
        "level": 0,
        "fields": list(m1.columns),
    }

    pilot = next((d for d in datasets if "trades_pilot" in d["path"]), None)
    data_blocked_full = max_level < 1 or not pilot
    can_pilot = pilot is not None and pilot.get("has_aggressor")

    result = {
        "primary_nq_1m": primary,
        "datasets": datasets,
        "max_level_available": max_level,
        "full_history_microstructure_level": 0,
        "pilot_microstructure_level": 1 if can_pilot else 0,
        "pilot_range": f"{pilot['start']} → {pilot['end']}" if pilot else None,
        "data_blocked_full_history": True,
        "data_blocked_microstructure": not can_pilot,
        "recommendation": (
            "Purchase Databento GLBX.MDP3 `trades` schema for full NQ history (~$10/mo per month) "
            "to run Phase68 on full sample. Optional `mbp-1` (~$18/mo) for Families D/E quote features."
            if can_pilot else
            "Acquire Databento trades + optional mbp-1 before any microstructure research."
        ),
        "ohlc_only_years": "~2017-2026 (3.1M bars)",
        "trades_pilot_months": 1 if can_pilot else 0,
    }

    (CHECKPOINTS / "00_data_inventory.json").write_text(json.dumps(result, indent=2, default=str))
    write_md(result)
    return result


def write_md(r: dict) -> Path:
    out = REPORTS / "PHASE68_DATA_AVAILABILITY_AUDIT.md"
    lines = [
        "PHASE68 — DATA AVAILABILITY AUDIT",
        "=================================",
        "",
        f"**Primary NQ 1M stack:** LEVEL 0 (OHLCV) — {r['primary_nq_1m']['bars']:,} bars",
        f"  Range: {r['primary_nq_1m']['start']} → {r['primary_nq_1m']['end']}",
        f"  Fields: {', '.join(r['primary_nq_1m']['fields'])}",
        "",
        f"**Full-history microstructure:** LEVEL {r['full_history_microstructure_level']} — **DATA BLOCKED**",
        f"**Pilot microstructure (Phase27):** LEVEL {r['pilot_microstructure_level']} — {r.get('pilot_range', 'N/A')}",
        "",
        "## Hard data gate",
        "",
        f"- Full-history Phase68: **{'STOP — DATA_BLOCKED_MICROSTRUCTURE' if r['data_blocked_full_history'] else 'PROCEED'}**",
        f"- Pilot-only Phase68: **{'PROCEED (1 month trades)' if not r['data_blocked_microstructure'] else 'STOP'}**",
        "",
        "## Candidate datasets",
        "",
    ]
    for d in r["datasets"]:
        lines.extend([
            f"### `{d['path']}`",
            f"- Size: {d['size_mb']} MB",
            f"- Level hint: {d['level']}",
            f"- Range: {d.get('start', '?')} → {d.get('end', '?')}",
            f"- Trades: {d.get('has_trades')} | Aggressor: {d.get('has_aggressor')} | Quotes: {d.get('has_quotes')}",
            f"- Columns: `{', '.join(d['columns'][:12])}{'...' if len(d['columns'])>12 else ''}`",
            "",
        ])
    lines.extend([
        "## Required data to unblock full Phase68",
        "",
        r["recommendation"],
        "",
        "| Schema | Est. cost | Enables |",
        "|--------|-----------|---------|",
        "| `trades` (GLBX.MDP3) | ~$10/mo | P1–P10, Families A/B/C/F/G/H |",
        "| `mbp-1` | ~$18/mo | Q1–Q8, Families D/E |",
        "| `mbp-10` / `mbo` | higher | D1–D5 depth features |",
        "",
    ])
    out.write_text("\n".join(lines))
    return out


if __name__ == "__main__":
    r = run_audit()
    print(REPORTS / "PHASE68_DATA_AVAILABILITY_AUDIT.md")
