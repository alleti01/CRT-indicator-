"""Slippage sim router tests."""
from __future__ import annotations

import unittest

from phase73.execution.orders import Order, OrderSide
from phase74.execution.slippage_router import SlippageSimRouter


class TestSlippageRouter(unittest.TestCase):
    def test_long_entry_pays_adverse_slippage(self):
        r = SlippageSimRouter(entry_slippage_ticks=2, tick_size=0.25)
        order = Order.new("MARKET_BUY", OrderSide.BUY, 1, "NQ", "sig-1")
        _, fill = r.submit(order, 20000.0)
        self.assertIsNotNone(fill)
        self.assertEqual(fill.price, 20000.5)

    def test_short_entry_pays_adverse_slippage(self):
        r = SlippageSimRouter(entry_slippage_ticks=1, tick_size=0.25)
        order = Order.new("MARKET_SELL", OrderSide.SELL, 1, "NQ", "sig-2")
        _, fill = r.submit(order, 20000.0)
        self.assertIsNotNone(fill)
        self.assertEqual(fill.price, 19999.75)


if __name__ == "__main__":
    unittest.main()
