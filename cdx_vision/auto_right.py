"""Pan TradingView right only when the current CDX trade is off screen.

Ctrl+Right is sent only after the TradingView window is foreground and focused.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from cdx_vision.models import OCRToken
from cdx_vision.window_locator import WindowInfo

VK_CONTROL = 0x11
VK_RIGHT = 0x27
KEYEVENTF_KEYUP = 0x0002


@dataclass
class NavigationState:
    triggered: bool = False
    attempts: int = 0
    success: bool = False
    reason: str = ""
    frames: list[list[OCRToken]] = field(default_factory=list)


class ChartNavigator:
    """Real keystrokes. Unit tests use a fake with the same methods."""

    def __init__(self, focus_x: float = 0.40, focus_y: float = 0.45) -> None:
        self.focus_x = focus_x
        self.focus_y = focus_y
        self.keypresses = 0

    def minimized(self, hwnd: int) -> bool:
        from cdx_vision.screen_capture import is_minimized

        return is_minimized(hwnd)

    def focus_and_confirm(self, window: WindowInfo) -> bool:
        import ctypes

        user32 = ctypes.windll.user32
        if self.minimized(window.hwnd):
            return False
        user32.ShowWindow(window.hwnd, 9)
        self._try_foreground(window.hwnd)
        if user32.GetForegroundWindow() != window.hwnd:
            return False
        width = max(window.width, 1)
        height = max(window.height, 1)
        x = int(window.left + width * self.focus_x)
        y = int(window.top + height * self.focus_y)
        user32.SetCursorPos(x, y)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        return user32.GetForegroundWindow() == window.hwnd

    def ctrl_right(self, window: WindowInfo) -> bool:
        import ctypes

        user32 = ctypes.windll.user32
        if user32.GetForegroundWindow() != window.hwnd:
            return False
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_RIGHT, 0, 0, 0)
        user32.keybd_event(VK_RIGHT, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        self.keypresses += 1
        return True

    def _try_foreground(self, hwnd: int) -> None:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if user32.GetForegroundWindow() == hwnd:
            return
        current = kernel32.GetCurrentThreadId()
        remote = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        target = user32.GetWindowThreadProcessId(hwnd, None)
        user32.AttachThreadInput(current, remote, True)
        user32.AttachThreadInput(current, target, True)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.AttachThreadInput(current, remote, False)
        user32.AttachThreadInput(current, target, False)


def run_navigation(
    *,
    window: WindowInfo,
    initial_tokens: list[OCRToken] | None,
    initial_visible: bool,
    read_once,
    navigator: ChartNavigator,
    max_attempts: int,
    redraw_s: float,
) -> NavigationState:
    """read_once returns (tokens, visible). It is not called when the first view is enough."""
    if initial_visible and initial_tokens is not None:
        return NavigationState(False, 0, True, "VISION_INITIAL_LEVELS_VISIBLE", [initial_tokens])
    state = NavigationState(True, 0, False, "VISION_AUTO_RIGHT_TRIGGERED")
    if navigator.minimized(window.hwnd):
        state.reason = "VISION_TRADINGVIEW_MINIMIZED"
        return state
    for _attempt in range(max(0, max_attempts)):
        if not navigator.focus_and_confirm(window):
            state.reason = "VISION_TRADINGVIEW_FOCUS_FAIL"
            return state
        if not navigator.ctrl_right(window):
            state.reason = "VISION_TRADINGVIEW_FOCUS_FAIL"
            return state
        state.attempts += 1
        if redraw_s:
            time.sleep(redraw_s)
        observed = read_once()
        if len(observed) == 3:
            tokens, visible, moved = observed
        else:
            tokens, visible = observed
            moved = True
        if not moved:
            state.reason = "VISION_AUTO_RIGHT_NO_MOVEMENT"
            return state
        if not visible or not tokens:
            continue
        if redraw_s:
            time.sleep(min(0.25, redraw_s))
        second_obs = read_once()
        second = second_obs[0]
        second_visible = second_obs[1]
        state.frames = [tokens]
        if second and second_visible:
            state.frames.append(second)
        state.success = True
        state.reason = "VISION_AUTO_RIGHT_LEVELS_FOUND"
        return state
    state.reason = "VISION_AUTO_RIGHT_EXHAUSTED"
    return state
