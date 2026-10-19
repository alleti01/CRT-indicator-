"""Higher-timeframe market-structure bias for CDX signals.

The live 1-minute bars are grouped into 15m and 1H candles. On each one, swing
highs and lows decide the bias:

- close beyond the last swing high / low  -> BULLISH / BEARISH (break of structure)
- higher high and higher low              -> BULLISH
- lower high and lower low                -> BEARISH
- anything else, or too little history    -> NEUTRAL

A CDX signal is skipped only when every timeframe points against it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from phase73.market_data.bar import Bar

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class HtfBiasConfig:
    enabled: bool = False
    enforce: bool = False
    timeframes_minutes: tuple[int, ...] = (15, 60)
    swing_bars: int = 2

    @classmethod
    def from_dict(cls, raw: dict) -> HtfBiasConfig:
        tfs = raw.get("timeframes_minutes") or [15, 60]
        return cls(
            enabled=bool(raw.get("enabled", False)),
            enforce=bool(raw.get("enforce", False)),
            timeframes_minutes=tuple(int(t) for t in tfs),
            swing_bars=int(raw.get("swing_bars", 2)),
        )


@dataclass
class HtfBiasDecision:
    decision: str
    reason: str
    biases: dict[str, str] = field(default_factory=dict)


def resample(bars: Sequence[Bar], minutes: int) -> list[Bar]:
    """Group bars into closed `minutes` candles. The still-forming candle is dropped."""
    if not bars:
        return []
    step = timedelta(minutes=minutes)
    out: list[Bar] = []
    cur: list[Bar] = []
    cur_start: datetime | None = None
    for b in bars:
        ts = b.timestamp if b.timestamp.tzinfo else b.timestamp.replace(tzinfo=timezone.utc)
        start = _EPOCH + ((ts - _EPOCH) // step) * step
        if cur_start is not None and start != cur_start:
            out.append(_merge(cur_start, cur))
            cur = []
        cur_start = start
        cur.append(b)
    last_ts = bars[-1].timestamp if bars[-1].timestamp.tzinfo else bars[-1].timestamp.replace(tzinfo=timezone.utc)
    # A 1-minute bar stamped at its open closes the bucket on the bucket's last minute.
    if cur and cur_start is not None and last_ts + timedelta(minutes=1) >= cur_start + step:
        out.append(_merge(cur_start, cur))
    return out


def _merge(start: datetime, group: list[Bar]) -> Bar:
    return Bar(
        timestamp=start,
        open=group[0].open,
        high=max(b.high for b in group),
        low=min(b.low for b in group),
        close=group[-1].close,
        volume=sum(b.volume for b in group),
    )


def _swings(bars: Sequence[Bar], n: int) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(n, len(bars) - n):
        left = bars[i - n : i]
        right = bars[i + 1 : i + n + 1]
        if all(bars[i].high > b.high for b in left) and all(bars[i].high >= b.high for b in right):
            highs.append(bars[i].high)
        if all(bars[i].low < b.low for b in left) and all(bars[i].low <= b.low for b in right):
            lows.append(bars[i].low)
    return highs, lows


def structure_bias(bars: Sequence[Bar], swing_bars: int = 2) -> str:
    highs, lows = _swings(bars, swing_bars)
    if not highs or not lows:
        return NEUTRAL
    close = bars[-1].close
    if close > highs[-1]:
        return BULLISH
    if close < lows[-1]:
        return BEARISH
    if len(highs) < 2 or len(lows) < 2:
        return NEUTRAL
    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        return BULLISH
    if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
        return BEARISH
    return NEUTRAL


def _label(minutes: int) -> str:
    return f"{minutes // 60}H" if minutes % 60 == 0 else f"{minutes}m"


def evaluate_htf_bias(bars: Sequence[Bar], direction: str, cfg: HtfBiasConfig) -> HtfBiasDecision:
    biases = {_label(m): structure_bias(resample(bars, m), cfg.swing_bars) for m in cfg.timeframes_minutes}
    against = BEARISH if direction == "LONG" else BULLISH if direction == "SHORT" else ""
    if against and biases and all(b == against for b in biases.values()):
        return HtfBiasDecision("SKIP", f"HTF_ALL_{against}", biases)
    return HtfBiasDecision("TAKE", "HTF_NOT_ALL_AGAINST", biases)


def log_htf_decision(
    log_dir: Path,
    dec: HtfBiasDecision,
    *,
    signal_id: str,
    direction: str,
    enforced: bool,
) -> None:
    row = {
        "received_at_utc": datetime.now(timezone.utc).isoformat(),
        "signal_id": signal_id,
        "direction": direction,
        "decision": dec.decision,
        "reason": dec.reason,
        "biases": dec.biases,
        "enforced": enforced,
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "htf_bias.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
