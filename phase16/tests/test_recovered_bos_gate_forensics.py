"""Tests for recovered BOS gate forensics reproduction."""

from __future__ import annotations

import unittest
from pathlib import Path

from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase16.recovered_bos_gate_forensics import run_recovered_bos_gate_forensics


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "phase16" / "data" / "processed" / "nq_5m.csv"


class RecoveredBosGateForensicsTests(unittest.TestCase):
    def test_reproduction_and_funnel(self):
        if not DATA.exists():
            self.skipTest("dataset unavailable")
        config = FrozenConfig()
        data = load_ohlcv_csv(DATA, exchange_timezone=config.exchange_timezone)
        out = ROOT / "phase16" / "results" / "recovered_bos_gate_forensics_test"
        manifest = run_recovered_bos_gate_forensics(
            data,
            start="2024-01-01",
            end="2026-06-26",
            config=config,
            output=out,
        )
        self.assertTrue(manifest["reproduced"])
        self.assertEqual(manifest["recovered_bos"], 158)
        self.assertEqual(manifest["recovered_entries"], 54)
        models = {row["model"]: row for row in manifest["gate_model_comparison"]}
        self.assertEqual(models["MODEL_D_CONFIRM_ENTRY"]["N"], 54)
        self.assertAlmostEqual(models["MODEL_D_CONFIRM_ENTRY"]["net_TotalR"], -0.93, delta=0.2)


if __name__ == "__main__":
    unittest.main()
