"""CDX signals Sep 22 - Oct 2: stop type x target x higher-timeframe filter. Research only.

Bars are the 1-minute closes in phase74/logs/decisions.jsonl (bars.csv with real
highs and lows is only on the Windows machine). Each 1-minute bar is rebuilt as
open = previous close, high/low = max/min of open and close, so wicks are missing.

Rules that hold for every variant:
- entry at the webhook signal price, path starts on the signal minute
- one position at a time; signals during an open trade are ignored
- stop checked before target inside a bar
- 1.0 point round-trip cost charged on every trade
- a trade still open after 4 hours closes at that minute's close
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cdx_ml.dataset import is_alert_id
from phase73.market_data.bar import Bar
from phase74.quality.htf_bias import BEARISH, BULLISH, HtfBiasConfig, evaluate_htf_bias, resample

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "phase74" / "logs"
OUT = ROOT / "forward_rehearsal" / "reports" / "htf_stop_replay"
UTC = timezone.utc

START = datetime(2026, 9, 22, 4, 0, tzinfo=UTC)  # Sep 22 00:00 ET, first CDX-only day
COST = 1.0
MAX_HOLD = timedelta(hours=4)
MIN_STOP = 4.0
ATR_BUF = 0.05
STOPS = ("fixed_14.25", "struct5", "struct10", "atr1.5")
TARGETS = (1.0, 2.0, 3.0)
FILTERS = ("none", "skip_all_against", "15m_agrees", "15m_agrees_1h_not_against")


def parse(ts: str) -> datetime:
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def load_bars() -> list[Bar]:
    """Real OHLC from bars.csv where it exists, else closes rebuilt from decisions.jsonl."""
    real: dict[datetime, Bar] = {}
    path = LOGS / "bars.csv"
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                t = parse(r["timestamp_utc"])
                real[t] = Bar(t, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"] or 0))
    rebuilt = {b.timestamp: b for b in _close_bars()}
    merged = {**rebuilt, **real}
    out = []
    prev = None
    for t in sorted(merged):
        b = merged[t]
        if b.low < 25000 or (prev is not None and abs(b.close - prev) / prev > 0.02):
            continue
        out.append(b)
        prev = b.close
    return out


def _close_bars() -> list[Bar]:
    closes: dict[datetime, float] = {}
    with (LOGS / "decisions.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("reason_code") != "bar" or not r.get("current_price"):
                continue
            closes[parse(r["market_timestamp"])] = float(r["current_price"])
    bars: list[Bar] = []
    prev = None
    for t in sorted(closes):
        c = closes[t]
        if c < 25000 or (prev is not None and abs(c - prev) / prev > 0.02):
            continue  # placeholder prices and bad ticks
        o = prev if prev is not None else c
        bars.append(Bar(t, o, max(o, c), min(o, c), c))
        prev = c
    return bars


def load_signals(last_bar: datetime) -> list[dict]:
    seen: dict[str, dict] = {}
    with (LOGS / "signals.jsonl").open(encoding="utf-8") as fh:
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
        if START <= t <= last_bar - MAX_HOLD:
            out.append({"id": r["signal_id"], "t": t, "side": "LONG" if r["event"] == "SIGNAL_LONG" else "SHORT", "price": float(r["signal_price"])})
    out.sort(key=lambda s: s["t"])
    dedup: list[dict] = []
    for s in out:
        if dedup and dedup[-1]["side"] == s["side"] and (s["t"] - dedup[-1]["t"]) <= timedelta(seconds=60):
            continue
        dedup.append(s)
    return dedup


def atr14(threes: list[Bar]) -> float | None:
    if len(threes) < 15:
        return None
    trs = [max(b.high - b.low, abs(b.high - p.close), abs(b.low - p.close)) for p, b in zip(threes[-15:-1], threes[-14:])]
    return sum(trs) / 14.0


def stop_distances(sig: dict, threes: list[Bar]) -> dict[str, float]:
    atr = atr14(threes)
    entry = sig["price"]
    out = {"fixed_14.25": 14.25}
    for n in (5, 10):
        w = threes[-n:]
        if atr is None or len(w) < n:
            continue
        lvl = min(b.low for b in w) - ATR_BUF * atr if sig["side"] == "LONG" else max(b.high for b in w) + ATR_BUF * atr
        d = entry - lvl if sig["side"] == "LONG" else lvl - entry
        out[f"struct{n}"] = max(d, MIN_STOP)
    if atr is not None:
        out["atr1.5"] = max(1.5 * atr, MIN_STOP)
    return out


def simulate(side: str, entry: float, dist: float, target_r: float, path: list[Bar]) -> dict:
    sgn = 1 if side == "LONG" else -1
    stop = entry - sgn * dist
    target = entry + sgn * dist * target_r
    mfe = 0.0
    for b in path:
        adverse = b.low if side == "LONG" else b.high
        favor = b.high if side == "LONG" else b.low
        if (adverse - stop) * sgn <= 0:
            pts, why, t = -dist, "STOP", b.timestamp
            break
        mfe = max(mfe, (favor - entry) * sgn)
        if (favor - target) * sgn >= 0:
            pts, why, t = dist * target_r, "TARGET", b.timestamp
            break
    else:
        pts, why, t = (path[-1].close - entry) * sgn, "TIME", path[-1].timestamp
    return {"pts": pts - COST, "R": (pts - COST) / dist, "why": why, "exit_t": t, "mfe": mfe}


def premature(side: str, entry: float, dist: float, path: list[Bar]) -> bool:
    """Stopped out, then price still reached +2R inside the 4-hour window."""
    sgn = 1 if side == "LONG" else -1
    stopped = False
    for b in path:
        if not stopped and ((b.low if side == "LONG" else b.high) - (entry - sgn * dist)) * sgn <= 0:
            stopped = True
            continue
        if stopped and ((b.high if side == "LONG" else b.low) - (entry + sgn * 2 * dist)) * sgn >= 0:
            return True
    return False


def passes(filt: str, side: str, biases: dict[str, str]) -> bool:
    want = BULLISH if side == "LONG" else BEARISH
    against = BEARISH if side == "LONG" else BULLISH
    if filt == "none":
        return True
    if filt == "skip_all_against":
        return not all(v == against for v in biases.values())
    if filt == "15m_agrees":
        return biases["15m"] == want
    return biases["15m"] == want and biases["1H"] != against


def align(side: str, b15: str) -> str:
    want = BULLISH if side == "LONG" else BEARISH
    return "agrees" if b15 == want else "neutral" if b15 not in (BULLISH, BEARISH) else "against"


def stats(rs: list[float]) -> dict:
    if not rs:
        return {"n": 0, "win": 0.0, "avgR": 0.0, "totR": 0.0, "pf": 0.0, "maxdd": 0.0}
    eq = peak = dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    gain = sum(r for r in rs if r > 0)
    loss = -sum(r for r in rs if r < 0)
    return {
        "n": len(rs),
        "win": sum(r > 0 for r in rs) / len(rs),
        "avgR": statistics.mean(rs),
        "totR": sum(rs),
        "pf": gain / loss if loss else float("inf"),
        "maxdd": dd,
    }


def main() -> None:
    bars = load_bars()
    sigs = load_signals(bars[-1].timestamp)
    cfg = HtfBiasConfig(enabled=True)
    times = [b.timestamp for b in bars]

    import bisect

    rows = []
    for s in sigs:
        # Bars are stamped at their close: the bar stamped at the signal minute is known; the path starts after it.
        i = bisect.bisect_right(times, s["t"].replace(second=0, microsecond=0))
        hist = bars[max(0, i - 2000) : i]
        path = [b for b in bars[i : i + 300] if b.timestamp < s["t"] + MAX_HOLD]
        if len(hist) < 600 or len(path) < 30:
            continue
        threes = resample(hist, 3)
        s["biases"] = evaluate_htf_bias(hist, s["side"], cfg).biases
        s["align"] = align(s["side"], s["biases"]["15m"])
        s["dists"] = stop_distances(s, threes)
        s["path"] = path
        s["mfe4h"] = max(((b.high - s["price"]) if s["side"] == "LONG" else (s["price"] - b.low)) for b in path)
        rows.append(s)

    results: dict[tuple, list[dict]] = defaultdict(list)
    for stop in STOPS:
        for tr in TARGETS:
            for filt in FILTERS:
                busy_until = None
                for s in rows:
                    if stop not in s["dists"] or (busy_until and s["t"] < busy_until):
                        continue
                    if not passes(filt, s["side"], s["biases"]):
                        continue
                    res = simulate(s["side"], s["price"], s["dists"][stop], tr, s["path"])
                    busy_until = res["exit_t"]
                    results[(stop, tr, filt)].append({**res, "sig": s})

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "SIGNALS.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["signal_time_utc", "side", "price", "bias_15m", "bias_1h", "align_15m", "mfe_4h_pts", *[f"dist_{k}" for k in STOPS]])
        for s in rows:
            w.writerow([s["t"].isoformat(), s["side"], s["price"], s["biases"]["15m"], s["biases"]["1H"], s["align"], round(s["mfe4h"], 2), *[round(s["dists"].get(k, 0), 2) for k in STOPS]])
    with (OUT / "SCORECARD.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["stop", "target_R", "filter", "n", "win_rate", "avg_R", "total_R", "profit_factor", "max_dd_R", "first_half_R", "second_half_R"])
        mid = datetime(2026, 9, 27, tzinfo=UTC)
        for (stop, tr, filt), res in sorted(results.items()):
            st = stats([r["R"] for r in res])
            h1 = sum(r["R"] for r in res if r["sig"]["t"] < mid)
            h2 = sum(r["R"] for r in res if r["sig"]["t"] >= mid)
            w.writerow([stop, tr, filt, st["n"], f"{st['win']:.3f}", f"{st['avgR']:.3f}", f"{st['totR']:.2f}", f"{st['pf']:.2f}", f"{st['maxdd']:.2f}", f"{h1:.2f}", f"{h2:.2f}"])

    # Per-signal view, independent of the one-position rule.
    by_align = defaultdict(list)
    prem = defaultdict(lambda: [0, 0])
    for s in rows:
        by_align[s["align"]].append(s)
        for stop in STOPS:
            if stop in s["dists"]:
                r = simulate(s["side"], s["price"], s["dists"][stop], 2.0, s["path"])
                if r["why"] == "STOP":
                    prem[(stop, s["align"])][1] += 1
                    prem[(stop, s["align"])][0] += premature(s["side"], s["price"], s["dists"][stop], s["path"])

    summary = {
        "bars": len(bars),
        "bar_range": [bars[0].timestamp.isoformat(), bars[-1].timestamp.isoformat()],
        "signals": len(rows),
        "align_counts": {k: len(v) for k, v in by_align.items()},
        "median_mfe_4h_by_align": {k: statistics.median(x["mfe4h"] for x in v) for k, v in by_align.items()},
        "median_dist": {k: statistics.median(s["dists"][k] for s in rows if k in s["dists"]) for k in STOPS},
        "premature_stops_2R": {f"{k[0]}|{k[1]}": f"{v[0]}/{v[1]}" for k, v in sorted(prem.items())},
        "per_signal_2R_avgR": {
            f"{stop}|{a}": round(statistics.mean(simulate(x["side"], x["price"], x["dists"][stop], 2.0, x["path"])["R"] for x in v), 3)
            for stop in STOPS
            for a, v in by_align.items()
            if all(stop in x["dists"] for x in v)
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
