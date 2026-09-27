"""Find tesseract.exe without hard-coding one machine path."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

_KNOWN = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    Path.home() / "AppData" / "Local" / "Tesseract-OCR" / "tesseract.exe",
)


def resolve_tesseract(env: dict | None = None) -> str | None:
    """1. TESSERACT_CMD  2. PATH  3. known Windows install locations."""
    env = os.environ if env is None else env
    configured = (env.get("TESSERACT_CMD") or "").strip().strip('"')
    if configured and Path(configured).is_file():
        return str(Path(configured))
    found = shutil.which("tesseract")
    if found:
        return found
    for path in _KNOWN:
        if path.is_file():
            return str(path)
    return None
