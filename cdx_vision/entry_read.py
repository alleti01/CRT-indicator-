"""Read the faint CDX Entry label. The line locates the crop. The text sets the price."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from cdx_vision.models import OCRToken
from cdx_vision.parser import folded_is_bare_cdx, parse_price, parse_tokens

_PSM = 7


@dataclass
class EntryObservation:
    price: Decimal | None
    status: str
    raw: list[str] = field(default_factory=list)
    tokens: list[OCRToken] = field(default_factory=list)
    band: tuple[int, int, int, int] | None = None


def read_visual_entry(
    engine,
    image: Image.Image,
    roi: tuple[float, float, float, float],
    anchor_tokens: list[OCRToken],
    *,
    scale: int = 3,
    debug_dir: Path | None = None,
) -> EntryObservation:
    """Return one agreed entry price, or a status that forbids guessing."""
    bands = _dark_bands(image, roi)
    if not bands:
        anchor = _anchor_band(image, roi, anchor_tokens, scale)
        bands = [anchor] if anchor else []
    if not bands:
        return EntryObservation(None, "NOT_FOUND")
    votes: list[Decimal] = []
    raw: list[str] = []
    chosen_band = bands[0]
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        image.save(debug_dir / "window.png")
    for band in bands:
        crop = image.crop(band)
        if debug_dir is not None:
            crop.save(debug_dir / "entry_crop.png")
        for name, variant in _variants(crop):
            tokens = _recognize(engine, variant)
            prices = _entry_prices(tokens)
            raw.append(f"{name}:" + (",".join(format(price, "f") for price in sorted(prices)) or "none"))
            if debug_dir is not None:
                _save_variant(debug_dir, name, variant, tokens, prices)
            if len(prices) > 1:
                return EntryObservation(None, "UNSTABLE", raw, _conflict_tokens(prices, anchor_tokens, image, roi, scale, band), band)
            if len(prices) == 1:
                votes.append(next(iter(prices)))
        if votes:
            chosen_band = band
            break
    if not votes:
        return EntryObservation(None, "NOT_FOUND", raw, band=chosen_band)
    unique = set(votes)
    if len(unique) != 1:
        return EntryObservation(None, "UNSTABLE", raw, _conflict_tokens(unique, anchor_tokens, image, roi, scale, chosen_band), chosen_band)
    price = next(iter(unique))
    if votes.count(price) < 2:
        return EntryObservation(None, "NOT_FOUND", raw, band=chosen_band)
    token = _synthetic(price, image, roi, scale, chosen_band)
    return EntryObservation(price, "AGREED", raw, [token], chosen_band)


def _entry_prices(tokens: list[OCRToken]) -> set[Decimal]:
    levels, _direction = parse_tokens(tokens)
    prices = {level.price for level in levels if level.normalized_label == "ENTRY"}
    if prices:
        return prices
    for token in tokens:
        if not folded_is_bare_cdx(token.text):
            continue
        for other in tokens:
            if other.x1 < token.x1:
                continue
            if abs(other.cy - token.cy) > max(24, (token.y2 - token.y1) * 1.5):
                continue
            price = parse_price(other.text)
            if price is not None:
                prices.add(price)
    return prices


def _variants(band: Image.Image) -> list[tuple[str, Image.Image]]:
    gray = ImageOps.grayscale(band)
    auto = ImageOps.autocontrast(gray)

    def up(im: Image.Image) -> Image.Image:
        return im.resize((max(1, im.width * 4), max(1, im.height * 4)), Image.Resampling.LANCZOS)

    dark = up(gray.point(lambda value: min(255, int(value) * 8)))
    variants = [
        ("gray", up(auto)),
        ("invert", up(ImageOps.invert(auto))),
        ("dark", dark),
        ("dark_invert", ImageOps.invert(dark.convert("L"))),
    ]
    try:
        import cv2
        import numpy as np

        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        lifted = clahe.apply(np.asarray(gray))
        variants.append(("clahe", up(Image.fromarray(lifted))))
    except Exception:
        return variants
    return variants


def _recognize(engine, image: Image.Image) -> list[OCRToken]:
    from cdx_vision.ocr import TesseractOcr

    if isinstance(engine, TesseractOcr):
        return TesseractOcr(engine.executable, psm=_PSM).recognize(image)
    return engine.recognize(image)


def _dark_bands(image: Image.Image, roi: tuple[float, float, float, float]) -> list[tuple[int, int, int, int]]:
    import numpy as np

    width, height = image.size
    x1, y1 = int(width * roi[0]), int(height * roi[1])
    x2, y2 = int(width * roi[2]), int(height * roi[3])
    if x2 <= x1 or y2 <= y1:
        return []
    arr = np.asarray(image.crop((x1, y1, x2, y2)))
    if arr.ndim != 3:
        return []
    dark = (arr[:, :, 0] < 12) & (arr[:, :, 1] < 12) & (arr[:, :, 2] < 12)
    counts = dark.sum(axis=1)
    rows = [index for index, count in enumerate(counts.tolist()) if count >= 20]
    clusters: list[tuple[int, int]] = []
    start = prev = None
    for row in rows:
        if start is None:
            start = prev = row
            continue
        if row - prev <= 2:
            prev = row
            continue
        clusters.append((start, prev))
        start = prev = row
    if start is not None and prev is not None:
        clusters.append((start, prev))
    bands = []
    for top, bottom in clusters:
        if bottom - top < 5 or bottom - top > 28:
            continue
        pad = 22
        bands.append((x1, max(0, y1 + top - pad), x2, min(height, y1 + bottom + pad)))
    return bands


def _anchor_band(
    image: Image.Image,
    roi: tuple[float, float, float, float],
    tokens: list[OCRToken],
    scale: int,
) -> tuple[int, int, int, int] | None:
    from cdx_vision.parser import normalize_label

    def center(label: str) -> float | None:
        found = [token.cy for token in tokens if normalize_label(token.text) == label]
        if not found:
            return None
        return sum(found) / len(found)

    sl = center("SL")
    tp1 = center("TP1")
    if sl is None or tp1 is None or scale <= 0:
        return None
    width, height = image.size
    origin_y = int(height * roi[1])
    mid = origin_y + ((sl + tp1) / 2) / scale
    y1 = max(0, int(mid - 36))
    y2 = min(height, int(mid + 36))
    return (int(width * roi[0]), y1, int(width * roi[2]), y2)


def _synthetic(
    price: Decimal,
    image: Image.Image,
    roi: tuple[float, float, float, float],
    scale: int,
    band: tuple[int, int, int, int],
) -> OCRToken:
    origin_y = int(image.height * roi[1])
    center = (band[1] + band[3]) / 2
    y = max(0, int((center - origin_y) * scale))
    text = f"CDX ENTRY {format(price, 'f')}"
    return OCRToken(text, 8, y, 8 + 220, y + 18)


def _conflict_tokens(
    prices: set[Decimal],
    _anchor: list[OCRToken],
    image: Image.Image,
    roi: tuple[float, float, float, float],
    scale: int,
    band: tuple[int, int, int, int],
) -> list[OCRToken]:
    return [_synthetic(price, image, roi, scale, band) for price in sorted(prices)]


def _save_variant(folder: Path, name: str, image: Image.Image, tokens: list[OCRToken], prices: set[Decimal]) -> None:
    marked = image.convert("RGB")
    draw = ImageDraw.Draw(marked)
    accepted = len(prices) == 1
    for token in tokens:
        draw.rectangle((token.x1, token.y1, token.x2, token.y2), outline=(0, 255, 0) if accepted else (255, 64, 64))
        draw.text((token.x1, max(0, token.y1 - 12)), token.text, fill=(255, 255, 0))
    marked.save(folder / f"entry_{name}.png")
