"""Pan TradingView right only when the current CDX trade is off screen.

Ctrl+Right is sent only after the TradingView window is foreground and focused.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from cdx_vision.models import OCRToken
from cdx_vision.window_locator import WindowInfo

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_LEFT = 0x25
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

    def arrow_left(self, window: WindowInfo) -> bool:
        """One small step back toward the live price. No Ctrl, so it does not jump."""
        import ctypes

        user32 = ctypes.windll.user32
        if user32.GetForegroundWindow() != window.hwnd:
            return False
        user32.keybd_event(VK_LEFT, 0, 0, 0)
        user32.keybd_event(VK_LEFT, 0, KEYEVENTF_KEYUP, 0)
        self.keypresses += 1
        return True

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

    def reset_chart_view(self, window: WindowInfo) -> bool:
        """Alt+Shift+Right. Jumps to the latest bar so the chart follows price again.

        Alt+R is not used. On this chart it opens the signal settings.
        """
        import ctypes

        user32 = ctypes.windll.user32
        if not self.focus_and_confirm(window):
            return False
        if user32.GetForegroundWindow() != window.hwnd:
            return False
        user32.keybd_event(VK_ESCAPE, 0, 0, 0)
        user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_SHIFT, 0, 0, 0)
        user32.keybd_event(VK_RIGHT, 0, 0, 0)
        user32.keybd_event(VK_RIGHT, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
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


def price_on_the_right(image) -> float:
    """Where the last candle sits, as a fraction of the window width.

    Horizontal CDX lines run across the empty future, so only a tall candle
    body counts. The price scale on the far right is ignored. No candle
    returns 1.0 so a blank capture is not treated as an offset.
    """
    import numpy as np

    arr = np.asarray(image)
    height, width = arr.shape[:2]
    if width < 80 or height < 80:
        return 1.0
    y0, y1 = int(height * 0.18), int(height * 0.78)
    x1 = int(width * 0.78)
    body = arr[y0:y1, :x1]
    red = body[:, :, 0].astype(int)
    green = body[:, :, 1].astype(int)
    blue = body[:, :, 2].astype(int)
    color = ((red > 150) & (red > green + 40) & (red > blue + 40)) | (
        (green > 140) & (green > red + 30) & (green > blue + 20)
    )
    last = -1
    for x in range(color.shape[1]):
        run = peak = 0
        for on in color[:, x]:
            run = run + 1 if on else 0
            if run > peak:
                peak = run
        if peak >= 8:
            last = x
    if last < 0:
        return 1.0
    return last / width


def follow_live_price(window: WindowInfo, navigator: ChartNavigator, capture, *, max_steps: int = 16) -> int:
    """Scroll the chart back until the last candle sits on the right again.

    Ctrl+Right leaves empty future on the screen. TradingView then waits for
    someone to drag that space away. This does that scroll. It stops as soon
    as the picture stops moving, so it does not walk off into old bars.
    """
    shot = capture(window)
    if shot is None:
        return 0
    frac = price_on_the_right(shot.image)
    if frac >= 0.62:
        return 0
    if not navigator.focus_and_confirm(window):
        return 0
    steps = 0
    previous = frac
    for _ in range(max_steps):
        if not navigator.arrow_left(window):
            break
        time.sleep(0.12)
        shot = capture(window)
        if shot is None:
            break
        frac = price_on_the_right(shot.image)
        steps += 1
        if frac >= 0.68:
            break
        if frac <= previous + 0.008:
            break
        previous = frac
    return steps
