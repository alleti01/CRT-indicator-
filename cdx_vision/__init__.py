"""Shadow-only reader for CDX Entry, SL, TP1, and TP2 drawn on TradingView.

The webhook remains the signal. This package never places or changes orders.
"""
from cdx_vision.config import VisionConfig

__all__ = ["VisionConfig"]
