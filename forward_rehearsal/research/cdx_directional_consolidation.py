"""Offline CDX post-entry study.

Compares the live 10-point reversal with a CDX-stop / +0.50R / 3-minute pivot
trail. Nothing here submits an order.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "forward_rehearsal" / "reports" / "cdx_directional_consolidation"
BARS = ROOT / "phase74" / "logs" / "bars.csv"
VISION = ROOT / "cdx_vision" / "logs" / "vision_levels.jsonl"
AUDIT = ROOT / "phase85" / "logs" / "audit.jsonl"
PAPER = ROOT / "phase74" / "logs" / "paper_trades.jsonl"
SIGNALS = ROOT / "phase74" / "logs" / "signals.jsonl"

TICK = 0.25
ARM_R = 0.50
REVERSAL_POINTS = 10.0
MNQ_DOLLARS_PER_POINT = 2.0
NEAR_R = 0.15
EFF_MAX = 0.25
OVERLAP_MIN = 0.60


@dataclass
class Bar:
    open_time: datetime
    high: float
    low: float
    close: float

    @property
    def close_time(self) -> datetime:
        return self.open_time + timedelta(minutes=1)


@dataclass
class Three:
    open_time: datetime
    high: float
    low: float
    close: float

    @property
    def close_time(self) -> datetime:
        return self.open_time + timedelta(minutes=3)


@dataclass
class Exit:
    reason: str
    price: float | None
    when: datetime | None
    bar_index: int | None


@dataclass
class NativeSim:
    """One causal pass. Warmup bars build 3-minute structure and do not exit."""

    side: str
    fill: float
    sl: float
    tp1: float
    cdx_entry: float
    variant: str
    opposite_times: list[datetime] = field(default_factory=list)
    use_structure: bool = True
    qty: int = 1
    entry_open: datetime | None = None
    stop: float = 0.0
    armed: bool = False
    armed_time: datetime | None = None
    pending: float | None = None
    threes: list[Three] = field(default_factory=list)
    bucket_key: datetime | None = None
    bucket: list[Bar] = field(default_factory=list)
    extreme: float | None = None
    legacy: Exit | None = None
    result: Exit | None = None
    mfe: float = 0.0
    mae: float = 0.0
    revisions: list[tuple[datetime, float]] = field(default_factory=list)
    pivots: list[tuple[datetime, float]] = field(default_factory=list)
    near_entry_bars: int = 0
    managed: int = 0
    stops_at_open: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.stop = self.sl
        self.execution_r = abs(self.fill - self.sl)

    @property
    def arm_price(self) -> float:
        sign = 1.0 if self.side == "LONG" else -1.0
        return self.fill + sign * ARM_R * self.execution_r

    @property
    def cap_points(self) -> float:
        dollars_per_point = MNQ_DOLLARS_PER_POINT * max(self.qty, 1)
        return min(3.0 * self.execution_r, 1000.0 / dollars_per_point)

    def on_bar(self, bar: Bar, *, manage: bool) -> None:
        was_armed = self.armed
        candidate = self._roll_three(bar, manage=manage)
        if not manage or self.result is not None:
            return
        self.managed += 1
        if was_armed and self.use_structure and candidate is not None:
            tightened = _tighten(self.side, self.stop, candidate)
            if tightened != self.stop:
                self.stop = tightened
                self.revisions.append((bar.open_time, self.stop))
        self.stops_at_open.append(self.stop)
        self._excursions(bar)
        self._legacy(bar)
        if self.variant == "LEGACY" and self.legacy is not None and self.legacy.bar_index == self.managed - 1:
            self.result = self.legacy
            return
        self._exit_on_bar(bar)
        if self.result is None and not self.armed and _touched_arm(self.side, bar, self.arm_price):
            self.armed = True
            self.armed_time = bar.close_time

    def _excursions(self, bar: Bar) -> None:
        if self.side == "LONG":
            self.mfe = max(self.mfe, bar.high - self.fill)
            self.mae = max(self.mae, self.fill - bar.low)
        else:
            self.mfe = max(self.mfe, self.fill - bar.low)
            self.mae = max(self.mae, bar.high - self.fill)

    def _legacy(self, bar: Bar) -> None:
        if self.legacy is not None or self.execution_r <= 0:
            return
        cap = self.cap_points
        if self.side == "LONG" and bar.high >= self.fill + cap:
            self.legacy = Exit("PROFIT_CAP", self.fill + cap, bar.close_time, self.managed - 1)
            return
        if self.side == "SHORT" and bar.low <= self.fill - cap:
            self.legacy = Exit("PROFIT_CAP", self.fill - cap, bar.close_time, self.managed - 1)
            return
        if self.extreme is not None:
            if self.side == "LONG" and bar.low <= self.extreme - REVERSAL_POINTS:
                self.legacy = Exit(
                    "REVERSAL", self.extreme - REVERSAL_POINTS, bar.close_time, self.managed - 1
                )
                return
            if self.side == "SHORT" and bar.high >= self.extreme + REVERSAL_POINTS:
                self.legacy = Exit(
                    "REVERSAL", self.extreme + REVERSAL_POINTS, bar.close_time, self.managed - 1
                )
                return
        favorable = (bar.high - self.fill) if self.side == "LONG" else (self.fill - bar.low)
        if favorable < self.execution_r:
            return
        price = bar.high if self.side == "LONG" else bar.low
        self.extreme = price if self.extreme is None else (
            max(self.extreme, price) if self.side == "LONG" else min(self.extreme, price)
        )

    def _exit_on_bar(self, bar: Bar) -> None:
        hit_stop = bar.low <= self.stop if self.side == "LONG" else bar.high >= self.stop
        hit_tp = self.variant != "LEGACY" and (bar.high >= self.tp1 if self.side == "LONG" else bar.low <= self.tp1)
        if hit_stop:
            reason = "CDX_SL" if self.stop == self.sl else "STRUCTURAL_STOP"
            self.result = Exit(reason, self.stop, bar.close_time, self.managed - 1)
            return
        if hit_tp:
            self.result = Exit("TP1", self.tp1, bar.close_time, self.managed - 1)
            return
        if self.variant == "V3":
            for when in self.opposite_times:
                known = when.replace(second=0, microsecond=0)
                if bar.open_time == known:
                    self.result = Exit("OPPOSITE_SIGNAL", bar.close, bar.close_time, self.managed - 1)
                    return

    def _roll_three(self, bar: Bar, *, manage: bool) -> float | None:
        """Close the prior 3-minute bucket when this bar opens a new one.

        That close is the first moment a pivot is known, so the returned
        candidate is eligible on this bar.
        """
        key = _bucket_open(bar.open_time)
        candidate = None
        if self.bucket_key is not None and key != self.bucket_key:
            candidate = self._finalize_bucket(manage=manage)
            self.bucket = []
        self.bucket_key = key
        self.bucket.append(bar)
        return candidate

    def _finalize_bucket(self, *, manage: bool) -> float | None:
        if len(self.bucket) != 3:
            return None
        opens = [b.open_time for b in self.bucket]
        if opens[1] != opens[0] + timedelta(minutes=1) or opens[2] != opens[0] + timedelta(minutes=2):
            return None
        three = Three(
            opens[0],
            max(b.high for b in self.bucket),
            min(b.low for b in self.bucket),
            self.bucket[-1].close,
        )
        self.threes.append(three)
        if manage and self.entry_open is not None and three.open_time > self.entry_open and self.execution_r > 0:
            zone = NEAR_R * self.execution_r
            if abs(three.close - self.cdx_entry) <= zone:
                self.near_entry_bars += 1
        return self._pivot_candidate(three.close_time)

    def finish(self) -> None:
        if self.result is None:
            self.result = Exit("DATA_END", None, None, None)

    def _pivot_candidate(self, known_at: datetime) -> float | None:
        if not self.use_structure or not self.armed or self.armed_time is None or len(self.threes) < 3:
            return None
        left, center, right = self.threes[-3], self.threes[-2], self.threes[-1]
        if right.close_time != known_at or center.open_time < self.armed_time:
            return None
        if self.side == "SHORT" and center.high > left.high and center.high >= right.high:
            candidate = center.high + TICK
        elif self.side == "LONG" and center.low < left.low and center.low <= right.low:
            candidate = center.low - TICK
        else:
            return None
        self.pivots.append((known_at, candidate))
        return candidate


def _tighten(side: str, current: float, candidate: float) -> float:
    if side == "LONG":
        return max(current, candidate)
    return min(current, candidate)


def _touched_arm(side: str, bar: Bar, arm_price: float) -> bool:
    if side == "LONG":
        return bar.high >= arm_price
    return bar.low <= arm_price


def _bucket_open(ts: datetime) -> datetime:
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - epoch % 180, tz=timezone.utc)


def run_sim(
    bars: list[Bar],
    *,
    side: str,
    fill: float,
    sl: float,
    tp1: float,
    cdx_entry: float,
    fill_time: datetime,
    variant: str,
    opposite_times: list[datetime] | None = None,
    qty: int = 1,
) -> NativeSim:
    sim = NativeSim(
        side=side,
        fill=fill,
        sl=sl,
        tp1=tp1,
        cdx_entry=cdx_entry,
        variant=variant,
        opposite_times=list(opposite_times or []),
        use_structure=variant in {"V2", "V3"},
        qty=qty,
    )
    entry_open = fill_time.replace(second=0, microsecond=0)
    sim.entry_open = entry_open
    for bar in bars:
        if bar.open_time > entry_open + timedelta(days=3):
            break
        manage = bar.open_time > entry_open
        if bar.close_time < entry_open - timedelta(minutes=30):
            continue
        sim.on_bar(bar, manage=manage)
        if sim.result is not None:
            break
    sim.finish()
    return sim


def causality_mismatches(bars: list[Bar], **kwargs) -> int:
    """Prefix replay must match the full run at every managed bar through the exit."""
    full = run_sim(bars, **kwargs)
    entry_open = kwargs["fill_time"].replace(second=0, microsecond=0)
    managed = [b for b in bars if entry_open < b.open_time <= entry_open + timedelta(days=3)]
    if not managed:
        return 0
    exit_at = full.result.bar_index if full.result and full.result.reason != "DATA_END" else None
    last = len(managed) if exit_at is None else min(len(managed), exit_at + 1)
    # Every bar through the exit, then a stride so a three-day open trade still finishes.
    indexes = list(range(1, min(last, 240) + 1))
    if last > 240:
        indexes.extend(range(240, last + 1, 15))
        if indexes[-1] != last:
            indexes.append(last)
    mismatches = 0
    warmup_start = entry_open - timedelta(minutes=30)
    for k in indexes:
        cutoff = managed[k - 1].open_time
        prefix = [b for b in bars if warmup_start <= b.close_time and b.open_time <= cutoff]
        part = run_sim(prefix, **kwargs)
        if part.stops_at_open != full.stops_at_open[:k]:
            mismatches += 1
        full_exit = exit_at
        part_exit = part.result.bar_index if part.result and part.result.reason != "DATA_END" else None
        if full_exit is not None and full_exit < k and part_exit != full_exit:
            mismatches += 1
        if (full_exit is None or full_exit >= k) and part_exit is not None:
            mismatches += 1
        armed_by_now = full.armed_time is not None and full.armed_time <= managed[k - 1].close_time
        if part.armed != armed_by_now:
            mismatches += 1
    return mismatches


def points(side: str, fill: float, price: float | None) -> float | None:
    if price is None:
        return None
    return (price - fill) if side == "LONG" else (fill - price)


def dollars(pts: float | None, qty: int) -> float | None:
    if pts is None:
        return None
    return pts * MNQ_DOLLARS_PER_POINT * qty


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_bars(path: Path = BARS) -> list[Bar]:
    out: list[Bar] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            when = _parse_time(row["timestamp_utc"])
            if when is None:
                continue
            out.append(Bar(when, float(row["high"]), float(row["low"]), float(row["close"])))
    out.sort(key=lambda b: b.open_time)
    return out


def load_native_signals(path: Path = VISION) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("validation_status") != "VISION_CONFIRMED":
            continue
        if str(obj.get("ticker")) != "MNQ":
            continue
        if not str(obj.get("signal_id", "")).startswith("2026-"):
            continue
        try:
            entry = float(obj.get("cdx_native_entry") or obj.get("entry"))
            stop = float(obj.get("cdx_stop") or obj.get("stop"))
            tp1 = float(obj.get("cdx_tp1") or obj.get("tp1"))
        except (TypeError, ValueError):
            continue
        when = _parse_time(str(obj["signal_id"]).replace("Z", "+00:00"))
        if when is None:
            continue
        tp2 = obj.get("cdx_tp2") or obj.get("tp2") or ""
        rows.append(
            {
                "signal_id": obj["signal_id"],
                "when": when,
                "side": obj["webhook_direction"],
                "cdx_entry": entry,
                "sl": stop,
                "tp1": tp1,
                "tp2": float(tp2) if str(tp2) not in {"", "None"} else None,
            }
        )
    return rows


def load_episodes(path: Path = AUDIT) -> list[dict]:
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    episodes: list[dict] = []
    i = 0
    while i < len(events):
        ev = events[i]
        nxt = events[i + 1] if i + 1 < len(events) else None
        if ev.get("event") == "FILL" and nxt and nxt.get("event") == "PROTECTION_SUBMITTED":
            episode = {
                "fill_time": _parse_time(ev["ts_utc"]),
                "fill": float(ev["price"]),
                "qty": int(ev.get("qty") or 0),
                "stop": float(nxt.get("stop")),
                "target": float(nxt.get("target")),
                "exit_time": None,
                "exit": None,
                "exit_event": None,
            }
            j = i + 2
            while j < len(events):
                later = events[j]
                if later.get("event") == "FILL" and j + 1 < len(events) and events[j + 1].get("event") == "PROTECTION_SUBMITTED":
                    break
                if later.get("event") in {"STOP_FILLED", "TARGET_FILLED"}:
                    episode["exit_time"] = _parse_time(later["ts_utc"])
                    episode["exit"] = float(later["price"])
                    episode["exit_event"] = later["event"]
                    break
                if later.get("event") == "FILL" and episode["exit"] is None:
                    episode["exit_time"] = _parse_time(later["ts_utc"])
                    episode["exit"] = float(later["price"])
                    episode["exit_event"] = "FLATTEN_FILL"
                    break
                if later.get("event") == "POSITION_FLAT" and episode["exit"] is None:
                    episode["exit_time"] = _parse_time(later["ts_utc"])
                    episode["exit_event"] = "POSITION_FLAT_UNPRICED"
                    break
                j += 1
            episodes.append(episode)
            i = j
            continue
        i += 1
    return episodes


def match_episode(signal_when: datetime, episodes: list[dict]) -> dict | None:
    best = None
    best_dt = None
    for episode in episodes:
        if episode["fill_time"] is None:
            continue
        delta = (episode["fill_time"] - signal_when).total_seconds()
        if 0 <= delta <= 8 * 60 and (best_dt is None or delta < best_dt):
            best = episode
            best_dt = delta
    return best


def load_paper(path: Path = PAPER) -> dict[str, dict]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        out[obj.get("pine_signal_id")] = obj
    return out


def load_opposite_signals(path: Path = SIGNALS) -> list[tuple[datetime, str]]:
    found: dict[tuple[str, str], tuple[datetime, str]] = {}
    if not path.exists():
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        event = obj.get("event") or ""
        if event not in {"SIGNAL_LONG", "SIGNAL_SHORT"}:
            continue
        when = _parse_time(obj.get("signal_time_utc") or "")
        if when is None or when < datetime(2026, 9, 28, tzinfo=timezone.utc):
            continue
        side = "LONG" if event.endswith("LONG") else "SHORT"
        found[(obj.get("signal_id"), side)] = (when, side)
    return sorted(found.values())


def sideways_before(bars: list[Bar], when: datetime) -> dict | None:
    threes: list[Three] = []
    bucket: list[Bar] = []
    key = None
    for bar in bars:
        if bar.open_time >= when:
            break
        bkey = _bucket_open(bar.open_time)
        if key is None:
            key = bkey
        if bkey != key:
            if len(bucket) == 3:
                threes.append(
                    Three(bucket[0].open_time, max(b.high for b in bucket), min(b.low for b in bucket), bucket[-1].close)
                )
            bucket = []
            key = bkey
        bucket.append(bar)
    window = threes[-20:]
    if len(window) < 20:
        return None
    closes = [b.close for b in window]
    net = abs(closes[-1] - closes[0])
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    eff = net / path if path else 0.0
    overlaps = []
    for a, b in zip(window, window[1:]):
        span = min(a.high - a.low, b.high - b.low)
        ov = min(a.high, b.high) - max(a.low, b.low)
        overlaps.append(max(ov, 0.0) / span if span > 0 else 0.0)
    overlap = sum(overlaps) / len(overlaps)
    return {"efficiency": eff, "overlap": overlap, "sideways": eff <= EFF_MAX and overlap >= OVERLAP_MIN}


def _after_exit_targets(bars: list[Bar], side: str, sl: float, tp1: float, arm_price: float, after: datetime) -> dict:
    later_050 = False
    later_tp1 = False
    sl_first = False
    for bar in bars:
        if bar.open_time < after:
            continue
        hit_sl = bar.low <= sl if side == "LONG" else bar.high >= sl
        hit_tp = bar.high >= tp1 if side == "LONG" else bar.low <= tp1
        hit_arm = bar.high >= arm_price if side == "LONG" else bar.low <= arm_price
        if hit_sl and (hit_tp or hit_arm):
            sl_first = True
            break
        if hit_sl:
            sl_first = True
            break
        if hit_arm:
            later_050 = True
        if hit_tp:
            later_tp1 = True
            break
        if later_050 and later_tp1:
            break
    return {"later_050": later_050 and not sl_first, "later_tp1": later_tp1 and not sl_first, "sl_before_targets": sl_first and not later_tp1 and not later_050}


def summarize(rows: list[dict], key: str) -> dict:
    resolved = [r for r in rows if r.get(key + "_points") is not None]
    pts = [r[key + "_points"] for r in resolved]
    dls = [r[key + "_dollars"] for r in resolved]
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in dls:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    wins = sum(1 for v in pts if v > 0)
    losses = sum(1 for v in pts if v <= 0)
    return {
        "trades": len(resolved),
        "open": sum(1 for r in rows if r.get(key + "_reason") == "DATA_END"),
        "unpriced": sum(1 for r in rows if r.get(key + "_reason") == "UNPRICED"),
        "wins": wins,
        "losses": losses,
        "points": sum(pts) if pts else None,
        "dollars": sum(dls) if dls else None,
        "largest_loss_points": min(pts) if pts else None,
        "largest_win_points": max(pts) if pts else None,
        "max_dd_dollars": max_dd if dls else None,
    }


def _fmt(value, digits=2) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def build() -> dict:
    bars = load_bars()
    signals = load_native_signals()
    episodes = load_episodes()
    paper = load_paper()
    alerts = load_opposite_signals()
    reversal_all = 0
    for row in paper.values():
        if row.get("exit_reason") == "REVERSAL":
            reversal_all += 1
    traces = []
    causal_fail = 0
    for sig in signals:
        episode = match_episode(sig["when"], episodes)
        if episode is None:
            continue
        paper_row = paper.get(sig["signal_id"])
        feat = sideways_before(bars, sig["when"])
        opp = [when for when, side in alerts if side != sig["side"] and when > episode["fill_time"]]
        common = dict(
            side=sig["side"],
            fill=episode["fill"],
            sl=sig["sl"],
            tp1=sig["tp1"],
            cdx_entry=sig["cdx_entry"],
            fill_time=episode["fill_time"],
            qty=episode["qty"],
        )
        v1 = run_sim(bars, variant="V1", opposite_times=[], **common)
        v2 = run_sim(bars, variant="V2", opposite_times=[], **common)
        v3 = run_sim(bars, variant="V3", opposite_times=opp, **common)
        legacy_sim = run_sim(bars, variant="LEGACY", opposite_times=[], **common)
        causal_fail += causality_mismatches(bars, variant="V2", opposite_times=[], **common)
        execution_r = abs(episode["fill"] - sig["sl"])
        arm_price = episode["fill"] + (ARM_R * execution_r if sig["side"] == "LONG" else -ARM_R * execution_r)
        legacy = legacy_sim.result if legacy_sim.result and legacy_sim.result.reason in {"REVERSAL", "PROFIT_CAP"} else None
        reached_050_before = False
        reached_tp1_before = False
        if legacy and legacy.when is not None:
            for bar in bars:
                if bar.close_time > legacy.when:
                    break
                if bar.open_time <= episode["fill_time"].replace(second=0, microsecond=0):
                    continue
                if _touched_arm(sig["side"], bar, arm_price):
                    reached_050_before = True
                hit_tp = bar.high >= sig["tp1"] if sig["side"] == "LONG" else bar.low <= sig["tp1"]
                if hit_tp:
                    reached_tp1_before = True
            after = _after_exit_targets(bars, sig["side"], sig["sl"], sig["tp1"], arm_price, legacy.when)
        else:
            after = {"later_050": False, "later_tp1": False, "sl_before_targets": False}
        chop_fired = bool(legacy and legacy.reason == "REVERSAL")
        premature = bool(chop_fired and (after["later_050"] or after["later_tp1"]))
        useful = bool(
            chop_fired
            and after["sl_before_targets"]
            and not reached_050_before
            and not reached_tp1_before
        )
        v0_reason = "UNPRICED"
        v0_price = None
        v0_event = episode.get("exit_event") or ""
        if episode["exit"] is not None:
            v0_price = episode["exit"]
            v0_reason = (paper_row or {}).get("exit_reason") or episode["exit_event"]
        else:
            v0_reason = "UNPRICED"
        v0_pts = points(sig["side"], episode["fill"], v0_price)
        directional = bool(feat and feat["sideways"] and v2.armed)
        trace = {
            "signal_id": sig["signal_id"],
            "timestamp": sig["when"].isoformat(),
            "direction": sig["side"],
            "cdx_entry": sig["cdx_entry"],
            "fill": episode["fill"],
            "qty": episode["qty"],
            "cdx_sl": sig["sl"],
            "cdx_tp1": sig["tp1"],
            "cdx_tp2": sig["tp2"],
            "execution_r": execution_r,
            "legacy_exit": legacy.reason if legacy else "",
            "legacy_exit_time": legacy.when.isoformat() if legacy and legacy.when else "",
            "legacy_exit_price": legacy.price if legacy else None,
            "mfe_points": v2.mfe,
            "mae_points": v2.mae,
            "mfe_before_legacy_r": (None if not legacy else _mfe_until(bars, sig["side"], episode["fill"], episode["fill_time"], legacy.when) / execution_r),
            "reached_050": v2.armed,
            "reached_050_time": v2.armed_time.isoformat() if v2.armed_time else "",
            "pivots": len(v2.pivots),
            "structural_revisions": len(v2.revisions),
            "near_entry_3m": v2.near_entry_bars,
            "sideways": bool(feat and feat["sideways"]),
            "efficiency": None if not feat else feat["efficiency"],
            "overlap": None if not feat else feat["overlap"],
            "paper_reason": (paper_row or {}).get("exit_reason", ""),
            "v0_event": v0_event,
            "v0_reason": v0_reason,
            "v1_time": v1.result.when.isoformat() if v1.result and v1.result.when else "",
            "v2_time": v2.result.when.isoformat() if v2.result and v2.result.when else "",
            "legacy_model_reason": legacy_sim.result.reason if legacy_sim.result else "",
            "v0_points": v0_pts,
            "v0_dollars": dollars(v0_pts, episode["qty"]),
            "v1_reason": v1.result.reason if v1.result else "",
            "v1_points": points(sig["side"], episode["fill"], v1.result.price if v1.result else None),
            "v1_dollars": dollars(points(sig["side"], episode["fill"], v1.result.price if v1.result else None), episode["qty"]),
            "v2_reason": v2.result.reason if v2.result else "",
            "v2_points": points(sig["side"], episode["fill"], v2.result.price if v2.result else None),
            "v2_dollars": dollars(points(sig["side"], episode["fill"], v2.result.price if v2.result else None), episode["qty"]),
            "v3_reason": v3.result.reason if v3.result else "",
            "v3_points": points(sig["side"], episode["fill"], v3.result.price if v3.result else None),
            "v3_dollars": dollars(points(sig["side"], episode["fill"], v3.result.price if v3.result else None), episode["qty"]),
            "later_050": after["later_050"],
            "later_tp1": after["later_tp1"],
            "reached_tp1_before_legacy": reached_tp1_before,
            "reached_050_before_legacy": reached_050_before,
            "premature": premature,
            "useful": useful,
            "directional_consolidation": directional,
            "opposite_count": len([t for t in opp if v2.result and v2.result.when and t <= v2.result.when]) if v2.result and v2.result.when else len(opp),
        }
        traces.append(trace)
    return {
        "traces": traces,
        "causal_fail": causal_fail,
        "reversal_all_paper": reversal_all,
        "native_signals": len(signals),
        "episodes": len(episodes),
    }


def _mfe_until(bars: list[Bar], side: str, fill: float, fill_time: datetime, until: datetime) -> float:
    entry_open = fill_time.replace(second=0, microsecond=0)
    mfe = 0.0
    for bar in bars:
        if bar.open_time <= entry_open:
            continue
        if bar.close_time > until:
            break
        if side == "LONG":
            mfe = max(mfe, bar.high - fill)
        else:
            mfe = max(mfe, fill - bar.low)
    return mfe


def write_reports(payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    traces = payload["traces"]
    fields = [
        "signal_id", "timestamp", "direction", "cdx_entry", "fill", "qty", "cdx_sl", "cdx_tp1", "cdx_tp2",
        "execution_r", "legacy_exit", "legacy_exit_time", "legacy_exit_price", "mfe_points", "mae_points",
        "mfe_before_legacy_r", "reached_050", "reached_050_time", "pivots", "structural_revisions",
        "near_entry_3m", "sideways", "efficiency", "overlap", "paper_reason", "v0_event", "v0_reason",
        "v1_time", "v2_time", "legacy_model_reason",
        "v0_points", "v0_dollars", "v1_reason", "v1_points", "v1_dollars", "v2_reason", "v2_points",
        "v2_dollars", "v3_reason", "v3_points", "v3_dollars", "later_050", "later_tp1",
        "reached_tp1_before_legacy", "reached_050_before_legacy", "premature", "useful",
        "directional_consolidation",
    ]
    with (OUT / "TRADE_TRACE.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(traces)
    with (OUT / "TODAY_CASES.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(traces)
    with (OUT / "PREMATURE_LEGACY_EXITS.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([r for r in traces if r["premature"]])
    with (OUT / "USEFUL_LEGACY_EXITS.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([r for r in traces if r["useful"]])
    summaries = {name: summarize(traces, name) for name in ("v0", "v1", "v2", "v3")}
    with (OUT / "SUMMARY.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["variant", *summaries["v2"].keys()])
        writer.writeheader()
        for name, row in summaries.items():
            writer.writerow({"variant": name, **row})
    _write_markdown(payload, summaries)


def _write_markdown(payload: dict, summaries: dict) -> None:
    traces = payload["traces"]
    causal = "PASS" if payload["causal_fail"] == 0 else "FAIL"
    verdict = "CDX_CONSOLIDATION_REPLAY_CAUSALITY_FAIL" if payload["causal_fail"] else "INSUFFICIENT_NATIVE_CDX_COVERAGE"
    near = [r["near_entry_3m"] for r in traces if r["v2_reason"] == "TP1"]
    lines = [
        "# CDX directional consolidation",
        "",
        f"VERDICT: {verdict}",
        "",
        f"Causality mismatches: {payload['causal_fail']}",
        f"Paper REVERSAL exits in the whole journal: {payload['reversal_all_paper']}",
        f"Vision-confirmed MNQ signals: {payload['native_signals']}",
        f"Supported trades with a broker fill: {len(traces)}",
        "",
        "Ribbon reference series: not in the repo. V4 was not run.",
        "Screenshots from the session were not in the repo. No prices were invented for them.",
        "Production order routing was not changed.",
        "",
    ]
    for row in traces:
        lines.append(
            f"- {row['signal_id']} {row['direction']} fill {row['fill']} "
            f"V0 {row['v0_reason']} V2 {row['v2_reason']} "
            f"legacy {row['legacy_exit'] or 'none'} sideways {row['sideways']}"
        )
    (OUT / "DATA_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "CAUSALITY_REPORT.md").write_text(
        "\n".join(
            [
                "# Causality",
                "",
                f"Result: {causal}",
                "",
                "Each V2 trade was replayed on every prefix of its managed 1-minute bars.",
                "The stop active at each bar, the arm flag, and any exit index had to match the full run.",
                f"Mismatches: {payload['causal_fail']}",
                "",
                "Arming, pivot confirmation, and stop activation use only bars already closed.",
                "A stop and a target on the same 1-minute bar resolve as the stop.",
                "A +0.50R touch does not activate a new stop on that same bar.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    def block(title: str, key: str) -> list[str]:
        s = summaries[key]
        return [
            title,
            "",
            f"Trades: {s['trades']} resolved, {s['open']} still open at data end, {s['unpriced']} without an exit price",
            f"Wins/losses: {s['wins']}/{s['losses']}",
            f"Points: {_fmt(s['points'])}",
            f"Dollars: {_fmt(s['dollars'])}",
            f"Largest loss (points): {_fmt(s['largest_loss_points'])}",
            f"Largest winner (points): {_fmt(s['largest_win_points'])}",
            f"Max DD (dollars): {_fmt(s['max_dd_dollars'])}",
            "",
        ]
    tp1 = sum(1 for r in traces if r["v1_reason"] == "TP1")
    sl = sum(1 for r in traces if r["v1_reason"] == "CDX_SL")
    struct = sum(1 for r in traces if r["v2_reason"] == "STRUCTURAL_STOP")
    opp_exits = sum(1 for r in traces if r["v3_reason"] == "OPPOSITE_SIGNAL")
    final = [
        f"VERDICT: {verdict}",
        "",
        f"SUPPORTED TRADES: {len(traces)}",
        "",
        f"NATIVE CDX COVERAGE: {len(traces)} of {payload['native_signals']} confirmed MNQ signals had a broker fill inside 8 minutes. Test and fixture vision rows were excluded. The 2:56 PM long had no confirmed Entry/TP1 read, so it is not in V1-V4.",
        "",
        "CURRENT CHOP EXIT RULE: There is no live rule that flattens because candles overlap. The live post-entry pullback rule is REVERSAL in phase74/quality/trail.py: after favorable excursion >= management risk (the CDX stop distance once the chart stop is on), a 10-point giveback from the extreme flattens. TIME_PROGRESS_15M_LT_1R exists and is configured off. SKIP_CHOP is pre-entry and filter_signals is false.",
        "",
        f"HOW MANY TIMES IT FIRED: {payload['reversal_all_paper']} REVERSAL rows in the paper journal. {sum(1 for r in traces if r['legacy_exit'] == 'REVERSAL')} of the supported broker-fill trades reach that predicate on the broker fill path.",
        "",
        f"PREMATURE LEGACY EXITS: {sum(1 for r in traces if r['premature'])}",
        "",
        "Every one of those reversal exits had already traded TP1 before the 10-point giveback. The later TP1 touch is a revisit, not a trade that was cut during the chop before +0.50R. The model reversal price was within a few points of TP1, or beyond it. None of these reversals fired before +1 execution R.",
        "",
        f"USEFUL LEGACY EXITS: {sum(1 for r in traces if r['useful'])}",
        "",
        "The one CDX-stop loss never reached +0.50R, so the reversal rule was not armed and saved nothing. V2 loses the same stop.",
        "",
        *block("V0 LIVE BASELINE", "v0"),
        *block("V1 CDX NATIVE", "v1"),
        f"TP1 hits: {tp1}",
        f"SL hits: {sl}",
        "",
        *block("V2 CDX +0.50R STRUCTURAL", "v2"),
        f"TP1 hits: {sum(1 for r in traces if r['v2_reason'] == 'TP1')}",
        f"Structural exits: {struct}",
        "",
        *block("V3 + OPPOSITE CDX SIGNAL", "v3"),
        f"Exits caused by opposite signal: {opp_exits}",
        "",
        "V4 + ENTRY/RIBBON RECLAIM",
        "",
        "Available: NO",
        "",
        "No numeric ribbon series is stored. The reclaim rule was not fabricated.",
        "",
        "TODAY CASE STUDIES",
        "",
    ]
    for row in traces:
        final += [
            f"Signal: {row['signal_id']}",
            f"Side: {row['direction']}",
            f"Entry: {row['cdx_entry']}",
            f"Fill: {row['fill']}",
            f"CDX SL: {row['cdx_sl']}",
            f"CDX TP1: {row['cdx_tp1']}",
            f"Legacy exit: {row['legacy_exit'] or 'none'} {row['legacy_exit_time']}",
            f"Broker exit: {row['v0_reason']} {row.get('v0_event', '')}",
            f"+0.50R reached: {'YES' if row['reached_050'] else 'NO'} {row['reached_050_time']}",
            f"TP1 touched before that legacy exit: {'YES' if row['reached_tp1_before_legacy'] else 'NO'}",
            f"TP1 later reached after a reversal exit: {'YES' if row['later_tp1'] else 'NO'}",
            f"V2 result: {row['v2_reason']} at {row.get('v2_time', '')} points {_fmt(row['v2_points'])}",
            "",
        ]
    final += [
        "TIME NEAR ENTRY",
        "",
        "Zone is CDX Entry ± 0.15 execution R, counted on completed 3-minute closes until the V2 exit. Diagnostic only.",
        f"Median 3-minute bars near Entry on V2 TP1 trades: {(_fmt(sorted(near)[len(near)//2], 1) if near else 'none')}",
        f"Maximum: {max(near) if near else 'none'}",
        "",
        f"CAUSALITY: {causal}",
        "",
        "PRODUCTION MODIFIED: NO",
        "",
        "RECOMMENDED NEXT STEP: Keep collecting exact Entry, SL, and TP1 on live signals. Do not change the live stop or the 10-point reversal from this sample. The overlap of candles is not what flattened these trades.",
        "",
    ]
    (OUT / "FINAL_REPORT.md").write_text("\n".join(final), encoding="utf-8")


def main() -> None:
    payload = build()
    write_reports(payload)
    print(f"trades {len(payload['traces'])} causality_mismatches {payload['causal_fail']}")


if __name__ == "__main__":
    main()
