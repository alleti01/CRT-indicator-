"""Live connection states (Phase74 extension)."""
from __future__ import annotations

from enum import Enum


class ConnectionState(str, Enum):
    DATA_CONNECTED = "DATA_CONNECTED"
    DATA_DISCONNECTED = "DATA_DISCONNECTED"
    DATA_RECONNECTED = "DATA_RECONNECTED"
    DATA_STALE = "DATA_STALE"
    DATA_GAP = "DATA_GAP"
    DATA_DUPLICATE = "DATA_DUPLICATE"
    DATA_OUT_OF_ORDER = "DATA_OUT_OF_ORDER"
