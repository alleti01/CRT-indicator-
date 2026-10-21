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
        # Bars are stamped at their close: the bar stamped at the signal minute is known; the path starts after it.
        i = bisect.bisect_right(times, s["t"].replace(second=0, microsecond=0))
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


def run(rows, stop, filt, risk_usd, start_day, max_stop=1e9, day_loss=400.0, max_losers=2, max_qty=10):
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
        if st["w"] >= 1 or st["l"] >= max_losers or st["pnl"] <= -day_loss:
            continue
        qty = 10 if risk_usd == "10MNQ" else max(1, min(max_qty, math.floor(risk_usd / (dist * MNQ_PER_POINT))))
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


def rolling(rows, sessions, first, **kw):
    out = []
    for d0 in sessions:
        if d0 < first:
            continue
        left = [d for d in sessions if d >= d0]
        res, day, _ = run(rows, start_day=d0, **kw)
        n = len([d for d in left if d <= day]) if day else None
        if res == "OPEN" and len(left) < 5:
            continue  # ran out of data, not a result
        out.append((res, n))
    return out


def compare_day_rules() -> None:
    """Option A: smaller risk under the $400 day limit. Option B: $600 risk with a bigger day limit."""
    rows = prepare(datetime(2026, 9, 8, 4, 0, tzinfo=R.UTC))
    sessions = sorted({s["day"] for s in rows})
    cdx_start = datetime(2026, 9, 22).date()
    setups = [
        ("current: $600 risk, $400 day limit", 600, 400),
        ("A: $300 risk, $400 day limit", 300, 400),
        ("A: $350 risk, $400 day limit", 350, 400),
        ("A: $400 risk, $400 day limit", 400, 400),
        ("B: $600 risk, $1,000 day limit", 600, 1000),
        ("B: $600 risk, $1,200 day limit", 600, 1200),
    ]
    print(f"{len(rows)} signals, {len(sessions)} sessions {sessions[0]} to {sessions[-1]}; stop 1.5xATR, 2R, max 10 MNQ, 2 losers or the dollar limit ends the day")
    for filt in ("15m_agrees", "none"):
        for label, first in (("CDX", cdx_start), ("ALL", sessions[0])):
            print(f"\n== filter={filt}  signals={label}")
            print(f"{'setup':36} starts  pass<=5  passed  blown  median_sessions")
            for name, risk, dl in setups:
                out = rolling(rows, sessions, first, stop="atr1.5", filt=filt, risk_usd=risk, day_loss=dl)
                passed = sorted(n for r, n in out if r == "PASSED")
                print(f"{name:36} {len(out):6} {sum(1 for r, n in out if r == 'PASSED' and n <= 5):8} {len(passed):7} "
                      f"{sum(1 for r, _ in out if r == 'BLOWN'):6}  {passed[len(passed) // 2] if passed else '-'}")


def day_results(rows, filt, stop="atr1.5", max_losers=2):
    """R of each trade the bot would take, grouped by futures day, under one-position and the
    1-winner / N-loser day rule (the $ day limit is applied later, per risk size)."""
    days: dict = {}
    busy = None
    for s in rows:
        if stop not in s["dists"] or (busy and s["t"] < busy) or not R.passes(filt, s["side"], s["biases"]):
            continue
        res = R.simulate(s["side"], s["price"], s["dists"][stop], 2.0, s["path"])
        days.setdefault(s["day"], []).append(res["pts"] / s["dists"][stop])
        busy = res["exit_t"]
    return [days.get(d, []) for d in sorted({s["day"] for s in rows})]


def bootstrap(day_rs, risk_usd, day_loss=400.0, max_losers=2, n=20000, max_days=60, seed=7):
    """Resample real trading days into many possible evals. Returns pass/blow rates and days to pass."""
    import random

    rng = random.Random(seed)
    passed, blown, days_to_pass = 0, 0, []
    for _ in range(n):
        bal = peak = 0.0
        for day in range(1, max_days + 1):
            pnl, w, l = 0.0, 0, 0
            for r in rng.choice(day_rs):
                if w >= 1 or l >= max_losers or pnl <= -day_loss:
                    break
                usd = min(r * risk_usd, 1000.0)
                pnl += usd
                bal += usd
                peak = max(peak, bal)
                w, l = (w + 1, l) if usd > 0 else (w, l + 1)
                if bal <= peak - DRAWDOWN_USD:
                    break
            if bal <= peak - DRAWDOWN_USD:
                blown += 1
                break
            if bal >= TARGET_USD:
                passed += 1
                days_to_pass.append(day)
                break
    days_to_pass.sort()
    return {
        "pass": passed / n,
        "blow": blown / n,
        "pass_5": sum(d <= 5 for d in days_to_pass) / n,
        "pass_10": sum(d <= 10 for d in days_to_pass) / n,
        "median_days": days_to_pass[len(days_to_pass) // 2] if days_to_pass else None,
    }


def compare_risk_bootstrap() -> None:
    rows = prepare(datetime(2026, 9, 22, 4, 0, tzinfo=R.UTC))  # real CDX signals only
    for filt in ("15m_agrees", "none"):
        day_rs = day_results(rows, filt)
        trades = [r for d in day_rs for r in d]
        print(f"\n== filter={filt}: {len(day_rs)} real sessions, {len(trades)} trades, "
              f"avg {sum(trades) / len(trades):+.2f}R; 20,000 resampled evals, 60-session limit")
        print(f"{'risk/trade':10} {'losses to blow':>14} {'pass':>6} {'blown':>6} {'pass<=5d':>9} {'pass<=10d':>10} {'median days':>11}")
        for risk in (200, 300, 400, 500, 600):
            b = bootstrap(day_rs, risk)
            print(f"${risk:<9} {2000 // risk:14} {b['pass']:6.0%} {b['blow']:6.0%} {b['pass_5']:9.0%} {b['pass_10']:10.0%} {str(b['median_days']):>11}")


def main() -> None:
    import sys

    if "--bootstrap" in sys.argv:
        compare_risk_bootstrap()
        return
    if "--day-rules" in sys.argv:
        compare_day_rules()
        return
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
