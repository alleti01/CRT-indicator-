"""Exit rules for CDX trades with a 1.5 x ATR(3m) stop. Research only.

Same entries for every rule (market at the signal price), 1 point round-trip cost,
4-hour limit, stop checked before anything else inside a 1-minute bar. Results in R
of the initial stop distance; partial exits are averaged by size.

    python -m forward_rehearsal.research.exit_variants
"""
from __future__ import annotations

import bisect
import statistics
from datetime import timedelta

from cdx_ml import dataset as D
from phase74.quality.htf_bias import resample, structure_bias

STOP_ATR = 1.5


def simulate(side: str, entry: float, dist: float, path, rule: dict) -> float:
    """Return R. rule keys: target (R or None), be_at (R or None), trail_at (R), trail_atr_r (trail distance in R),
    partial_at (R), partial_frac."""
    sgn = 1 if side == "LONG" else -1
    stop = entry - sgn * dist
    best = 0.0
    open_frac, banked = 1.0, 0.0
    for b in path:
        adverse = b.low if sgn > 0 else b.high
        favor = b.high if sgn > 0 else b.low
        if sgn * (adverse - stop) <= 0:
            return banked + open_frac * (sgn * (stop - entry)) / dist - D.COST_PTS / dist
        fav_r = sgn * (favor - entry) / dist
        if rule.get("partial_at") and open_frac == 1.0 and fav_r >= rule["partial_at"]:
            frac = rule["partial_frac"]
            banked += frac * rule["partial_at"]
            open_frac -= frac
        if rule.get("target") is not None and fav_r >= rule["target"]:
            return banked + open_frac * rule["target"] - D.COST_PTS / dist
        best = max(best, fav_r)
        # Stop moves only after the bar that earned it (no same-bar look-ahead).
        if rule.get("be_at") is not None and best >= rule["be_at"]:
            stop = sgn * max(sgn * stop, sgn * entry)
        if rule.get("trail_at") is not None and best >= rule["trail_at"]:
            trail = entry + sgn * (best - rule["trail_r"]) * dist
            stop = sgn * max(sgn * stop, sgn * trail)
    last = path[-1].close
    return banked + open_frac * sgn * (last - entry) / dist - D.COST_PTS / dist


RULES = {
    "2R target (now)": {"target": 2.0},
    "1R target": {"target": 1.0},
    "3R target": {"target": 3.0},
    "breakeven at +1R, 2R target": {"target": 2.0, "be_at": 1.0},
    "half off at +1R, BE, rest 2R": {"target": 2.0, "be_at": 1.0, "partial_at": 1.0, "partial_frac": 0.5},
    "half off at +1R, BE, rest 3R": {"target": 3.0, "be_at": 1.0, "partial_at": 1.0, "partial_frac": 0.5},
    "trail 1R behind after +1R, no target": {"target": None, "trail_at": 1.0, "trail_r": 1.0},
    "trail 1R behind after +1R, 3R cap": {"target": 3.0, "trail_at": 1.0, "trail_r": 1.0},
    "trail 0.5R behind after +1.5R, 3R cap": {"target": 3.0, "trail_at": 1.5, "trail_r": 0.5},
}


def load() -> list[dict]:
    bars = D.load_bars()
    times = [b.timestamp for b in bars]
    out = []
    for s in D.load_signals():
        if s["source"] != "cdx":
            continue
        minute = s["t"].replace(second=0, microsecond=0)
        i = bisect.bisect_right(times, minute)
        hist = bars[max(0, i - 2000): i]
        path = [b for b in bars[i: i + 400] if b.timestamp < s["t"] + D.HORIZON]
        if len(hist) < D.MIN_HISTORY_BARS or s["t"] - hist[-1].timestamp > timedelta(minutes=10) or len(path) < 30:
            continue
        if any(D._data_hole(a.timestamp, b.timestamp) for a, b in zip(path[:60], path[1:60])):
            continue
        atr = D._atr(resample(hist, 3))
        if not atr:
            continue
        s["align_15m"] = D._align(s["side"], structure_bias(resample(hist, 15)))
        s["dist"] = max(STOP_ATR * atr, D.MIN_STOP)
        s["path"] = path
        out.append(s)
    return out


def main() -> None:
    sigs = load()
    print(f"{len(sigs)} real CDX signals; stop 1.5 x ATR(3m); same entries for every rule\n")
    # How much is given back with the 2R target?
    gave_back = 0
    for s in sigs:
        sgn = 1 if s["side"] == "LONG" else -1
        stop = s["price"] - sgn * s["dist"]
        best = 0.0
        for b in s["path"]:
            if sgn * ((b.low if sgn > 0 else b.high) - stop) <= 0:
                break
            fav = sgn * ((b.high if sgn > 0 else b.low) - s["price"]) / s["dist"]
            if fav >= 2.0:
                best = None
                break
            best = max(best, fav)
        if best is not None and best >= 1.0:
            r = simulate(s["side"], s["price"], s["dist"], s["path"], {"target": 2.0})
            if r < 0:
                gave_back += 1
    print(f"Reached +1R, never reached +2R, and ended at a loss: {gave_back} of {len(sigs)}\n")
    print(f"{'rule':40} {'all: avg R':>10} {'total':>7} {'win%':>5} | {'15m agrees: avg R':>17} {'total':>7}")
    for name, rule in RULES.items():
        rs = [simulate(s["side"], s["price"], s["dist"], s["path"], rule) for s in sigs]
        ag = [r for r, s in zip(rs, sigs) if s["align_15m"] == 1]
        print(f"{name:40} {statistics.mean(rs):+10.2f} {sum(rs):+7.1f} {sum(r > 0 for r in rs) / len(rs):5.0%} | "
              f"{statistics.mean(ag):+17.2f} {sum(ag):+7.1f}")
    half = len(sigs) // 2
    print(f"\nFirst half vs second half (by time, {half} / {len(sigs) - half} signals), avg R:")
    for name, rule in RULES.items():
        rs = [simulate(s["side"], s["price"], s["dist"], s["path"], rule) for s in sigs]
        print(f"  {name:40} {statistics.mean(rs[:half]):+.2f} / {statistics.mean(rs[half:]):+.2f}")


if __name__ == "__main__":
    main()
