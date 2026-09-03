"""Position reconciliation."""
from __future__ import annotations

from phase73.execution.positions import PositionBook
from phase73.trader.fsm import TraderAction


def reconcile(book: PositionBook) -> TraderAction | None:
    if book.mismatch():
        return TraderAction.POSITION_MISMATCH
    return None
