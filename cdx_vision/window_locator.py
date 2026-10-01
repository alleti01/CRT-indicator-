"""Find a visible TradingView window. Does not click or send keys."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


def list_windows(title_contains: str = "") -> list[WindowInfo]:
    user32 = ctypes.windll.user32
    found: list[WindowInfo] = []
    needle = title_contains.lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if needle and needle not in title.lower():
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        found.append(WindowInfo(int(hwnd), title, rect.left, rect.top, rect.right, rect.bottom))
        return True

    user32.EnumWindows(_enum, 0)
    return found


def _process_name(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    access = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
    handle = kernel32.OpenProcess(access, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(512)
        buf = ctypes.create_unicode_buffer(512)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name.lower()
    finally:
        kernel32.CloseHandle(handle)
    return ""


_TRADINGVIEW_PROCESS = "tradingview.exe"


def select_bot_window(windows: list[WindowInfo], title_pattern: str) -> WindowInfo | None:
    """The calibrated chart. Does not fall through to a random TradingView window."""
    needle = (title_pattern or "").lower()
    if not needle:
        return None
    matches = [window for window in windows if needle in window.title.lower()]
    if not matches:
        return None
    return max(matches, key=lambda window: window.width * window.height)


def list_tradingview_windows() -> list[WindowInfo]:
    """Visible windows owned by the TradingView desktop app only."""
    hits = []
    for window in list_windows(""):
        if _process_name(window.hwnd) != _TRADINGVIEW_PROCESS:
            continue
        if window.width < 400 or window.height < 300:
            continue
        hits.append(window)
    return hits
