"""Classification logic unit tests."""
from __future__ import annotations

from signal_ledger.hypothetical_outcomes import apply_m0_cost
from signal_ledger.ledger_builder import classify_row


def test_correct_take():
    assert classify_row(True, "long", 2.0, -1.0, 1.5) == "correct_take"


def test_false_positive():
    assert classify_row(True, "short", 1.0, -0.5, 1.5) == "false_positive"


def test_missed_reversal():
    assert classify_row(False, None, 0.5, 2.0, 1.5) == "missed_reversal"


def test_correct_pass():
    assert classify_row(False, None, 0.2, 0.3, 1.5) == "correct_pass"


def test_cost_adjustment_reduces_missed_reversal():
    """Net hyp_R after NQ.cost_r can reclassify gross missed-reversal bars as correct_pass."""
    gross = 2.0
    net = apply_m0_cost(gross, 100.0, 1.0)
    assert classify_row(False, None, gross, -1.0, 1.5) == "missed_reversal"
    assert classify_row(False, None, net, -1.0, 1.5) == "correct_pass"
    assert net < gross
