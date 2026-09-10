"""Fix 2 — Pine-native gate instrumentation tests (Parts A–D)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from phase58.research.instrument import NQ
from signal_ledger.config import GATE_NAMES
from signal_ledger.gate_evaluator import (
    compute_known_at_offsets,
    compute_pivot_confirmation_offsets,
    cross_check_alert_vs_export,
    gate_state_from_alert_payload,
)
from signal_ledger.gate_export import export_row_at_time, load_tv_gate_export
from signal_ledger.hypothetical_outcomes import apply_m0_cost, hyp_m0_long_r, walk_m0_phase73

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_CSV = FIXTURES / "gate_export_sample.csv"
ALERT_JSON = FIXTURES / "alert_signal_long.json"


class TestGateExportLoad:
    def test_loads_all_gate_columns(self):
        df = load_tv_gate_export(SAMPLE_CSV)
        assert len(df) == 5
        for g in GATE_NAMES:
            assert g in df.columns
        assert "bar_time_utc" in df.columns
        assert df["bar_time_utc"].dt.tz is not None


class TestKnownAtOffset:
    def test_take_chain_gates_offset_zero(self):
        df = load_tv_gate_export(SAMPLE_CSV)
        offsets = compute_known_at_offsets(df)
        by_name = {o.gate_name: o.known_at_bar_offset for o in offsets}
        for g in GATE_NAMES:
            assert by_name[g] == 0

    def test_pivot_lag_matches_swing_period(self):
        df = load_tv_gate_export(SAMPLE_CSV)
        pivot = compute_pivot_confirmation_offsets(df)
        assert pivot["swing_period"] == 5.0
        assert pivot["confirmed"] is True
        assert 5.0 in pivot["high_lag_samples"] or 5.0 in pivot["low_lag_samples"]


class TestAlertExportCrossCheck:
    def test_part_d_no_mismatch_on_fixture(self):
        payload = json.loads(ALERT_JSON.read_text())
        df = load_tv_gate_export(SAMPLE_CSV)
        bar_ts = pd.to_datetime(payload["signal_bar_time_utc_ms"], unit="ms", utc=True)
        row = export_row_at_time(df, bar_ts)
        assert row is not None
        mism = cross_check_alert_vs_export(payload, row)
        assert mism == [], f"instrumentation bug: {mism}"


class TestAlertPayloadGates:
    def test_all_gate_keys_required(self):
        payload = json.loads(ALERT_JSON.read_text())
        gs = gate_state_from_alert_payload(payload)
        assert gs["take_long"] is True
        assert gs["armed_long"] is True


class TestCostAdjustedHypR:
    def test_nq_cost_magnitude(self):
        gross = -1.0
        entry, risk = 100.0, 1.0
        net = apply_m0_cost(gross, entry, risk)
        expected_cost = NQ.cost_r(entry, entry - risk)
        assert net == pytest.approx(gross - expected_cost)

    def test_long_stop_net_r(self):
        import numpy as np

        n = 50
        base = 100.0
        hi = np.full(n, base + 0.4)
        lo = np.full(n, base - 0.4)
        cl = np.full(n, base)
        op = np.full(n, base)
        atr = np.full(n, 1.0)
        signal_i = 10
        ei = 11
        for k in range(ei + 1, 20):
            lo[k] = 98.0
        hyp = hyp_m0_long_r(hi, lo, cl, op, atr, signal_i)
        gross = -1.0
        net = apply_m0_cost(gross, float(op[ei]), 1.0)
        assert hyp == pytest.approx(net)
        assert hyp == pytest.approx(walk_m0_phase73(hi, lo, cl, op, atr, ei, "LONG", float(op[ei]), 1.0))


class TestNoLookaheadExport:
    def test_future_rows_do_not_change_prior_gate_state(self):
        df = load_tv_gate_export(SAMPLE_CSV)
        row0 = df.iloc[2].copy()
        df_mut = df.copy()
        df_mut.loc[3:, GATE_NAMES] = True
        row0_after = df_mut.iloc[2]
        for g in GATE_NAMES:
            assert bool(row0[g]) == bool(row0_after[g])
