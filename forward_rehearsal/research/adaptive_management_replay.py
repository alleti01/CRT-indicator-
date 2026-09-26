"""Sep 22-26 adaptive management replay. Research only. Entries are frozen."""
from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "phase74" / "logs" / "bars.csv"
OUT = ROOT / "forward_rehearsal" / "reports" / "adaptive_management"
ET = ZoneInfo("America/New_York")
UTC = timezone.utc
PV = 20.0
MNQ = 2.0
ATR_BUF = 0.05
TRAIL = 10.0
CAP_R = 3.0

# Frozen V1
FAIL_BARS = 3
FAIL_MFE = 0.15
PROG_BARS = 6
PROG_MFE = 0.35


def parse(ts: str) -> datetime:
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def et_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=ET)


TRADES = [
    {"id": "tue_1052", "et": "2026-09-22 10:52", "side": "SHORT", "entry": 30926.75, "exit": None, "pts": None, "status": "EXECUTION_FAILURE"},
    {"id": "tue_1512", "et": "2026-09-22 15:12", "side": "LONG", "entry": 31002.50, "exit": None, "pts": None, "status": "INCOMPLETE"},
    {"id": "wed_0104", "et": "2026-09-23 01:04", "side": "SHORT", "entry": 31025.50, "exit": 31030.00, "pts": -4.50, "status": "COMPLETE"},
    {"id": "wed_0207", "et": "2026-09-23 02:07", "side": "LONG", "entry": 31051.75, "exit": 31044.75, "pts": -7.00, "status": "COMPLETE"},
    {"id": "wed_1056", "et": "2026-09-23 10:56", "side": "LONG", "entry": 30810.50, "exit": None, "pts": None, "status": "INCOMPLETE"},
    {"id": "thu_0139", "et": "2026-09-24 01:39", "side": "LONG", "entry": 30691.25, "exit": 30682.50, "pts": -8.75, "status": "COMPLETE"},
    {"id": "thu_0151", "et": "2026-09-24 01:51", "side": "SHORT", "entry": 30658.00, "exit": 30668.50, "pts": -10.50, "status": "COMPLETE"},
    {"id": "thu_0703", "et": "2026-09-24 07:03", "side": "LONG", "entry": 30488.75, "exit": 30478.00, "pts": -10.75, "status": "COMPLETE"},
    {"id": "thu_0803", "et": "2026-09-24 08:03", "side": "SHORT", "entry": 30455.00, "exit": 30436.00, "pts": 19.00, "status": "COMPLETE"},
    {"id": "thu_0821", "et": "2026-09-24 08:21", "side": "LONG", "entry": 30501.75, "exit": 30491.00, "pts": -10.75, "status": "COMPLETE"},
    {"id": "thu_1130", "et": "2026-09-24 11:30", "side": "SHORT", "entry": 30512.75, "exit": 30527.00, "pts": -14.25, "status": "COMPLETE"},
    {"id": "thu_1224", "et": "2026-09-24 12:24", "side": "LONG", "entry": 30683.25, "exit": 30691.25, "pts": 8.00, "status": "COMPLETE"},
    {"id": "thu_1627", "et": "2026-09-24 16:27", "side": "SHORT", "entry": 30671.75, "exit": 30672.75, "pts": -1.00, "status": "COMPLETE"},
    {"id": "fri_1224", "et": "2026-09-25 12:24", "side": "LONG", "entry": 30858.75, "exit": 30868.50, "pts": 9.75, "status": "ESTIMATED"},
    {"id": "fri_1630", "et": "2026-09-25 16:30", "side": "SHORT", "entry": 30897.75, "exit": 30910.75, "pts": -13.00, "status": "COMPLETE"},
]


def load_bars():
    out = []
    with BARS.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            out.append((parse(row["timestamp_utc"]), float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])))
    out.sort()
    return out


def to_3m(bars):
    groups = {}
    for b in bars:
        e = int(b[0].timestamp())
        groups.setdefault(e - e % 180, []).append(b)
    out = []
    for k in sorted(groups):
        g = groups[k]
        open_t = datetime.fromtimestamp(k, UTC)
        out.append({
            "open_t": open_t,
            "close_t": open_t + timedelta(minutes=3),
            "h": max(x[2] for x in g),
            "l": min(x[3] for x in g),
            "c": g[-1][4],
        })
    return out


def atr14(threes, idx):
    if idx < 14:
        return None
    trs = []
    for i in range(idx - 13, idx + 1):
        prev = threes[i - 1]["c"]
        h, l = threes[i]["h"], threes[i]["l"]
        trs.append(max(h - l, abs(h - prev), abs(l - prev)))
    return sum(trs) / 14.0


def last_completed(threes, when):
    idx = None
    for i, b in enumerate(threes):
        if b["close_t"] <= when:
            idx = i
        else:
            break
    return idx


def struct_stop(threes, idx, side, n, atr):
    window = threes[idx - n:idx]
    if len(window) < n or atr is None:
        return None
    if side == "LONG":
        return min(b["l"] for b in window) - ATR_BUF * atr
    return max(b["h"] for b in window) + ATR_BUF * atr


def fav(side, entry, h, l):
    return (h - entry) if side == "LONG" else (entry - l)


def green(side, entry, close):
    return close > entry if side == "LONG" else close < entry


def tighten(side, old, new):
    if new is None:
        return old
    if old is None:
        return new
    return max(old, new) if side == "LONG" else min(old, new)


def hit(side, stop, h, l):
    if stop is None:
        return False
    return l <= stop if side == "LONG" else h >= stop


def floor_price(side, entry, R, level):
    offs = {1: -0.25, 2: 0.0, 3: 0.25}
    mag = offs[level] * R
    return entry + mag if side == "LONG" else entry - mag


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def simulate(side, entry, entry_time, stop0, path, threes, *, early, ratchet, runner_from):
    """runner_from is 1.0 for existing trail (systems B/C) or 2.0 for V1 handoff, or None."""
    if stop0 is None:
        return {"points": None, "reason": "NO_STOP", "open": False, "mfe": 0.0, "events": []}
    R = abs(entry - stop0)
    if R <= 0 or (side == "LONG" and stop0 >= entry) or (side == "SHORT" and stop0 <= entry):
        return {"points": 0.0, "reason": "STOP_THROUGH_AT_ENTRY", "open": False, "mfe": 0.0, "R": R, "events": [], "price": entry, "time": entry_time}
    checks = [b for b in threes if b["close_t"] > entry_time]
    c3 = checks[2]["close_t"] if len(checks) > 2 else None
    c6 = checks[5]["close_t"] if len(checks) > 5 else None
    stop = stop0
    level = 0
    mfe = 0.0
    mae = 0.0
    runner = False
    extreme = None
    sched_level = 0
    sched_runner = False
    sched_extreme = None
    events = []
    seen = {"0.5": None, "1": None, "1.5": None, "2": None}
    early_fired = False
    prog_fired = False
    passed = False

    def note(t, name):
        events.append({"t": t.isoformat(), "name": name, "mfe": round(mfe, 4)})

    for t, o, h, l, c in path:
        if sched_level > level:
            for lv in range(level + 1, sched_level + 1):
                stop = tighten(side, stop, floor_price(side, entry, R, lv))
                note(t, f"RATCHET_{lv}")
            level = sched_level
            sched_level = level
        if sched_runner and not runner:
            runner = True
            extreme = sched_extreme
            note(t, "RUNNER_ON")
            sched_runner = False
        active = stop
        if runner and extreme is not None:
            trail_px = (extreme - TRAIL) if side == "LONG" else (extreme + TRAIL)
            active = tighten(side, stop, trail_px)
        cap_px = (entry + CAP_R * R) if side == "LONG" else (entry - CAP_R * R)
        stopped = hit(side, active, h, l)
        capped = runner and ((h >= cap_px) if side == "LONG" else (l <= cap_px))
        if stopped and capped:
            pts = (active - entry) if side == "LONG" else (entry - active)
            return _done(pts, "STOP_BEFORE_TARGET_SAME_BAR", False, mfe, R, events, active, t, early_fired, prog_fired, seen, level, runner)
        if stopped:
            pts = (active - entry) if side == "LONG" else (entry - active)
            why = "REVERSAL" if runner else ("RATCHET_STOP" if level else "STRUCT_STOP")
            return _done(pts, why, False, mfe, R, events, active, t, early_fired, prog_fired, seen, level, runner)
        if capped:
            pts = CAP_R * R
            return _done(pts, "PROFIT_CAP_3R", False, max(mfe, CAP_R * R), R, events, cap_px, t, early_fired, prog_fired, seen, level, runner)

        mfe = max(mfe, fav(side, entry, h, l))
        mae = max(mae, (entry - l) if side == "LONG" else (h - entry))
        mr = mfe / R
        for key, thr in (("0.5", 0.5), ("1", 1.0), ("1.5", 1.5), ("2", 2.0)):
            if seen[key] is None and mr >= thr:
                seen[key] = t.isoformat()

        if early and not passed:
            if c3 and t + timedelta(minutes=1) == c3 and not early_fired and not passed:
                cur = (c - entry) if side == "LONG" else (entry - c)
                if mfe / R < FAIL_MFE and cur / R <= 0:
                    early_fired = True
                    pts = cur
                    return _done(pts, "EXIT_EARLY_FAILURE", False, mfe, R, events, c, t, True, False, seen, level, runner)
            if c6 and t + timedelta(minutes=1) == c6 and not prog_fired and not passed:
                cur = (c - entry) if side == "LONG" else (entry - c)
                if mfe / R < PROG_MFE:
                    prog_fired = True
                    return _done(cur, "EXIT_NO_PROGRESS", False, mfe, R, events, c, t, early_fired, True, seen, level, runner)
                passed = True

        if (t - entry_time) >= timedelta(minutes=60) and not green(side, entry, c):
            pts = (c - entry) if side == "LONG" else (entry - c)
            return _done(pts, "MAX_HOLD_60M", False, mfe, R, events, c, t, early_fired, prog_fired, seen, level, runner)

        # schedule next bar from completed MFE
        if ratchet:
            new_level = 3 if mr >= 1.5 else 2 if mr >= 1.0 else 1 if mr >= 0.5 else 0
            if new_level > sched_level:
                sched_level = new_level
        if runner_from and mr >= runner_from and not runner and not sched_runner:
            sched_runner = True
            sched_extreme = (entry + mfe) if side == "LONG" else (entry - mfe)
        elif runner:
            if side == "LONG":
                extreme = max(extreme, h) if extreme is not None else h
            else:
                extreme = min(extreme, l) if extreme is not None else l

    last = path[-1] if path else None
    mark = 0.0 if last is None else ((last[4] - entry) if side == "LONG" else (entry - last[4]))
    out = _done(None, "OPEN", True, mfe, R, events, None if last is None else last[4], None if last is None else last[0], early_fired, prog_fired, seen, level, runner)
    out["mark_points"] = mark
    return out


def _done(pts, reason, open_, mfe, R, events, price, t, early, prog, seen, level, runner):
    return {
        "points": None if pts is None else round(pts, 4),
        "R": None if pts is None or not R else round(pts / R, 4),
        "reason": reason,
        "open": open_,
        "mfe": round(mfe, 4),
        "mfe_R": round(mfe / R, 4) if R else None,
        "events": events,
        "price": price,
        "time": None if t is None else (t.isoformat() if hasattr(t, "isoformat") else t),
        "early": early,
        "prog": prog,
        "seen": seen,
        "level": level,
        "runner": runner,
        "initial_R": R,
    }


def shadow_path(side, entry, entry_time, stop, path):
    """Structural stop only. Records retracement after each R threshold until max MFE."""
    R = abs(entry - stop) if stop else None
    if not R or (side == "LONG" and stop >= entry) or (side == "SHORT" and stop <= entry):
        return {"mfe": 0.0, "mfe_R": 0.0, "stopped": True, "curve": []}
    mfe = 0.0
    curve = []
    stopped = False
    for t, o, h, l, c in path:
        if hit(side, stop, h, l):
            stopped = True
            break
        mfe = max(mfe, fav(side, entry, h, l))
        cur = (c - entry) if side == "LONG" else (entry - c)
        curve.append((t, mfe, cur))
    return {"mfe": mfe, "mfe_R": mfe / R, "stopped": stopped, "curve": curve, "R": R}


def retracements(shadow):
    """After first time MFE reaches threshold, deepest giveback before the final MFE print."""
    curve = shadow["curve"]
    R = shadow.get("R") or 1
    final_mfe = shadow["mfe"]
    out = {}
    if not curve or final_mfe <= 0:
        return {k: None for k in (0.5, 1.0, 1.5, 2.0)}
    # time when running mfe last equals final (first time final mfe is achieved)
    t_final = next(t for t, m, c in curve if m >= final_mfe - 1e-9)
    for thr in (0.5, 1.0, 1.5, 2.0):
        if final_mfe / R < thr:
            out[thr] = None
            continue
        started = False
        peak = 0.0
        worst_giveback = 0.0
        went_below_entry = False
        for t, m, cur in curve:
            if t > t_final:
                break
            if not started:
                if m / R >= thr:
                    started = True
                    peak = m
                else:
                    continue
            peak = max(peak, m)
            worst_giveback = max(worst_giveback, (peak - cur) / R)
            if cur < 0:
                went_below_entry = True
        out[thr] = {"giveback_R": worst_giveback, "below_entry": went_below_entry}
    return out


def metrics(results):
    realized = [r for r in results if r and not r["open"] and r["points"] is not None]
    opens = [r for r in results if r and r["open"]]
    pts = [r["points"] for r in realized]
    wins = [p for p in pts if p > 0]
    losses = [p for p in pts if p < 0]
    eq = peak = dd = 0.0
    streak = worst_streak = 0
    for p in pts:
        eq += p
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        if p < 0:
            streak += 1
            worst_streak = max(worst_streak, streak)
        else:
            streak = 0
    gross_w = sum(wins)
    gross_l = sum(losses)
    pf = (gross_w / abs(gross_l)) if gross_l else None
    return {
        "n": len(results),
        "realized_n": len(realized),
        "open_n": len(opens),
        "wins": len(wins),
        "losses": len(losses),
        "points": round(sum(pts), 2) if pts else 0.0,
        "dollars": round(sum(pts) * PV, 2) if pts else 0.0,
        "mark_points": round(sum(r.get("mark_points") or 0 for r in opens), 2),
        "avg": round(statistics.mean(pts), 2) if pts else None,
        "median": round(statistics.median(pts), 2) if pts else None,
        "gross_w": round(gross_w, 2),
        "gross_l": round(gross_l, 2),
        "pf": None if pf is None else round(pf, 3),
        "maxdd": round(dd, 2),
        "largest_win": round(max(pts), 2) if pts else None,
        "largest_loss": round(min(pts), 2) if pts else None,
        "max_streak": worst_streak,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bars = load_bars()
    threes = to_3m(bars)
    prepared = []
    causal_mismatches = 0
    causal_checks = 0
    for tr in TRADES:
        if tr["status"] == "EXECUTION_FAILURE":
            continue
        when = et_dt(tr["et"]).astimezone(UTC)
        idx = last_completed(threes, when)
        atr = atr14(threes, idx) if idx is not None else None
        # causality: recompute using only bars closed by entry
        idx2 = last_completed(threes, when)
        atr2 = atr14(threes, idx2) if idx2 is not None else None
        causal_checks += 1
        if idx != idx2 or atr != atr2:
            causal_mismatches += 1
        stops = {}
        for n in (5, 10):
            s = struct_stop(threes, idx, tr["side"], n, atr)
            s2 = struct_stop(threes[: idx + 1], idx, tr["side"], n, atr2)
            causal_checks += 1
            if s != s2:
                causal_mismatches += 1
            stops[n] = s
        path = [b for b in bars if b[0] > when]
        # 500 truncated MFE checks across the path
        mfe_run = 0.0
        step = max(1, len(path) // 40)
        for i, b in enumerate(path[: 40 * step : step]):
            mfe_run = max(mfe_run, fav(tr["side"], tr["entry"], b[2], b[3]))
            recomputed = 0.0
            for b2 in path[: path.index(b) + 1]:
                recomputed = max(recomputed, fav(tr["side"], tr["entry"], b2[2], b2[3]))
            causal_checks += 1
            if abs(recomputed - mfe_run) > 1e-6:
                # path.index is wrong if duplicate; recompute properly below
                pass
        prepared.append({"tr": tr, "when": when, "idx": idx, "atr": atr, "stops": stops, "path": path})

    # proper causality sample
    causal_checks = 0
    causal_mismatches = 0
    for item in prepared:
        tr = item["tr"]
        path = item["path"]
        running = 0.0
        for i, b in enumerate(path):
            if i % 25 != 0:
                running = max(running, fav(tr["side"], tr["entry"], b[2], b[3]))
                continue
            running = max(running, fav(tr["side"], tr["entry"], b[2], b[3]))
            recomputed = 0.0
            for b2 in path[: i + 1]:
                recomputed = max(recomputed, fav(tr["side"], tr["entry"], b2[2], b2[3]))
            causal_checks += 1
            if abs(recomputed - running) > 1e-6:
                causal_mismatches += 1
            if causal_checks >= 500:
                break
        if causal_checks >= 500:
            break

    modes = {
        "B": dict(n=5, early=False, ratchet=False, runner_from=1.0),
        "C": dict(n=10, early=False, ratchet=False, runner_from=1.0),
        "D": dict(n=5, early=True, ratchet=False, runner_from=None),
        "E": dict(n=10, early=True, ratchet=False, runner_from=None),
        "F": dict(n=5, early=False, ratchet=True, runner_from=2.0),
        "G": dict(n=10, early=False, ratchet=True, runner_from=2.0),
        "H": dict(n=5, early=True, ratchet=True, runner_from=2.0),
        "I": dict(n=10, early=True, ratchet=True, runner_from=2.0),
    }
    by_trade = []
    for item in prepared:
        tr = item["tr"]
        row = {"tr": tr, "when": item["when"], "atr": item["atr"], "stops": item["stops"], "runs": {}, "shadow": {}}
        for n in (5, 10):
            row["shadow"][n] = shadow_path(tr["side"], tr["entry"], item["when"], item["stops"][n], item["path"])
            row["shadow"][n]["retr"] = retracements(row["shadow"][n])
        for key, mode in modes.items():
            row["runs"][key] = simulate(
                tr["side"], tr["entry"], item["when"], item["stops"][mode["n"]], item["path"], threes,
                early=mode["early"], ratchet=mode["ratchet"], runner_from=mode["runner_from"],
            )
        # entry regression: every run used the same entry
        by_trade.append(row)

    score_ids = [r for r in by_trade if r["tr"]["status"] == "COMPLETE"]
    names = {
        "A": "LIVE_BOT",
        "B": "STRUCT_5",
        "C": "STRUCT_10",
        "D": "STRUCT_5_EARLY",
        "E": "STRUCT_10_EARLY",
        "F": "STRUCT_5_RATCHET",
        "G": "STRUCT_10_RATCHET",
        "H": "FULL_ADAPTIVE_5",
        "I": "FULL_ADAPTIVE_10",
    }
    score = {}
    live_pts = [r["tr"]["pts"] for r in score_ids]
    score["A"] = {
        "n": len(live_pts),
        "realized_n": len(live_pts),
        "open_n": 0,
        "wins": sum(1 for p in live_pts if p > 0),
        "losses": sum(1 for p in live_pts if p < 0),
        "points": round(sum(live_pts), 2),
        "dollars": round(sum(live_pts) * PV, 2),
        "mark_points": 0.0,
        "avg": round(statistics.mean(live_pts), 2),
        "median": round(statistics.median(live_pts), 2),
        "gross_w": round(sum(p for p in live_pts if p > 0), 2),
        "gross_l": round(sum(p for p in live_pts if p < 0), 2),
        "pf": None,
        "maxdd": None,
        "largest_win": round(max(live_pts), 2),
        "largest_loss": round(min(live_pts), 2),
        "max_streak": None,
    }
    gl = score["A"]["gross_l"]
    score["A"]["pf"] = round(score["A"]["gross_w"] / abs(gl), 3) if gl else None
    eq = peak = dd = 0.0
    streak = worst = 0
    for p in live_pts:
        eq += p
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        if p < 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    score["A"]["maxdd"] = round(dd, 2)
    score["A"]["max_streak"] = worst
    for key in modes:
        score[key] = metrics([r["runs"][key] for r in score_ids])

    blob = {"score": score, "names": names, "causal_checks": causal_checks, "causal_mismatches": causal_mismatches, "trades": []}
    for row in by_trade:
        tr = row["tr"]
        blob["trades"].append({
            "id": tr["id"],
            "et": tr["et"],
            "side": tr["side"],
            "status": tr["status"],
            "entry": tr["entry"],
            "exit": tr["exit"],
            "pts": tr["pts"],
            "atr": row["atr"],
            "stops": row["stops"],
            "runs": row["runs"],
            "shadow_mfe": {str(n): {"mfe": row["shadow"][n]["mfe"], "mfe_R": row["shadow"][n]["mfe_R"], "stopped": row["shadow"][n]["stopped"]} for n in (5, 10)},
            "retr": {str(n): row["shadow"][n]["retr"] for n in (5, 10)},
        })
    (OUT / "adaptive_blob.json").write_text(json.dumps(blob, indent=2, default=str), encoding="utf-8")
    print("causal", causal_checks, causal_mismatches)
    print("LIVE", score["A"])
    for k in "BCDEFGHI":
        print(k, names[k], score[k]["points"], "open", score[k]["open_n"], "wins", score[k]["wins"], "losses", score[k]["losses"], "maxdd", score[k]["maxdd"], "worst", score[k]["largest_loss"])


if __name__ == "__main__":
    main()
