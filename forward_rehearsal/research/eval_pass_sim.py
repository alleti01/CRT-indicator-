"""How long a $50k eval takes under each stop/filter/sizing, starting on every session. Research only.

Eval: $3,000 target, $2,000 trailing drawdown. Bot day rules: stop after 1 winner,
2 losers, or -$400. $1,000 cap per winning trade. One position at a time, 2R target.
MNQ at $2 per point.

    python -m forward_rehearsal.research.eval_pass_sim
"""
from __future__ import annotations

import bisect
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from forward_rehearsal.research import htf_stop_replay as R
from phase74.quality.htf_bias import HtfBiasConfig, evaluate_htf_bias, resample

ET = ZoneInfo("America/New_York")
TARGET_USD = 3000.0
DRAWDOWN_USD = 2000.0
MNQ_PER_POINT = 2.0


def prepare(start: datetime) -> list[dict]:
    R.START = start
    bars = R.load_bars()
    times = [b.timestamp for b in bars]
    rows = []
    for s in R.load_signals(bars[-1].timestamp):
        i = bisect.bisect_left(times, s["t"].replace(second=0, microsecond=0))
        hist = bars[max(0, i - 2000) : i]
        path = [b for b in bars[i : i + 300] if b.timestamp < s["t"] + R.MAX_HOLD]
        if len(hist) < 600 or len(path) < 30 or s["t"] - hist[-1].timestamp > timedelta(minutes=10):
            continue
        s["biases"] = evaluate_htf_bias(hist, s["side"], HtfBiasConfig(enabled=True)).biases
        s["dists"] = R.stop_distances(s, resample(hist, 3))
        s["path"] = path
        s["day"] = (s["t"].astimezone(ET) - timedelta(hours=18)).date()  # futures day starts 6 pm ET
        rows.append(s)
    return rows


def run(rows, stop, filt, risk_usd, start_day, max_stop=1e9):
    bal = peak = 0.0
    busy = None
    days: dict = {}
    trades = 0
    for s in rows:
        if s["day"] < start_day or stop not in s["dists"] or (busy and s["t"] < busy):
            continue
        if not R.passes(filt, s["side"], s["biases"]):
            continue
        dist = s["dists"][stop]
        if dist > max_stop:
            continue
        st = days.setdefault(s["day"], {"pnl": 0.0, "w": 0, "l": 0})
        if st["w"] >= 1 or st["l"] >= 2 or st["pnl"] <= -400:
            continue
        qty = 10 if risk_usd == "10MNQ" else max(1, math.floor(risk_usd / (dist * MNQ_PER_POINT)))
        res = R.simulate(s["side"], s["price"], dist, 2.0, s["path"])
        busy = res["exit_t"]
        usd = min(res["pts"] * MNQ_PER_POINT * qty, 1000.0)
        bal += usd
        peak = max(peak, bal)
        st["pnl"] += usd
        st["w" if usd > 0 else "l"] += 1
        trades += 1
        if bal <= peak - DRAWDOWN_USD:
            return "BLOWN", s["day"], trades
        if bal >= TARGET_USD:
            return "PASSED", s["day"], trades
    return "OPEN", None, trades


def main() -> None:
    rows = prepare(datetime(2026, 9, 8, 4, 0, tzinfo=R.UTC))
    sessions = sorted({s["day"] for s in rows})
    cdx_start = R.START.__class__(2026, 9, 22).date()
    print(f"{len(rows)} signals, {len(sessions)} sessions {sessions[0]} to {sessions[-1]}")
    print(f"{'stop':12} {'filter':11} {'risk':6} {'from':4} starts pass<=5 passed blown median_sessions")
    for stop in ("fixed_14.25", "atr1.5", "struct10", "struct5"):
        for filt in ("none", "15m_agrees"):
            for risk in (400, 600):
                for label, first in (("CDX", cdx_start), ("ALL", sessions[0])):
                    out = []
                    for d0 in sessions:
                        if d0 < first:
                            continue
                        left = [d for d in sessions if d >= d0]
                        res, day, _ = run(rows, stop, filt, risk, d0)
                        n = len([d for d in left if d <= day]) if day else None
                        if res == "OPEN" and len(left) < 5:
                            continue  # ran out of data, not a result
                        out.append((res, n))
                    passed = sorted(n for r, n in out if r == "PASSED")
                    print(
                        f"{stop:12} {filt:11} ${risk:<5} {label:4} {len(out):6} "
                        f"{sum(1 for r, n in out if r == 'PASSED' and n <= 5):7} {len(passed):6} "
                        f"{sum(1 for r, _ in out if r == 'BLOWN'):5} {passed[len(passed) // 2] if passed else '-'}"
                    )


if __name__ == "__main__":
    main()
