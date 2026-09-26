"""Prop day halt for a $2,000 DD / 50k / 1 NQ book (America/New_York session)."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
NQ_POINT_VALUE = 20.0
RTH_START = time(9, 30)
RTH_END = time(16, 0)


def session_date_ny(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(_NY).date()


def session_key_ny(now: datetime | None = None) -> tuple[date, str]:
    """RTH 9:30–16:00 ET is its own card. Globex/after-hours is the rest."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(_NY)
    tod = local.time()
    if RTH_START <= tod < RTH_END:
        return local.date(), "rth"
    if tod >= RTH_END:
        return local.date(), "globex"
    return local.date() - timedelta(days=1), "globex"


def new_entries_blocked_session(
    now: datetime | None = None,
    *,
    allow_globex_entries: bool = False,
) -> str:
    """Empty string if a new entry is allowed. SKIP_GLOBEX outside RTH unless opted in."""
    if allow_globex_entries:
        return ""
    _session_date, session = session_key_ny(now)
    if session == "globex":
        return "SKIP_GLOBEX"
    return ""


def nq_dollars(net_r: float, atr_points: float, point_value: float = NQ_POINT_VALUE) -> float:
    return float(net_r) * float(atr_points) * float(point_value)


@dataclass
class PropDayHalt:
    max_losers: int = 2
    max_loss_dollars: float = 400.0
    max_winners: int = 2
    big_win_dollars: float = 500.0
    giveback_arm_dollars: float = 400.0
    giveback_dollars: float = 300.0
    point_value: float = NQ_POINT_VALUE
    realized_r: float = 0.0
    realized_dollars: float = 0.0
    losers: int = 0
    winners: int = 0
    peak_dollars: float = 0.0
    had_big_win: bool = False
    session_date: date = field(default_factory=session_date_ny)
    session_key: tuple[date, str] = field(default_factory=session_key_ny)
    reason: str = ""

    def _roll(self, now: datetime | None = None) -> None:
        key = session_key_ny(now)
        if key != self.session_key:
            self.session_key = key
            self.session_date = key[0]
            self.realized_r = 0.0
            self.realized_dollars = 0.0
            self.losers = 0
            self.winners = 0
            self.peak_dollars = 0.0
            self.had_big_win = False
            self.reason = ""

    def record_closed(
        self,
        net_r: float,
        now: datetime | None = None,
        *,
        dollars: float | None = None,
        atr: float | None = None,
    ) -> None:
        self._roll(now)
        if dollars is None and atr is not None:
            dollars = nq_dollars(net_r, atr, self.point_value)
        if dollars is None:
            dollars = 0.0
        self.realized_r += net_r
        self.realized_dollars += dollars
        self.peak_dollars = max(self.peak_dollars, self.realized_dollars)
        if dollars >= self.big_win_dollars:
            self.had_big_win = True
        if dollars < 0 or net_r < 0:
            self.losers += 1
        elif dollars > 0 or net_r > 0:
            self.winners += 1

    def should_halt_new_entries(self, now: datetime | None = None) -> bool:
        self._roll(now)
        if self.losers >= self.max_losers:
            self.reason = "HALT_DAY_LOSERS"
            return True
        if self.realized_dollars <= -abs(self.max_loss_dollars):
            self.reason = "HALT_DAY_DOLLARS"
            return True
        if self.had_big_win:
            self.reason = "HALT_DAY_BIG_WIN"
            return True
        if self.winners >= self.max_winners:
            self.reason = "HALT_DAY_WINS"
            return True
        if (
            self.peak_dollars >= self.giveback_arm_dollars
            and self.realized_dollars <= self.peak_dollars - self.giveback_dollars
        ):
            self.reason = "HALT_DAY_GIVEBACK"
            return True
        self.reason = ""
        return False


def nt_rejected_signal_ids(audit_path: Path) -> set[str]:
    """Signal ids NinjaTrader refused. Those paper rows are not account results."""
    rejected: set[str] = set()
    if not audit_path.exists():
        return rejected
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if "COMMAND_REJECTED" not in line and "ORDER_REJECTED" not in line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("event") not in {"COMMAND_REJECTED", "ORDER_REJECTED"}:
            continue
        signal_id = str(rec.get("signal_id") or "")
        if signal_id:
            rejected.add(signal_id)
    return rejected


def seed_day_halt_from_paper_trades(
    halt: PropDayHalt,
    csv_path: Path,
    *,
    audit_path: Path | None = None,
) -> bool:
    """Replay closed journal rows so a restart keeps today's win/loss halt."""
    if not csv_path.exists():
        return False
    rejected = nt_rejected_signal_ids(audit_path) if audit_path is not None else set()
    seeded = False
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if not row.get("exit_timestamp") or not row.get("net_R"):
                continue
            if str(row.get("pine_signal_id") or "") in rejected:
                continue
            raw = row["exit_timestamp"].replace("Z", "+00:00")
            when = datetime.fromisoformat(raw)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            atr = float(row["atr"]) if row.get("atr") else None
            halt.record_closed(float(row["net_R"]), when, atr=atr)
            seeded = True
    return seeded
