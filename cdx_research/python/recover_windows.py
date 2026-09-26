"""Windows/Mac CDX data recovery: Path A Databento, else isolated NinjaTrader.

Never merges NT into phase58j. Never prints API keys. Never retunes V1.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CDX = ROOT / "cdx_research"
RUN = CDX / "runs" / "2026-09-21_windows_recovery"
DATA = CDX / "data"
PARITY = CDX / "parity"
REPORTS = CDX / "reports"
EXT_OLD = ROOT / "phase58j" / "data" / "nq_continuous_1m_lw_extension.csv"
NT_NAME = "nq_1m_ninjatrader_sep6_sep21.csv"

sys.path.insert(0, str(ROOT))

from cdx_research.python.align_labels import align_labels, matched_medium_frame, medium_gate
from cdx_research.python.match import load_labels
from cdx_research.python.tzutil import ET, UTC, iana_from_chart_tz, to_et, to_utc


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def key_present() -> bool:
    return bool(os.environ.get("DATABENTO_API_KEY", "").strip())


def databento_auth() -> str:
    if not key_present():
        return "NOT_ATTEMPTED"
    try:
        import databento as db

        client = db.Historical(os.environ["DATABENTO_API_KEY"])
        client.metadata.list_publishers()
        return "PASS"
    except Exception as exc:
        print("DATABENTO_AUTH_FAIL", type(exc).__name__)
        return "FAIL"


def find_nt_csv() -> Path | None:
    home = Path.home()
    candidates = [
        DATA / NT_NAME,
        home / "Documents" / "NinjaTrader 8" / "cdx_export" / NT_NAME,
        home / "OneDrive" / "Documents" / "NinjaTrader 8" / "cdx_export" / NT_NAME,
        Path(os.environ.get("USERPROFILE", "")) / "Documents" / "NinjaTrader 8" / "cdx_export" / NT_NAME,
        Path(os.environ.get("USERPROFILE", "")) / "OneDrive" / "Documents" / "NinjaTrader 8" / "cdx_export" / NT_NAME,
    ]
    for p in candidates:
        if p and p.exists() and p.stat().st_size > 200:
            return p
    return None


def load_nt_series(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    raw.columns = [c.strip().lower() for c in raw.columns]
    if "source" in raw.columns and (raw["source"].astype(str).str.upper() == "DATABENTO").any():
        raise RuntimeError("refusing NT loader on a file labeled DATABENTO")
    if "timestamp_utc" in raw.columns:
        utc = to_utc(raw["timestamp_utc"], "UTC")
        chart_tz = "UTC"
    elif "timestamp_et" in raw.columns:
        utc = to_utc(raw["timestamp_et"], "America/New_York")
        chart_tz = "America/New_York"
    elif "timestamp" in raw.columns:
        chart_tz = iana_from_chart_tz(raw["chart_timezone"].iloc[0] if "chart_timezone" in raw.columns else "America/New_York")
        utc = to_utc(raw["timestamp"], chart_tz)
    else:
        raise RuntimeError(f"NT csv missing timestamp columns: {list(raw.columns)}")

    df = pd.DataFrame(
        {
            "open": pd.to_numeric(raw["open"], errors="coerce"),
            "high": pd.to_numeric(raw["high"], errors="coerce"),
            "low": pd.to_numeric(raw["low"], errors="coerce"),
            "close": pd.to_numeric(raw["close"], errors="coerce"),
            "volume": pd.to_numeric(raw["volume"], errors="coerce") if "volume" in raw.columns else 0,
        },
        index=utc,
    )
    df.index.name = "timestamp_utc"
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df["source"] = "NINJATRADER"
    df["timestamp_et"] = to_et(df.index)
    if (df["high"] < df["low"]).any():
        raise RuntimeError("NT csv has high < low")
    return df


def load_databento_extension(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    utc = to_utc(raw["timestamp"], "UTC")
    df = pd.DataFrame(
        {
            "open": pd.to_numeric(raw["open"], errors="coerce"),
            "high": pd.to_numeric(raw["high"], errors="coerce"),
            "low": pd.to_numeric(raw["low"], errors="coerce"),
            "close": pd.to_numeric(raw["close"], errors="coerce"),
            "volume": pd.to_numeric(raw["volume"], errors="coerce"),
        },
        index=utc,
    )
    df.index.name = "timestamp_utc"
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df["source"] = "DATABENTO"
    df["timestamp_et"] = to_et(df.index)
    return df


def continuity_audit(old_raw: pd.DataFrame, new_df: pd.DataFrame) -> dict[str, Any]:
    old_ts = pd.to_datetime(old_raw["timestamp"], utc=True)
    old_last = old_ts.max()
    new_first = new_df.index.min()
    gap = (new_first - old_last).total_seconds()
    old_tail = old_raw.assign(_ts=old_ts).sort_values("_ts").tail(100)
    new_head = new_df.sort_index().head(100)
    last_close = float(old_tail.iloc[-1]["close"])
    first_open = float(new_head.iloc[0]["open"])
    jump = first_open - last_close
    dups = int(new_df.index.duplicated().sum())
    backward = bool(new_df.index.min() < old_last)
    ok = (not backward) and dups == 0 and gap >= 0
    # Mid-session next-minute should be ~60s; weekend/halt gaps are documented, not fatal.
    status = "PASS" if ok else "FAIL"
    return {
        "OLD_LAST_TIMESTAMP": str(old_last),
        "NEW_FIRST_TIMESTAMP": str(new_first),
        "GAP_SECONDS": gap,
        "DUPLICATES": dups,
        "PRICE_JUMP": jump,
        "BACKWARD": backward,
        "CONTINUITY_STATUS": status,
        "old_last_20": old_tail.tail(20)[["timestamp", "open", "high", "low", "close", "volume"]].to_dict(orient="records")
        if "timestamp" in old_tail.columns
        else [],
        "new_first_20": [
            {
                "timestamp": str(idx),
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume),
            }
            for idx, r in new_head.head(20).iterrows()
        ],
    }


def try_path_a() -> tuple[Path | None, dict[str, Any]]:
    info: dict[str, Any] = {"attempted": False}
    if not key_present():
        return None, info
    info["attempted"] = True
    dest = DATA / "nq_continuous_1m_lw_extension_sep2026.csv"
    DATA.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "cdx_research.python.extend_same_series",
        "--end-utc",
        "2026-09-22T04:00:00",
    ]
    print("PATH_A download start -> 2026-09-22T04:00:00Z")
    try:
        subprocess.run(cmd, check=True, cwd=str(ROOT))
    except subprocess.CalledProcessError as exc:
        info["error"] = f"download_exit_{exc.returncode}"
        return None, info
    if not dest.exists():
        # extend_same_series writes this path
        info["error"] = "extension_file_missing"
        return None, info
    return dest, info


def merge_databento(ext_path: Path) -> tuple[Path | None, dict[str, Any]]:
    old = pd.read_csv(EXT_OLD)
    new = load_databento_extension(ext_path)
    audit = continuity_audit(old, new)
    if audit["CONTINUITY_STATUS"] != "PASS":
        return None, audit
    merged_path = DATA / "nq_continuous_1m_lw_through_sep21.csv"
    new_raw = pd.read_csv(ext_path)
    old_ts = set(pd.to_datetime(old["timestamp"], utc=True).astype(str))
    new_raw["_ts"] = pd.to_datetime(new_raw["timestamp"], utc=True)
    keep = ~new_raw["_ts"].astype(str).isin(old_ts)
    add = new_raw.loc[keep].drop(columns=["_ts"])
    merged = pd.concat([old, add], ignore_index=True)
    merged_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(merged_path, index=False)
    audit["sha256_old"] = sha256_file(EXT_OLD)
    audit["sha256_extension"] = sha256_file(ext_path)
    audit["sha256_merged"] = sha256_file(merged_path)
    audit["merged_rows"] = int(len(merged))
    audit["merged_path"] = str(merged_path)
    return merged_path, audit


def tv_smoke_unused() -> dict[str, Any]:
    """Document the local TradingView 1m export. Never official alignment."""
    src = Path("/Users/anishalleti/Downloads/CME_MINI_NQ1!, 1_2418b.csv")
    if not src.exists():
        return {"present": False}
    raw = pd.read_csv(src)
    utc = pd.DatetimeIndex(pd.to_datetime(raw["time"], unit="s", utc=True))
    et = utc.tz_convert(ET)
    df = raw.copy()
    df.index = et
    labels = [
        ("s01 LONG 22:13", pd.Timestamp("2026-09-21 22:13:00", tz=ET), 30866.50),
        ("s01 SHORT 22:25", pd.Timestamp("2026-09-21 22:25:00", tz=ET), 30892.00),
    ]
    hits = []
    for name, ts, px in labels:
        if ts in df.index:
            row = df.loc[ts]
            hits.append(
                {
                    "label": name,
                    "status": "EXACT_ON_TV_NQ1",
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                    "label_price": px,
                }
            )
        else:
            hits.append({"label": name, "status": "NO_TV_BAR", "label_price": px})
    rejected = DATA / "rejected_not_used"
    rejected.mkdir(parents=True, exist_ok=True)
    dest = rejected / "tv_nq1_1m_sep21_only.csv"
    if not dest.exists():
        src_df = pd.DataFrame(
            {
                "timestamp_utc": utc,
                "timestamp_et": et,
                "open": raw["open"],
                "high": raw["high"],
                "low": raw["low"],
                "close": raw["close"],
                "source": "TRADINGVIEW_NQ1_NOT_USED",
            }
        )
        src_df.to_csv(dest, index=False)
    return {
        "present": True,
        "rows": int(len(raw)),
        "first_et": str(et.min()),
        "last_et": str(et.max()),
        "volume": False,
        "used_for_parity": False,
        "medium_labels_in_window": 2,
        "hits": hits,
        "reason_unused": "Not Databento and not NinjaTrader; 883 bars (~15h) cannot satisfy 7/10 MEDIUM gate",
    }


def write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def main() -> int:
    RUN.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    PARITY.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    present = key_present()
    print("DATABENTO_API_KEY_PRESENT=" + ("true" if present else "false"))
    auth = databento_auth()
    print("DATABENTO_AUTH=" + auth)

    labels = load_labels()
    assert int((labels.timestamp_confidence == "HIGH").sum()) == 0
    assert int((labels.timestamp_confidence == "MEDIUM").sum()) == 10
    assert int((labels.timestamp_confidence == "LOW").sum()) == 26

    path_used = ""
    source_name = ""
    series: pd.DataFrame | None = None
    continuity: dict[str, Any] = {"CONTINUITY_STATUS": "N/A"}
    canonical_modified = False
    separate_dataset = False
    start = end = ""
    rows = 0
    symbol = ""
    tz_note = ""

    if auth == "PASS":
        ext, info = try_path_a()
        if ext is not None:
            merged, continuity = merge_databento(ext)
            if continuity.get("CONTINUITY_STATUS") != "PASS":
                verdict = "CDX_RE_DATA_EXTENSION_INCOMPATIBLE"
                write_outputs(
                    verdict=verdict,
                    present=present,
                    auth=auth,
                    path_used="DATABENTO",
                    series=None,
                    labels=labels,
                    continuity=continuity,
                    extra={"reason": "continuity_fail", "info": info},
                )
                print("VERDICT", verdict)
                return 2
            series = load_databento_extension(ext)
            # Prefer merged file for alignment coverage (extension alone is enough if it covers Sep 6-21)
            path_used = "DATABENTO"
            source_name = "DATABENTO GLBX.MDP3 ohlcv-1m NQ.v.0"
            symbol = "NQ.v.0"
            tz_note = "raw UTC; derived timestamp_et via America/New_York"
            separate_dataset = True
            start = str(series.index.min())
            end = str(series.index.max())
            rows = int(len(series))

    if series is None:
        nt = find_nt_csv()
        if nt is not None:
            dest = DATA / NT_NAME
            if nt.resolve() != dest.resolve():
                dest.write_bytes(nt.read_bytes())
            series = load_nt_series(dest)
            path_used = "NINJATRADER"
            source_name = "CDX_ALIGNMENT_NINJATRADER"
            symbol = str(series.get("instrument", pd.Series(["NQ"])).iloc[0]) if "instrument" in series.columns else "NQ (NinjaTrader)"
            tz_note = "timestamp_utc + timestamp_et via timezone-aware conversion"
            separate_dataset = True
            start = str(series.index.min())
            end = str(series.index.max())
            rows = int(len(series))
            meta = nt.with_suffix(".meta.txt")
            if meta.exists():
                (RUN / "ninjatrader_meta.txt").write_text(meta.read_text(errors="ignore"))

    tv = tv_smoke_unused()
    (RUN / "tv_nq1_smoke_not_used.json").write_text(json.dumps(tv, indent=2, default=str))

    if series is None:
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        empty.index = pd.DatetimeIndex([], tz=UTC)
        audit = align_labels(labels, empty, source="NONE")
        write_outputs(
            verdict="CDX_RE_DATA_EXTENSION_FAIL",
            present=present,
            auth=auth,
            path_used="",
            series=None,
            labels=labels,
            continuity=continuity,
            extra={
                "reason": "no_databento_key_and_no_ninjatrader_csv",
                "tv_smoke": tv,
                "nt_export_required": True,
            },
            audit=audit,
        )
        print("VERDICT CDX_RE_DATA_EXTENSION_FAIL")
        return 2

    audit = align_labels(labels, series, source=path_used)
    gate = medium_gate(audit)
    analysis = None
    verdict = "CDX_RE_DATA_EXTENDED" if path_used == "DATABENTO" else "CDX_RE_NINJATRADER_DATA_READY"
    if not gate["gate_pass"]:
        verdict = "CDX_RE_LABEL_ALIGNMENT_WEAK"
    else:
        from cdx_research.python.first_real_analysis import run_analysis

        feat_dir = CDX / "features"
        feat_dir.mkdir(parents=True, exist_ok=True)
        analysis = run_analysis(series, labels, matched_medium_frame(audit), RUN)
        # copy official feature artifact
        src_feat = RUN / "matched_signal_features.csv"
        if src_feat.exists():
            (feat_dir / "matched_signal_features.csv").write_text(src_feat.read_text())
        verdict = "CDX_RE_FIRST_REAL_PARITY_READY"

    write_outputs(
        verdict=verdict,
        present=present,
        auth=auth,
        path_used=path_used,
        series=series,
        labels=labels,
        continuity=continuity,
        extra={
            "source_name": source_name,
            "symbol": symbol,
            "timezone": tz_note,
            "start": start,
            "end": end,
            "rows": rows,
            "canonical_modified": canonical_modified,
            "separate_dataset": separate_dataset,
            "tv_smoke": tv,
            "gate": gate,
            "analysis": analysis,
        },
        audit=audit,
    )
    print("VERDICT", verdict)
    print("ALIGNMENT_GATE", "PASS" if gate["gate_pass"] else "FAIL", gate)
    return 0 if gate["gate_pass"] else 3


def write_outputs(
    *,
    verdict: str,
    present: bool,
    auth: str,
    path_used: str,
    series: pd.DataFrame | None,
    labels: pd.DataFrame,
    continuity: dict[str, Any],
    extra: dict[str, Any],
    audit: pd.DataFrame | None = None,
) -> None:
    if audit is None:
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        empty.index = pd.DatetimeIndex([], tz=UTC)
        audit = align_labels(labels, empty, source="NONE")
    gate = medium_gate(audit)
    audit_path = PARITY / "label_match_audit_windows.csv"
    audit.to_csv(audit_path, index=False)
    audit.to_csv(RUN / "label_match_audit_windows.csv", index=False)
    matched = matched_medium_frame(audit)
    matched.to_csv(PARITY / "matched_medium_labels_windows.csv", index=False)
    matched.to_csv(RUN / "matched_medium_labels_windows.csv", index=False)

    analysis = extra.get("analysis")
    v1 = (analysis or {}).get("v1") if analysis else None
    causality = (analysis or {}).get("causality", {}) if analysis else {}

    old_end = "2026-09-02 10:48:00-05:00 America/Chicago"
    new_end = extra.get("end") or "unchanged"

    report = f"""# CDX V3 Windows data recovery — 2026-09-21

Prior package verdict (preserved): `CDX_RE_INSUFFICIENT_INFORMATION`

This run verdict: **`{verdict}`**

## Probe

- DATABENTO_API_KEY_PRESENT: `{'true' if present else 'false'}`
- DATABENTO_AUTH: `{auth}`
- Host: this runner (do not print secrets)

## Data

- PATH: `{path_used or 'NONE'}`
- SOURCE: {extra.get('source_name', 'none')}
- SYMBOL: {extra.get('symbol', '')}
- TIMEFRAME: 1m
- START: {extra.get('start', '')}
- END: {new_end}
- ROWS: {extra.get('rows', 0)}
- TIMEZONE: {extra.get('timezone', '')}
- CONTINUITY: {continuity.get('CONTINUITY_STATUS', 'N/A')}
- CANONICAL DATABENTO SERIES MODIFIED: `{'YES' if extra.get('canonical_modified') else 'NO'}`
- SEPARATE CDX DATASET CREATED: `{'YES' if extra.get('separate_dataset') else 'NO'}`

## Continuity detail

```
{json.dumps({k: continuity[k] for k in continuity if k not in ('old_last_20', 'new_first_20')}, indent=2, default=str)}
```

## Labels

- HIGH=0 MEDIUM=10 LOW=26 (unchanged; no confidence upgrades)
- EXACT: {gate['exact']}
- ±1: {gate['plus_minus_1']}
- AMBIGUOUS: {gate['ambiguous']}
- UNMATCHED: {gate['unmatched']}
- ALIGNMENT GATE (>=7/10 EXACT or ±1): `{'PASS' if gate['gate_pass'] else 'FAIL'}`
- LONG MATCHED: {gate['long_matched']}
- SHORT MATCHED: {gate['short_matched']}
- LOW used for strict parity: NO

## Candidate V1

Scored: `{'YES' if v1 else 'NO'}`
{json.dumps(v1, indent=2) if v1 else 'Not scored (alignment gate failed or no series). Frozen rule untouched.'}

## Features / transition / state

Run: `{'YES' if analysis else 'NO'}`
Causality: `{causality.get('status', 'NOT RUN')}`

## TradingView file found on this Mac

Used for official parity: **NO**

```
{json.dumps(extra.get('tv_smoke'), indent=2, default=str)}
```

## Production

Unchanged. Phase72A / 73 / 74 / 85 not modified. No SIM/funded routing.

## Next action

"""
    if verdict == "CDX_RE_DATA_EXTENSION_FAIL":
        report += (
            "On the Windows trading PC, from the repo root:\n\n"
            "```powershell\n"
            ".\\cdx_research\\windows\\Recover-CdxData.ps1\n"
            "```\n\n"
            "If Databento key is absent, add `CDXHistoricalBarExport` to an NQ 1-minute "
            "**ETH / electronic** chart with >= 30 days loaded, wait for export, re-run the script.\n"
        )
    elif verdict == "CDX_RE_LABEL_ALIGNMENT_WEAK":
        report += "Do not resume feature discovery. Inspect `label_match_audit_windows.csv` and the recovered series timezone/session.\n"
    elif verdict == "CDX_RE_FIRST_REAL_PARITY_READY":
        report += "Read FIRST_REAL_PARITY_REPORT. Do not retune V1. Collect forward CDX prints.\n"
    else:
        report += "Continue from the dated run folder. Do not merge NT into phase58j.\n"

    write_md(REPORTS / "WINDOWS_DATA_RECOVERY.md", report)
    write_md(RUN / "WINDOWS_DATA_RECOVERY.md", report)

    if analysis:
        top = analysis.get("top_features") or []
        hyps = analysis.get("hypotheses") or {}
        write_md(
            REPORTS / "FEATURE_DISCRIMINATION.md",
            "# Feature discrimination (MEDIUM-aligned, screenshot-covered bars)\n\n"
            + "Signal vs non-signal. Common conditions are not triggers.\n\n"
            + json.dumps(top, indent=2, default=str)
            + "\n\nHypotheses:\n\n"
            + json.dumps(hyps, indent=2, default=str)
            + "\n",
        )
        write_md(
            REPORTS / "TRANSITION_ANALYSIS.md",
            "# Transition analysis\n\nSee `runs/2026-09-21_windows_recovery/transition_table.csv`.\n"
            "Columns t_minus_0..20 and delta_t_vs_t1 / t5.\n",
        )
        write_md(
            REPORTS / "STATE_ANALYSIS.md",
            "# State / cooldown\n\n"
            + json.dumps(analysis.get("state_rows"), indent=2, default=str)
            + "\n",
        )
        write_md(
            REPORTS / "FIRST_REAL_PARITY_REPORT.md",
            "# First real parity report — Windows recovery run\n\n"
            f"Verdict: `{verdict}`\n\n"
            f"Path: {path_used}\n\n"
            f"V1 (frozen, not retuned):\n\n```\n{json.dumps(v1, indent=2)}\n```\n",
        )
        pd.DataFrame([v1]).to_csv(PARITY / "candidate_parity.csv", index=False)
    else:
        skip = (
            f"# Not run\n\nAlignment gate failed or no recovered series.\n\n"
            f"Verdict: `{verdict}`\n"
        )
        write_md(REPORTS / "FEATURE_DISCRIMINATION.md", skip)
        write_md(REPORTS / "TRANSITION_ANALYSIS.md", skip)
        write_md(REPORTS / "STATE_ANALYSIS.md", skip)
        write_md(
            REPORTS / "FIRST_REAL_PARITY_REPORT.md",
            "# First real parity — not started\n\n"
            f"Verdict: `{verdict}`\n\nFrozen Candidate V1 was not scored.\n",
        )

    summary = {
        "prior_verdict": "CDX_RE_INSUFFICIENT_INFORMATION",
        "this_run_verdict": verdict,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "DATABENTO_API_KEY_PRESENT": present,
        "DATABENTO_AUTH": auth,
        "path_used": path_used or "NONE",
        "continuity": continuity.get("CONTINUITY_STATUS"),
        "canonical_databento_modified": False,
        "separate_cdx_dataset": bool(extra.get("separate_dataset")),
        "gate": gate,
        "old_data_end": old_end,
        "new_data_end": new_end,
        "tv_used": False,
        "v1_scored": bool(v1),
        "production_modified": False,
    }
    (RUN / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print("wrote", audit_path)


if __name__ == "__main__":
    raise SystemExit(main())
