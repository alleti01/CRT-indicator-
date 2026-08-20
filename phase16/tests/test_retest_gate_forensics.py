"""Regression checks for the diagnostic-only retest-gate trace."""

from pathlib import Path
import difflib
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PINE_BASELINE = ROOT / "outputs" / "CRT_Core_SAME_BAR_SETUP_BOS_DIAGNOSTIC.pine"
PINE_FORENSIC = ROOT / "outputs" / "CRT_Core_RETEST_GATE_FORENSIC_TRACE.pine"
FORENSIC_DIR = ROOT / "phase16" / "results" / "retest_gate_forensics"
PARITY_TRADES = ROOT / "phase16" / "results" / "parity" / "trades.csv"


class RetestGateForensicTests(unittest.TestCase):
    def test_01_pine_changes_are_observability_only(self):
        before = PINE_BASELINE.read_text().splitlines()
        after = PINE_FORENSIC.read_text().splitlines()
        changed = [
            line
            for line in difflib.ndiff(before, after)
            if line.startswith("+ ") or line.startswith("- ")
        ]
        allowed_tokens = (
            "liveGateRetestTouchEvt",
            "liveGateRetestRejectEvt",
            "liveGateConfirmCandidateEvt",
            "liveGateInvalidatedEvt",
            "liveGateRetestEvt",
            "retestTouchEvt",
            "retestRejectEvt",
            "confirmCandidateEvt",
            "invalidatedEvt",
            "RETEST ACCEPT",
            "RETEST TOUCH S",
            "RETEST REJECT S",
            "CONFIRM CANDIDATE S",
            "INVALIDATED S",
            "liveAdvanceRetestGate(",
            "readyEvt]",
        )
        self.assertTrue(changed)
        for line in changed:
            self.assertTrue(any(token in line for token in allowed_tokens), line)

    def test_02_original_mode_source_is_unchanged(self):
        before = PINE_BASELINE.read_text()
        after = PINE_FORENSIC.read_text()
        start = "// Original mode preserves the prior immediate-entry semantics exactly."
        end = "// Retest-gated official state changes only on a CLOSED candle"
        self.assertEqual(
            before[before.index(start) : before.index(end)],
            after[after.index(start) : after.index(end)],
        )

    def test_03_required_short_markers_exist(self):
        source = PINE_FORENSIC.read_text()
        for marker in (
            "SETUP S",
            "BOS S",
            "RETEST TOUCH S",
            "RETEST ACCEPT S",
            "RETEST REJECT S",
            "CONFIRM CANDIDATE S",
            "CONFIRM S",
            "INVALIDATED S",
        ):
            self.assertIn(marker, source)

    def test_04_forensic_entries_reconcile_to_frozen_parity(self):
        candidates = pd.read_csv(FORENSIC_DIR / "all_setup_candidates.csv")
        forensic_entries = candidates[candidates.final_result == "ENTRY"].copy()
        parity = pd.read_csv(PARITY_TRADES)
        parity = parity[parity.model == "Confirm"].copy()
        expected = set(zip(parity.direction, parity.entry_timestamp))
        actual = set(zip(forensic_entries.direction, forensic_entries.entry_timestamp))
        self.assertEqual(len(actual), 42)
        self.assertEqual(expected, actual)

    def test_05_short_funnel_is_monotone(self):
        candidates = pd.read_csv(FORENSIC_DIR / "short_candidates.csv")
        counts = [
            len(candidates),
            int(candidates.variant_c_qualified.sum()),
            int(candidates.candidate_accepted.sum()),
            int(candidates.bos_timestamp.notna().sum()),
            int(candidates.retest_touched.sum()),
            int(candidates.retest_accepted.sum()),
            int(candidates.confirmation_candidate_seen.sum()),
            int(candidates.confirmation_accepted.sum()),
            int((candidates.final_result == "ENTRY").sum()),
        ]
        self.assertEqual(counts, [120, 70, 60, 44, 40, 26, 26, 21, 21])
        self.assertTrue(all(left >= right for left, right in zip(counts, counts[1:])))


if __name__ == "__main__":
    unittest.main()
