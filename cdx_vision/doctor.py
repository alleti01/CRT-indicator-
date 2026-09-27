"""Local OCR health check. No network. No orders."""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cdx_vision.config import VisionConfig
from cdx_vision.parser import parse_tokens
from cdx_vision.tesseract_cmd import resolve_tesseract

_LINES = (
    "SL 30947.00",
    "CDX ENTRY 30909.50",
    "TP1 30872.00",
    "TP2 30845.00",
)


def synthetic_label_image() -> Image.Image:
    image = Image.new("RGB", (640, 220), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    y = 20
    for line in _LINES:
        draw.text((20, y), line, fill="black", font=font)
        y += 48
    return image


def main() -> int:
    print("OS", platform.platform())
    print("PYTHON", sys.version.split()[0], sys.executable)
    config = VisionConfig.from_env()
    print("CDX_VISION_ENABLED", config.enabled)
    print("CDX_VISION_SHADOW_ONLY", config.shadow_only)
    print("CDX_VISION_EXECUTION_ENABLED", config.execution_enabled)
    print("ORDERS", config.may_route_orders())
    for name in ("PIL", "cv2", "mss", "win32gui", "pytesseract"):
        print(name, "yes" if shutil.which("python") and _has(name) else "no")
    exe = resolve_tesseract()
    if not exe:
        print("TESSERACT MISSING")
        return 1
    version = subprocess.run([exe, "--version"], capture_output=True, text=True)
    print("TESSERACT", exe)
    print(version.stdout.splitlines()[0] if version.stdout else version.stderr)
    if version.returncode != 0:
        return 1
    from cdx_vision.ocr import TesseractOcr, preprocess

    image = preprocess(synthetic_label_image(), scale=3)
    tokens = TesseractOcr(exe, psm=6).recognize(image)
    levels, _direction = parse_tokens(tokens)
    found = {level.normalized_label: format(level.price, "f") for level in levels}
    print("PARSED", found)
    expected = {"SL": "30947.00", "ENTRY": "30909.50", "TP1": "30872.00", "TP2": "30845.00"}
    if found != expected:
        print("OCR_HEALTH_FAIL")
        debug = Path(tempfile.gettempdir()) / "cdx_vision_doctor.png"
        image.save(debug)
        print("debug", debug)
        return 1
    print("OCR_HEALTH_PASS")
    return 0


def _has(name: str) -> bool:
    try:
        __import__(name if name != "PIL" else "PIL")
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
