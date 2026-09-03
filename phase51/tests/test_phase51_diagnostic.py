"""Tests for Phase51 diagnostic layer (trading logic must remain frozen)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PINE = ROOT / "phase51" / "pine" / "phase51_nq_live_indicator.pine"
P50 = ROOT / "phase50" / "pine" / "phase50_nq_indicator.pine"
MANIFEST = ROOT / "phase51" / "frozen_model" / "model_manifest.json"


def _extract_export(text: str) -> str:
    start = text.find("phase44ExportBundle() =>")
    if start < 0:
        return ""
    tail = text[start:]
    for marker in ("// ═══ PHASE44 DIAGNOSTIC", "// ═══ PHASE50"):
        end = tail.find(marker)
        if end > 0:
            return tail[:end].rstrip()
    return tail.rstrip()


def test_trading_bundle_unchanged_vs_phase50():
    assert _extract_export(PINE.read_text()) == _extract_export(P50.read_text())


def test_diagnostic_bundle_isolated():
    text = PINE.read_text()
    assert "phase44DiagnosticBundle()" in text
    assert "phase44ExportBundle()" in text
    assert text.index("phase44DiagnosticBundle") > text.index("phase44ExportBundle")


def test_diagnostic_security_lookahead_off():
    text = PINE.read_text()
    m = re.search(
        r"phase44DiagnosticBundle\(\).*?lookahead = barmerge\.lookahead_off",
        text,
        re.DOTALL,
    )
    assert m


def test_no_realtime_strategy_branch():
    section = re.search(r"if chart1m and barstate.isconfirmed(.*?)// Opportunity diagnostic", PINE.read_text(), re.DOTALL)
    assert section
    assert "barstate.isrealtime" not in section.group(1)


def test_model_hash_unchanged():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["model_hash"] == "f29e61a82ef19fe21e13aa040035ca7bcabf7504f0477ebc4643253f7fd6f1f0"


def test_opp_diag_input_exists():
    assert "Opportunity Diagnostic Mode" in PINE.read_text()
