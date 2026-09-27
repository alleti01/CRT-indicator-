"""Capture source. Tests inject images or skip the screen entirely."""
from __future__ import annotations

from pathlib import Path

from PIL import Image


class ImageCaptureSource:
    """Fixture PNGs stand in for the screen. CI does not need TradingView."""

    def __init__(self, paths: list[Path]) -> None:
        self.paths = paths

    def capture_frames(self) -> list[Image.Image]:
        return [Image.open(path).convert("RGB") for path in self.paths]


def capture_window_image(hwnd: int) -> Image.Image | None:
    """Capture a window client area with Win32. Returns None if the window is gone."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    if not user32.IsWindow(hwnd):
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    width, height = int(rect.right), int(rect.bottom)
    if width <= 0 or height <= 0:
        return None
    hwnd_dc = user32.GetDC(hwnd)
    if not hwnd_dc:
        return None
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    # 2 = PW_RENDERFULLCONTENT so a background browser still paints.
    printed = bool(user32.PrintWindow(hwnd, mem_dc, 2))
    if not printed:
        gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, 0x00CC0020)
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    info = BITMAPINFOHEADER()
    info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.biWidth = width
    info.biHeight = -height
    info.biPlanes = 1
    info.biBitCount = 32
    info.biCompression = 0
    buf = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(info), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)
    image = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)
    return image.convert("RGB")
