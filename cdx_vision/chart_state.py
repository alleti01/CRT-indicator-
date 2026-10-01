"""Chart state before OCR. A CDX marker is not a complete level set."""
from __future__ import annotations

import re

from cdx_vision.models import OCRToken
from cdx_vision.parser import parse_price

_TIMEFRAMES = {"30s", "45s", "1m", "3m", "5m", "15m", "1h", "4h"}
_RIBBON = re.compile(r"\d{2},?\d{3}\.\d{2}")


# TradingView's interval box treats "3M" as 3 months. Minutes are a bare number.
_INTERVAL_KEYS = {
    "30s": "30S",
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
}
_SYMBOL_ROOTS = ("MNQ", "MES", "M2K", "MYM", "NQ", "ES", "RTY", "YM")


def menu_row_matches(text: str, number: str, unit: str) -> bool:
    """True when a menu row is that interval. 15 minutes is not 1 or 5 minutes."""
    compact = "".join(ch for ch in text.lower() if ch.isalnum())
    if not number or not unit:
        return False
    return re.search(rf"(?<!\d){re.escape(number)}{re.escape(unit)}", compact) is not None


def interval_menu_target(timeframe: str) -> tuple[str, str]:
    """Number and unit shown in the TradingView interval menu."""
    tf = normalize_timeframe(timeframe)
    match = re.fullmatch(r"(\d+)(s|m|h|d)", tf)
    if not match:
        return "", ""
    unit = {"s": "second", "m": "minute", "h": "hour", "d": "day"}[match.group(2)]
    return match.group(1), unit


def interval_keystrokes(timeframe: str) -> str:
    """Keys typed into the TradingView interval box. Never the month suffix."""
    return _INTERVAL_KEYS.get(normalize_timeframe(timeframe), "")


def detect_symbol(title: str) -> str:
    upper = title.upper()
    for root in _SYMBOL_ROOTS:
        if root in upper:
            return root
    return ""


def symbol_matches(title: str, ticker: str) -> bool:
    expected = "".join(ch for ch in ticker.upper() if ch.isalpha())
    if not expected:
        return True
    return detect_symbol(title) == expected


def normalize_timeframe(text: str) -> str:
    key = "".join(text.lower().split())
    aliases = {
        "3m": "3m",
        "3min": "3m",
        "3mins": "3m",
        "3minute": "3m",
        "3minutes": "3m",
        "1m": "1m",
        "1min": "1m",
        "1minute": "1m",
        "30s": "30s",
        "30sec": "30s",
        "30secs": "30s",
        "30second": "30s",
        "30seconds": "30s",
    }
    if key in aliases:
        return aliases[key]
    if key in _TIMEFRAMES:
        return key
    if re.fullmatch(r"\d+(s|m|h|d)", key):
        return key
    return ""


def detect_timeframe(
    words: list[tuple[str, int, int]],
    *,
    width: int,
    height: int,
    cropped: bool = False,
) -> str:
    """Toolbar interval only. Ignores the alerts panel on the right."""
    found: list[tuple[int, str]] = []
    for text, x, y in words:
        if not cropped and (y > height * 0.14 or x > width * 0.45):
            continue
        tf = normalize_timeframe(text)
        if tf:
            found.append((x, tf))
    if not found:
        return ""
    found.sort()
    return found[0][1]


def signal_marker_visible(tokens: list[OCRToken]) -> bool:
    blob = " ".join(token.text.upper() for token in tokens)
    return "CDX" in blob and ("LONG" in blob or "SHORT" in blob)


def label_flags(tokens: list[OCRToken]) -> dict[str, bool]:
    blob = " ".join(token.text.upper() for token in tokens)
    return {
        "entry": "ENTRY" in blob,
        "sl": bool(re.search(r"\bSL\b", blob)),
        "tp1": "TP1" in blob,
        "tp2": "TP2" in blob,
    }


def ribbon_values(tokens: list[OCRToken]) -> list[str]:
    """Off-tick prices. They are not Entry, SL, TP1, or TP2."""
    found = []
    for token in tokens:
        compact = token.text.replace(" ", "")
        if not _RIBBON.search(compact):
            continue
        if parse_price(compact) is None:
            found.append(token.text)
    return found


def recovery_route(
    *,
    timeframe_ok: bool,
    level_set_complete: bool,
    live_edge: bool,
    offscreen: bool,
) -> str:
    """Marker visibility is intentionally not an input."""
    if not timeframe_ok:
        return "RESTORE_TIMEFRAME"
    if level_set_complete:
        return "READY"
    if live_edge:
        return "NATIVE_LABELS_MISSING"
    if offscreen:
        return "AUTO_RIGHT"
    return "DIAGNOSTIC_RIGHT"
