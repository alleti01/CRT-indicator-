import unittest

import pandas as pd

from phase16.indicators import confirmed_pivots


class PivotTests(unittest.TestCase):
    def test_pivot_is_emitted_only_on_confirmation_bar(self):
        values = pd.Series([1.0, 2.0, 5.0, 3.0, 2.0, 1.0])
        result = confirmed_pivots(values, left=2, right=2, kind="high")
        self.assertTrue(result.iloc[:4].isna().all())
        self.assertEqual(result.iloc[4], 5.0)

    def test_future_append_does_not_rewrite_existing_outputs(self):
        original = pd.Series([1.0, 4.0, 2.0, 3.0, 1.0, 2.0])
        extended = pd.concat([original, pd.Series([10.0, 0.0, 5.0])], ignore_index=True)
        before = confirmed_pivots(original, 1, 1, "high")
        after = confirmed_pivots(extended, 1, 1, "high").iloc[: len(original)]
        pd.testing.assert_series_equal(before.reset_index(drop=True), after.reset_index(drop=True))


if __name__ == "__main__":
    unittest.main()

