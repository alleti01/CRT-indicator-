"""Prefix-invariance audit for overnight freeze, 2M aggregation, and decisions."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase83.python.config import CAUSALITY_SAMPLES, CAUSALITY_SEED, NY_TZ
from phase83.python.events import session_events


def _ny_naive(ny) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(ny).tz_convert(NY_TZ).tz_localize(None)


def overnight_prefix_ok(arr: dict, sess, rng) -> bool:
    """ON high/low from data ending at/after freeze must match stored freeze."""
    T = sess.rth_open_i - 1
    if T < sess.on_end_i:
        return True
    sl = slice(sess.on_start_i, sess.on_end_i + 1)
    # prefix ending at T includes the full overnight window
    if sess.on_end_i > T:
        return False
    h = float(arr["hi"][sl].max())
    l = float(arr["lo"][sl].min())
    return abs(h - sess.on_high) < 1e-9 and abs(l - sess.on_low) < 1e-9


def twom_prefix_ok(arr: dict, twom: dict, i: int) -> bool:
    """Completed 2M at i is a function of bars in its bucket only (≤ i)."""
    if not twom["complete"][i]:
        return True
    # Local clock only — do not rebuild 3M timestamp arrays per sample.
    ny_i = arr["ny"][i]
    start = i
    while start > 0:
        ny_p = arr["ny"][start - 1]
        same_bucket = (
            ny_p.date() == ny_i.date()
            and (ny_p.hour * 60 + ny_p.minute) // 2 == (ny_i.hour * 60 + ny_i.minute) // 2
        )
        if not same_bucket:
            break
        start -= 1
    sl = slice(start, i + 1)
    if (i + 1 - start) < 2:
        return False
    o = float(arr["op"][start])
    h = float(arr["hi"][sl].max())
    l = float(arr["lo"][sl].min())
    c = float(arr["cl"][i])
    return (
        abs(o - float(twom["open"][i])) < 1e-9
        and abs(h - float(twom["high"][i])) < 1e-9
        and abs(l - float(twom["low"][i])) < 1e-9
        and abs(c - float(twom["close"][i])) < 1e-9
    )


def decision_prefix_ok(arr, twom, sess, model: str, T: int) -> bool:
    """Events confirmed by T using a truncated research window must match the full-session run."""
    from dataclasses import replace

    T = int(max(sess.rth_open_i, min(T, sess.research_end_i)))
    sess_cut = replace(sess, research_end_i=T)
    full = session_events(arr, twom, sess, model)
    pref = session_events(arr, twom, sess_cut, model)

    def key(e):
        return (e.direction, e.level_type, e.family)

    fmap = {key(e): e for e in full}
    pmap = {key(e): e for e in pref}
    for k, e in fmap.items():
        if e.confirm_i <= T:
            pe = pmap.get(k)
            if pe is None or pe.confirm_i != e.confirm_i or pe.entry_i != e.entry_i:
                return False
        elif k in pmap and pmap[k].confirm_i > T:
            return False
    for e in pref:
        if e.confirm_i > T or e.touch_i > T:
            return False
    return True


def run_causality_audit(arr, twom, sessions, models=("B0", "B1", "B2", "F1", "F2")) -> dict:
    rng = np.random.default_rng(CAUSALITY_SEED)
    n_on = n_on_fail = 0
    n_2m = n_2m_fail = 0
    n_dec = n_dec_fail = 0
    failures: list[str] = []

    sample_sess = rng.choice(len(sessions), size=min(CAUSALITY_SAMPLES, len(sessions)), replace=False)
    print(f"  overnight checks {len(sample_sess)}", flush=True)
    for si in sample_sess:
        sess = sessions[int(si)]
        n_on += 1
        if not overnight_prefix_ok(arr, sess, rng):
            n_on_fail += 1
            if len(failures) < 8:
                failures.append(f"ON_FREEZE {sess.date}")

    print("  2M prefix checks", flush=True)
    complete_idx = np.flatnonzero(twom["complete"] & (np.arange(arr["n"]) > 5000))
    if len(complete_idx):
        pick = rng.choice(complete_idx, size=min(CAUSALITY_SAMPLES, len(complete_idx)), replace=False)
        for i in pick:
            n_2m += 1
            if not twom_prefix_ok(arr, twom, int(i)):
                n_2m_fail += 1
                if len(failures) < 12:
                    failures.append(f"2M {int(i)}")

    print("  decision prefix checks", flush=True)
    for si in sample_sess[: min(200, len(sample_sess))]:
        sess = sessions[int(si)]
        model = str(rng.choice(list(models)))
        n_dec += 1
        T = int(rng.integers(sess.rth_open_i, max(sess.rth_open_i + 1, sess.research_end_i + 1)))
        if not decision_prefix_ok(arr, twom, sess, model, T):
            n_dec_fail += 1
            if len(failures) < 16:
                failures.append(f"DECISION {sess.date} {model}")

    total_fail = n_on_fail + n_2m_fail + n_dec_fail
    return {
        "overnight_checks": n_on,
        "overnight_fail": n_on_fail,
        "twom_checks": n_2m,
        "twom_fail": n_2m_fail,
        "decision_checks": n_dec,
        "decision_fail": n_dec_fail,
        "sampled": n_on + n_2m + n_dec,
        "failures": total_fail,
        "fail_examples": failures,
        "status": "PASS" if total_fail == 0 else "FAIL",
    }
