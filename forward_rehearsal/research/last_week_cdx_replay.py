"""Diagnostic replay of Sep 22-26 2026 live CDX trades. Research only."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "phase74" / "logs" / "bars.csv"
SIGS = ROOT / "phase74" / "logs" / "signals.csv"
OUT = ROOT / "forward_rehearsal" / "reports" / "last_week_cdx"
ET = ZoneInfo("America/New_York")
UTC = timezone.utc
PV = 20.0
HORIZON_MIN = 480

# Frozen V1. Not tuned.
EFF_MAX = 0.25
OVERLAP_MIN = 0.60
EDGE = 0.25
ATR_BUF = 0.05
ARM_BARS = 3
FAIL_BARS = 3
FAIL_MFE = 0.15
PROG_BARS = 6
PROG_MFE = 0.35


def parse(ts: str) -> datetime:
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t


def et_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=ET)


trades = [
    {"id": "tue_1052", "et": "2026-09-22 10:52", "side": "SHORT", "entry": 30926.75, "exit": None, "status": "EXECUTION_FAILURE", "pnl": None, "stop_pts": None},
    {"id": "tue_1512", "et": "2026-09-22 15:12", "side": "LONG", "entry": 31002.50, "exit": None, "status": "INCOMPLETE", "pnl": None, "stop_pts": None},
    {"id": "wed_0104", "et": "2026-09-23 01:04", "side": "SHORT", "entry": 31025.50, "exit": 31030.00, "status": "COMPLETE", "pnl": -90.0, "stop_pts": 4.50},
    {"id": "wed_0207", "et": "2026-09-23 02:07", "side": "LONG", "entry": 31051.75, "exit": 31044.75, "status": "COMPLETE", "pnl": -140.0, "stop_pts": 7.00},
    {"id": "wed_1056", "et": "2026-09-23 10:56", "side": "LONG", "entry": 30810.50, "exit": None, "status": "INCOMPLETE", "pnl": None, "stop_pts": None},
    {"id": "thu_0139", "et": "2026-09-24 01:39", "side": "LONG", "entry": 30691.25, "exit": 30682.50, "status": "COMPLETE", "pnl": -175.0, "stop_pts": 8.75},
    {"id": "thu_0151", "et": "2026-09-24 01:51", "side": "SHORT", "entry": 30658.00, "exit": 30668.50, "status": "COMPLETE", "pnl": -210.0, "stop_pts": 10.50},
    {"id": "thu_0703", "et": "2026-09-24 07:03", "side": "LONG", "entry": 30488.75, "exit": 30478.00, "status": "COMPLETE", "pnl": -215.0, "stop_pts": 10.75},
    {"id": "thu_0803", "et": "2026-09-24 08:03", "side": "SHORT", "entry": 30455.00, "exit": 30436.00, "status": "COMPLETE", "pnl": 380.0, "stop_pts": None},
    {"id": "thu_0821", "et": "2026-09-24 08:21", "side": "LONG", "entry": 30501.75, "exit": 30491.00, "status": "COMPLETE", "pnl": -215.0, "stop_pts": 10.75},
    {"id": "thu_1130", "et": "2026-09-24 11:30", "side": "SHORT", "entry": 30512.75, "exit": 30527.00, "status": "COMPLETE", "pnl": -285.0, "stop_pts": 14.25},
    {"id": "thu_1224", "et": "2026-09-24 12:24", "side": "LONG", "entry": 30683.25, "exit": 30691.25, "status": "COMPLETE", "pnl": 160.0, "stop_pts": None},
    {"id": "thu_1627", "et": "2026-09-24 16:27", "side": "SHORT", "entry": 30671.75, "exit": 30672.75, "status": "COMPLETE", "pnl": -20.0, "stop_pts": None},
    {"id": "fri_1224", "et": "2026-09-25 12:24", "side": "LONG", "entry": 30858.75, "exit": 30868.50, "status": "ESTIMATED", "pnl": 195.0, "stop_pts": 80.25},
    {"id": "fri_1630", "et": "2026-09-25 16:30", "side": "SHORT", "entry": 30897.75, "exit": 30910.75, "status": "COMPLETE", "pnl": -260.0, "stop_pts": 13.00},
]


def load_bars():
    out = []
    with BARS.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            t = parse(row["timestamp_utc"])
            out.append((t, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])))
    out.sort()
    return out


def load_signals():
    seen = {}
    with SIGS.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            sid = row["signal_id"]
            if sid in seen:
                continue
            seen[sid] = {
                "id": sid,
                "event": row["event"],
                "time": parse(row["signal_time_utc"]),
                "bar": parse(row["signal_bar_time_utc"]),
                "price": float(row["signal_price"]),
                "tf": row["timeframe"],
            }
    return list(seen.values())


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
            "o": g[0][1],
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
        prev_c = threes[i - 1]["c"] if i else threes[i]["o"]
        h, l = threes[i]["h"], threes[i]["l"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return sum(trs) / 14.0


def signal_bar_index(threes, when):
    idx = None
    for i, b in enumerate(threes):
        if b["close_t"] <= when:
            idx = i
        else:
            break
    return idx


def features(threes, sig_idx):
    window = threes[sig_idx - 20:sig_idx]
    if len(window) < 20:
        return None
    rh = max(b["h"] for b in window)
    rl = min(b["l"] for b in window)
    closes = [b["c"] for b in window]
    net = abs(closes[-1] - closes[0])
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    eff = net / path if path else 0.0
    overlaps = []
    for a, b in zip(window, window[1:]):
        ov = min(a["h"], b["h"]) - max(a["l"], b["l"])
        span = min(a["h"] - a["l"], b["h"] - b["l"])
        overlaps.append(max(ov, 0.0) / span if span > 0 else 0.0)
    overlap = sum(overlaps) / len(overlaps)
    sig = threes[sig_idx]
    pos = (sig["c"] - rl) / (rh - rl) if rh > rl else 0.5
    return {
        "range_high": rh,
        "range_low": rl,
        "efficiency": eff,
        "overlap": overlap,
        "range_position": pos,
        "sideways": eff <= EFF_MAX and overlap >= OVERLAP_MIN,
        "signal_close": sig["c"],
        "signal_high": sig["h"],
        "signal_low": sig["l"],
    }


def struct_stop(threes, sig_idx, side, n, atr):
    window = threes[sig_idx - n:sig_idx]
    if len(window) < n or atr is None:
        return None
    if side == "LONG":
        return min(b["l"] for b in window) - ATR_BUF * atr
    return max(b["h"] for b in window) + ATR_BUF * atr


def bars_after(bars, when, minutes):
    end = when + timedelta(minutes=minutes)
    return [b for b in bars if when < b[0] <= end]


def fav(side, entry, high, low):
    return (high - entry) if side == "LONG" else (entry - low)


def adv(side, entry, high, low):
    return (entry - low) if side == "LONG" else (high - entry)


def hit_stop(side, stop, high, low):
    if stop is None:
        return False
    return low <= stop if side == "LONG" else high >= stop


def walk_stop(side, entry, stop, path):
    """Return exit price, reason, mfe, mae. Stop bar favorable extreme is ignored."""
    mfe = 0.0
    mae = 0.0
    if stop is None or (side == "LONG" and stop >= entry) or (side == "SHORT" and stop <= entry):
        return entry, "STOP_ALREADY_THROUGH", 0.0, 0.0
    for t, o, h, l, c in path:
        if hit_stop(side, stop, h, l):
            mae = max(mae, abs(entry - stop))
            return stop, "STRUCT_STOP", mfe, mae
        mfe = max(mfe, fav(side, entry, h, l))
        mae = max(mae, adv(side, entry, h, l))
    if not path:
        return entry, "NO_BARS", 0.0, 0.0
    last = path[-1][4]
    return last, "HORIZON_8H", mfe, mae


def completed_3m_after(threes, when, n):
    out = []
    for b in threes:
        if b["close_t"] > when:
            out.append(b)
        if len(out) >= n:
            break
    return out


def mfe_until(side, entry, bars, until):
    mfe = 0.0
    mae = 0.0
    for t, o, h, l, c in bars:
        if t > until:
            break
        mfe = max(mfe, fav(side, entry, h, l))
        mae = max(mae, adv(side, entry, h, l))
    return mfe, mae


def r_of(points, risk):
    if risk is None or risk <= 0:
        return None
    return points / risk


def shadow_after_exit(side, entry, exit_t, exit_px, bot_risk, bars):
    path = [b for b in bars if b[0] > exit_t and b[0] <= exit_t + timedelta(hours=6)]
    mfe = 0.0
    mae = 0.0
    recover = None
    hits = {k: None for k in (0.25, 0.5, 1.0, 2.0)}
    for t, o, h, l, c in path:
        mfe = max(mfe, fav(side, entry, h, l))
        mae = max(mae, adv(side, entry, h, l))
        # recovery of original entry after the stop
        if recover is None:
            if side == "LONG" and h >= entry:
                recover = t
            if side == "SHORT" and l <= entry:
                recover = t
        if bot_risk and bot_risk > 0:
            for k in hits:
                if hits[k] is None and mfe >= k * bot_risk:
                    hits[k] = t
    return {
        "post_mfe": mfe,
        "post_mae": mae,
        "recover_min": None if recover is None else (recover - exit_t).total_seconds() / 60.0,
        "t_025": None if hits[0.25] is None else (hits[0.25] - exit_t).total_seconds() / 60.0,
        "t_050": None if hits[0.5] is None else (hits[0.5] - exit_t).total_seconds() / 60.0,
        "t_1": None if hits[1.0] is None else (hits[1.0] - exit_t).total_seconds() / 60.0,
        "t_2": None if hits[2.0] is None else (hits[2.0] - exit_t).total_seconds() / 60.0,
    }


def classify(struct10_hit_before_plus1_bot, post_mfe, bot_risk, struct_hit):
    meaningful = bot_risk and post_mfe >= bot_risk
    if struct_hit and not meaningful:
        return "TRUE_FAILURE"
    if (not struct_hit) and meaningful:
        return "PREMATURE_BOT_STOP"
    if meaningful and struct_hit:
        return "AMBIGUOUS"
    if not meaningful and not struct_hit:
        return "AMBIGUOUS"
    return "AMBIGUOUS"


def simulate_management(side, entry, stop, risk, origin_sideways, escaped, boundary, path_1m, threes, entry_time):
    """Structural stop plus optional sideways progress. Returns points, reason."""
    if stop is None or risk is None or risk <= 0:
        return 0.0, "NO_STOP", 0.0
    if (side == "LONG" and stop >= entry) or (side == "SHORT" and stop <= entry):
        return -risk, "STOP_ALREADY_THROUGH", 0.0
    mfe = 0.0
    mae = 0.0
    checks = completed_3m_after(threes, entry_time, 6)
    check_times = {3: checks[2]["close_t"] if len(checks) > 2 else None, 6: checks[5]["close_t"] if len(checks) > 5 else None}
    escape_closes = []
    end = entry_time + timedelta(minutes=HORIZON_MIN)
    progress_done = not origin_sideways
    for t, o, h, l, c in path_1m:
        if t > end:
            break
        if hit_stop(side, stop, h, l):
            mae = max(mae, risk)
            return -risk, "STRUCT_STOP", mfe
        mfe = max(mfe, fav(side, entry, h, l))
        mae = max(mae, adv(side, entry, h, l))
        # progress at completed 3m checkpoints, using this bar only when it is the checkpoint close minute
        if origin_sideways and not progress_done:
            for nbar, rule in ((3, "early"), (6, "prog")):
                ct = check_times[nbar]
                if ct is not None and t >= ct and (nbar == 3 or True):
                    # evaluate once when first 1m bar at or after checkpoint is seen; use 3m close
                    bar3 = checks[nbar - 1]
                    if t >= bar3["close_t"] and t < bar3["close_t"] + timedelta(minutes=1):
                        cur = (bar3["c"] - entry) if side == "LONG" else (entry - bar3["c"])
                        cur_r = cur / risk
                        mfe_r = mfe / risk
                        if nbar == 3 and mfe_r < FAIL_MFE and cur_r <= 0:
                            return cur, "EXIT_SIDEWAYS_EARLY_FAILURE", mfe
                        if nbar == 6 and mfe_r < PROG_MFE:
                            return cur, "EXIT_SIDEWAYS_NO_PROGRESS", mfe
                        if nbar == 6:
                            progress_done = True
        if escaped and boundary is not None:
            # consecutive 3m closes tracked when a 3m bar completes on this minute
            pass
    # escape failure scanned on 3m closes inside horizon
    if escaped and boundary is not None:
        atr = None
        seq = completed_3m_after(threes, entry_time, 40)
        below = 0
        for b in seq:
            if b["close_t"] > end:
                break
            if side == "LONG":
                if b["c"] < boundary:
                    below += 1
                else:
                    below = 0
                if below >= 2 or b["c"] <= boundary - ATR_BUF * (risk / 10.0 if risk else 1):
                    # use frozen atr passed via boundary logic below; replaced by caller atr
                    pass
            else:
                if b["c"] > boundary:
                    below += 1
                else:
                    below = 0
    last = path_1m[-1][4] if path_1m else entry
    pts = (last - entry) if side == "LONG" else (entry - last)
    return pts, "HORIZON_8H", mfe


def escape_exit(side, entry, boundary, atr, threes, entry_time, end):
    if boundary is None or atr is None:
        return None
    seq = [b for b in threes if entry_time < b["close_t"] <= end]
    streak = 0
    for b in seq:
        if side == "LONG":
            back = b["c"] < boundary
            hard = b["c"] <= boundary - ATR_BUF * atr
        else:
            back = b["c"] > boundary
            hard = b["c"] >= boundary + ATR_BUF * atr
        streak = streak + 1 if back else 0
        if streak >= 2 or hard:
            pts = (b["c"] - entry) if side == "LONG" else (entry - b["c"])
            return pts, "EXIT_SIDEWAYS_ESCAPE_FAILURE", b["close_t"]
    return None


def confirm_entry(side, feat, atr, threes, sig_idx):
    """Return (entry_time, entry_price, how) or None if cancelled."""
    if feat is None or atr is None:
        return None
    rh, rl = feat["range_high"], feat["range_low"]
    future = threes[sig_idx + 1:sig_idx + 1 + ARM_BARS]
    if len(future) < 1:
        return None
    for b in future[:ARM_BARS]:
        if side == "LONG":
            a = b["c"] >= rh + ATR_BUF * atr
            bconf = feat["range_position"] <= EDGE and b["c"] > feat["signal_high"]
        else:
            a = b["c"] <= rl - ATR_BUF * atr
            bconf = feat["range_position"] >= (1 - EDGE) and b["c"] < feat["signal_low"]
        if a or bconf:
            return b["close_t"], b["c"], "ESCAPE" if a else "EDGE_RECLAIM", b
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bars = load_bars()
    signals = load_signals()
    threes = to_3m(bars)
    rows = []
    for tr in trades:
        when = et_dt(tr["et"]).astimezone(UTC)
        side = tr["side"]
        same = [s for s in signals if ("LONG" if "LONG" in s["event"] else "SHORT") == side]
        same.sort(key=lambda s: abs((s["time"] - when).total_seconds()))
        sig = same[0] if same and abs((same[0]["time"] - when).total_seconds()) <= 180 else None
        sig_time = sig["time"] if sig else when
        sig_idx = signal_bar_index(threes, sig_time)
        atr = atr14(threes, sig_idx) if sig_idx is not None else None
        feat = features(threes, sig_idx) if sig_idx is not None and sig_idx >= 20 else None
        stops = {}
        for n in (5, 10, 20):
            stops[n] = struct_stop(threes, sig_idx, side, n, atr) if sig_idx else None
        entry = tr["entry"]
        path = bars_after(bars, when, HORIZON_MIN)
        # post-entry mfe/mae ignoring stop, full horizon, stop-bar included only before a hypothetical
        mfe_h = 0.0
        mae_h = 0.0
        for b in path:
            mfe_h = max(mfe_h, fav(side, entry, b[2], b[3]))
            mae_h = max(mae_h, adv(side, entry, b[2], b[3]))
        mfe_n = {}
        for n in (1, 2, 3, 6):
            cbs = completed_3m_after(threes, when, n)
            if len(cbs) < n:
                mfe_n[n] = None
            else:
                mfe_n[n], _ = mfe_until(side, entry, path, cbs[n - 1]["close_t"])
        bot_risk = tr["stop_pts"]
        post = None
        klass = ""
        struct10_hit = None
        if tr["status"] == "COMPLETE" and tr["pnl"] is not None and tr["pnl"] < 0 and tr["exit"] is not None:
            exit_t = when + timedelta(minutes=2)
            # actual exit time is a couple minutes after entry for most; use fill audit if we only have et minute
            post = shadow_after_exit(side, entry, when + timedelta(minutes=1), tr["exit"], bot_risk or 14.25, bars)
            # did structural 10 get hit before +1 bot-risk favorable move after entry
            s10 = stops[10]
            struct_hit_time = None
            plus1_time = None
            run_mfe = 0.0
            for b in path:
                run_mfe = max(run_mfe, fav(side, entry, b[2], b[3]))
                if struct_hit_time is None and hit_stop(side, s10, b[2], b[3]):
                    struct_hit_time = b[0]
                if bot_risk and plus1_time is None and run_mfe >= bot_risk:
                    plus1_time = b[0]
            struct10_hit = struct_hit_time is not None and (plus1_time is None or struct_hit_time <= plus1_time)
            meaningful = bool(bot_risk) and post["post_mfe"] >= bot_risk
            # structural invalidation over the shadow, not only before +1R
            struct_eventually = struct_hit_time is not None
            if (not struct_eventually) and meaningful:
                klass = "PREMATURE_BOT_STOP"
            elif struct_eventually and not meaningful:
                klass = "TRUE_FAILURE"
            elif struct_eventually and meaningful and struct10_hit:
                klass = "TRUE_FAILURE"
            elif meaningful and not struct10_hit:
                klass = "PREMATURE_BOT_STOP"
            else:
                klass = "AMBIGUOUS"
        rec = {
            "trade": tr,
            "when": when,
            "sig": sig,
            "sig_idx": sig_idx,
            "atr": atr,
            "feat": feat,
            "stops": stops,
            "mfe_h": mfe_h,
            "mae_h": mae_h,
            "mfe_n": mfe_n,
            "post": post,
            "class": klass,
            "path": path,
        }
        rows.append(rec)

    # systems
    def run_systems(rec, nstop):
        tr = rec["trade"]
        side = tr["side"]
        feat = rec["feat"]
        atr = rec["atr"]
        sig_idx = rec["sig_idx"]
        stop = rec["stops"][nstop]
        origin_sw = bool(feat and feat["sideways"])
        # system 1
        if tr["entry"] is None or stop is None:
            s1 = (None, "NO_DATA")
        else:
            px, why, _, _mae = walk_stop(side, tr["entry"], stop, rec["path"])
            pts = (px - tr["entry"]) if side == "LONG" else (tr["entry"] - px)
            if why == "STRUCT_STOP":
                pts = -abs(tr["entry"] - stop)
            s1 = (pts, why)
        # system 2 entry
        if not origin_sw:
            ent_t, ent_px, how = rec["when"], tr["entry"], "IMMEDIATE"
            stop2 = stop
        else:
            conf = confirm_entry(side, feat, atr, threes, sig_idx) if sig_idx is not None else None
            if conf is None:
                return {"s1": s1, "s2": (0.0, "CANCEL_NO_CONFIRMATION"), "s3": s1, "s4": (0.0, "CANCEL_NO_CONFIRMATION"), "entry_how": "CANCEL"}
            ent_t, ent_px, how, bar = conf
            stop2 = struct_stop(threes, signal_bar_index(threes, ent_t), side, nstop, atr14(threes, signal_bar_index(threes, ent_t)))
        path2 = bars_after(bars, ent_t, HORIZON_MIN)
        if stop2 is None:
            s2 = (None, "NO_STOP")
        else:
            px, why, _, _mae = walk_stop(side, ent_px, stop2, path2)
            pts = -abs(ent_px - stop2) if why == "STRUCT_STOP" else ((px - ent_px) if side == "LONG" else (ent_px - px))
            s2 = (pts, why if not origin_sw else f"{how}:{why}")
        # system 3 progress on original entry if sideways
        s3 = progress_or_stop(side, tr["entry"], stop, origin_sw, False, None, atr, rec["path"], rec["when"])
        # system 4
        escaped = origin_sw and how == "ESCAPE"
        boundary = None
        if escaped and feat:
            boundary = feat["range_high"] if side == "LONG" else feat["range_low"]
        s4 = progress_or_stop(side, ent_px, stop2, origin_sw, escaped, boundary, atr, path2, ent_t)
        return {"s1": s1, "s2": s2, "s3": s3, "s4": s4, "entry_how": how, "ent_px": ent_px}

    def progress_or_stop(side, entry, stop, origin_sw, escaped, boundary, atr, path, entry_time):
        if stop is None or entry is None:
            return None, "NO_STOP"
        risk = abs(entry - stop)
        if risk <= 0 or (side == "LONG" and stop >= entry) or (side == "SHORT" and stop <= entry):
            return -abs(entry - stop) if risk else 0.0, "STOP_ALREADY_THROUGH"
        checks = completed_3m_after(threes, entry_time, 8)
        end = entry_time + timedelta(minutes=HORIZON_MIN)
        mfe = 0.0
        saw3 = False
        saw6 = False
        for t, o, h, l, c in path:
            if hit_stop(side, stop, h, l):
                return -risk, "STRUCT_STOP"
            mfe = max(mfe, fav(side, entry, h, l))
            if origin_sw and len(checks) >= 3 and not saw3 and t >= checks[2]["close_t"]:
                saw3 = True
                cur = (checks[2]["c"] - entry) if side == "LONG" else (entry - checks[2]["c"])
                if mfe / risk < FAIL_MFE and cur / risk <= 0:
                    return cur, "EXIT_SIDEWAYS_EARLY_FAILURE"
            if origin_sw and len(checks) >= 6 and not saw6 and t >= checks[5]["close_t"]:
                saw6 = True
                cur = (checks[5]["c"] - entry) if side == "LONG" else (entry - checks[5]["c"])
                if mfe / risk < PROG_MFE:
                    return cur, "EXIT_SIDEWAYS_NO_PROGRESS"
            esc = None
        if escaped:
            esc = escape_exit(side, entry, boundary, atr, threes, entry_time, end)
            if esc and esc[2] <= end:
                # only if escape exit is before structural stop; structural already returned if hit first in 1m loop
                # re-check: if stop hit before escape time, stop wins. Already returned above if stop hit inside path.
                return esc[0], esc[1]
        if not path:
            return 0.0, "NO_BARS"
        last = path[-1][4]
        pts = (last - entry) if side == "LONG" else (entry - last)
        return pts, "HORIZON_8H"

    summaries = {5: [], 10: [], 20: []}
    for rec in rows:
        rec["systems"] = {n: run_systems(rec, n) for n in (5, 10, 20)}

    # write csv using 10-bar as the unoptimized middle lookback for the single R columns
    csv_path = OUT / "LAST_WEEK_REPLAY.csv"
    fields = [
        "trade_id", "signal_time", "entry_time", "direction", "actual_entry", "actual_exit",
        "actual_result_dollars", "actual_result_points", "status", "sideways", "efficiency",
        "overlap_20", "range_position", "actual_bot_stop", "bot_stop_distance",
        "structural_stop_5", "structural_stop_10", "structural_stop_20", "cdx_native_stop_if_known",
        "mfe_after_1_bar", "mfe_after_2_bars", "mfe_after_3_bars", "mfe_after_6_bars",
        "total_post_entry_mfe", "mae", "premature_stop_classification",
        "baseline_R", "structural_only_R", "armed_entry_R", "progress_exit_R", "full_state_machine_R",
        "structural_only_R_5", "structural_only_R_20", "s1_reason_10", "s2_reason_10", "s3_reason_10", "s4_reason_10",
        "notes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for rec in rows:
            tr = rec["trade"]
            feat = rec["feat"] or {}
            sig = rec["sig"]
            sys10 = rec["systems"][10]
            def rr(n, key):
                pts, why = rec["systems"][n][key]
                risk = None if rec["stops"][n] is None else abs(tr["entry"] - rec["stops"][n])
                if key in ("s2", "s4") and why and "CANCEL" in why:
                    return 0.0
                if pts is None or not risk or risk <= 0:
                    return ""
                return round(pts / risk, 4)
            bot_r = ""
            if tr["pnl"] is not None and tr["stop_pts"]:
                bot_r = round((tr["pnl"] / PV) / tr["stop_pts"], 4)
            notes = []
            if tr["status"] != "COMPLETE":
                notes.append(tr["status"])
            if sig is None:
                notes.append("no webhook within 3 minutes; fill time used")
            w.writerow({
                "trade_id": tr["id"],
                "signal_time": "" if sig is None else sig["time"].astimezone(ET).strftime("%Y-%m-%d %H:%M:%S"),
                "entry_time": tr["et"],
                "direction": tr["side"],
                "actual_entry": tr["entry"],
                "actual_exit": "" if tr["exit"] is None else tr["exit"],
                "actual_result_dollars": "" if tr["pnl"] is None else tr["pnl"],
                "actual_result_points": "" if tr["pnl"] is None else round(tr["pnl"] / PV, 2),
                "status": tr["status"],
                "sideways": "" if feat is None else feat["sideways"],
                "efficiency": "" if not feat else round(feat["efficiency"], 4),
                "overlap_20": "" if not feat else round(feat["overlap"], 4),
                "range_position": "" if not feat else round(feat["range_position"], 4),
                "actual_bot_stop": "",
                "bot_stop_distance": "" if tr["stop_pts"] is None else tr["stop_pts"],
                "structural_stop_5": "" if rec["stops"][5] is None else round(rec["stops"][5], 2),
                "structural_stop_10": "" if rec["stops"][10] is None else round(rec["stops"][10], 2),
                "structural_stop_20": "" if rec["stops"][20] is None else round(rec["stops"][20], 2),
                "cdx_native_stop_if_known": "",
                "mfe_after_1_bar": "" if rec["mfe_n"][1] is None else round(rec["mfe_n"][1], 2),
                "mfe_after_2_bars": "" if rec["mfe_n"][2] is None else round(rec["mfe_n"][2], 2),
                "mfe_after_3_bars": "" if rec["mfe_n"][3] is None else round(rec["mfe_n"][3], 2),
                "mfe_after_6_bars": "" if rec["mfe_n"][6] is None else round(rec["mfe_n"][6], 2),
                "total_post_entry_mfe": round(rec["mfe_h"], 2),
                "mae": round(rec["mae_h"], 2),
                "premature_stop_classification": rec["class"],
                "baseline_R": bot_r,
                "structural_only_R": rr(10, "s1"),
                "armed_entry_R": rr(10, "s2"),
                "progress_exit_R": rr(10, "s3"),
                "full_state_machine_R": rr(10, "s4"),
                "structural_only_R_5": rr(5, "s1"),
                "structural_only_R_20": rr(20, "s1"),
                "s1_reason_10": sys10["s1"][1],
                "s2_reason_10": sys10["s2"][1],
                "s3_reason_10": sys10["s3"][1],
                "s4_reason_10": sys10["s4"][1],
                "notes": "; ".join(notes),
            })

    # json blob for the report writer
    blob = []
    for rec in rows:
        tr = rec["trade"]
        feat = rec["feat"] or {}
        sig = rec["sig"]
        item = {
            "id": tr["id"],
            "et": tr["et"],
            "side": tr["side"],
            "status": tr["status"],
            "entry": tr["entry"],
            "exit": tr["exit"],
            "pnl": tr["pnl"],
            "stop_pts": tr["stop_pts"],
            "signal_time": None if sig is None else sig["time"].astimezone(ET).isoformat(),
            "signal_price": None if sig is None else sig["price"],
            "signal_tf_field": None if sig is None else sig["tf"],
            "delta_sec": None if sig is None else (sig["time"] - rec["when"]).total_seconds(),
            "atr": rec["atr"],
            "sideways": feat.get("sideways"),
            "efficiency": feat.get("efficiency"),
            "overlap": feat.get("overlap"),
            "range_position": feat.get("range_position"),
            "stops": {str(k): rec["stops"][k] for k in rec["stops"]},
            "mfe_h": rec["mfe_h"],
            "mae_h": rec["mae_h"],
            "mfe_n": {str(k): rec["mfe_n"][k] for k in rec["mfe_n"]},
            "post": rec["post"],
            "class": rec["class"],
        }
        for n in (5, 10, 20):
            item[f"sys{n}"] = {
                k: rec["systems"][n][k] if k == "entry_how" else [rec["systems"][n][k][0], rec["systems"][n][k][1]]
                for k in ("s1", "s2", "s3", "s4", "entry_how")
            }
        blob.append(item)
    (OUT / "replay_blob.json").write_text(json.dumps(blob, indent=2, default=str), encoding="utf-8")
    print("wrote", csv_path, "trades", len(rows))


if __name__ == "__main__":
    main()
