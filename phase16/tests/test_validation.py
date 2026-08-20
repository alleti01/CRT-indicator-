import tempfile
import unittest
from pathlib import Path

import pandas as pd

from phase16.validation import compare_parity, require_parity_pass


class ValidationTests(unittest.TestCase):
    def test_parity_comparison_and_oos_gate(self):
        python = pd.DataFrame(
            [
                {
                    "model": model,
                    "N": 10,
                    "wins": 5,
                    "losses": 5,
                    "win_pct": 50.0,
                    "avg_R": 0.1,
                    "total_R": 1.0,
                    "profit_factor": 1.2,
                    "max_drawdown_R": 2.0,
                }
                for model in ("Control", "BOS", "Retest", "Confirm")
            ]
        )
        reference = python.copy()
        report, status = compare_parity(python, reference)
        self.assertEqual(status, "PARITY PASS")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parity_summary.csv"
            report.to_csv(path, index=False)
            require_parity_pass(path)

    def test_failed_parity_blocks_oos(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parity_summary.csv"
            pd.DataFrame([{"overall_status": "PARITY FAIL"}]).to_csv(path, index=False)
            with self.assertRaises(RuntimeError):
                require_parity_pass(path)


if __name__ == "__main__":
    unittest.main()

