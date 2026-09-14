"""Causal breakout / failed-break event detection. One first event per side per session."""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from phase83.python.config import (
    B6_MAX_WAIT,
    B7_MAX_WAIT,
    EXTENDED_ATR,
    F2_RETURN_BARS,
    F4_DISP_ATR,
    F4_DISP_BARS,
    RESET_ATR,
    RETEST_ATR,
)
from phase83.python.levels import Session, time_bucket
from phase83.python.management import first_passage_from_price, forward_excursions, net_with_slip, walk_m0


@dataclass
class Event:
    date: str
    model: str
    family: str  # CONTINUATION | REVERSAL | NO_ENTRY
    direction: str
    level_type: str
    level_price: float
    touch_i: int
    confirm_i: int
    entry_i: int
    entry_price: float
    atr: float
    confirmation_type: str
    distance_beyond_atr: float
    volume_ratio: float
    body_fraction: float
    time_bucket: str
    reason_code: str
    opportunity_state: str
    move_from_open_atr: float
    move_last_5m_atr: float
    move_last_10m_atr: float
    breakout_range_atr: float
    gap_atr: float
    on_range_atr: float
    open_class: str


def _body_frac(o, h, l, c) -> float:
    rng = h - l
    if rng <= 0:
        return 0.0
    return abs(c - o) / rng


def _chase(arr, sess: Session, i: int, atr: float) -> dict:
    o = sess.rth_open
    cl = arr["cl"]
    hi = arr["hi"]
    lo = arr["lo"]
    a = atr if atr > 0 else 1.0
    i0 = max(sess.rth_open_i, i - 5)
    i1 = max(sess.rth_open_i, i - 10)
    return {
        "move_from_open_atr": float(abs(cl[i] - o) / a),
        "move_last_5m_atr": float(abs(cl[i] - cl[i0]) / a),
        "move_last_10m_atr": float(abs(cl[i] - cl[i1]) / a),
        "breakout_range_atr": float((hi[i] - lo[i]) / a),
    }


def _pack_event(
    sess: Session,
    arr: dict,
    *,
    model: str,
    family: str,
    direction: str,
    level_type: str,
    level: float,
    touch_i: int,
    confirm_i: int,
    entry_i: int,
    atr: float,
    confirmation_type: str,
    dist_atr: float,
    vol_ratio: float,
    body: float,
    reason: str,
    state: str,
) -> Event:
    ny = arr["ny"][confirm_i]
    chase = _chase(arr, sess, confirm_i, atr)
    return Event(
        date=sess.date,
        model=model,
        family=family,
        direction=direction,
        level_type=level_type,
        level_price=float(level),
        touch_i=int(touch_i),
        confirm_i=int(confirm_i),
        entry_i=int(entry_i),
        entry_price=float(arr["op"][entry_i]),
        atr=float(atr),
        confirmation_type=confirmation_type,
        distance_beyond_atr=float(dist_atr),
        volume_ratio=float(vol_ratio),
        body_fraction=float(body),
        time_bucket=time_bucket(int(ny.hour), int(ny.minute)),
        reason_code=reason,
        opportunity_state=state,
        gap_atr=sess.gap_atr,
        on_range_atr=sess.on_range_atr,
        open_class=sess.open_class,
        **chase,
    )


def _window(sess: Session) -> range:
    return range(sess.rth_open_i, sess.research_end_i + 1)


def _first_touch(arr, sess, level, side: str) -> int | None:
    hi, lo = arr["hi"], arr["lo"]
    for i in _window(sess):
        if side == "LONG" and hi[i] > level:
            return i
        if side == "SHORT" and lo[i] < level:
            return i
    return None


def _scan_b0(arr, sess, level, side) -> Event | None:
    t = _first_touch(arr, sess, level, side)
    if t is None or t + 1 >= arr["n"]:
        return None
    atr = float(arr["atr"][t])
    if not np.isfinite(atr) or atr <= 0:
        return None
    dist = (arr["hi"][t] - level) / atr if side == "LONG" else (level - arr["lo"][t]) / atr
    return _pack_event(
        sess, arr, model="B0", family="CONTINUATION", direction=side,
        level_type="ON_HIGH" if side == "LONG" else "ON_LOW", level=level,
        touch_i=t, confirm_i=t, entry_i=t + 1, atr=atr,
        confirmation_type="RAW_TOUCH", dist_atr=dist, vol_ratio=np.nan,
        body=_body_frac(arr["op"][t], arr["hi"][t], arr["lo"][t], arr["cl"][t]),
        reason="B0_FIRST_TOUCH", state="TRADED",
    )


def _scan_b1(arr, sess, level, side) -> Event | None:
    t = _first_touch(arr, sess, level, side)
    if t is None:
        return None
    cl = arr["cl"]
    for i in range(t, sess.research_end_i + 1):
        ok = cl[i] > level if side == "LONG" else cl[i] < level
        if ok and i + 1 < arr["n"]:
            atr = float(arr["atr"][i])
            if not np.isfinite(atr) or atr <= 0:
                continue
            dist = (cl[i] - level) / atr if side == "LONG" else (level - cl[i]) / atr
            return _pack_event(
                sess, arr, model="B1", family="CONTINUATION", direction=side,
                level_type="ON_HIGH" if side == "LONG" else "ON_LOW", level=level,
                touch_i=t, confirm_i=i, entry_i=i + 1, atr=atr,
                confirmation_type="1M_CLOSE", dist_atr=dist, vol_ratio=np.nan,
                body=_body_frac(arr["op"][i], arr["hi"][i], arr["lo"][i], arr["cl"][i]),
                reason="B1_1M_CLOSE", state="ACCEPTED",
            )
    return None


def _scan_b2(arr, twom, sess, level, side, *, model="B2", min_body=0.0, min_dist=0.0, min_vol=0.0) -> Event | None:
    t = _first_touch(arr, sess, level, side)
    if t is None:
        return None
    for i in range(t, sess.research_end_i + 1):
        if not twom["complete"][i]:
            continue
        c2, o2, h2, l2 = twom["close"][i], twom["open"][i], twom["high"][i], twom["low"][i]
        ok = c2 > level if side == "LONG" else c2 < level
        if not ok:
            continue
        atr = float(arr["atr"][i])
        if not np.isfinite(atr) or atr <= 0:
            continue
        body = _body_frac(o2, h2, l2, c2)
        if min_body > 0 and body < min_body:
            continue
        if min_body > 0:
            directed = c2 > o2 if side == "LONG" else c2 < o2
            if not directed:
                continue
        dist = (c2 - level) / atr if side == "LONG" else (level - c2) / atr
        if dist < min_dist:
            continue
        vb = twom["vol_base"][i]
        vr = float(twom["volume"][i] / vb) if np.isfinite(vb) and vb > 0 else np.nan
        if min_vol > 0 and (not np.isfinite(vr) or vr < min_vol):
            continue
        if i + 1 >= arr["n"]:
            return None
        tag = "2M_CLOSE"
        if min_body:
            tag = "2M_BODY"
        if min_dist:
            tag = "2M_DIST"
        if min_vol:
            tag = "2M_VOL"
        return _pack_event(
            sess, arr, model=model, family="CONTINUATION", direction=side,
            level_type="ON_HIGH" if side == "LONG" else "ON_LOW", level=level,
            touch_i=t, confirm_i=i, entry_i=i + 1, atr=atr,
            confirmation_type=tag, dist_atr=dist, vol_ratio=vr if np.isfinite(vr) else np.nan,
            body=body, reason=f"{model}_CONFIRMED", state="ACCEPTED",
        )
    return None


def _scan_b6(arr, sess, level, side) -> Event | None:
    """Confirmed 1M close, then first causal retest that holds, then reaction."""
    base = _scan_b1(arr, sess, level, side)
    if base is None:
        return None
    c0 = base.confirm_i
    atr = base.atr
    cl, hi, lo, op = arr["cl"], arr["hi"], arr["lo"], arr["op"]
    end = min(c0 + B6_MAX_WAIT, sess.research_end_i)
    for i in range(c0 + 1, end + 1):
        lost = cl[i] < level if side == "LONG" else cl[i] > level
        if lost:
            return None
        if side == "LONG":
            retest = lo[i] <= level + RETEST_ATR * atr and hi[i] >= level
            hold = cl[i] > level
            react = cl[i] > op[i]
        else:
            retest = hi[i] >= level - RETEST_ATR * atr and lo[i] <= level
            hold = cl[i] < level
            react = cl[i] < op[i]
        if retest and hold and react and i + 1 < arr["n"]:
            dist = (cl[i] - level) / atr if side == "LONG" else (level - cl[i]) / atr
            return _pack_event(
                sess, arr, model="B6", family="CONTINUATION", direction=side,
                level_type=base.level_type, level=level,
                touch_i=base.touch_i, confirm_i=i, entry_i=i + 1, atr=atr,
                confirmation_type="RETEST_HOLD", dist_atr=dist, vol_ratio=np.nan,
                body=_body_frac(op[i], hi[i], lo[i], cl[i]),
                reason="B6_RETEST_HOLD", state="TRADED",
            )
    return None


def _scan_b7(arr, sess, level, side) -> Event | None:
    base = _scan_b1(arr, sess, level, side)
    if base is None or base.distance_beyond_atr < EXTENDED_ATR:
        return None
    c0 = base.confirm_i
    atr = base.atr
    cl, op, hi, lo = arr["cl"], arr["op"], arr["hi"], arr["lo"]
    end = min(c0 + B7_MAX_WAIT, sess.research_end_i)
    reset_i = None
    for i in range(c0 + 1, end + 1):
        lost = cl[i] < level if side == "LONG" else cl[i] > level
        if lost:
            return None
        dist = (cl[i] - level) / atr if side == "LONG" else (level - cl[i]) / atr
        if reset_i is None and 0 <= dist <= RESET_ATR:
            reset_i = i
            continue
        if reset_i is not None:
            react = cl[i] > op[i] and cl[i] > level if side == "LONG" else cl[i] < op[i] and cl[i] < level
            if react and i + 1 < arr["n"]:
                return _pack_event(
                    sess, arr, model="B7", family="CONTINUATION", direction=side,
                    level_type=base.level_type, level=level,
                    touch_i=base.touch_i, confirm_i=i, entry_i=i + 1, atr=atr,
                    confirmation_type="WAIT_RESET", dist_atr=dist, vol_ratio=np.nan,
                    body=_body_frac(op[i], hi[i], lo[i], cl[i]),
                    reason="B7_RESET_REACTION", state="TRADED",
                )
    return None


def _scan_f1(arr, sess, level, break_side) -> Event | None:
    """Wick beyond level, close back inside → fade."""
    t = _first_touch(arr, sess, level, break_side)
    if t is None:
        return None
    cl, hi, lo, op = arr["cl"], arr["hi"], arr["lo"], arr["op"]
    for i in range(t, sess.research_end_i + 1):
        if break_side == "LONG":
            fail = hi[i] > level and cl[i] < level
            fade = "SHORT"
        else:
            fail = lo[i] < level and cl[i] > level
            fade = "LONG"
        if fail and i + 1 < arr["n"]:
            atr = float(arr["atr"][i])
            if not np.isfinite(atr) or atr <= 0:
                continue
            dist = (level - cl[i]) / atr if fade == "SHORT" else (cl[i] - level) / atr
            return _pack_event(
                sess, arr, model="F1", family="REVERSAL", direction=fade,
                level_type="ON_HIGH" if break_side == "LONG" else "ON_LOW", level=level,
                touch_i=t, confirm_i=i, entry_i=i + 1, atr=atr,
                confirmation_type="WICK_FAILURE", dist_atr=dist, vol_ratio=np.nan,
                body=_body_frac(op[i], hi[i], lo[i], cl[i]),
                reason="F1_WICK_FAIL", state="FAILED_BREAK_TRADED",
            )
    return None


def _scan_f2(arr, sess, level, break_side) -> Event | None:
    """Close outside then return inside within F2_RETURN_BARS."""
    t = _first_touch(arr, sess, level, break_side)
    if t is None:
        return None
    cl = arr["cl"]
    outside_i = None
    for i in range(t, sess.research_end_i + 1):
        out = cl[i] > level if break_side == "LONG" else cl[i] < level
        if out:
            outside_i = i
            break
    if outside_i is None:
        return None
    fade = "SHORT" if break_side == "LONG" else "LONG"
    end = min(outside_i + F2_RETURN_BARS, sess.research_end_i)
    for i in range(outside_i + 1, end + 1):
        back = cl[i] < level if break_side == "LONG" else cl[i] > level
        if back and i + 1 < arr["n"]:
            atr = float(arr["atr"][i])
            if not np.isfinite(atr) or atr <= 0:
                continue
            dist = abs(cl[i] - level) / atr
            return _pack_event(
                sess, arr, model="F2", family="REVERSAL", direction=fade,
                level_type="ON_HIGH" if break_side == "LONG" else "ON_LOW", level=level,
                touch_i=t, confirm_i=i, entry_i=i + 1, atr=atr,
                confirmation_type="ACCEPTANCE_FAILURE", dist_atr=dist, vol_ratio=np.nan,
                body=_body_frac(arr["op"][i], arr["hi"][i], arr["lo"][i], arr["cl"][i]),
                reason="F2_RETURN_INSIDE", state="FAILED_BREAK_TRADED",
            )
    return None


def _scan_f3(arr, sess, level, break_side) -> Event | None:
    """Failed break + reclaim + reaction."""
    f2 = _scan_f2(arr, sess, level, break_side)
    if f2 is None:
        return None
    # require reclaim already (F2 close back inside). Add reaction on confirm bar.
    i = f2.confirm_i
    react = arr["cl"][i] > arr["op"][i] if f2.direction == "LONG" else arr["cl"][i] < arr["op"][i]
    if not react:
        return None
    ev = f2
    ev.model = "F3"
    ev.confirmation_type = "RECLAIM"
    ev.reason_code = "F3_RECLAIM_REACTION"
    return ev


def _scan_f4(arr, sess, level, break_side) -> Event | None:
    """Failure then opposite displacement."""
    seed = _scan_f1(arr, sess, level, break_side) or _scan_f2(arr, sess, level, break_side)
    if seed is None:
        return None
    fade = seed.direction
    atr = seed.atr
    cl = arr["cl"]
    end = min(seed.confirm_i + F4_DISP_BARS, sess.research_end_i)
    for i in range(seed.confirm_i, end + 1):
        if fade == "SHORT":
            ok = cl[i] <= level - F4_DISP_ATR * atr
        else:
            ok = cl[i] >= level + F4_DISP_ATR * atr
        if ok and i + 1 < arr["n"]:
            return _pack_event(
                sess, arr, model="F4", family="REVERSAL", direction=fade,
                level_type=seed.level_type, level=level,
                touch_i=seed.touch_i, confirm_i=i, entry_i=i + 1, atr=atr,
                confirmation_type="FAIL_PLUS_DISPLACEMENT", dist_atr=abs(cl[i] - level) / atr,
                vol_ratio=np.nan, body=_body_frac(arr["op"][i], arr["hi"][i], arr["lo"][i], cl[i]),
                reason="F4_OPPOSITE_DISP", state="FAILED_BREAK_TRADED",
            )
    return None


def session_events(arr, twom, sess: Session, model: str, *, level_source: str = "ON") -> list[Event]:
    if level_source == "ON":
        hi_lvl, lo_lvl = sess.on_high, sess.on_low
        hi_type, lo_type = "ON_HIGH", "ON_LOW"
    elif level_source == "PRIOR_RTH":
        hi_lvl, lo_lvl = sess.prior_rth_high, sess.prior_rth_low
        hi_type, lo_type = "PRIOR_RTH_HIGH", "PRIOR_RTH_LOW"
    elif level_source == "SYNTH_OPEN":
        width = sess.on_high - sess.on_low
        hi_lvl, lo_lvl = sess.rth_open + width, sess.rth_open - width
        hi_type, lo_type = "SYNTH_HIGH", "SYNTH_LOW"
    else:
        raise ValueError(level_source)

    scanners = {
        "B0": lambda a, s, lv, sd: _scan_b0(a, s, lv, sd),
        "B1": _scan_b1,
        "B2": lambda a, s, lv, sd: _scan_b2(a, twom, s, lv, sd, model="B2"),
        "B3_55": lambda a, s, lv, sd: _scan_b2(a, twom, s, lv, sd, model="B3_55", min_body=0.55),
        "B4_10": lambda a, s, lv, sd: _scan_b2(a, twom, s, lv, sd, model="B4_10", min_dist=0.10),
        "B5_125": lambda a, s, lv, sd: _scan_b2(a, twom, s, lv, sd, model="B5_125", min_vol=1.25),
        "B6": _scan_b6,
        "B7": _scan_b7,
        "F1": _scan_f1,
        "F2": _scan_f2,
        "F3": _scan_f3,
        "F4": _scan_f4,
    }
    scan = scanners[model]
    out: list[Event] = []
    for side, lvl in (("LONG", hi_lvl), ("SHORT", lo_lvl)):
        ev = scan(arr, sess, lvl, side)
        if ev is None:
            continue
        ev.level_type = hi_type if side == "LONG" and ev.family == "CONTINUATION" else ev.level_type
        if ev.family == "CONTINUATION":
            ev.level_type = hi_type if side == "LONG" else lo_type
        ev.level_price = float(lvl)
        out.append(ev)
    return out


def collect_events(arr, twom, sessions: list[Session], models: tuple[str, ...], *, level_source: str = "ON") -> list[Event]:
    events: list[Event] = []
    for sess in sessions:
        for m in models:
            events.extend(session_events(arr, twom, sess, m, level_source=level_source))
    return events


def events_to_trades(events: list[Event], arr: dict) -> list[dict]:
    rows = []
    hi, lo, cl, op = arr["hi"], arr["lo"], arr["cl"], arr["op"]
    for ev in events:
        if ev.entry_i >= arr["n"] - 2:
            continue
        m0 = walk_m0(hi, lo, cl, entry_i=ev.entry_i, direction=ev.direction, entry_price=ev.entry_price, atr=ev.atr)
        exc = forward_excursions(hi, lo, cl, event_i=ev.confirm_i, direction=ev.direction, atr=ev.atr)
        a = ev.atr
        origin = float(cl[ev.confirm_i])
        fp = {
            "fp_0p5_before_0p5": first_passage_from_price(hi, lo, event_i=ev.confirm_i, origin=origin, direction=ev.direction, up_pts=0.5 * a, dn_pts=0.5 * a),
            "fp_1p0_before_0p5": first_passage_from_price(hi, lo, event_i=ev.confirm_i, origin=origin, direction=ev.direction, up_pts=1.0 * a, dn_pts=0.5 * a),
            "fp_1r_before_1r": first_passage_from_price(hi, lo, event_i=ev.confirm_i, origin=origin, direction=ev.direction, up_pts=a, dn_pts=a),
            "fp_2p5r_before_1r": first_passage_from_price(hi, lo, event_i=ev.confirm_i, origin=origin, direction=ev.direction, up_pts=2.5 * a, dn_pts=a),
        }
        # structural stop diagnostic
        if ev.direction == "LONG":
            struct_stop = float(lo[ev.confirm_i])
        else:
            struct_stop = float(hi[ev.confirm_i])
        struct = walk_m0(
            hi, lo, cl, entry_i=ev.entry_i, direction=ev.direction,
            entry_price=ev.entry_price, atr=ev.atr, stop_price=struct_stop,
        )
        struct_dist_atr = abs(ev.entry_price - struct_stop) / a if a > 0 else np.nan
        row = asdict(ev)
        row.update(m0)
        row.update(exc)
        row.update(fp)
        row["struct_net_r"] = struct["net_r"]
        row["struct_gross_r"] = struct["gross_r"]
        row["struct_dist_atr"] = float(struct_dist_atr)
        row["struct_exit"] = struct["exit_reason"]
        for ticks in (0, 1, 2):
            row[f"net_r_slip{ticks}"] = net_with_slip(m0["gross_r"], ev.entry_price, m0["risk"], ticks)
        ny_e = arr["ny"][ev.entry_i]
        ny_c = arr["ny"][ev.confirm_i]
        ny_t = arr["ny"][ev.touch_i]
        row["entry_ts"] = str(ny_e)
        row["confirm_ts"] = str(ny_c)
        row["touch_ts"] = str(ny_t)
        row["year"] = int(ny_e.year)
        rows.append(row)
    return rows
