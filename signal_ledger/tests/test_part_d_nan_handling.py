"""Part D — ledger three-state NaN handling (no silent na→False)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from signal_ledger.config import ARM_TOTAL_PROV_COLD_START, ARM_TOTAL_PROV_FRESH, ARM_TOTAL_PROV_STALE_HOLD
from signal_ledger.gate_evaluator import blocking_gates_for_direction, gate_state_from_export_row
from signal_ledger.gate_export import load_tv_gate_export
from signal_ledger.gate_tri_state import (
    arm_total_state,
    evidence_threshold_state,
    gate_state_detail_from_export_row,
)

FIXTURES = Path(__file__).parent / "fixtures"
COLD_CSV = FIXTURES / "gate_export_cold_start.csv"
SAMPLE_CSV = FIXTURES / "gate_export_sample.csv"


class TestNullableExportLoad:
    def test_cold_start_evidence_not_coerced_to_false(self):
        df = load_tv_gate_export(COLD_CSV)
        assert len(df) == 1
        assert pd.isna(df.iloc[0]["evidence_threshold_long"])
        assert pd.isna(df.iloc[0]["evidence_threshold_short"])

    def test_warm_export_still_boolean(self):
        df = load_tv_gate_export(SAMPLE_CSV)
        row = df.iloc[2]
        assert row["evidence_threshold_long"] is True or row["evidence_threshold_long"] == True  # noqa: E712


class TestTriStateInterpretation:
    def test_cold_start_states(self):
        df = load_tv_gate_export(COLD_CSV)
        row = df.iloc[0]
        assert arm_total_state(row, "long") == "insufficient_warmup"
        assert evidence_threshold_state(row, "long") == "insufficient_warmup"
        detail = gate_state_detail_from_export_row(row)
        assert detail["pass_reason_code"] == 1
        assert detail["htf_warmup_ready"] is False

    def test_fresh_arm_total(self):
        df = load_tv_gate_export(SAMPLE_CSV)
        row = df.iloc[2].copy()
        row["arm_total_long_prov"] = ARM_TOTAL_PROV_FRESH
        row["arm_total_long"] = 5.0
        assert arm_total_state(row, "long") == "fresh"
        assert evidence_threshold_state(row, "long") == "pass"

    def test_stale_hold_arm_total(self):
        row = pd.Series(
            {
                "evidence_threshold_long": True,
                "arm_total_long_prov": ARM_TOTAL_PROV_STALE_HOLD,
                "arm_total_long": 4.0,
                "pass_reason_code": 0,
            }
        )
        assert arm_total_state(row, "long") == "stale_hold"
        assert evidence_threshold_state(row, "long") == "pass"

    def test_unknown_na_without_cold_markers(self):
        row = pd.Series({"evidence_threshold_long": pd.NA, "pass_reason_code": 0})
        assert evidence_threshold_state(row, "long") == "unknown_na"

    def test_warm_prov0_unset_snap_not_insufficient_warmup(self):
        row = pd.Series(
            {
                "evidence_threshold_long": False,
                "arm_total_long_prov": ARM_TOTAL_PROV_COLD_START,
                "pass_reason_code": 0,
                "htf_warmup_ready": True,
            }
        )
        assert arm_total_state(row, "long") == "unset"
        assert evidence_threshold_state(row, "long") == "fail"


class TestBlockingGates:
    def test_insufficient_warmup_not_counted_as_block(self):
        df = load_tv_gate_export(COLD_CSV)
        row = df.iloc[0]
        gs = gate_state_from_export_row(row)
        detail = gate_state_detail_from_export_row(row)
        blocked = blocking_gates_for_direction(gs, "long", detail=detail)
        assert "evidence_threshold_long" not in blocked

    def test_explicit_fail_still_blocks(self):
        df = load_tv_gate_export(SAMPLE_CSV)
        row = df.iloc[1]
        gs = gate_state_from_export_row(row)
        detail = gate_state_detail_from_export_row(row)
        blocked = blocking_gates_for_direction(gs, "long", detail=detail)
        assert "evidence_threshold_long" in blocked
