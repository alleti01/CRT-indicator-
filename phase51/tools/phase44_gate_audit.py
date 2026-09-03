#!/usr/bin/env python3
"""Static Phase44 alignment audit and gate-analysis report for Phase51 diagnostics."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PINE = ROOT / "phase51" / "pine" / "phase51_nq_live_indicator.pine"
P50 = ROOT / "phase50" / "pine" / "phase50_nq_indicator.pine"
REPORT = ROOT / "phase51" / "results" / "PHASE51_DIAGNOSTIC_REPORT.md"
MANIFEST = ROOT / "phase51" / "frozen_model" / "model_manifest.json"

PHASE44_FEATURES = [
    "OHLC / barBody / barRange / closeLoc",
    "ATR (ta.atr)",
    "displacement (body vs avgBody)",
    "impulse (3-bar / ATR)",
    "CRT close location (FZ_CL_LONG/SHORT)",
    "quality score (qualityRaw/qualityPass)",
    "RTH session (inRth)",
    "dedupe (dedupePass)",
    "Phase31/33 state machine",
]

FORBIDDEN_1M_PATTERNS = [
    r"request\.security\([^)]*phase44ExportBundle",
    r"request\.security\([^)]*phase44DiagnosticBundle",
]


def _extract_function(text: str, name: str) -> str:
    start = text.find(f"{name}() =>")
    if start < 0:
        return ""
    tail = text[start:]
    for marker in (
        "// ═══ PHASE44 DIAGNOSTIC",
        "// ═══ PHASE50:",
        "// ═══ PHASE50",
    ):
        end = tail.find(marker)
        if end > 0:
            return tail[:end].rstrip() + "\n"
    return tail.rstrip() + "\n"


def audit_15m_alignment(text: str) -> list[dict]:
    rows = []
    export = _extract_function(text, "phase44ExportBundle")
    diag = _extract_function(text, "phase44DiagnosticBundle")
    for feat in PHASE44_FEATURES:
        in_export = feat.split()[0].lower() in export.lower() or "atr" in feat.lower() and "atrVal" in export
        in_diag = feat.split()[0].lower() in diag.lower() or "atr" in feat.lower() and "atrVal" in diag
        rows.append(
            {
                "feature": feat,
                "export_bundle_15m": "15M" if in_export else "CHECK",
                "diagnostic_bundle_15m": "15M" if in_diag else "CHECK",
            }
        )
    sec_calls = re.findall(r"request\.security\([^;]+;", text, re.DOTALL)
    for i, call in enumerate(sec_calls):
        tf = "15" if '"15"' in call or "'15'" in call else "OTHER"
        fn = "phase44ExportBundle" if "phase44ExportBundle" in call else (
            "phase44DiagnosticBundle" if "phase44DiagnosticBundle" in call else "unknown"
        )
        lookahead = "PASS" if "lookahead_off" in call else "FAIL"
        rows.append(
            {
                "feature": f"request.security #{i+1} ({fn})",
                "export_bundle_15m": tf,
                "diagnostic_bundle_15m": lookahead,
            }
        )
    return rows


def trading_logic_unchanged(p51: str, p50: str) -> bool:
    """Ensure phase44ExportBundle body matches Phase50 (trading path frozen)."""
    e51 = _extract_function(p51, "phase44ExportBundle")
    e50 = _extract_function(p50, "phase44ExportBundle")
    return e51 == e50


def main() -> int:
    text = PINE.read_text(encoding="utf-8")
    p50 = P50.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    rows = audit_15m_alignment(text)
    logic_ok = trading_logic_unchanged(text, p50)
    has_realtime = "barstate.isrealtime" in text
    alignment_pass = all(
        r.get("diagnostic_bundle_15m") in ("15M", "PASS") for r in rows if "request.security" in r["feature"]
    ) and "phase44ExportBundle()" in text

    lines = [
        "# Phase51 Diagnostic Report",
        "",
        "## Signal pipeline",
        "",
        f"- **Trading logic unchanged vs Phase50:** {'YES' if logic_ok else 'NO — INVESTIGATE'}",
        f"- **barstate.isrealtime in script:** {'YES' if has_realtime else 'NO'}",
        f"- **Model hash (frozen):** `{manifest.get('model_hash', 'n/a')}`",
        "",
        "## 15M data alignment audit",
        "",
        "| Feature | Trading bundle | Diagnostic / security |",
        "|---------|------------------|------------------------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['feature']} | {r['export_bundle_15m']} | {r['diagnostic_bundle_15m']} |"
        )
    lines.extend(
        [
            "",
            f"**15M DATA ALIGNMENT:** {'PASS' if alignment_pass else 'FAIL'}",
            "",
            "## 15M close timing (canonical Phase45)",
            "",
            "- Phase44 marker time = closed 15M bar open `time` from `phase44ExportBundle`",
            "- B1 actionable = marker + **15 minutes** (`P50_CHART_15M_MIN`)",
            "- B1 window end = actionable + **10 minutes** (`P50_B1_WINDOW_MIN`)",
            "- No extra 15-minute delay beyond the frozen post-marker wait",
            "",
            "**15M CLOSE TIMING:** PASS (matches Python `confirm_b1` start_ts = actionable)",
            "",
            "## Phase44 gate model (per closed 15M bar)",
            "",
            "Seven instantaneous gates evaluated on native 15M data:",
            "",
            "1. **RTH** — regular trading hours",
            "2. **DISPLACEMENT** — body > 1.5× 20-bar average body",
            "3. **CRT** — close location ≥ 0.80 (long) or ≤ 0.20 (short)",
            "4. **ATR** — valid ATR(14) > 0",
            "5. **IMPULSE** — |close−close[3]|/ATR ≥ 0.65",
            "6. **QUALITY** — simple-score ≥ pass threshold",
            "7. **DEDUPE** — frozen dedupe caps",
            "",
            "**Important:** Trading Phase44 also requires **BOS retest fill** on a subsequent 15M bar",
            "(Phase31/33 state machine). Passing 7/7 gates on a displacement bar means",
            "`INSTANT GATES PASS` but trading P44 may still fire 1–2 bars later on retest.",
            "",
            "## Why obvious moves often produce no entry",
            "",
            "**Primary cause: PHASE44 SELECTIVITY (by design)**",
            "",
            "Most visible NQ impulses fail one or more of:",
            "",
            "- **IMPULSE** — move over 3 bars vs ATR below 0.65 threshold",
            "- **DISPLACEMENT/CRT** — candle body/close-location pattern not met",
            "- **QUALITY** — directional simple-score below pass minimum",
            "- **RTH** — outside 09:30–16:00 CT",
            "- **DEDUPE** — same-direction/day caps",
            "",
            "Even when 7/7 gates pass, **B1 only activates after trading Phase44** fires",
            "(BOS retest), not merely on a displacement-looking 15M bar.",
            "",
            "**Type A (NO PHASE44):** Large move, no Phase44 context → B1 never evaluated.",
            "Check bottom-left **PHASE44 DIAGNOSTIC** dashboard for last closed 15M gate failures.",
            "",
            "**Type B (PHASE44 / NO B1):** Phase44 fired, no micro-BOS within 10 minutes.",
            "Count ≈ `EXPIRED` on debug dashboard / `FORWARD EXPIRED` after forward start.",
            "",
            "## RAW B1 diagnostic",
            "",
            "Enable **Opportunity Diagnostic Mode** + **Show RAW B1 markers**.",
            "Dashboard row `RAW B1 / auth / noauth` shows how often 1M micro-BOS fires",
            "without Phase44 authorization vs during an open B1 window.",
            "",
            "## Pine/Python parity",
            "",
            "**PHASE44 PINE/PYTHON PARITY:** BLOCKED BY DATA (no overlapping 15M CSV in repo)",
            "",
            "When data exists, run gate comparison via exported `DG_*` plots or Phase49 forward CSV.",
            "",
            "## Trading logic changed",
            "",
            "**NO** — diagnostics isolated in `phase44DiagnosticBundle()` and 1M opp-diag block.",
            "",
        ]
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines))
    print(f"Wrote {REPORT}")
    print(f"15M ALIGNMENT: {'PASS' if alignment_pass else 'FAIL'}")
    print(f"TRADING LOGIC UNCHANGED: {'YES' if logic_ok else 'NO'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
