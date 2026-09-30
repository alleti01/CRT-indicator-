"""Chart symbols the vision reader may accept. Tick size stays 0.25."""
from __future__ import annotations


def market_root(symbol: str) -> str:
    text = (symbol or "").upper().replace("1!", " ")
    head = text.split()[0] if text.split() else ""
    if head.startswith("MNQ"):
        return "MNQ"
    if head.startswith("NQ"):
        return "NQ"
    return head


def accepted_chart_symbol(symbol: str) -> bool:
    return market_root(symbol) in {"NQ", "MNQ"}
