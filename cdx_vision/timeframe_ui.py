"""Detect and restore the 3-minute bot chart. Does not place orders."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from cdx_vision.chart_state import detect_timeframe
from cdx_vision.models import Reason


@dataclass
class TimeframeState:
    ok: bool
    detected: str
    initial: str
    reasons: list[str] = field(default_factory=list)
    restore_attempted: bool = False


def _ocr_words(image, engine) -> list[tuple[str, int, int]]:
    tokens = list(engine.recognize(image))
    return [(token.text, token.x1, token.y1) for token in tokens]


def _send_input(flags: int, data: int = 0) -> None:
    import ctypes

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("mi", MOUSEINPUT)]

    extra = ctypes.c_ulong(0)
    event = INPUT(0, MOUSEINPUT(0, 0, data & 0xFFFFFFFF, flags, 0, ctypes.pointer(extra)))
    ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


def _click(x: int, y: int) -> None:
    import ctypes

    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    _send_input(0x0002)
    time.sleep(0.04)
    _send_input(0x0004)


def _scroll_down(x: int, y: int, notches: int = 1) -> None:
    import ctypes

    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    for _ in range(notches):
        _send_input(0x0800, -120)
        time.sleep(0.08)


def _screen_point(window, image, ix: float, iy: float) -> tuple[int, int]:
    sx = image.size[0] / max(window.width, 1)
    sy = image.size[1] / max(window.height, 1)
    return int(window.left + ix / sx), int(window.top + iy / sy)


def _foreground_is(window) -> bool:
    import ctypes

    from cdx_vision.screen_capture import is_minimized
    from cdx_vision.window_locator import _process_name

    user32 = ctypes.windll.user32
    if is_minimized(window.hwnd):
        return False
    if user32.GetForegroundWindow() != window.hwnd:
        return False
    return _process_name(window.hwnd) == "tradingview.exe"


def _find_word(words, predicate, *, max_x_fraction: float, width: int):
    hits = [item for item in words if item[1] <= width * max_x_fraction and predicate(item[0])]
    if not hits:
        return None
    hits.sort(key=lambda item: item[1])
    return hits[0]


def _send_vk(vk: int) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 0x0002, 0)


def _menu_lines(image, engine) -> list[tuple[int, int, str]]:
    """Lines in the interval menu. Plain OCR. Thresholding erased the highlighted row."""
    import pytesseract
    from pytesseract import Output

    pytesseract.pytesseract.tesseract_cmd = engine.executable
    data = pytesseract.image_to_data(image, output_type=Output.DICT, config="--psm 6")
    words = []
    for index, text in enumerate(data.get("text") or []):
        cleaned = (text or "").strip()
        if cleaned:
            words.append((cleaned, int(data["left"][index]), int(data["top"][index])))
    words.sort(key=lambda item: (item[2], item[1]))
    lines: list[tuple[int, int, list[str]]] = []
    for text, x, y in words:
        if lines and abs(y - lines[-1][0]) <= 16:
            lines[-1][2].append(text)
            continue
        lines.append((y, x, [text]))
    return [(y, x, " ".join(parts)) for y, x, parts in lines]


def _select_menu_row(window, engine, button_xy: tuple[float, float], number: str, unit: str) -> bool:
    """Open the interval menu and click the requested row. Scrolls until it is visible."""
    from cdx_vision.chart_state import menu_row_matches
    from cdx_vision.screen_capture import _mss

    if not _foreground_is(window):
        return False
    _click(*button_xy)
    time.sleep(0.4)
    origin_x = int(button_xy[0])
    origin_y = int(button_xy[1])
    for _ in range(8):
        if not _foreground_is(window):
            return False
        screen = _mss(window.hwnd)
        if screen is None:
            return False
        left = max(0, int(origin_x - window.left) - 30)
        top = max(0, int(origin_y - window.top) + 8)
        right = min(screen.size[0], left + 340)
        bottom = min(screen.size[1], top + 560)
        crop = screen.crop((left, top, right, bottom))
        for y, x, text in _menu_lines(crop, engine):
            if x > 140 or len(text) > 22:
                continue
            if not menu_row_matches(text, number, unit):
                continue
            _click(window.left + left + x + 28, window.top + top + y + 6)
            return True
        _scroll_down(origin_x, origin_y + 180, notches=1)
        time.sleep(0.15)
    _send_vk(0x1B)
    return False


def _read_timeframe(window, engine, capture_window):
    shot = capture_window(window)
    if shot is None:
        return None, "", []
    width, height = shot.image.size
    crop = shot.image.crop((0, 0, max(1, int(width * 0.50)), max(1, int(height * 0.16))))
    words = _ocr_words(crop, engine)
    detected = detect_timeframe(words, width=crop.size[0], height=crop.size[1], cropped=True)
    return shot, detected, words


def _save(debug_dir, name: str, image) -> None:
    if debug_dir is None or image is None:
        return
    from pathlib import Path

    folder = Path(debug_dir)
    folder.mkdir(parents=True, exist_ok=True)
    image.save(folder / name)


def ensure_required_timeframe(window, config, engine, capture_window, debug_dir=None) -> TimeframeState:
    """Switch the bot chart to 3m when it is on 30s or 1m. Verify the toolbar after."""
    required = (config.required_timeframe or "3m").lower()
    shot, detected, words = _read_timeframe(window, engine, capture_window)
    if shot is None:
        return TimeframeState(False, "", "", [Reason.VISION_CAPTURE_INVALID.value])
    initial = detected
    if detected == required:
        return TimeframeState(True, detected, initial)
    if not config.auto_restore_timeframe:
        _save(debug_dir, "02_wrong_timeframe.png", shot.image)
        return TimeframeState(False, detected, initial, [Reason.VISION_WRONG_TIMEFRAME.value])
    _save(debug_dir, "01_initial_capture.png", shot.image)
    _save(debug_dir, "02_wrong_timeframe.png", shot.image)
    from cdx_vision.auto_right import ChartNavigator

    nav = ChartNavigator(config.chart_focus_x, config.chart_focus_y)
    if not nav.focus_and_confirm(window) or not _foreground_is(window):
        return TimeframeState(
            False,
            detected,
            initial,
            [Reason.VISION_WRONG_TIMEFRAME.value, Reason.VISION_TRADINGVIEW_FOCUS_FAIL.value],
            True,
        )
    _send_vk(0x1B)
    time.sleep(0.2)
    shot, detected, words = _read_timeframe(window, engine, capture_window)
    if not initial:
        initial = detected
    if shot is None:
        return TimeframeState(False, detected, initial, [Reason.VISION_TIMEFRAME_RESTORE_FAIL.value], True)
    if detected == required:
        return TimeframeState(True, detected, initial, [Reason.VISION_TIMEFRAME_RESTORED.value], True)
    button = _find_word(
        words,
        lambda text: text.lower() in {detected, required, "30s", "1m", "3m", "5m", "15m", "15s"},
        max_x_fraction=0.45,
        width=shot.image.size[0],
    )
    if button is None:
        return TimeframeState(
            False,
            detected,
            initial,
            [Reason.VISION_WRONG_TIMEFRAME.value, Reason.VISION_TIMEFRAME_RESTORE_FAIL.value],
            True,
        )
    from cdx_vision.chart_state import interval_menu_target

    number, unit = interval_menu_target(required)
    if not number:
        return TimeframeState(
            False,
            detected,
            initial,
            [Reason.VISION_WRONG_TIMEFRAME.value, Reason.VISION_TIMEFRAME_RESTORE_FAIL.value],
            True,
        )
    button_xy = _screen_point(window, shot.image, button[1] + 12, button[2] + 8)
    selected = False
    for _attempt in range(2):
        if not _select_menu_row(window, engine, button_xy, number, unit):
            _send_vk(0x1B)
            time.sleep(0.2)
            continue
        time.sleep(max(0.5, config.redraw_wait_ms / 1000))
        checked, now, _words_now = _read_timeframe(window, engine, capture_window)
        if now == required:
            selected = True
            break
        _send_vk(0x1B)
        time.sleep(0.25)
    if not selected:
        return TimeframeState(
            False,
            detected,
            initial,
            [Reason.VISION_TIMEFRAME_RESTORE_ATTEMPTED.value, Reason.VISION_TIMEFRAME_RESTORE_FAIL.value],
            True,
        )
    time.sleep(0.35)
    deadline = time.perf_counter() + max(1.0, config.timeframe_restore_timeout_ms / 1000)
    confirmed = 0
    now = ""
    checked = None
    while time.perf_counter() < deadline:
        checked, now, _words = _read_timeframe(window, engine, capture_window)
        if checked is None:
            break
        if now == required:
            confirmed += 1
            if confirmed >= 2:
                _save(debug_dir, "03_after_3m_restore.png", checked.image)
                _save(debug_dir, "04_after_redraw.png", checked.image)
                return TimeframeState(True, now, initial, [Reason.VISION_TIMEFRAME_RESTORED.value], True)
        else:
            confirmed = 0
        time.sleep(0.45)
    if checked is not None:
        _save(debug_dir, "03_after_3m_restore.png", checked.image)
    return TimeframeState(
        False,
        now,
        initial,
        [Reason.VISION_TIMEFRAME_RESTORE_ATTEMPTED.value, Reason.VISION_TIMEFRAME_RESTORE_FAIL.value],
        True,
    )
