"""Read the TP2 price from its own line. The number has to be in the pixels."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

from cdx_vision.models import OCRToken
from cdx_vision.parser import normalize_label, parse_price

_TICK = Decimal("0.25")


@dataclass
class TP2Attempt:
    method: str
    text: str
    price: Decimal | None
    labeled: bool


@dataclass
class TP2Read:
    tokens: list[OCRToken] = field(default_factory=list)
    attempts: list[TP2Attempt] = field(default_factory=list)
    line_y: int | None = None
    box: tuple[int, int, int, int] | None = None
    edge_contact: bool = False
    expansions: int = 0
    accepted: bool = False


LAST_TP2: TP2Read | None = None


def _green_lines(image: Image.Image) -> list[int]:
    import numpy as np

    arr = np.asarray(image.convert("RGB"))
    height, width, _ = arr.shape
    x1, x2 = int(width * 0.35), int(width * 0.88)
    red = arr[:, x1:x2, 0].astype(int)
    green = arr[:, x1:x2, 1].astype(int)
    blue = arr[:, x1:x2, 2].astype(int)
    mask = (green > 140) & (green > red + 30) & (green > blue + 15)
    rows = []
    for y in range(int(height * 0.35), int(height * 0.82)):
        if int(mask[y].sum()) >= 80:
            rows.append(y)
    if not rows:
        return []
    lines = [rows[0]]
    for y in rows[1:]:
        if y - lines[-1] > 8:
            lines.append(y)
    return lines


def _variants(raw: Image.Image) -> list[tuple[str, Image.Image]]:
    gray = ImageOps.grayscale(raw)
    contrast = ImageEnhance.Contrast(gray).enhance(2.5)
    return [
        ("RAW", raw),
        ("2X", raw.resize((raw.width * 2, raw.height * 2), Image.Resampling.LANCZOS)),
        ("3X", raw.resize((raw.width * 3, raw.height * 3), Image.Resampling.LANCZOS)),
        ("6X", raw.resize((raw.width * 6, raw.height * 6), Image.Resampling.LANCZOS)),
        ("GRAYSCALE", gray.resize((gray.width * 3, gray.height * 3), Image.Resampling.LANCZOS)),
        ("CONTRAST", contrast.resize((contrast.width * 3, contrast.height * 3), Image.Resampling.LANCZOS)),
        ("INVERT", ImageOps.invert(gray).resize((gray.width * 3, gray.height * 3), Image.Resampling.LANCZOS)),
        ("THRESHOLD", contrast.point(lambda p: 255 if p > 140 else 0).resize(
            (contrast.width * 3, contrast.height * 3), Image.Resampling.NEAREST
        )),
    ]


def _ocr(image: Image.Image) -> str:
    import pytesseract

    from cdx_vision.tesseract_cmd import resolve_tesseract

    pytesseract.pytesseract.tesseract_cmd = resolve_tesseract()
    return " ".join(pytesseract.image_to_string(image, config="--psm 7").split())


def _band(image: Image.Image, line_y: int, *, left_pad: int = 210) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """A short band above the target line. Taller bands let the ribbon cut the first digit."""
    width, height = image.size
    right = min(width - 1, int(width * 0.856))
    left = max(0, right - int(width * 0.132) - left_pad)
    top = max(0, line_y - 15)
    bottom = min(height, line_y + 1)
    box = (left, top, right, bottom)
    return image.crop(box), box


def _touches_edge(box: tuple[int, int, int, int], size: tuple[int, int]) -> bool:
    left, top, right, bottom = box
    width, height = size
    return left <= 2 or top <= 2 or right >= width - 2 or bottom >= height - 2


def read_tp2(image: Image.Image, *, debug_dir: Path | None = None) -> TP2Read:
    """OCR each green target line. Keep a price only when the text says TP2."""
    global LAST_TP2
    result = TP2Read()
    lines = _green_lines(image)
    if not lines:
        LAST_TP2 = result
        return result
    # The upper target is the first one to try. Each line gets its own crop.
    labeled: dict[Decimal, str] = {}
    chosen_box = None
    chosen_line = None
    chosen_raw = None
    for line_y in lines:
        left_pad = 0
        for _expansion in range(3):
            raw, box = _band(image, line_y, left_pad=left_pad)
            if _touches_edge(box, image.size):
                result.edge_contact = True
            big = raw.resize((raw.width * 6, raw.height * 6), Image.Resampling.LANCZOS)
            text = _ocr(big)
            price = parse_price(text, _TICK)
            is_tp2 = normalize_label(text) == "TP2"
            result.attempts.append(TP2Attempt("6X", text, price, is_tp2))
            if is_tp2 and price is not None:
                labeled[price] = text
                chosen_box = box
                chosen_line = line_y
                chosen_raw = raw
                break
            if result.edge_contact and result.expansions < 2:
                result.expansions += 1
                left_pad += 40
                continue
            break
        if labeled:
            break
    if chosen_raw is not None:
        for name, variant in _variants(chosen_raw):
            if name == "6X":
                continue
            text = _ocr(variant)
            price = parse_price(text, _TICK)
            result.attempts.append(TP2Attempt(name, text, price, normalize_label(text) == "TP2"))
    result.line_y = chosen_line
    result.box = chosen_box
    agreed = {item.price for item in result.attempts if item.labeled and item.price is not None}
    if len(agreed) > 1:
        labeled.clear()
    if len(labeled) == 1 and chosen_box is not None:
        price = next(iter(labeled))
        left, top, right, bottom = chosen_box
        result.tokens.append(OCRToken(f"TP2 {price}", left, top, right, bottom))
        result.accepted = True
    LAST_TP2 = result
    if debug_dir is not None and chosen_box is not None:
        _save_debug(image, chosen_box, debug_dir)
    return result


def _save_debug(image: Image.Image, box: tuple[int, int, int, int], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    raw = image.crop(box)
    raw.save(folder / "tp2_raw.png")
    raw.save(folder / "tp2_padded.png")
    context = image.crop(
        (
            max(0, box[0] - 40),
            max(0, box[1] - 30),
            min(image.width, box[2] + 40),
            min(image.height, box[3] + 30),
        )
    )
    context.save(folder / "tp2_full_context.png")
    for name, variant in _variants(raw):
        safe = name.lower()
        variant.save(folder / f"tp2_{safe}.png")
