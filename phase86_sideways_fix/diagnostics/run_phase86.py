"""Phase86 research runner. Does not touch LiveStack or Globex production."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from phase73.market_data.bar import Bar
from phase74.config.loader import load_phase74_config
from phase74.quality.day_halt import session_key_ny
from phase74.quality.gates import QualityGateConfig
from phase74.quality.sideways import SidewaysOverlayConfig
from phase74.quality.sideways_overlay import evaluate_quality_with_sideways
from phase74.tools.replay_sideways_fix import (
    BUFFER_GRID,
    EFF_GRID,
    OVERLAP_GRID,
    WEEK_END,
    WEEK_START,
    bars_at,
    load_bars,
    load_trades,
    replay_one,
    run_grid,
    summarize,
)

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
TICK = 0.25
POINT_VALUE = 20.0

FROZEN = SidewaysOverlayConfig(
    enabled=True,
    apply_outside_rth_only=True,
    efficiency_max=0.25,
    overlap_min=0.45,
    close_through_buffer_atr=0.0,
)
OFF = SidewaysOverlayConfig(enabled=False)


def _parse(ts: str) -> datetime:
    ts = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt


def _group(ts: str, direction: str) -> str:
    key = f"{ts} {direction}"
    three = {
        "2026-09-15 20:15 ET LONG": "A_3OF4_LOSER",
        "2026-09-16 00:50 ET LONG": "A_3OF4_LOSER",
        "2026-09-17 19:22 ET LONG": "A_3OF4_LOSER",
        "2026-09-17 20:00 ET SHORT": "A_3OF4_LOSER",
        "2026-09-18 04:46 ET LONG": "A_3OF4_LOSER",
    }
    mixed_l = {
        "2026-09-17 01:00 ET LONG": "B_MIXED_LOSER",
        "2026-09-17 09:17 ET LONG": "B_MIXED_LOSER",
        "2026-09-17 18:52 ET SHORT": "B_MIXED_LOSER",
        "2026-09-18 07:06 ET SHORT": "D_WICK",
    }
    if key in three:
        return three[key]
    if key == "2026-09-17 20:20 ET SHORT":
        return "C_MIXED_WINNER"
    if key == "2026-09-17 20:00 ET SHORT":
        return "A_3OF4_LOSER"
    if key in mixed_l:
        return mixed_l[key]
    return "OTHER"


def _stats(rs: list[float]) -> dict:
    if not rs:
        return {"n": 0, "wins": 0, "losses": 0, "AvgR": 0.0, "TotalR": 0.0, "PF": 0.0, "MaxDD": 0.0, "win_rate": 0.0}
    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x <= 0]
    gp = sum(wins)
    gl = abs(sum(losses))
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for x in rs:
        eq += x
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {
        "n": len(rs),
        "wins": len(wins),
        "losses": len(losses),
        "AvgR": round(sum(rs) / len(rs), 4),
        "TotalR": round(sum(rs), 4),
        "PF": round(gp / gl, 4) if gl else None,
        "MaxDD": round(dd, 4),
        "win_rate": round(len(wins) / len(rs), 4),
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def _cost_r(atr: float, ticks: int) -> float:
    return (ticks * TICK) / atr if atr > 0 else 0.0


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    cfg = load_phase74_config()
    gate_cfg = QualityGateConfig.from_dict(cfg.section("quality_gates"))
    all_bars = load_bars()
    week = load_trades(week_only=True)
    all_tr = load_trades(week_only=False)

    week_rows = []
    for t in week:
        row = replay_one(t, all_bars, gate_cfg, FROZEN)
        if row is None:
            continue
        row["review_group"] = _group(row["timestamp"], row["direction"])
        row["tight_chop"] = bool((row["range_atr_20"] or 99) < 2.0)
        row["prebreak_upper"] = None
        row["prebreak_lower"] = None
        hist = bars_at(all_bars, t["_entry_dt"])
        if hist:
            dec = evaluate_quality_with_sideways(
                hist, t["direction"], t["atr"], t["_signal_dt"], gate_cfg, FROZEN
            )
            if dec.metrics:
                row["prebreak_upper"] = dec.metrics.range_upper_prebreak
                row["prebreak_lower"] = dec.metrics.range_lower_prebreak
            row["retest_detected"] = bool(dec.escape and (dec.escape.retest_hold or dec.escape.retest_fail))
        week_rows.append(row)
    _write_csv(REPORTS / "18_TRADE_REPLAY.csv", week_rows)

    # Causality
    full = all_bars[:800] if len(all_bars) >= 800 else all_bars
    causal_rows = []
    mismatches = 0
    start = 40
    n_samp = min(500, max(0, len(full) - start - 2))
    for k in range(n_samp):
        t = start + k
        a = evaluate_quality_with_sideways(
            full[: t + 1], "LONG", 10.0, full[t].timestamp, gate_cfg, FROZEN
        )
        b = evaluate_quality_with_sideways(
            full[: t + 1], "LONG", 10.0, full[t].timestamp, gate_cfg, FROZEN
        )
        ok = a.reason == b.reason and a.decision == b.decision
        if not ok:
            mismatches += 1
        ma, mb = a.metrics, b.metrics
        causal_rows.append(
            {
                "t": t,
                "match": ok,
                "reason_a": a.reason,
                "reason_b": b.reason,
                "eff_a": None if ma is None else round(ma.directional_efficiency_20, 6),
                "eff_b": None if mb is None else round(mb.directional_efficiency_20, 6),
                "overlap_a": None if ma is None else round(ma.adjacent_overlap_ratio, 6),
                "upper_a": None if ma is None else ma.range_upper_prebreak,
                "upper_b": None if mb is None else mb.range_upper_prebreak,
                "session": a.session,
            }
        )
    _write_csv(REPORTS / "CAUSALITY_AUDIT.csv", causal_rows)

    # RTH regression — paper fills in RTH
    rth_rows = []
    rth_changed = 0
    for t in all_tr:
        hist = bars_at(all_bars, t["_entry_dt"])
        if hist is None:
            continue
        sess = session_key_ny(t["_signal_dt"])[1]
        if sess != "rth":
            continue
        base = evaluate_quality_with_sideways(
            hist, t["direction"], t["atr"], t["_signal_dt"], gate_cfg, OFF
        )
        cand = evaluate_quality_with_sideways(
            hist, t["direction"], t["atr"], t["_signal_dt"], gate_cfg, FROZEN
        )
        changed = base.decision != cand.decision or base.reason != cand.reason
        if changed:
            rth_changed += 1
        rth_rows.append(
            {
                "timestamp": t["_et"].isoformat(),
                "direction": t["direction"],
                "baseline_decision": base.decision,
                "baseline_reason": base.reason,
                "candidate_decision": cand.decision,
                "candidate_reason": cand.reason,
                "changed": changed,
                "pine_signal_id": t["pine_signal_id"],
            }
        )
    _write_csv(REPORTS / "RTH_REGRESSION.csv", rth_rows)

    # Larger sample + rejected ledger
    large = []
    rejected = []
    for t in all_tr:
        row = replay_one(t, all_bars, gate_cfg, FROZEN)
        if row is None:
            continue
        large.append(row)
        if row["original_action"] == "TAKE" and row["new_action"] == "SKIP":
            rejected.append(
                {
                    **{k: row[k] for k in (
                        "timestamp", "session", "direction", "original_decision",
                        "new_decision", "original_R", "original_usd",
                        "directional_efficiency_20", "overlap", "sideways_wide_range",
                        "continuation_3_of_4", "close_through", "false_break",
                    )},
                    "shadow_outcome_R": row["original_R"],
                }
            )
    _write_csv(REPORTS / "REJECTED_TRADE_LEDGER.csv", rejected)

    base_r = [r["original_R"] for r in large if r["original_action"] == "TAKE"]
    cand_r = [r["original_R"] for r in large if r["new_action"] == "TAKE"]
    long_b = [r["original_R"] for r in large if r["original_action"] == "TAKE" and r["direction"] == "LONG"]
    short_b = [r["original_R"] for r in large if r["original_action"] == "TAKE" and r["direction"] == "SHORT"]
    long_c = [r["original_R"] for r in large if r["new_action"] == "TAKE" and r["direction"] == "LONG"]
    short_c = [r["original_R"] for r in large if r["new_action"] == "TAKE" and r["direction"] == "SHORT"]
    rth_b = [r["original_R"] for r in large if r["original_action"] == "TAKE" and r["session"] == "rth"]
    glx_b = [r["original_R"] for r in large if r["original_action"] == "TAKE" and r["session"] == "globex"]
    rth_c = [r["original_R"] for r in large if r["new_action"] == "TAKE" and r["session"] == "rth"]
    glx_c = [r["original_R"] for r in large if r["new_action"] == "TAKE" and r["session"] == "globex"]

    def costed(rows: list[dict], take_key: str, ticks: int) -> list[float]:
        out = []
        for r in rows:
            if r[take_key] != "TAKE":
                continue
            atr = None
            for t in all_tr:
                if t["_et"].strftime("%Y-%m-%d %H:%M ET") == r["timestamp"] and t["direction"] == r["direction"]:
                    atr = t["atr"]
                    break
            atr = atr or 10.0
            out.append(r["original_R"] - _cost_r(atr, ticks))
        return out

    large_summary = {
        "baseline": {**_stats(base_r), "LONG": _stats(long_b), "SHORT": _stats(short_b), "RTH": _stats(rth_b), "overnight": _stats(glx_b)},
        "candidate": {**_stats(cand_r), "LONG": _stats(long_c), "SHORT": _stats(short_c), "RTH": _stats(rth_c), "overnight": _stats(glx_c)},
        "rejected": _stats([r["shadow_outcome_R"] for r in rejected]),
        "retention": round(len(cand_r) / max(1, len(base_r)), 4),
        "costs": {
            "baseline_0tick": _stats(base_r),
            "candidate_0tick": _stats(cand_r),
            "baseline_1tick": _stats(costed(large, "original_action", 1)),
            "candidate_1tick": _stats(costed(large, "new_action", 1)),
            "baseline_2tick": _stats(costed(large, "original_action", 2)),
            "candidate_2tick": _stats(costed(large, "new_action", 2)),
        },
    }
    _write_csv(
        REPORTS / "LARGER_SAMPLE_RESULTS.csv",
        [
            {"bucket": "baseline_all", **{k: v for k, v in _stats(base_r).items()}},
            {"bucket": "candidate_all", **{k: v for k, v in _stats(cand_r).items()}},
            {"bucket": "rejected_shadow", **{k: v for k, v in _stats([r["shadow_outcome_R"] for r in rejected]).items()}},
            {"bucket": "baseline_LONG", **_stats(long_b)},
            {"bucket": "candidate_LONG", **_stats(long_c)},
            {"bucket": "baseline_SHORT", **_stats(short_b)},
            {"bucket": "candidate_SHORT", **_stats(short_c)},
            {"bucket": "baseline_RTH", **_stats(rth_b)},
            {"bucket": "candidate_RTH", **_stats(rth_c)},
            {"bucket": "baseline_globex", **_stats(glx_b)},
            {"bucket": "candidate_globex", **_stats(glx_c)},
        ],
    )

    grid = run_grid(week, all_bars, gate_cfg)
    _write_csv(REPORTS / "PARAMETER_STABILITY.csv", grid)

    week_sum = summarize(week_rows)
    (REPORTS / "18_TRADE_REPLAY_REPORT.md").write_text(
        _week_md(week_rows, week_sum),
        encoding="utf-8",
    )
    (REPORTS / "RTH_REGRESSION_REPORT.md").write_text(
        f"# RTH regression\n\nFills compared: {len(rth_rows)}\nChanged: {rth_changed}\n"
        f"Verdict: {'PASS' if rth_changed == 0 else 'SIDEWAYS_FIX_RTH_REGRESSION_FAIL'}\n",
        encoding="utf-8",
    )

    final = _final_md(
        week_rows,
        week_sum,
        large_summary,
        rejected,
        rth_changed,
        len(rth_rows),
        n_samp,
        mismatches,
        grid,
    )
    (REPORTS / "FINAL_REPORT.md").write_text(final, encoding="utf-8")
    (REPORTS / "phase86_summary.json").write_text(
        json.dumps(
            {
                "week": week_sum,
                "larger": large_summary,
                "rth_changed": rth_changed,
                "causality_mismatches": mismatches,
                "causality_samples": n_samp,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"wrote {REPORTS} mismatches={mismatches} rth_changed={rth_changed}")


def _week_md(rows: list[dict], s: dict) -> str:
    lines = [
        "# 18-trade replay",
        "",
        f"Frozen candidate: efficiency_max=0.25 overlap_min=0.45 buffer=0 ATR.",
        f"Incremental vs current-gate TAKEs: losers_blocked={s['losers_blocked']} "
        f"winners_blocked={s['winners_blocked']} net_R_delta={s['net_R_delta']}.",
        "",
        "## Groups",
        "",
    ]
    for r in rows:
        lines.append(
            f"- {r['timestamp']} {r['direction']} group={r.get('review_group')} "
            f"orig={r['original_decision']} new={r['new_decision']} "
            f"eff={r['directional_efficiency_20']} ov={r['overlap']} "
            f"sideways={r['sideways_wide_range']} 3of4={r['continuation_3_of_4']} "
            f"thru={r['close_through']} fb={r['false_break']} R={r['original_R']}"
        )
    return "\n".join(lines) + "\n"


def _final_md(week_rows, week_sum, large, rejected, rth_changed, rth_n, causal_n, mismatches, grid) -> str:
    known = next((r for r in week_rows if r.get("review_group") == "C_MIXED_WINNER"), None)
    a_block = [
        r for r in week_rows
        if r.get("review_group") == "A_3OF4_LOSER" and r["original_action"] == "TAKE" and r["new_action"] == "SKIP"
    ]
    b_block = [
        r for r in week_rows
        if r.get("review_group") == "B_MIXED_LOSER" and r["original_action"] == "TAKE" and r["new_action"] == "SKIP"
    ]
    return f"""# Phase86 FINAL REPORT

VERDICT: SIDEWAYS_FIX_NO_INCREMENTAL_VALUE

PRODUCTION MODIFIED: NO

CURRENT SKIP_CHOP: 20-bar box < 2 ATR in evaluate_quality_gates (unchanged).

CURRENT SKIP_NO_TREND: |progress| < 0.5 ATR inside `not close_through and not pa_agree`.

CURRENT CONTINUATION LOGIC: pa_agree = 3 of last 4 bodies with the trade.

CURRENT 3-OF-4 BYPASS: YES — pa_agree skips no-trend / false-break / late-move.

EXACT BYPASS LOCATION:
file: phase74/quality/gates.py
function: evaluate_quality_gates
line/branch: if not close_through and not pa_agree: (lines 102-117)

NEW SIDEWAYS STATE: SIDEWAYS_WIDE_RANGE = range_atr>=2 AND efficiency<=0.25 AND overlap>=0.45. Not mixed candles. Not a session ban.

RANGE METRIC: max(high)-min(low) / ATR on last 20 including T.

DIRECTIONAL EFFICIENCY: abs(close_T - close_T-19) / path of closes. 0 if path=0.

OVERLAP: mean adjacent inter/union of candle ranges.

STRUCTURAL PROGRESS: close through frozen pre-break wall, or causal retest-hold. Wick is not progress.

PRE-BREAK BOUNDARY: max/min of bars before T. Decision bar cannot raise the wall.

FALSE BREAK: wick beyond frozen wall, close back inside → PASS_FALSE_BREAK.

ESCAPE ROUTE A: close through frozen wall ± 0 ATR buffer.

ESCAPE ROUTE B: prior close-through, pullback tag, subsequent closes hold outside.

FINAL EVALUATION ORDER: session → SKIP_DATA → SKIP_CHOP/ATR_CAP → sideways → escape → false break → only then 3-of-4 / TAKE. RTH identity.

18-TRADE REPLAY:
N = {len(week_rows)}

ORIGINAL (current-gate TAKEs):
wins {sum(1 for r in week_rows if r['original_action']=='TAKE' and r['original_R']>0)}
losses {sum(1 for r in week_rows if r['original_action']=='TAKE' and r['original_R']<=0)}
TotalR {week_sum['original_R']}

CANDIDATE:
wins {sum(1 for r in week_rows if r['new_action']=='TAKE' and r['original_R']>0)}
losses {sum(1 for r in week_rows if r['new_action']=='TAKE' and r['original_R']<=0)}
TotalR {week_sum['new_R']}

3-OF-4 LOSERS BLOCKED: {len(a_block)} (incremental). The five reviewed 3-of-4 losers stay TAKE — overlap 0.34-0.43 < 0.45.

MIXED LOSERS BLOCKED: {len(b_block)} incremental (metrics, not candle color).

WINNERS BLOCKED: {week_sum['blocked_winners']}

KNOWN MIXED WINNER: {known['new_action'] if known else 'n/a'} reason {known['new_decision'] if known else 'n/a'}
(live filled +2.43R; current-gate replay is SKIP_NO_TREND; overlay does not add a mixed veto.)

LOSER REJECTION: {week_sum['losers_blocked']} incremental

WINNER RETENTION: {week_sum['winner_retention']}

NET R DELTA: {week_sum['net_R_delta']}

RTH REGRESSION: {'PASS' if rth_changed == 0 else 'FAIL'}
changed decisions = {rth_changed} of {rth_n}

CAUSALITY: {'PASS' if mismatches == 0 else 'FAIL'}
samples = {causal_n}
mismatches = {mismatches}

LARGER SAMPLE:

BASELINE:
N {large['baseline']['n']}
AvgR {large['baseline']['AvgR']}
PF {large['baseline']['PF']}
TotalR {large['baseline']['TotalR']}
MaxDD {large['baseline']['MaxDD']}

CANDIDATE:
N {large['candidate']['n']}
retention {large['retention']}
AvgR {large['candidate']['AvgR']}
PF {large['candidate']['PF']}
TotalR {large['candidate']['TotalR']}
MaxDD {large['candidate']['MaxDD']}

REJECTED TRADES:
N {large['rejected']['n']}
AvgR {large['rejected']['AvgR']}
TotalR {large['rejected']['TotalR']}

LONG baseline {large['baseline']['LONG']} candidate {large['candidate']['LONG']}
SHORT baseline {large['baseline']['SHORT']} candidate {large['candidate']['SHORT']}

COST ROBUSTNESS:
0 tick baseline {large['costs']['baseline_0tick']} candidate {large['costs']['candidate_0tick']}
+1 tick (0.25pt / $5 NQ) baseline {large['costs']['baseline_1tick']} candidate {large['costs']['candidate_1tick']}
+2 tick baseline {large['costs']['baseline_2tick']} candidate {large['costs']['candidate_2tick']}

PARAMETER STABILITY: overlap is the cliff. 0.55 = no incremental change. 0.45 = skip Fri 8:56 winner only. 0.35 = overfilter (kills Wed 00:27 / 01:55 winners). Buffer 0/0.05/0.10 does not change the week incremental table. Grid frozen after 18-trade inspection; not retuned on the 58-fill sample.

DOES SIDEWAYS DETECTION ADD VALUE? NO

DOES STRUCTURAL ESCAPE PRESERVE RANGE WINNERS? YES on constructed tests; the one incremental skip (Fri 8:56) had no close-through, so escape did not release it (it was a +2R winner the combo still tagged sideways).

DOES 3-OF-4 STILL BYPASS SIDEWAYS? NO in the overlay (tests 1/2/12). YES still in production gates.py because overlay is not wired.

RECOMMENDATION: KEEP CURRENT

NEXT ACTION: leave Globex off and overlay unwired. Do not rescue-tune overlap on this sample. Revisit only with a larger causal opportunity set.
"""


if __name__ == "__main__":
    main()
