"""Offline inspection of a saved chart image. Does not place orders."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from cdx_vision.active_trade_selector import classify, select_active
from cdx_vision.models import OCRToken
from cdx_vision.parser import parse_tokens
from cdx_vision.validator import build_candidates


def tokens_from_sidecar(image_path: Path) -> list[OCRToken]:
    sidecar = image_path.with_suffix(".tokens.json")
    if not sidecar.exists():
        return []
    raw = json.loads(sidecar.read_text(encoding="utf-8"))
    frame = raw[0] if raw and isinstance(raw[0], list) else raw
    return [OCRToken(**token) for token in frame]


def format_inspection(tokens: list[OCRToken], side: str, price: Decimal | None) -> str:
    levels, _seen = parse_tokens(tokens)
    candidates, reasons = build_candidates(
        levels,
        webhook_direction=side,
        webhook_price=price,
        tick=Decimal("0.25"),
        sanity_points=Decimal("500"),
    )
    chosen, select_reasons, verdicts = select_active(
        candidates,
        tokens,
        webhook_direction=side,
        webhook_price=price,
        sanity_points=Decimal("500"),
    )
    lines = ["DETECTED LABELS:"]
    for level in levels:
        lines.append(f"  {level.normalized_label} {level.price} x={level.x1}")
    if not levels:
        lines.append("  none")
    lines.append("CANDIDATES:")
    if not verdicts:
        lines.append("  none")
        lines.append("REJECTED: " + ",".join(reasons or select_reasons))
    for item in verdicts:
        trade = item.candidate
        lines.append(
            f"  {item.status} x={item.cluster_x:.0f} fraction={item.x_fraction:.2f} "
            f"entry={trade.visual_entry or trade.entry} stop={trade.stop} tp1={trade.tp1} tp2={trade.tp2}"
        )
    if chosen is None:
        lines.append("SELECTED: none")
        lines.append("REASONS: " + ",".join(select_reasons or reasons))
    else:
        lines.append(
            f"SELECTED: entry={chosen.visual_entry or chosen.entry} stop={chosen.stop} "
            f"tp1={chosen.tp1} tp2={chosen.tp2} source={chosen.entry_source}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a CDX chart image. Does not place orders.")
    parser.add_argument("image")
    parser.add_argument("--side", default="SHORT")
    parser.add_argument("--webhook-price", default="")
    args = parser.parse_args(argv)
    image = Path(args.image)
    price = Decimal(args.webhook_price) if args.webhook_price else None
    tokens = tokens_from_sidecar(image)
    if not tokens and image.exists():
        tokens = _ocr_image(image)
    print(format_inspection(tokens, args.side.upper(), price))
    return 0


def _ocr_image(image_path: Path) -> list[OCRToken]:
    from PIL import Image

    from cdx_vision.entry_read import read_visual_entry
    from cdx_vision.ocr import TesseractOcr, chart_crop, preprocess
    from cdx_vision.tesseract_cmd import resolve_tesseract

    exe = resolve_tesseract()
    if not exe:
        return []
    image = Image.open(image_path)
    roi = (0.5, 0.12, 0.78, 0.82)
    engine = TesseractOcr(exe, psm=11)
    tokens = list(engine.recognize(preprocess(chart_crop(image, roi), scale=3)))
    observed = read_visual_entry(engine, image, roi, tokens, scale=3)
    tokens.extend(observed.tokens)
    return tokens


if __name__ == "__main__":
    raise SystemExit(main())
