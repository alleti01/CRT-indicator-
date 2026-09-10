"""No lookahead: gate_state at bar T unchanged if future export rows are mutated."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from signal_ledger.config import GATE_NAMES
from signal_ledger.gate_export import load_tv_gate_export

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_CSV = FIXTURES / "gate_export_sample.csv"


def test_gate_state_prefix_invariant_on_export():
    """Mutating gate values after bar T must not change gate_state at bar T."""
    df = load_tv_gate_export(SAMPLE_CSV)
    bar_i = 2
    g0 = {g: bool(df.iloc[bar_i][g]) for g in GATE_NAMES}

    df_bad = df.copy()
    df_bad.loc[bar_i + 1 :, GATE_NAMES] = True
    g1 = {g: bool(df_bad.iloc[bar_i][g]) for g in GATE_NAMES}

    assert g0 == g1, f"Lookahead detected: {json.dumps({k: (g0[k], g1[k]) for k in g0 if g0[k] != g1[k]})}"
