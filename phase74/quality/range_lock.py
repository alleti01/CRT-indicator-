"""One attempt per trade range. Replay wall is the last fill, not the 20-bar box."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from phase74.quality.day_halt import session_key_ny

SKIP_RANGE_LOCK = "SKIP_RANGE_LOCK"


@dataclass(frozen=True)
class RangeLockConfig:
    enabled: bool = False
    arm_on: str = "any"

    @classmethod
    def from_dict(cls, raw: dict | None) -> RangeLockConfig:
        raw = raw or {}
        return cls(
            enabled=bool(raw.get("enabled", False)),
            arm_on=str(raw.get("arm_on", "any")),
        )


def trade_excursion(
    direction: str,
    fill: float,
    exit_px: float,
    mfe_r: float,
    mae_r: float,
    atr: float,
    stop_atr: float = 1.0,
) -> tuple[float, float]:
    """High/low of the completed trade from fill, MFE/MAE, and exit."""
    risk = max(0.0, float(stop_atr) * float(atr))
    fill = float(fill)
    exit_px = float(exit_px)
    if direction == "SHORT":
        high = max(fill + float(mae_r) * risk, fill, exit_px)
        low = min(fill - float(mfe_r) * risk, fill, exit_px)
    else:
        high = max(fill + float(mfe_r) * risk, fill, exit_px)
        low = min(fill - float(mae_r) * risk, fill, exit_px)
    return high, low


class RangeLock:
    def __init__(self, cfg: RangeLockConfig | None = None, path: Path | None = None) -> None:
        self.cfg = cfg or RangeLockConfig()
        self.path = path
        self.high: float | None = None
        self.low: float | None = None
        self.session: tuple[date, str] | None = None
        self._load()

    @property
    def active(self) -> bool:
        return self.high is not None and self.low is not None

    def evaluate(self, close: float, now: datetime) -> str:
        """Empty if a new entry is allowed. Clears on session roll or close-through."""
        if not self.cfg.enabled or not self.active:
            return ""
        if self.session is not None and session_key_ny(now) != self.session:
            self.clear()
            return ""
        assert self.high is not None and self.low is not None
        if close > self.high or close < self.low:
            self.clear()
            return ""
        if self.low <= close <= self.high:
            return SKIP_RANGE_LOCK
        return ""

    def arm(self, high: float, low: float, now: datetime) -> None:
        if high < low:
            high, low = low, high
        self.high = float(high)
        self.low = float(low)
        self.session = session_key_ny(now)
        self._save()

    def clear(self) -> None:
        self.high = None
        self.low = None
        self.session = None
        self._save()

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "high": self.high,
            "low": self.low,
            "session_date": None if self.session is None else self.session[0].isoformat(),
            "session": None if self.session is None else self.session[1],
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if raw.get("high") is None or raw.get("low") is None:
            return
        self.high = float(raw["high"])
        self.low = float(raw["low"])
        day = raw.get("session_date")
        sess = raw.get("session")
        if day and sess:
            self.session = (date.fromisoformat(str(day)), str(sess))


def seed_from_paper_trades(lock: RangeLock, csv_path: Path) -> bool:
    """Arm from the last closed journal row if this process has no lock yet."""
    if not lock.cfg.enabled or lock.active or not csv_path.exists():
        return False
    last: dict[str, str] | None = None
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("exit_timestamp") and row.get("exit_price"):
                last = row
    if last is None:
        return False
    raw = last["exit_timestamp"].replace("Z", "+00:00")
    when = datetime.fromisoformat(raw)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    high, low = trade_excursion(
        last["direction"],
        fill=float(last["fill_price"]),
        exit_px=float(last["exit_price"]),
        mfe_r=float(last.get("MFE") or 0.0),
        mae_r=float(last.get("MAE") or 0.0),
        atr=float(last["atr"]),
    )
    lock.arm(high, low, when)
    return True
