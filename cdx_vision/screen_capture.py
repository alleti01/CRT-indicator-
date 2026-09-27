"""Capture the TradingView app window. Reject a blank PrintWindow image."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from PIL import Image

from cdx_vision.window_locator import WindowInfo


@dataclass(frozen=True)
class Capture:
    image: Image.Image
    method: str


def _aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            return


def is_minimized(hwnd: int) -> bool:
    return bool(ctypes.windll.user32.IsIconic(hwnd))


def image_is_usable(image: Image.Image) -> bool:
    if image.width < 80 or image.height < 80:
        return False
    sample = list(image.convert("L").resize((64, 36)).getdata())
    mean = sum(sample) / len(sample)
    var = sum((p - mean) ** 2 for p in sample) / len(sample)
    return mean > 8 and var > 20


def _printwindow(hwnd: int) -> Image.Image | None:
    from cdx_vision.capture import capture_window_image

    return capture_window_image(hwnd)


def _screen_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    if width <= 0 or height <= 0:
        return None
    return int(rect.left), int(rect.top), width, height


def _mss(hwnd: int) -> Image.Image | None:
    box = _screen_rect(hwnd)
    if box is None:
        return None
    left, top, width, height = box
    import mss

    with mss.mss() as sct:
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def capture_window(window: WindowInfo) -> Capture | None:
    _aware()
    if is_minimized(window.hwnd):
        return None
    printed = _printwindow(window.hwnd)
    if printed is not None and image_is_usable(printed):
        return Capture(printed, "PRINTWINDOW")
    grabbed = _mss(window.hwnd)
    if grabbed is not None and image_is_usable(grabbed):
        return Capture(grabbed, "MSS_SCREEN_REGION")
    return None
