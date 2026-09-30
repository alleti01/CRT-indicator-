"""Read CDX prices from right-edge tags tied to horizontal lines.

A bare price-scale number is not a level. Screen Y is never turned into a price.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from cdx_vision.models import OCRToken, ParsedLevel, Reason
from cdx_vision.parser import parse_price

# Fractions of the TradingView window. The alerts sidebar starts near 0.80.
CHART_ROI = (0.08, 0.12, 0.72, 0.78)
LABEL_ROI = (0.18, 0.18, 0.70, 0.70)
TAG_ROI = (0.60, 0.16, 0.80, 0.72)
PRICE_SCALE_EXCLUSION = (0.78, 0.10, 0.84, 0.80)
ALERT_EXCLUSION = (0.80, 0.00, 1.00, 1.00)
TICK = Decimal("0.25")


@dataclass
class TagHit:
    text: str
    price: Decimal | None
    x1: int
    y1: int
    x2: int
    y2: int
    color: str
    line_y: int | None = None
    reject: str = ""

    @property
    def associated(self) -> bool:
        return self.line_y is not None and self.price is not None and not self.reject


@dataclass
class LineHit:
    y: int
    x1: int
    x2: int
    color: str


@dataclass
class VisibleRead:
    tokens: list[OCRToken] = field(default_factory=list)
    tags: list[TagHit] = field(default_factory=list)
    lines: list[LineHit] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    entry: Decimal | None = None
    entry_source: str = ""
    stop: Decimal | None = None
    tp1: Decimal | None = None
    tp2: Decimal | None = None
    known_price_role: str = "UNKNOWN"


def _crop(image: Image.Image, roi: tuple[float, float, float, float]) -> tuple[Image.Image, int, int]:
    width, height = image.size
    x1, y1, x2, y2 = roi
    box = (int(width * x1), int(height * y1), int(width * x2), int(height * y2))
    return image.crop(box), box[0], box[1]


def _masks(image: Image.Image):
    import numpy as np

    arr = np.asarray(image.convert("RGB"))
    red = arr[:, :, 0].astype(int)
    green = arr[:, :, 1].astype(int)
    blue = arr[:, :, 2].astype(int)
    return {
        "red": (red > 160) & (red > green + 30) & (red > blue + 20) & (green < 160),
        "green": (green > 170) & (green > red + 40) & (green > blue + 40) & (red < 160),
        "blue": (blue > 140) & (blue > red + 20) & (blue > green) & (red < 140),
    }


def _boxes(mask, min_w: int, max_w: int, min_h: int, max_h: int) -> list[tuple[int, int, int, int]]:
    import cv2
    import numpy as np

    binary = mask.astype(np.uint8) * 255
    count, _labels, stats, _cent = cv2.connectedComponentsWithStats(binary, 8)
    found = []
    for index in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[index])
        if not (min_w <= w <= max_w and min_h <= h <= max_h):
            continue
        if area < 0.35 * w * h:
            continue
        found.append((x, y, x + w, y + h))
    return found


def _lines(mask, min_run: int) -> list[tuple[int, int, int]]:
    import numpy as np

    height, width = mask.shape
    raw: list[tuple[int, int, int]] = []
    for y in range(height):
        row = mask[y]
        start = None
        for x in range(width + 1):
            on = x < width and bool(row[x])
            if on and start is None:
                start = x
            if not on and start is not None:
                if x - start >= min_run:
                    raw.append((y, start, x))
                start = None
    if not raw:
        return []
    merged: list[list[int]] = []
    for y, x1, x2 in raw:
        if merged and y - merged[-1][0] <= 2 and abs(x1 - merged[-1][1]) < 30:
            merged[-1][0] = y
            merged[-1][1] = min(merged[-1][1], x1)
            merged[-1][2] = max(merged[-1][2], x2)
        else:
            merged.append([y, x1, x2])
    return [(y, x1, x2) for y, x1, x2 in merged]


def _ocr_tag(image: Image.Image, box: tuple[int, int, int, int], engine) -> str:
    x1, y1, x2, y2 = box
    pad = 2
    crop = image.crop((max(0, x1 - pad), max(0, y1 - pad), min(image.width, x2 + pad), min(image.height, y2 + pad)))
    gray = ImageOps.autocontrast(ImageOps.grayscale(crop))
    gray = gray.resize((max(1, gray.width * 4), max(1, gray.height * 4)), Image.Resampling.NEAREST)
    executable = getattr(engine, "executable", "")
    if executable:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = executable
        return pytesseract.image_to_string(
            gray,
            config="--psm 7 -c tessedit_char_whitelist=0123456789.,",
        )
    return "".join(token.text for token in engine.recognize(gray))


def read_visible_tags(image: Image.Image, engine) -> tuple[list[TagHit], list[LineHit]]:
    """Tags inside the right-edge ROI. Unassociated tags are not CDX levels."""
    chart, chart_x, chart_y = _crop(image, CHART_ROI)
    tag_img, tag_x, tag_y = _crop(image, TAG_ROI)
    chart_masks = _masks(chart)
    tag_masks = _masks(tag_img)
    min_run = max(40, int(chart.width * 0.22))
    lines: list[LineHit] = []
    for color, mask in chart_masks.items():
        for y, x1, x2 in _lines(mask, min_run):
            lines.append(LineHit(chart_y + y, chart_x + x1, chart_x + x2, color))
    tags: list[TagHit] = []
    for color, mask in tag_masks.items():
        for x1, y1, x2, y2 in _boxes(mask, 28, 220, 8, 40):
            abs_box = (tag_x + x1, tag_y + y1, tag_x + x2, tag_y + y2)
            text = _ocr_tag(image, abs_box, engine)
            price = parse_price(text, TICK)
            cy = (abs_box[1] + abs_box[3]) / 2
            line_y = None
            best = None
            for line in lines:
                if line.color != color:
                    continue
                gap = abs(line.y - cy)
                if gap > 18:
                    continue
                if best is None or gap < best:
                    best = gap
                    line_y = line.y
            reject = ""
            if price is None:
                reject = Reason.VISION_OFF_TICK.value if any(ch.isdigit() for ch in text) else "NO_PRICE"
            elif line_y is None:
                reject = "NO_CDX_LINE"
            tags.append(
                TagHit(text, price, abs_box[0], abs_box[1], abs_box[2], abs_box[3], color, line_y, reject)
            )
    return tags, lines


def _label_token(label: str, price: Decimal, x: int, y: int, source: str) -> OCRToken:
    return OCRToken(f"{label} {price} {source}", x, y, x + 80, y + 16)


def assemble(
    tags: list[TagHit],
    *,
    direction: str,
    webhook_price: Decimal | None,
    label_levels: list[ParsedLevel] | None = None,
) -> VisibleRead:
    """Build SL/TP tokens only from line-associated on-tick tags. Never invent a price."""
    read = VisibleRead(tags=list(tags))
    associated = [tag for tag in tags if tag.associated]
    label_levels = label_levels or []
    label_sl = [level.price for level in label_levels if level.normalized_label == "SL"]
    label_tp1 = [level.price for level in label_levels if level.normalized_label == "TP1"]
    label_tp2 = [level.price for level in label_levels if level.normalized_label == "TP2"]

    sl_tags = [tag for tag in associated if tag.color == "red"]
    tp_tags = [tag for tag in associated if tag.color == "green"]
    entry = webhook_price
    read.entry_source = "WEBHOOK" if webhook_price is not None else ""
    for level in label_levels:
        if level.normalized_label == "ENTRY":
            entry = level.price
            read.entry_source = "VISION"
            break
    read.entry = entry
    if entry is None:
        read.reasons.append(Reason.VISION_REJECT_ENTRY_UNAVAILABLE.value)
        return read

    def on_side(tag: TagHit, profit: bool) -> bool:
        if direction == "LONG":
            return tag.price > entry if profit else tag.price < entry
        if direction == "SHORT":
            return tag.price < entry if profit else tag.price > entry
        return False

    stops = [tag for tag in sl_tags if on_side(tag, False)]
    targets = [tag for tag in tp_tags if on_side(tag, True)]
    targets.sort(key=lambda tag: abs(tag.price - entry))
    if len(stops) != 1:
        read.reasons.append(Reason.VISION_SL_NOT_FOUND.value)
    else:
        read.stop = stops[0].price
        if label_sl and label_sl[0] != read.stop:
            read.reasons.append(Reason.VISION_LEVEL_CONFLICT.value)
            read.stop = None
    if not targets:
        read.reasons.append(Reason.VISION_TP1_NOT_FOUND.value)
        read.reasons.append(Reason.VISION_TP2_NOT_FOUND.value)
    else:
        read.tp1 = targets[0].price
        if len(targets) < 2:
            read.reasons.append(Reason.VISION_TP2_NOT_FOUND.value)
        else:
            read.tp2 = targets[1].price
            if direction == "LONG" and not (read.tp2 > read.tp1 > entry):
                read.reasons.append(Reason.VISION_INVALID_ORDERING.value)
                read.tp1 = read.tp2 = None
            if direction == "SHORT" and not (entry > read.tp1 > read.tp2):
                read.reasons.append(Reason.VISION_INVALID_ORDERING.value)
                read.tp1 = read.tp2 = None
            if label_tp1 and read.tp1 is not None and label_tp1[0] != read.tp1:
                read.reasons.append(Reason.VISION_LEVEL_CONFLICT.value)
                read.tp1 = read.tp2 = None
            if label_tp2 and read.tp2 is not None and label_tp2[0] != read.tp2:
                read.reasons.append(Reason.VISION_LEVEL_CONFLICT.value)
                read.tp1 = read.tp2 = None
    if read.stop is None or read.tp1 is None or read.tp2 is None or read.reasons:
        return read
    anchor_x = max(tag.x1 for tag in associated) if associated else 700
    read.tokens = [
        _label_token("SL", read.stop, anchor_x, 40, "LINE_ASSOCIATED_TAG"),
        _label_token("TP1", read.tp1, anchor_x, 80, "LINE_ASSOCIATED_TAG"),
        _label_token("TP2", read.tp2, anchor_x, 120, "LINE_ASSOCIATED_TAG"),
    ]
    if read.entry_source == "VISION" and entry is not None:
        read.tokens.append(_label_token("CDX ENTRY", entry, anchor_x, 60, "LABEL_OCR"))
    return read


def role_of(price: Decimal, read: VisibleRead) -> str:
    if read.stop == price:
        return "SL"
    if read.tp1 == price:
        return "TP1"
    if read.tp2 == price:
        return "TP2"
    if read.entry == price and read.entry_source == "VISION":
        return "ENTRY"
    for tag in read.tags:
        if tag.price != price:
            continue
        if tag.reject == "NO_CDX_LINE":
            return "CURRENT_PRICE"
        if tag.associated:
            return "OTHER"
    return "UNKNOWN"


def vertical_clip(lines: list[LineHit], image_height: int, roi: tuple[float, float, float, float] = CHART_ROI) -> bool:
    top = int(image_height * roi[1])
    bottom = int(image_height * roi[3])
    return any(abs(line.y - top) <= 3 or abs(line.y - bottom) <= 3 for line in lines)


def save_debug(directory: Path, image: Image.Image, read: VisibleRead, meta: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    image.save(directory / "01_full_capture.png")
    chart, _, _ = _crop(image, CHART_ROI)
    chart.save(directory / "02_chart_roi.png")
    labels, _, _ = _crop(image, LABEL_ROI)
    labels.save(directory / "03_level_label_roi.png")
    tags, _, _ = _crop(image, TAG_ROI)
    tags.save(directory / "04_right_edge_tag_roi.png")
    overlay = image.convert("RGB")
    draw = ImageDraw.Draw(overlay)
    for line in read.lines:
        draw.line((line.x1, line.y, line.x2, line.y), fill=_ink(line.color), width=2)
    overlay.save(directory / "05_detected_lines.png")
    for tag in read.tags:
        draw.rectangle((tag.x1, tag.y1, tag.x2, tag.y2), outline=_ink(tag.color), width=2)
    overlay.save(directory / "06_detected_tags.png")
    overlay.save(directory / "07_ocr_boxes.png")
    overlay.save(directory / "08_candidate_groups.png")
    overlay.save(directory / "09_final_rejections.png")
    payload = {
        "reasons": read.reasons,
        "entry": _num(read.entry),
        "entry_source": read.entry_source,
        "stop": _num(read.stop),
        "tp1": _num(read.tp1),
        "tp2": _num(read.tp2),
        "lines": [line.__dict__ for line in read.lines],
        "tags": [
            {
                "text": tag.text,
                "price": _num(tag.price),
                "color": tag.color,
                "line_y": tag.line_y,
                "reject": tag.reject,
                "box": [tag.x1, tag.y1, tag.x2, tag.y2],
            }
            for tag in read.tags
        ],
        **meta,
    }
    (directory / "debug.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _ink(color: str) -> tuple[int, int, int]:
    return {"red": (255, 60, 60), "green": (40, 220, 80), "blue": (60, 120, 255)}.get(color, (255, 255, 0))


def _num(price: Decimal | None) -> str:
    return "" if price is None else format(price, "f")
