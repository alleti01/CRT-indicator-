"""One row per CDX signal: market conditions at the signal, then the outcome of every stop/target option.

Features use only bars that closed before the signal minute. Labels replay the
1-minute bars after the signal (triple barrier: target, stop, or 4-hour limit),
so every signal teaches every option, whether or not the bot traded it.

    python -m cdx_ml.dataset            # writes cdx_ml/data/dataset.csv and DATA_CARD.md
"""
from __future__ import annotations

import bisect
import csv
import json
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

from phase73.market_data.bar import Bar
from phase74.quality.htf_bias import BEARISH, BULLISH, structure_bias, resample

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "phase74" / "logs"
VISION = ROOT / "cdx_vision" / "logs" / "vision_levels.jsonl"
OUT = Path(__file__).resolve().parent / "data"
UTC = timezone.utc
ET = ZoneInfo("America/New_York")

CDX_START = datetime(2026, 9, 22, 4, 0, tzinfo=UTC)  # first day the bot took CDX prints as-is
HORIZON = timedelta(hours=4)
COST_PTS = 1.0  # round-trip slippage + fees, in points
MIN_STOP = 4.0
MIN_HISTORY_BARS = 600
MAX_PATH_GAP = timedelta(minutes=5)
TARGETS = (1.0, 2.0, 3.0)
STOP_KINDS = ("fixed14", "struct5", "struct10", "atr1", "atr1.5", "atr2", "cdx")


# ---------- loading ----------

def parse(ts: str) -> datetime:
    t = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def load_bars(logs: Path = LOGS) -> list[Bar]:
    """Real OHLC from bars.csv; closes from decisions.jsonl fill minutes bars.csv lacks."""
    merged: dict[datetime, Bar] = {}
    dec = logs / "decisions.jsonl"
    if dec.exists():
        prev = None
        closes = {}
        with dec.open(encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("reason_code") == "bar" and r.get("current_price"):
                    closes[parse(r["market_timestamp"])] = float(r["current_price"])
        for t in sorted(closes):
            c = closes[t]
            o = prev if prev is not None else c
            merged[t] = Bar(t, o, max(o, c), min(o, c), c)
            prev = c
    path = logs / "bars.csv"
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                t = parse(r["timestamp_utc"])
                merged[t] = Bar(t, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"] or 0))
    out: list[Bar] = []
    prev_c = None
    for t in sorted(merged):
        b = merged[t]
        if b.low < 25000 or (prev_c is not None and abs(b.close - prev_c) / prev_c > 0.02):
            continue  # placeholder prices and bad ticks
        out.append(b)
        prev_c = b.close
    return out


_ALERT_ID = re.compile(r"^\d{4}-\d{2}-\d{2}T")


def is_alert_id(signal_id: str) -> bool:
    """TradingView alerts carry a timestamp id. Random-UUID ids are the bot's own readiness-probe
    test signals (make_test_signal), and REEN* ids are manual reentries; neither is a CDX print."""
    return bool(_ALERT_ID.match(signal_id))


def load_signals(logs: Path = LOGS) -> list[dict]:
    seen: dict[str, dict] = {}
    with (logs / "signals.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("event") in ("SIGNAL_LONG", "SIGNAL_SHORT") and is_alert_id(r["signal_id"]):
                seen[r["signal_id"]] = r
    out = []
    for r in seen.values():
        t = parse(r["signal_time_utc"])
        out.append({
            "signal_id": r["signal_id"],
            "t": t,
            "side": "LONG" if r["event"] == "SIGNAL_LONG" else "SHORT",
            "price": float(r["signal_price"]),
            "source": "cdx" if t >= CDX_START else "phase72a",
        })
    out.sort(key=lambda s: s["t"])
    dedup: list[dict] = []
    for s in out:
        if dedup and dedup[-1]["side"] == s["side"] and s["t"] - dedup[-1]["t"] <= timedelta(seconds=60):
            continue  # same alert delivered twice
        dedup.append(s)
    return dedup


def load_cdx_levels(path: Path = VISION) -> dict[str, dict]:
    """Vision-confirmed CDX Entry/SL/TP per signal id."""
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("validation_status") != "VISION_CONFIRMED" or not r.get("cdx_stop"):
                continue
            out[r["signal_id"]] = {k: float(r[k]) if r.get(k) else None for k in ("cdx_stop", "cdx_tp1", "cdx_tp2")}
    return out


# ---------- features ----------

def _atr(bars: Sequence[Bar], n: int = 14) -> float | None:
    if len(bars) < n + 1:
        return None
    w = list(bars[-(n + 1):])
    return sum(max(b.high - b.low, abs(b.high - p.close), abs(b.low - p.close)) for p, b in zip(w, w[1:])) / n


def _efficiency(bars: Sequence[Bar]) -> float:
    if len(bars) < 2:
        return 0.0
    path = sum(abs(b.close - a.close) for a, b in zip(bars, bars[1:]))
    return abs(bars[-1].close - bars[0].close) / path if path else 0.0


def _overlap(bars: Sequence[Bar]) -> float:
    vals = []
    for a, b in zip(bars, bars[1:]):
        rng = max(a.high, b.high) - min(a.low, b.low)
        inter = min(a.high, b.high) - max(a.low, b.low)
        vals.append(max(inter, 0.0) / rng if rng else 1.0)
    return statistics.mean(vals) if vals else 0.0


def _session(t: datetime) -> str:
    h = t.astimezone(ET).hour + t.astimezone(ET).minute / 60
    if h >= 18 or h < 2:
        return "asia"
    if h < 8:
        return "london"
    if h < 11:
        return "ny_open"
    if h < 14:
        return "ny_mid"
    if h < 17:
        return "ny_pm"
    return "close"


def _futures_day_start(t: datetime) -> datetime:
    et = t.astimezone(ET)
    start = et.replace(hour=18, minute=0, second=0, microsecond=0)
    if et < start:
        start -= timedelta(days=1)
    return start.astimezone(UTC)


def _align(side: str, bias: str) -> int:
    want, against = (BULLISH, BEARISH) if side == "LONG" else (BEARISH, BULLISH)
    return 1 if bias == want else -1 if bias == against else 0


def features(sig: dict, hist: Sequence[Bar], prev_sig: dict | None, cdx: dict | None) -> dict:
    """Everything here is known before the signal minute. `hist` must end before it."""
    sgn = 1 if sig["side"] == "LONG" else -1
    entry = sig["price"]
    threes = resample(hist, 3)
    atr3 = _atr(threes) or float("nan")
    atr3_slow = statistics.mean([b.high - b.low for b in threes[-100:]]) if len(threes) >= 20 else float("nan")
    last20 = threes[-20:]
    hi20 = max(b.high for b in last20)
    lo20 = min(b.low for b in last20)
    day0 = _futures_day_start(sig["t"])
    day = [b for b in hist if b.timestamp >= day0] or list(hist[-1:])
    day_hi = max(b.high for b in day)
    day_lo = min(b.low for b in day)

    def ret(minutes: int) -> float:
        cut = sig["t"] - timedelta(minutes=minutes)
        i = bisect.bisect_left([b.timestamp for b in hist], cut)
        base = hist[min(i, len(hist) - 1)].close
        return sgn * (hist[-1].close - base) / atr3 if atr3 == atr3 and atr3 else float("nan")

    et = sig["t"].astimezone(ET)
    row = {
        "side": sgn,
        "align_15m": _align(sig["side"], structure_bias(resample(hist, 15))),
        "align_1h": _align(sig["side"], structure_bias(resample(hist, 60))),
        "atr3": atr3,
        "atr_ratio": atr3 / atr3_slow if atr3_slow == atr3_slow and atr3_slow else float("nan"),
        "session": _session(sig["t"]),
        "hour_et": et.hour + et.minute / 60,
        "weekday": et.weekday(),
        "eff20": _efficiency(last20),
        "overlap20": _overlap(last20),
        "range20_atr": (hi20 - lo20) / atr3 if atr3 else float("nan"),
        # Where the signal sits in the last hour's range: 0 = at the extreme the trade fades from, 1 = at the far side.
        "pos20": ((entry - lo20) / (hi20 - lo20) if sgn > 0 else (hi20 - entry) / (hi20 - lo20)) if hi20 > lo20 else 0.5,
        "room_day_atr": ((day_hi - entry) if sgn > 0 else (entry - day_lo)) / atr3 if atr3 else float("nan"),
        "ret15_atr": ret(15),
        "ret60_atr": ret(60),
        "mins_since_prev": (sig["t"] - prev_sig["t"]).total_seconds() / 60 if prev_sig else float("nan"),
        "prev_same_side": int(prev_sig is not None and prev_sig["side"] == sig["side"]),
        "cdx_sl_pts": float("nan"),
        "cdx_tp1_r": float("nan"),
        "cdx_tp2_r": float("nan"),
    }
    if cdx and cdx.get("cdx_stop"):
        risk = sgn * (entry - cdx["cdx_stop"])
        if risk > 0:
            row["cdx_sl_pts"] = risk
            if cdx.get("cdx_tp1"):
                row["cdx_tp1_r"] = sgn * (cdx["cdx_tp1"] - entry) / risk
            if cdx.get("cdx_tp2"):
                row["cdx_tp2_r"] = sgn * (cdx["cdx_tp2"] - entry) / risk
    return row


def stop_distances(sig: dict, hist: Sequence[Bar], feats: dict) -> dict[str, float]:
    sgn = 1 if sig["side"] == "LONG" else -1
    entry = sig["price"]
    threes = resample(hist, 3)
    atr = feats["atr3"]
    out = {"fixed14": 14.25}
    if atr == atr:
        for n in (5, 10):
            w = threes[-n:]
            lvl = min(b.low for b in w) - 0.05 * atr if sgn > 0 else max(b.high for b in w) + 0.05 * atr
            out[f"struct{n}"] = max(sgn * (entry - lvl), MIN_STOP)
        for m in (1.0, 1.5, 2.0):
            out[f"atr{m:g}"] = max(m * atr, MIN_STOP)
    if feats["cdx_sl_pts"] == feats["cdx_sl_pts"]:
        out["cdx"] = max(feats["cdx_sl_pts"], MIN_STOP)
    return out


# ---------- labels ----------

@dataclass(frozen=True)
class Outcome:
    r: float
    exit: str  # TARGET, STOP, TIME
    minutes: float


def triple_barrier(side: str, entry: float, dist: float, target_r: float, path: Sequence[Bar]) -> Outcome:
    """Stop is checked before target inside a bar. Cost is charged in R."""
    sgn = 1 if side == "LONG" else -1
    stop = entry - sgn * dist
    target = entry + sgn * dist * target_r
    t0 = path[0].timestamp
    for b in path:
        if sgn * ((b.low if sgn > 0 else b.high) - stop) <= 0:
            return Outcome(-1.0 - COST_PTS / dist, "STOP", (b.timestamp - t0).total_seconds() / 60)
        if sgn * ((b.high if sgn > 0 else b.low) - target) >= 0:
            return Outcome(target_r - COST_PTS / dist, "TARGET", (b.timestamp - t0).total_seconds() / 60)
    pts = sgn * (path[-1].close - entry)
    return Outcome(pts / dist - COST_PTS / dist, "TIME", (path[-1].timestamp - t0).total_seconds() / 60)


def label_columns(sig: dict, dists: dict[str, float], path: Sequence[Bar], atr: float) -> dict:
    sgn = 1 if sig["side"] == "LONG" else -1
    entry = sig["price"]
    mfe = max(sgn * ((b.high if sgn > 0 else b.low) - entry) for b in path)
    mae = max(sgn * (entry - (b.low if sgn > 0 else b.high)) for b in path)
    row = {"mfe_pts": mfe, "mae_pts": mae, "mfe_atr": mfe / atr if atr else float("nan"), "mae_atr": mae / atr if atr else float("nan")}
    for kind in STOP_KINDS:
        d = dists.get(kind)
        row[f"dist_{kind}"] = d if d is not None else float("nan")
        for tr in TARGETS:
            key = f"{kind}_t{tr:g}"
            if d is None:
                row[f"r_{key}"] = float("nan")
                row[f"exit_{key}"] = ""
                continue
            o = triple_barrier(sig["side"], entry, d, tr, path)
            row[f"r_{key}"] = o.r
            row[f"exit_{key}"] = o.exit
    return row


# ---------- build ----------

def _data_hole(a: datetime, b: datetime) -> bool:
    """A gap over 5 minutes that is not the 5-6 pm ET daily futures break."""
    if b - a <= MAX_PATH_GAP:
        return False
    ea, eb = a.astimezone(ET), b.astimezone(ET)
    a_min = ea.hour * 60 + ea.minute
    b_min = eb.hour * 60 + eb.minute
    in_break = 16 * 60 + 55 <= a_min <= 17 * 60 + 5 and 17 * 60 + 55 <= b_min <= 18 * 60 + 10
    return not in_break


def build(bars: list[Bar], signals: list[dict], cdx_levels: dict[str, dict]) -> tuple[list[dict], Counter]:
    times = [b.timestamp for b in bars]
    rows: list[dict] = []
    dropped: Counter = Counter()
    prev = None
    for sig in signals:
        minute = sig["t"].replace(second=0, microsecond=0)
        # Bars are stamped at their close: the bar stamped at the signal minute is known; the path starts after it.
        i = bisect.bisect_right(times, minute)
        hist = bars[max(0, i - 2000) : i]
        path = [b for b in bars[i : i + 400] if b.timestamp < sig["t"] + HORIZON]
        reason = ""
        if len(hist) < MIN_HISTORY_BARS:
            reason = "short_history"
        elif sig["t"] - hist[-1].timestamp > timedelta(minutes=10):
            reason = "stale_bars_before_signal"
        elif len(path) < 30:
            reason = "no_bars_after_signal"
        elif any(_data_hole(a.timestamp, b.timestamp) for a, b in zip(path[:60], path[1:60])):
            reason = "gap_in_first_hour"
        if reason:
            dropped[reason] += 1
            prev = sig
            continue
        feats = features(sig, hist, prev, cdx_levels.get(sig["signal_id"]))
        dists = stop_distances(sig, hist, feats)
        rows.append({
            "signal_id": sig["signal_id"],
            "signal_time_utc": sig["t"].isoformat(),
            "source": sig["source"],
            "direction": sig["side"],
            "price": sig["price"],
            **feats,
            **label_columns(sig, dists, path, feats["atr3"]),
        })
        prev = sig
    return rows, dropped


def write(rows: list[dict], dropped: Counter, n_signals: int, out: Path = OUT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys())
    with (out / "dataset.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) and not math.isnan(v) else ("" if isinstance(v, float) else v)) for k, v in r.items()})
    (out / "DATA_CARD.md").write_text(data_card(rows, dropped, n_signals), encoding="utf-8")


def _mean(vals) -> float:
    vals = [v for v in vals if v == v]
    return statistics.mean(vals) if vals else float("nan")


def data_card(rows: list[dict], dropped: Counter, n_signals: int) -> str:
    cdx = [r for r in rows if r["source"] == "cdx"]
    lines = [
        "# CDX learning dataset",
        "",
        "Generated by `python -m cdx_ml.dataset`. One row per signal. Features use bars closed before the signal minute; labels replay the next 4 hours.",
        "",
        "## Coverage",
        "",
        f"- Signals in the webhook log: {n_signals}",
        f"- Rows kept: {len(rows)} ({len(cdx)} CDX, {len(rows) - len(cdx)} Phase72A before Sep 22)",
        f"- Dropped: {dict(dropped) or 'none'}",
        f"- First / last row: {rows[0]['signal_time_utc']} / {rows[-1]['signal_time_utc']}",
        f"- Rows with a vision-confirmed CDX stop: {sum(1 for r in rows if r['cdx_sl_pts'] == r['cdx_sl_pts'])}",
        "",
        "## Average R per option, CDX rows (every signal, no filter)",
        "",
        "| Stop | Median distance | 1R | 2R | 3R |",
        "|---|---|---|---|---|",
    ]
    for kind in STOP_KINDS:
        d = [r[f"dist_{kind}"] for r in cdx if r[f"dist_{kind}"] == r[f"dist_{kind}"]]
        if not d:
            lines.append(f"| {kind} | n/a | | | |")
            continue
        cells = " | ".join(f"{_mean(r[f'r_{kind}_t{t:g}'] for r in cdx):+.2f}" for t in TARGETS)
        lines.append(f"| {kind} | {statistics.median(d):.1f} pts (n={len(d)}) | {cells} |")
    lines += ["", "## Average R by 15m alignment, CDX rows, atr1.5 stop / 2R", "", "| 15m vs. signal | Rows | Avg R | Median MFE (ATR) |", "|---|---|---|---|"]
    for a, name in ((1, "agrees"), (0, "neutral"), (-1, "against")):
        g = [r for r in cdx if r["align_15m"] == a]
        if g:
            lines.append(f"| {name} | {len(g)} | {_mean(r['r_atr1.5_t2'] for r in g):+.2f} | {statistics.median(r['mfe_atr'] for r in g):.1f} |")
    lines += [
        "",
        "## Columns",
        "",
        "- Inputs: `side`, `align_15m`, `align_1h` (+1 agrees, 0 neutral, −1 against), `atr3`, `atr_ratio` (ATR vs. its 100-bar average), `session`, `hour_et`, `weekday`, `eff20` / `overlap20` (chop over the last 20 3m bars), `range20_atr`, `pos20`, `room_day_atr`, `ret15_atr` / `ret60_atr` (move into the signal, signed by side), `mins_since_prev`, `prev_same_side`, `cdx_sl_pts`, `cdx_tp1_r`, `cdx_tp2_r`.",
        "- Answers: `r_<stop>_t<target>` is the R result after 1 point of cost, `exit_<stop>_t<target>` is TARGET, STOP or TIME. `mfe_*` / `mae_*` are the best and worst moves within 4 hours.",
        "- Stops: fixed14 (14.25 pts), struct5 / struct10 (beyond the last 5 / 10 closed 3m bars), atr1 / atr1.5 / atr2 (× 3m ATR14), cdx (vision-confirmed CDX SL; mostly empty until vision reads improve).",
        "",
        "## Limits",
        "",
        "- Bars end Oct 2 2026; later signals are dropped until the NinjaTrader bar feed is fixed.",
        "- Stop is assumed hit before target when both fall inside one 1-minute bar.",
        "- Rows overlap in time (signals minutes apart share a price path). Training must split by time and leave a gap between train and test.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    bars = load_bars()
    signals = load_signals()
    rows, dropped = build(bars, signals, load_cdx_levels())
    write(rows, dropped, len(signals))
    print((OUT / "DATA_CARD.md").read_text())


if __name__ == "__main__":
    main()
