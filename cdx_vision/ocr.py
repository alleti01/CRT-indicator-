"""Deterministic crops. OCR is pluggable and local. No network calls."""
from __future__ import annotations

from PIL import Image, ImageOps

from cdx_vision.models import OCRToken


def chart_crop(image: Image.Image, roi: tuple[float, float, float, float] = (0.05, 0.08, 0.82, 0.92)) -> Image.Image:
    """Normalized ROI (x1, y1, x2, y2) relative to the window image."""
    width, height = image.size
    x1, y1, x2, y2 = roi
    box = (int(width * x1), int(height * y1), int(width * x2), int(height * y2))
    return image.crop(box)


def preprocess(image: Image.Image, scale: int = 2) -> Image.Image:
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray)
    if scale > 1:
        gray = gray.resize((gray.width * scale, gray.height * scale), Image.Resampling.BICUBIC)
    return gray


class OcrEngine:
    def recognize(self, image: Image.Image) -> list[OCRToken]:
        return []


class TokenOcr(OcrEngine):
    """Test double. Returns the tokens supplied for each recognize() call."""

    def __init__(self, frames: list[list[OCRToken]]) -> None:
        self.frames = list(frames)
        self.calls = 0

    def recognize(self, image: Image.Image) -> list[OCRToken]:
        if self.calls >= len(self.frames):
            return []
        tokens = self.frames[self.calls]
        self.calls += 1
        return tokens
