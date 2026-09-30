"""Pre-entry descriptions and MNQ stop sizing. Does not place or resize orders."""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "forward_rehearsal" / "reports" / "cdx_preentry_filter"
BARS = ROOT / "phase74" / "logs" / "bars.csv"
VISION = ROOT / "cdx_vision" / "logs" / "vision_levels.jsonl"
AUDIT = ROOT / "phase85" / "logs" / "audit.jsonl"
MNQ_DOLLARS_PER_POINT = 2.0
RISK_TIERS = (50.0, 75.0, 100.0)

# Natural units chosen before looking at feature values. A skip is not frozen
# from these. They are recorded so the next batch can be counted without fitting.
F1_FLIP_WINDOW = 6


@dataclass(frozen=True)
class Bar:
    open_time: datetime
    high: float
    low: float
    close: float

    @property
    def close_time(self) -> datetime:
        return self.open_time + timedelta(minutes=1)


@dataclass(frozen=True)
class Three:
    open_time: datetime
    high: float
    low: float
    close: float

    @property
    def close_time(self) -> datetime:
        return self.open_time + timedelta(minutes=3)


def adverse_displacement(side: str, cdx_entry: float, fill: float) -> float:
    """Positive means the fill is worse than the CDX entry."""
    if side == "LONG":
        return fill - cdx_entry
    if side == "SHORT":
        return cdx_entry - fill
    raise ValueError(side)


def size_mnq(entry: float, stop: float, cap_dollars: float) -> tuple[int, str, float]:
    """Quantity from the full stop distance. The stop argument is not changed."""
    distance = abs(entry - stop)
    risk = distance * MNQ_DOLLARS_PER_POINT
    if distance <= 0 or cap_dollars <= 0:
        return 0, "RISK_MIN_CONTRACT_EXCEEDS_CAP", risk
    raw = math.floor(cap_dollars / risk)
    if raw < 1:
        return 0, "RISK_MIN_CONTRACT_EXCEEDS_CAP", risk
    return int(raw), "RISK_ACCEPT", risk


def efficiency(closes: list[float]) -> float | None:
    if len(closes) < 2:
        return None
    net = abs(closes[-1] - closes[0])
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    if path <= 0:
        return None
    return net / path


def overlap(bars: list[Three]) -> float | None:
    if len(bars) < 2:
        return None
    ratios = []
    for left, right in zip(bars, bars[1:]):
        span = min(left.high - left.low, right.high - right.low)
        shared = min(left.high, right.high) - max(left.low, right.low)
        ratios.append(max(shared, 0.0) / span if span > 0 else 0.0)
    return sum(ratios) / len(ratios)


def true_ranges(bars: list[Three]) -> list[float]:
    out = []
    prev_close = None
    for bar in bars:
        span = bar.high - bar.low
        if prev_close is None:
            out.append(span)
        else:
            out.append(max(span, abs(bar.high - prev_close), abs(bar.low - prev_close)))
        prev_close = bar.close
    return out


def atr14(bars: list[Three]) -> float | None:
    ranges = true_ranges(bars)
    if len(ranges) < 14:
        return None
    return sum(ranges[-14:]) / 14.0


def flip_count(signals: list[tuple[datetime, str]], asof: datetime, window: list[Three]) -> int:
    """Direction changes among confirmed signals inside the completed-bar window."""
    if not window:
        return 0
    start = window[0].open_time
    inside = [(t, side) for t, side in signals if start <= t < asof]
    inside.sort()
    flips = 0
    for (_, prev), (_, cur) in zip(inside, inside[1:]):
        if prev != cur:
            flips += 1
    return flips


def opposite_bars_ago(signals: list[tuple[datetime, str]], asof: datetime, side: str, threes: list[Three]) -> int | None:
    prior = [t for t, other in signals if t < asof and other != side]
    if not prior or not threes:
        return None
    last = max(prior)
    return sum(1 for bar in threes if last < bar.close_time <= asof)


def completed_threes(bars: list[Bar], asof: datetime) -> list[Three]:
    known = [bar for bar in bars if bar.close_time <= asof]
    buckets: dict[datetime, list[Bar]] = {}
    for bar in known:
        epoch = int(bar.open_time.timestamp())
        key = datetime.fromtimestamp(epoch - epoch % 180, tz=timezone.utc)
        buckets.setdefault(key, []).append(bar)
    out = []
    for key in sorted(buckets):
        group = sorted(buckets[key], key=lambda b: b.open_time)
        if len(group) != 3:
            continue
        opens = [b.open_time for b in group]
        if opens[1] != opens[0] + timedelta(minutes=1) or opens[2] != opens[0] + timedelta(minutes=2):
            continue
        if group[-1].close_time > asof:
            continue
        out.append(Three(opens[0], max(b.high for b in group), min(b.low for b in group), group[-1].close))
    return out


def first_touch(bars: list[Bar], side: str, fill_time: datetime, sl: float, tp1: float) -> str:
    """TP1_BEFORE_SL or SL_BEFORE_TP1. Same-bar collision is the stop."""
    entry_open = fill_time.replace(second=0, microsecond=0)
    for bar in bars:
        if bar.open_time <= entry_open:
            continue
        hit_sl = bar.low <= sl if side == "LONG" else bar.high >= sl
        hit_tp = bar.high >= tp1 if side == "LONG" else bar.low <= tp1
        if hit_sl:
            return "SL_BEFORE_TP1"
        if hit_tp:
            return "TP1_BEFORE_SL"
    return "unresolved"


def features_at(
    bars: list[Bar],
    signals: list[tuple[datetime, str]],
    *,
    asof: datetime,
    side: str,
    cdx_entry: float,
    fill: float,
    sl: float,
    tp1: float,
) -> dict:
    threes = completed_threes(bars, asof)
    last6 = threes[-6:]
    last10 = threes[-10:]
    last3 = threes[-3:]
    atr = atr14(threes)
    native_r = abs(cdx_entry - sl)
    execution_r = abs(fill - sl)
    tp1_native = abs(tp1 - cdx_entry)
    if side == "LONG":
        tp1_from_fill = tp1 - fill
    else:
        tp1_from_fill = fill - tp1
    adverse = adverse_displacement(side, cdx_entry, fill)
    range6 = (max(b.high for b in last6) - min(b.low for b in last6)) if len(last6) == 6 else None
    range10 = (max(b.high for b in last10) - min(b.low for b in last10)) if len(last10) == 10 else None

    def norm(value: float | None) -> float | None:
        if value is None or atr in (None, 0):
            return None
        return value / atr

    return {
        "opposite_signal_bars_ago": opposite_bars_ago(signals, asof, side, threes),
        "flips_3": flip_count(signals, asof, last3),
        "flips_6": flip_count(signals, asof, last6),
        "flips_10": flip_count(signals, asof, last10),
        "efficiency_6": efficiency([b.close for b in last6]) if len(last6) == 6 else None,
        "efficiency_10": efficiency([b.close for b in last10]) if len(last10) == 10 else None,
        "overlap_6": overlap(last6) if len(last6) == 6 else None,
        "overlap_10": overlap(last10) if len(last10) == 10 else None,
        "atr_14": atr,
        "range_6_atr": norm(range6),
        "range_10_atr": norm(range10),
        "native_R": native_r,
        "execution_R": execution_r,
        "native_R_atr": norm(native_r),
        "execution_R_atr": norm(execution_r),
        "tp1_native_R": (tp1_native / native_r) if native_r else None,
        "tp1_execution_R": (tp1_from_fill / execution_r) if execution_r else None,
        "adverse_entry_slippage_points": adverse,
        "fill_displacement_R": (adverse / native_r) if native_r else None,
        "fill_displacement_ATR": norm(abs(fill - cdx_entry)),
        "f1_recent_whipsaw": flip_count(signals, asof, last6) >= 1,
        "f2_adverse_fill": adverse > 0,
    }


def shadow_decision(row: dict) -> dict:
    """Observation only. Nothing here is allowed to change an order."""
    return {
        "F1_RECENT_WHIPSAW": bool(row.get("f1_recent_whipsaw")),
        "F2_ADVERSE_FILL": bool(row.get("f2_adverse_fill")),
        "F3_RIBBON_CONFLICT": None,
        "SHADOW_DECISION": "WOULD_TAKE",
        "reason": "NO_FROZEN_SKIP",
    }


def append_shadow_record(path: Path, record: dict, order: dict | None = None) -> dict:
    """Append one research row. Does not read it back into the order."""
    decision = shadow_decision(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({**record, **decision}) + "\n")
    if order is not None:
        return dict(order)
    return decision


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
    out = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            when = _parse_time(row["timestamp_utc"])
            if when is None:
                continue
            out.append(Bar(when, float(row["high"]), float(row["low"]), float(row["close"])))
    out.sort(key=lambda b: b.open_time)
    return out


def load_confirmed_signals(path: Path = VISION) -> list[tuple[datetime, str]]:
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("validation_status") != "VISION_CONFIRMED":
            continue
        if not str(obj.get("signal_id", "")).startswith("2026-"):
            continue
        when = _parse_time(str(obj["signal_id"]))
        side = obj.get("webhook_direction")
        if when is None or side not in {"LONG", "SHORT"}:
            continue
        found.append((when, side))
    return sorted(set(found))


def load_episodes(path: Path = AUDIT) -> list[dict]:
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    episodes = []
    i = 0
    while i < len(events):
        ev = events[i]
        nxt = events[i + 1] if i + 1 < len(events) else None
        if ev.get("event") == "FILL" and nxt and nxt.get("event") == "PROTECTION_SUBMITTED":
            episode = {
                "fill_time": _parse_time(ev["ts_utc"]),
                "fill": float(ev["price"]),
                "qty": int(ev.get("qty") or 0),
            }
            episodes.append(episode)
            i += 2
            continue
        i += 1
    return episodes


def match_fill(when: datetime, episodes: list[dict]) -> dict | None:
    best = None
    best_dt = None
    for episode in episodes:
        delta = (episode["fill_time"] - when).total_seconds()
        if 0 <= delta <= 8 * 60 and (best_dt is None or delta < best_dt):
            best = episode
            best_dt = delta
    return best


def load_native(path: Path = VISION) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("validation_status") != "VISION_CONFIRMED":
            continue
        if str(obj.get("ticker")) != "MNQ" or not str(obj.get("signal_id", "")).startswith("2026-"):
            continue
        when = _parse_time(str(obj["signal_id"]))
        if when is None:
            continue
        rows.append(
            {
                "signal_id": obj["signal_id"],
                "when": when,
                "side": obj["webhook_direction"],
                "cdx_entry": float(obj.get("cdx_native_entry") or obj["entry"]),
                "sl": float(obj.get("cdx_stop") or obj["stop"]),
                "tp1": float(obj.get("cdx_tp1") or obj["tp1"]),
            }
        )
    return rows


def build_rows() -> list[dict]:
    bars = load_bars()
    signals = load_confirmed_signals()
    episodes = load_episodes()
    rows = []
    for sig in load_native():
        episode = match_fill(sig["when"], episodes)
        if episode is None:
            continue
        outcome = first_touch(bars, sig["side"], episode["fill_time"], sig["sl"], sig["tp1"])
        feat = features_at(
            bars,
            signals,
            asof=sig["when"],
            side=sig["side"],
            cdx_entry=sig["cdx_entry"],
            fill=episode["fill"],
            sl=sig["sl"],
            tp1=sig["tp1"],
        )
        truncated = [b for b in bars if b.close_time <= sig["when"]]
        again = features_at(
            truncated,
            signals,
            asof=sig["when"],
            side=sig["side"],
            cdx_entry=sig["cdx_entry"],
            fill=episode["fill"],
            sl=sig["sl"],
            tp1=sig["tp1"],
        )
        if again != feat:
            raise RuntimeError(f"future leakage {sig['signal_id']}")
        intended_distance = abs(sig["cdx_entry"] - sig["sl"])
        actual_distance = abs(episode["fill"] - sig["sl"])
        row = {
            "signal_id": sig["signal_id"],
            "timestamp": sig["when"].isoformat(),
            "side": sig["side"],
            "outcome": outcome,
            "cdx_entry": sig["cdx_entry"],
            "actual_fill": episode["fill"],
            "cdx_sl": sig["sl"],
            "cdx_tp1": sig["tp1"],
            "actual_qty": episode["qty"],
            "stop_points_from_fill": actual_distance,
            "stop_points_from_entry": intended_distance,
            **feat,
        }
        for cap in RISK_TIERS:
            qty, reason, _ = size_mnq(episode["fill"], sig["sl"], cap)
            row[f"qty_at_{int(cap)}_from_fill"] = qty
            row[f"reason_at_{int(cap)}_from_fill"] = reason
            eqty, ereason, _ = size_mnq(sig["cdx_entry"], sig["sl"], cap)
            row[f"qty_at_{int(cap)}_from_entry"] = eqty
            row[f"reason_at_{int(cap)}_from_entry"] = ereason
        row["full_stop_exposure"] = actual_distance * MNQ_DOLLARS_PER_POINT * episode["qty"]
        row["risk_per_1_mnq_fill"] = actual_distance * MNQ_DOLLARS_PER_POINT
        row["risk_per_1_mnq_entry"] = intended_distance * MNQ_DOLLARS_PER_POINT
        shadow = shadow_decision(row)
        row.update(shadow)
        rows.append(row)
    return rows


def _fmt(value, digits=4) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def write_outputs(rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    feature_cols = [
        "signal_id", "timestamp", "side", "outcome", "cdx_entry", "actual_fill", "cdx_sl", "cdx_tp1",
        "native_R", "execution_R", "opposite_signal_bars_ago", "flips_3", "flips_6", "flips_10",
        "efficiency_6", "efficiency_10", "overlap_6", "overlap_10", "atr_14", "range_6_atr", "range_10_atr",
        "native_R_atr", "execution_R_atr", "tp1_native_R", "tp1_execution_R",
        "adverse_entry_slippage_points", "fill_displacement_R", "fill_displacement_ATR",
    ]
    with (OUT / "PREENTRY_FEATURES.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=feature_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with (OUT / "FROZEN_TRADES.csv").open("w", newline="", encoding="utf-8") as handle:
        cols = ["signal_id", "timestamp", "side", "cdx_entry", "actual_fill", "cdx_sl", "cdx_tp1", "outcome", "actual_qty"]
        writer = csv.DictWriter(handle, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    frozen_copy = ROOT / "cdx_preentry_frozen_trades.csv"
    with frozen_copy.open("w", newline="", encoding="utf-8") as handle:
        cols = ["signal_id", "timestamp", "side", "cdx_entry", "actual_fill", "cdx_sl", "cdx_tp1", "outcome"]
        writer = csv.DictWriter(handle, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    risk_cols = [
        "signal_id", "side", "outcome", "stop_points_from_fill", "stop_points_from_entry", "actual_qty",
        "full_stop_exposure", "risk_per_1_mnq_fill", "risk_per_1_mnq_entry",
        "qty_at_50_from_fill", "qty_at_75_from_fill", "qty_at_100_from_fill",
        "qty_at_50_from_entry", "qty_at_75_from_entry", "qty_at_100_from_entry",
    ]
    with (OUT / "RISK_SIZING.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=risk_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    hist_cols = feature_cols + [
        "actual_qty", "full_stop_exposure", "qty_at_50_from_fill", "qty_at_75_from_fill", "qty_at_100_from_fill",
        "F1_RECENT_WHIPSAW", "F2_ADVERSE_FILL", "SHADOW_DECISION",
    ]
    with (OUT / "HISTORICAL_COMPARISON.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=hist_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    _write_markdown(rows)


def _nums(rows: list[dict], key: str) -> list[float]:
    out = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out.append(float(value))
    return out


def _write_markdown(rows: list[dict]) -> None:
    loser = next(r for r in rows if r["signal_id"] == "2026-09-29T13:51:00Z")
    winners = [r for r in rows if r is not loser]
    compare_keys = [
        "opposite_signal_bars_ago", "flips_3", "flips_6", "flips_10", "efficiency_6", "efficiency_10",
        "overlap_6", "overlap_10", "atr_14", "range_6_atr", "range_10_atr", "native_R_atr", "execution_R_atr",
        "tp1_native_R", "tp1_execution_R", "adverse_entry_slippage_points", "fill_displacement_R",
        "fill_displacement_ATR", "native_R", "execution_R",
    ]
    lines = ["# 9:51 AM short versus the four TP1 trades", ""]
    lines.append("| Feature | Loser | Winner min | Winner median | Winner max | Separation |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    separated = []
    for key in compare_keys:
        values = _nums(winners, key)
        raw = loser.get(key)
        if raw is None or not values:
            sep = "unavailable"
            lines.append(f"| {key} | {_fmt(raw)} | | | | {sep} |")
            continue
        loser_v = float(raw)
        ordered = sorted(values)
        mid = ordered[len(ordered) // 2]
        outside = loser_v < ordered[0] or loser_v > ordered[-1]
        sep = "sample shows separation" if outside else "inside winner range"
        if outside:
            separated.append(key)
        lines.append(
            f"| {key} | {_fmt(loser_v)} | {_fmt(ordered[0])} | {_fmt(mid)} | {_fmt(ordered[-1])} | {sep} |"
        )
    lines += [
        "",
        "Separation means the loser is outside the min/max of the four winners.",
        "That is a hypothesis on five trades, not a filter.",
        "",
        f"Features outside the winner range: {', '.join(separated) if separated else 'none'}",
        "",
    ]
    (OUT / "LOSER_2026-09-29_0951.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    rows = build_rows()
    expected = {
        "2026-09-28T11:42:00Z": "TP1_BEFORE_SL",
        "2026-09-28T14:00:00Z": "TP1_BEFORE_SL",
        "2026-09-29T06:27:00Z": "TP1_BEFORE_SL",
        "2026-09-29T13:51:00Z": "SL_BEFORE_TP1",
        "2026-09-30T01:06:00Z": "TP1_BEFORE_SL",
    }
    got = {r["signal_id"]: r["outcome"] for r in rows}
    if got != expected:
        raise SystemExit(f"outcome mismatch {got}")
    write_outputs(rows)
    print(f"rows {len(rows)} outcomes {got}")


if __name__ == "__main__":
    main()
