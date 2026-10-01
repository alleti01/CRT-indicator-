"""Level OCR crop. The scan box follows the chart pane, not a fixed 78% cut."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from PIL import Image

from cdx_vision.models import OCRToken, Reason

# The old window crop. Kept so the regression can prove it clips the labels.
OLD_LEVEL_ROI = (0.18, 0.10, 0.78, 0.88)
_EDGE_MARGIN = 8


@dataclass
class ChartPane:
    left: int
    top: int
    right: int
    bottom: int

    def as_fractions(self, size: tuple[int, int]) -> tuple[float, float, float, float]:
        width, height = size
        return (
            self.left / width,
            self.top / height,
            self.right / width,
            self.bottom / height,
        )


@dataclass
class LevelCrop:
    box: tuple[int, int, int, int]
    pane: ChartPane
    base_box: tuple[int, int, int, int] = (0, 0, 0, 0)
    attempts: int = 0
    truncated: bool = False
    unresolved: bool = False
    reasons: list[str] = field(default_factory=list)
    tokens: list[OCRToken] = field(default_factory=list)


LAST: LevelCrop | None = None


def _fractions() -> tuple[float, float]:
    start = float(os.environ.get("CDX_LEVEL_ROI_X_START", "0.45"))
    end = float(os.environ.get("CDX_LEVEL_ROI_X_END", "0"))
    return start, end


def detect_chart_pane_bounds(image: Image.Image) -> ChartPane:
    """Right edge is the chart gutter before the side toolbar. Labels sit inside it."""
    import numpy as np

    gray = np.asarray(image.convert("L"))
    height, width = gray.shape
    band = gray[int(height * 0.16): int(height * 0.84)]
    means = band.mean(axis=0)
    stds = band.std(axis=0)
    # Stop at the left edge of the right-hand toolbar. A dark chart background is not the edge.
    rail = width - 1
    seen = False
    for x in range(width - 2, int(width * 0.80), -1):
        if stds[x] > 40:
            rail = x
            seen = True
        elif seen and stds[x] < 22:
            break
        elif seen:
            rail = x
    right = min(max(int(width * 0.82), rail - 6), int(width * 0.86))
    left = int(width * 0.06)
    for x in range(int(width * 0.02), int(width * 0.18)):
        if stds[x] > 15 and means[x] > 30:
            left = x
            break
    return ChartPane(left, int(height * 0.12), max(left + 20, right), int(height * 0.88))


def level_box(image: Image.Image, pane: ChartPane | None = None) -> tuple[int, int, int, int]:
    """Right-half of the chart pane through the pane's right edge."""
    pane = pane or detect_chart_pane_bounds(image)
    width, height = image.size
    start, end = _fractions()
    span = max(1, pane.right - pane.left)
    left = pane.left + int(span * start)
    right = pane.right
    if end > 0:
        right = min(right, int(width * end))
    top = pane.top
    bottom = pane.bottom
    return (max(0, left), max(0, top), min(width, right), min(height, bottom))


def old_level_box(image: Image.Image) -> tuple[int, int, int, int]:
    width, height = image.size
    x1, y1, x2, y2 = OLD_LEVEL_ROI
    return (int(width * x1), int(height * y1), int(width * x2), int(height * y2))


def _words(image: Image.Image, engine) -> list[OCRToken]:
    import pytesseract
    from pytesseract import Output

    pytesseract.pytesseract.tesseract_cmd = engine.executable
    data = pytesseract.image_to_data(image, output_type=Output.DICT, config="--psm 6")
    tokens: list[OCRToken] = []
    for index, text in enumerate(data.get("text") or []):
        cleaned = (text or "").strip()
        if not cleaned:
            continue
        x = int(data["left"][index])
        y = int(data["top"][index])
        w = int(data["width"][index])
        h = int(data["height"][index])
        tokens.append(OCRToken(cleaned, x, y, x + w, y + h))
    return tokens


def ocr_box(image: Image.Image, box: tuple[int, int, int, int], engine) -> list[OCRToken]:
    """Raw OCR. The crop is not enlarged until its edges are known to be clear."""
    crop = image.crop(box)
    tokens: list[OCRToken] = []
    origin_x, origin_y = box[0], box[1]
    strip = 120
    step = 100
    top = 0
    while top < crop.height:
        bottom = min(crop.height, top + strip)
        part = crop.crop((0, top, crop.width, bottom))
        if part.height < 24:
            break
        for token in _words(part, engine):
            tokens.append(
                OCRToken(
                    token.text,
                    origin_x + token.x1,
                    origin_y + top + token.y1,
                    origin_x + token.x2,
                    origin_y + top + token.y2,
                )
            )
        if bottom >= crop.height:
            break
        top += step
    unique: list[OCRToken] = []
    for token in tokens:
        if any(
            token.text == prior.text and abs(token.y1 - prior.y1) < 18 and abs(token.x1 - prior.x1) < 24
            for prior in unique
        ):
            continue
        unique.append(token)
    return unique


def _looks_cut(text: str) -> bool:
    compact = text.replace(" ", "")
    if compact.endswith(",") or compact.endswith("_"):
        return True
    if "SL_" in compact.upper() and "." not in compact:
        return True
    return False


def roi_truncated(tokens: list[OCRToken], box: tuple[int, int, int, int], margin: int = _EDGE_MARGIN) -> bool:
    """True when a label or price is cut by the right edge of the crop."""
    right = box[2]
    for token in tokens:
        labelish = any(part in token.text.upper() for part in ("ENTRY", "SL", "TP", "CDX"))
        priceish = sum(ch.isdigit() for ch in token.text) >= 4
        if not (labelish or priceish):
            continue
        touches_right = token.x2 >= right - margin
        if touches_right or (_looks_cut(token.text) and touches_right):
            return True
    return False


def _expand(box: tuple[int, int, int, int], max_right: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    gap = max_right - right
    if gap <= 2:
        return box
    return (left, top, right + max(8, gap // 2), bottom)


def resolve_level_crop(image: Image.Image, engine, *, base: tuple[int, int, int, int] | None = None) -> LevelCrop:
    """OCR the chart-pane crop. Expand at most twice if text is cut off."""
    global LAST
    pane = detect_chart_pane_bounds(image)
    box = base or level_box(image, pane)
    max_right = min(image.size[0] - 1, max(pane.right, box[2]))
    tokens = ocr_box(image, box, engine)
    truncated = roi_truncated(tokens, box)
    reasons: list[str] = []
    attempts = 0
    if truncated:
        reasons.append(Reason.VISION_ROI_TRUNCATED.value)
    while truncated and attempts < 2:
        widened = _expand(box, max_right)
        if widened == box:
            break
        box = widened
        attempts += 1
        reasons.append(Reason.VISION_ROI_EXPANDED.value)
        tokens = ocr_box(image, box, engine)
        truncated = roi_truncated(tokens, box)
    if attempts and not truncated:
        reasons.append(Reason.VISION_ROI_EXPANSION_SUCCESS.value)
    unresolved = truncated
    if unresolved:
        reasons.append(Reason.VISION_ROI_TRUNCATION_UNRESOLVED.value)
        reasons.append(Reason.VISION_LABEL_PARTIAL.value)
    state = LevelCrop(box, pane, base or box, attempts, truncated, unresolved, reasons, tokens)
    LAST = state
    return state
