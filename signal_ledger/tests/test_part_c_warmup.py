"""Part C — cold-start warmup export constants and optional column parsing."""
from __future__ import annotations

from signal_ledger.config import (
    ARM_TOTAL_PROV_COLD_START,
    ARM_TOTAL_PROV_FRESH,
    ARM_TOTAL_PROV_STALE_HOLD,
    GLD_HTF_WARMUP_MIN_BARS_DEFAULT,
    PASS_REASON_INSUFFICIENT_WARMUP,
    PASS_REASON_NONE,
)


def test_warmup_window_default_bound():
    assert GLD_HTF_WARMUP_MIN_BARS_DEFAULT == 12 * 15 + 5


def test_arm_total_provenance_codes():
    assert ARM_TOTAL_PROV_COLD_START == 0
    assert ARM_TOTAL_PROV_FRESH == 1
    assert ARM_TOTAL_PROV_STALE_HOLD == 2


def test_pass_reason_codes():
    assert PASS_REASON_NONE == 0
    assert PASS_REASON_INSUFFICIENT_WARMUP == 1
