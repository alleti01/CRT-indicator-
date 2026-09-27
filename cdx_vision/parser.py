"""Parse CDX labels and NQ prices from OCR tokens. Does not guess missing digits."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from cdx_vision.models import OCRToken, ParsedLevel

TICK = Decimal("0.25")
_PRICE = re.compile(r"(?<!\d)(\d{4,6}(?:\.\d{1,2})?)(?!\d)")
_LABELS = (
    ("CDX ENTRY", "ENTRY"),
    ("CDX LONG", "LONG"),
    ("CDX SHORT", "SHORT"),
    ("TP1", "TP1"),
    ("TP2", "TP2"),
    ("TPI", "TP1"),
    ("TP 1", "TP1"),
    ("TP 2", "TP2"),
    ("SL", "SL"),
)


def on_tick(price: Decimal, tick: Decimal = TICK) -> bool:
    if tick <= 0:
        return False
    units = price / tick
    return units == units.to_integral_value()


def parse_price(text: str, tick: Decimal = TICK) -> Decimal | None:
    match = _PRICE.search(text.replace(",", ""))
    if not match:
        return None
    try:
        price = Decimal(match.group(1))
    except InvalidOperation:
        return None
    if price <= 0 or not on_tick(price, tick):
        return None
    return price


def normalize_label(text: str) -> str:
    folded = " ".join(text.upper().split())
    for raw, label in _LABELS:
        if raw in folded:
            return label
    return ""


def parse_tokens(tokens: list[OCRToken], tick: Decimal = TICK) -> tuple[list[ParsedLevel], str]:
    """Return parsed levels and a direction seen in the text, if any."""
    levels: list[ParsedLevel] = []
    direction = ""
    for token in tokens:
        label = normalize_label(token.text)
        if label == "LONG":
            direction = direction or "LONG"
        elif label == "SHORT":
            direction = direction or "SHORT"
        if label not in {"ENTRY", "SL", "TP1", "TP2"}:
            continue
        price = parse_price(token.text, tick)
        if price is None:
            continue
        levels.append(
            ParsedLevel(
                raw_text=token.text,
                normalized_label=label,
                price=price,
                x1=token.x1,
                y1=token.y1,
                x2=token.x2,
                y2=token.y2,
            )
        )
    return levels, direction
