"""Parse CDX labels and NQ prices from OCR tokens. Does not guess missing digits."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from cdx_vision.models import OCRToken, ParsedLevel

TICK = Decimal("0.25")
_PRICE = re.compile(r"(?<!\d)(\d{4,6}(?:\.\d{1,2})?)(?!\d)")
_LABELS = (
    ("CDX ENTRY", "ENTRY"),
    ("CDXENTRY", "ENTRY"),
    ("ENTRY", "ENTRY"),
    ("CDX LONG", "LONG"),
    ("CDX SHORT", "SHORT"),
    ("TP1", "TP1"),
    ("TP2", "TP2"),
    ("TPI", "TP1"),
    ("TP 1", "TP1"),
    ("TP 2", "TP2"),
    ("$L", "SL"),
    ("SL", "SL"),
)


def on_tick(price: Decimal, tick: Decimal = TICK) -> bool:
    if tick <= 0:
        return False
    units = price / tick
    return units == units.to_integral_value()


def parse_price(text: str, tick: Decimal = TICK) -> Decimal | None:
    """A trailing comma on a whole number is a cut-off token, not a price."""
    cleaned = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)
    match = _PRICE.search(cleaned)
    if not match:
        return None
    number = match.group(1)
    tail = cleaned[match.end(): match.end() + 1]
    if tail in {",", "_"} and "." not in number:
        return None
    try:
        price = Decimal(number)
    except InvalidOperation:
        return None
    if price <= 0 or not on_tick(price, tick):
        return None
    return price


_NOISE = re.compile(
    r"(%|\bRSI\b|WIN\s*RATE|AVG\s*RUNNER|\bTRADES\b|\bWINS\b|\bLOSSES\b|"
    r"\bVOLATILITY\b|\bBIAS\b|SCHEMA|NQ=|\d+(?:\.\d+)?R\b|\d{1,2}:\d{2})",
    re.IGNORECASE,
)


def is_noise(text: str) -> bool:
    """Side-panel and table text is not a CDX level."""
    return bool(_NOISE.search(text))


def folded_is_bare_cdx(text: str) -> bool:
    """A lone CDX token can be the entry label when ENTRY was split off."""
    return " ".join(text.upper().split()) == "CDX"


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
    used: set[int] = set()
    for index, token in enumerate(tokens):
        if is_noise(token.text):
            continue
        label = normalize_label(token.text)
        if label == "LONG":
            direction = direction or "LONG"
        elif label == "SHORT":
            direction = direction or "SHORT"
        if label not in {"ENTRY", "SL", "TP1", "TP2"}:
            continue
        price = parse_price(token.text, tick)
        source = token
        if price is None:
            price, source = _price_to_the_right(tokens, token, tick, used)
        if price is None:
            continue
        used.add(id(source))
        levels.append(
            ParsedLevel(
                raw_text=token.text if source is token else f"{token.text} {source.text}",
                normalized_label=label,
                price=price,
                x1=token.x1,
                y1=min(token.y1, source.y1),
                x2=max(token.x2, source.x2),
                y2=max(token.y2, source.y2),
            )
        )
    return levels, direction


def _price_to_the_right(tokens: list[OCRToken], label: OCRToken, tick: Decimal, used: set[int]) -> tuple[Decimal | None, OCRToken]:
    best: tuple[float, Decimal, OCRToken] | None = None
    label_mid = (label.y1 + label.y2) / 2
    for token in tokens:
        if id(token) in used or token.x1 < label.x1 or is_noise(token.text):
            continue
        price = parse_price(token.text, tick)
        if price is None or normalize_label(token.text):
            continue
        mid = (token.y1 + token.y2) / 2
        if abs(mid - label_mid) > max(24, (label.y2 - label.y1) * 1.5):
            continue
        distance = token.x1 - label.x2
        if best is None or distance < best[0]:
            best = (distance, price, token)
    if best is None:
        return None, label
    return best[1], best[2]
