"""Sequential one-position R replay from phase74 logs."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from forward_rehearsal.shadow.position_tracker import ShadowPositionTracker
from phase73.config.loader import Phase73Config, load_config
from phase73.market_data.bar import Bar
from phase73.market_data.health import DataHealth, HealthReport
from phase73.market_data.provider import ReplayDataProvider
from phase73.trader.entry_quality import evaluate_entry
from phase73.trader.fsm import TraderAction
from phase73.webhook.schemas import PineSignal, _parse_ts

LOGS = Path(__file__).resolve().parents[1] / "logs"


@dataclass
class SequentialTrade:
    signal_id: str
    event: str
    entry_price: float
    exit_price: float
    atr: float
    exit_action: str
    gross_r: float


@dataclass
class SequentialResult:
    day: str
    signals: int
    trades_taken: int
    signals_skipped: int
    wins: int
    losses: int
    total_gross_r: float
    trades: list[SequentialTrade]
    skipped: list[dict]


def load_signals(day: str, logs: Path = LOGS) -> list[PineSignal]:
    by_id: dict[str, PineSignal] = {}
    path = logs / "signals.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row["received_at_utc"].startswith(day):
                continue
            sig = PineSignal(
                schema_version=row["schema_version"],
                strategy=row["strategy"],
                pine_hash=row["pine_hash"],
                signal_id=row["signal_id"],
                event=row["event"],
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                signal_time_utc=_parse_ts(row["signal_time_utc"]),
                signal_bar_time_utc=_parse_ts(row["signal_bar_time_utc"]),
                signal_price=float(row["signal_price"]),
                atr=float(row["atr"]),
                evidence=int(row.get("evidence") or 5),
                context=row.get("context") or "",
                state=row.get("state") or "",
                received_at_utc=_parse_ts(row["received_at_utc"]),
            )
            by_id[sig.signal_id] = sig
    return sorted(by_id.values(), key=lambda s: s.received_at_utc)


def load_bars_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp_utc"])
    df = df.rename(columns={"timestamp_utc": "timestamp"})
    df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    if "health" not in df.columns:
        df["health"] = "DATA_HEALTHY"
    return df.sort_index()


def load_bars_watch(start: datetime, end: datetime, logs: Path = LOGS) -> pd.DataFrame:
    rows: list[dict] = []
    path = logs / "decisions.csv"
    if not path.exists():
        return pd.DataFrame()
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("action") != "WATCH":
                continue
            ts = row.get("market_timestamp") or ""
            if not ts:
                continue
            t = _parse_ts(ts.replace("Z", "+00:00") if ts.endswith("Z") else ts)
            if t < start or t > end:
                continue
            rows.append(
                {
                    "timestamp": t,
                    "close": float(row["current_price"]),
                    "atr": float(row["current_atr"]) if row.get("current_atr") else 0.0,
                    "health": row.get("market_data_health") or "DATA_HEALTHY",
                }
            )
    rows.sort(key=lambda r: r["timestamp"])
    if not rows:
        return pd.DataFrame()
    out, prev = [], rows[0]["close"]
    for r in rows:
        o, c = prev, r["close"]
        out.append({"open": o, "high": max(o, c), "low": min(o, c), "close": c, "volume": 100.0, "atr": r["atr"], "health": r["health"]})
        prev = c
    idx = pd.DatetimeIndex([r["timestamp"] for r in rows], tz="UTC")
    return pd.DataFrame(out, index=idx)


def load_bars(day: str, logs: Path = LOGS) -> pd.DataFrame:
    bars_path = logs / "bars.csv"
    if bars_path.exists() and bars_path.stat().st_size > 100:
        df = load_bars_csv(bars_path)
        day_start = pd.Timestamp(day, tz="UTC")
        day_end = day_start + pd.Timedelta(days=2)
        return df[(df.index >= day_start - pd.Timedelta(hours=1)) & (df.index <= day_end)]
    signals = load_signals(day, logs)
    if not signals:
        return pd.DataFrame()
    start = signals[0].received_at_utc - timedelta(minutes=30)
    end = signals[-1].received_at_utc + timedelta(hours=2)
    return load_bars_watch(start, end, logs)


class _Pin(ReplayDataProvider):
    def __init__(self, df, i, health, atr):
        super().__init__(df, start_index=i)
        self._health = health
        self._atr = atr

    def health(self) -> HealthReport:
        last = self.latest_bar()
        now = self.current_time()
        if self._health != DataHealth.DATA_HEALTHY:
            return HealthReport(self._health, last_bar_timestamp=last.timestamp if last else None, current_time=now)
        return HealthReport(DataHealth.DATA_HEALTHY, last_bar_timestamp=last.timestamp if last else None, current_time=now, latency_seconds=0.0)

    def atr(self, period: int = 14) -> float:
        return self._atr or super().atr(period)


def _bar_index(df: pd.DataFrame, when: datetime) -> int:
    when = when.astimezone(timezone.utc)
    return max(0, min(int(df.index.searchsorted(when, side="right") - 1), len(df) - 1))


def _with_live_atr(sig: PineSignal, live_atr: float) -> PineSignal:
    from dataclasses import replace

    return replace(sig, atr=live_atr) if live_atr > 0 else sig


def sequential_replay(
    day: str,
    *,
    pass_chase: bool = True,
    pass_late: bool = True,
    late_age_seconds: int = 60,
    max_chase_atr: float = 1.5,
    cfg: Phase73Config | None = None,
    logs: Path = LOGS,
) -> SequentialResult:
    cfg = cfg or load_config()
    eq = cfg.raw.setdefault("entry_quality", {})
    eq["pass_chase_enabled"] = pass_chase
    eq["pass_late_enabled"] = pass_late
    eq["max_chase_atr"] = max_chase_atr
    if pass_late:
        eq["max_signal_age_seconds"] = late_age_seconds

    signals = load_signals(day, logs)
    bars = load_bars(day, logs)
    skipped: list[dict] = []
    trades: list[SequentialTrade] = []
    if not signals or bars.empty:
        return SequentialResult(day, len(signals), 0, 0, 0, 0, 0.0, [], skipped)

    tracker = ShadowPositionTracker(cfg)
    entry_bar_idx: int | None = None
    by_bar: dict[int, list[PineSignal]] = {}
    for sig in signals:
        by_bar.setdefault(_bar_index(bars, sig.received_at_utc), []).append(sig)

    def record_close() -> None:
        t = tracker.closed_trades[-1]
        atr = _atr_for_signal(t["signal_id"], signals, bars)
        risk = cfg.stop_atr * atr
        move = (t["exit_price"] - t["entry_price"]) if t["direction"] == "LONG" else (t["entry_price"] - t["exit_price"])
        gr = move / risk if risk > 0 else 0.0
        sig = next((s for s in signals if s.signal_id == t["signal_id"]), None)
        trades.append(
            SequentialTrade(
                signal_id=t["signal_id"],
                event=sig.event if sig else "",
                entry_price=t["entry_price"],
                exit_price=t["exit_price"],
                atr=atr,
                exit_action=t["action"],
                gross_r=gr,
            )
        )

    for j in range(len(bars)):
        ts = bars.index[j]
        row = bars.iloc[j]
        for sig in by_bar.get(j, []):
            if tracker.is_active:
                skipped.append({"signal_id": sig.signal_id, "reason": "POSITION_ACTIVE"})
                continue
            live_atr = float(row["atr"]) if row.get("atr") else 0.0
            if live_atr <= 0:
                skipped.append({"signal_id": sig.signal_id, "reason": "NO_ATR"})
                continue
            health = DataHealth.DATA_HEALTHY if row.get("health", "DATA_HEALTHY") == "DATA_HEALTHY" else DataHealth.DATA_MISSING
            pin = _Pin(bars, j, health, live_atr)
            sig2 = _with_live_atr(sig, live_atr)
            entry = evaluate_entry(sig2, pin, cfg, position_side="FLAT", now=sig.received_at_utc)
            if entry.action not in (TraderAction.TAKE_LONG, TraderAction.TAKE_SHORT):
                skipped.append({"signal_id": sig.signal_id, "reason": entry.action.value})
                continue
            entry_time = ts.to_pydatetime()
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
            tracker.open_from_signal(sig2, float(row["close"]), entry_time)
            entry_bar_idx = j

        if not tracker.is_active or entry_bar_idx == j:
            continue
        bar = Bar(
            timestamp=ts.to_pydatetime().replace(tzinfo=timezone.utc),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 100)),
        )
        was = tracker.is_active
        tracker.on_bar(bar, bar.timestamp)
        if was and not tracker.is_active and tracker.closed_trades:
            record_close()
            entry_bar_idx = None

    if tracker.is_active and tracker.position:
        mgmt = tracker.position.mgmt
        last = float(bars.iloc[-1]["close"])
        risk = mgmt.risk
        move = (last - mgmt.entry_price) if mgmt.side == "LONG" else (mgmt.entry_price - last)
        gr = move / risk if risk > 0 else 0.0
        sig = next((s for s in signals if s.signal_id == tracker.position.signal_id), None)
        trades.append(
            SequentialTrade(
                signal_id=tracker.position.signal_id,
                event=sig.event if sig else "",
                entry_price=mgmt.entry_price,
                exit_price=last,
                atr=risk / cfg.stop_atr,
                exit_action="OPEN_AT_SESSION_END",
                gross_r=gr,
            )
        )

    wins = sum(1 for t in trades if t.gross_r > 0)
    losses = sum(1 for t in trades if t.gross_r <= 0)
    total = sum(t.gross_r for t in trades)
    return SequentialResult(
        day=day,
        signals=len(signals),
        trades_taken=len(trades),
        signals_skipped=len(skipped),
        wins=wins,
        losses=losses,
        total_gross_r=total,
        trades=trades,
        skipped=skipped,
    )


def _atr_for_signal(signal_id: str, signals: list[PineSignal], bars: pd.DataFrame) -> float:
    for s in signals:
        if s.signal_id == signal_id:
            j = _bar_index(bars, s.received_at_utc)
            return float(bars.iloc[j]["atr"]) or 7.0
    return 7.0
