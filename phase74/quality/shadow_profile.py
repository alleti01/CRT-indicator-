"""Shadow trading profiles: paper-trade every real CDX signal under an alternative rule set.

A profile never sends orders. For each CDX alert it decides whether it would
trade (one position at a time, its own day limits), sizes to a fixed dollar
risk with a 1.5 x ATR(3m) stop and a 2R target, then follows the closed bars
to the stop, the target, or the time limit. Every decision and exit goes to
`shadow_profiles.jsonl`; open trades and balances survive restarts.
"""
from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence
from zoneinfo import ZoneInfo

from phase73.market_data.bar import Bar
from phase74.quality.htf_bias import BEARISH, BULLISH, resample, structure_bias

log = logging.getLogger("phase74.shadow_profile")
ET = ZoneInfo("America/New_York")
_ALERT_ID = re.compile(r"^\d{4}-\d{2}-\d{2}T")


@dataclass(frozen=True)
class ProfileConfig:
    name: str
    enabled: bool = True
    stop_atr: float = 1.5
    target_r: float = 2.0
    risk_usd: float = 600.0
    filter: str = "none"  # none | 15m_agrees
    point_value: float = 2.0  # MNQ
    min_stop_points: float = 4.0
    max_hold_minutes: int = 240
    day_max_winners: int = 1
    day_max_losers: int = 2
    day_max_loss_usd: float = 400.0
    trade_cap_usd: float = 1000.0
    eval_target_usd: float = 3000.0
    eval_drawdown_usd: float = 2000.0
    max_bar_age_minutes: int = 10

    @classmethod
    def from_dict(cls, raw: dict) -> ProfileConfig:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class OpenTrade:
    signal_id: str
    side: str
    entry: float
    stop: float
    target: float
    qty: int
    opened_at: str
    day: str


@dataclass
class ProfileState:
    open: Optional[OpenTrade] = None
    balance: float = 0.0
    peak: float = 0.0
    eval_status: str = "RUNNING"
    days: dict = field(default_factory=dict)
    seen: list = field(default_factory=list)


def is_alert_id(signal_id: str) -> bool:
    return bool(_ALERT_ID.match(signal_id or ""))


def futures_day(t: datetime) -> str:
    return (t.astimezone(ET) - timedelta(hours=18)).date().isoformat()


def atr3(bars: Sequence[Bar], n: int = 14) -> float:
    threes = resample(bars, 3)
    if len(threes) < n + 1:
        return 0.0
    w = threes[-(n + 1):]
    return sum(max(b.high - b.low, abs(b.high - p.close), abs(b.low - p.close)) for p, b in zip(w, w[1:])) / n


def _align(side: str, bias: str) -> int:
    want, against = (BULLISH, BEARISH) if side == "LONG" else (BEARISH, BULLISH)
    return 1 if bias == want else -1 if bias == against else 0


class ShadowProfile:
    def __init__(self, cfg: ProfileConfig, log_dir: Path) -> None:
        self.cfg = cfg
        self.log_path = log_dir / "shadow_profiles.jsonl"
        self.state_path = log_dir / f"shadow_profile_{cfg.name}.json"
        self.state = self._load()

    # ---------- persistence ----------

    def _load(self) -> ProfileState:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            open_ = OpenTrade(**raw["open"]) if raw.get("open") else None
            return ProfileState(open_, raw["balance"], raw["peak"], raw["eval_status"], raw["days"], raw["seen"])
        except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError):
            return ProfileState()

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self.state)
        self.state_path.write_text(json.dumps(data), encoding="utf-8")

    def _log(self, event: str, **fields: Any) -> None:
        row = {"logged_at_utc": datetime.now(timezone.utc).isoformat(), "profile": self.cfg.name, "event": event, **fields}
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    # ---------- signals ----------

    def on_signal(self, signal_id: str, side: str, price: float, t: datetime, bars: Sequence[Bar]) -> str:
        """Decide and log. Returns the event name (OPEN or SKIP_*)."""
        if not self.cfg.enabled or not is_alert_id(signal_id) or side not in ("LONG", "SHORT"):
            return "IGNORED"
        if signal_id in self.state.seen:
            return "DUPLICATE"
        self.state.seen = (self.state.seen + [signal_id])[-500:]
        hist = [b for b in bars if b.timestamp <= t]
        base = {"signal_id": signal_id, "direction": side, "signal_price": price, "signal_time_utc": t.isoformat()}

        def skip(reason: str, **extra: Any) -> str:
            self._log("SKIP", reason=reason, **base, **extra)
            self._save()
            return "SKIP_" + reason

        if not hist or t - hist[-1].timestamp > timedelta(minutes=self.cfg.max_bar_age_minutes):
            return skip("STALE_BARS", last_bar_utc=hist[-1].timestamp.isoformat() if hist else None)
        atr = atr3(hist)
        if atr <= 0:
            return skip("NO_ATR")
        a15 = _align(side, structure_bias(resample(hist, 15)))
        a1h = _align(side, structure_bias(resample(hist, 60)))
        base.update(atr3=round(atr, 2), align_15m=a15, align_1h=a1h)
        if self.state.open is not None:
            return skip("POSITION_OPEN", open_signal_id=self.state.open.signal_id)
        if self.cfg.filter == "15m_agrees" and a15 != 1:
            return skip("15M_NOT_AGREEING")
        day = futures_day(t)
        d = self.state.days.setdefault(day, {"pnl": 0.0, "w": 0, "l": 0})
        if d["w"] >= self.cfg.day_max_winners or d["l"] >= self.cfg.day_max_losers or d["pnl"] <= -self.cfg.day_max_loss_usd:
            return skip("DAY_LIMIT", day_pnl=round(d["pnl"], 2), day_w=d["w"], day_l=d["l"])

        dist = max(self.cfg.stop_atr * atr, self.cfg.min_stop_points)
        qty = max(1, math.floor(self.cfg.risk_usd / (dist * self.cfg.point_value)))
        sgn = 1 if side == "LONG" else -1
        trade = OpenTrade(
            signal_id=signal_id,
            side=side,
            entry=price,
            stop=round(price - sgn * dist, 2),
            target=round(price + sgn * dist * self.cfg.target_r, 2),
            qty=qty,
            opened_at=t.isoformat(),
            day=day,
        )
        self.state.open = trade
        self._log("OPEN", **base, entry=trade.entry, stop=trade.stop, target=trade.target, qty=qty,
                  stop_points=round(dist, 2), risk_usd=round(dist * qty * self.cfg.point_value, 2))
        self._save()
        return "OPEN"

    # ---------- bars ----------

    def on_bar(self, bar: Bar) -> Optional[dict]:
        tr = self.state.open
        if tr is None:
            return None
        opened = datetime.fromisoformat(tr.opened_at)
        if bar.timestamp <= opened:
            return None  # signal bar or earlier
        sgn = 1 if tr.side == "LONG" else -1
        adverse = bar.low if sgn > 0 else bar.high
        favor = bar.high if sgn > 0 else bar.low
        if sgn * (adverse - tr.stop) <= 0:  # stop first when both are inside one bar
            return self._close(tr, tr.stop, "STOP", bar.timestamp)
        if sgn * (favor - tr.target) >= 0:
            return self._close(tr, tr.target, "TARGET", bar.timestamp)
        if bar.timestamp - opened >= timedelta(minutes=self.cfg.max_hold_minutes):
            return self._close(tr, bar.close, "TIME", bar.timestamp)
        return None

    def _close(self, tr: OpenTrade, price: float, why: str, at: datetime) -> dict:
        sgn = 1 if tr.side == "LONG" else -1
        pts = sgn * (price - tr.entry)
        usd = min(pts * self.cfg.point_value * tr.qty, self.cfg.trade_cap_usd)
        risk_pts = abs(tr.entry - tr.stop)
        st = self.state
        st.balance += usd
        st.peak = max(st.peak, st.balance)
        d = st.days.setdefault(tr.day, {"pnl": 0.0, "w": 0, "l": 0})
        d["pnl"] += usd
        d["w" if usd > 0 else "l"] += 1
        if st.eval_status == "RUNNING":
            if st.balance >= self.cfg.eval_target_usd:
                st.eval_status = f"PASSED {tr.day}"
            elif st.balance <= st.peak - self.cfg.eval_drawdown_usd:
                st.eval_status = f"BLOWN {tr.day}"
        st.open = None
        row = {
            "signal_id": tr.signal_id, "direction": tr.side, "exit_reason": why, "exit_price": price,
            "exit_time_utc": at.isoformat(), "points": round(pts, 2), "r": round(pts / risk_pts, 3) if risk_pts else 0.0,
            "usd": round(usd, 2), "qty": tr.qty, "balance": round(st.balance, 2), "eval_status": st.eval_status,
        }
        self._log("CLOSE", **row)
        self._save()
        return row


def build_profiles(raw: Sequence[dict], log_dir: Path) -> list[ShadowProfile]:
    return [ShadowProfile(ProfileConfig.from_dict(r), log_dir) for r in raw if r.get("enabled", True)]
