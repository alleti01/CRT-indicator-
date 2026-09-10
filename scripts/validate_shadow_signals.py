#!/usr/bin/env python3
"""Validate Phase74 shadow signals — entry gates + virtual trade outcomes."""
from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forward_rehearsal.shadow.position_tracker import ShadowPositionTracker
from phase73.config.loader import load_config
from phase73.market_data.bar import Bar
from phase73.market_data.health import DataHealth, HealthReport
from phase73.market_data.provider import ReplayDataProvider
from phase73.trader.entry_quality import evaluate_entry
from phase73.trader.fsm import TraderAction
from phase73.webhook.schemas import PineSignal, _parse_ts

LOGS = ROOT / "phase74" / "logs"
OUT = ROOT / "forward_rehearsal" / "reports"
ET = ZoneInfo("America/New_York")


@dataclass
class ValidationRow:
    signal_id: str
    event: str
    signal_bar_time_utc: str
    received_at_utc: str
    signal_price: float
    atr: float
    observed_action: str
    market_health: str
    entry_price: float | None
    chase_points: float | None
    chase_atr: float | None
    signal_age_s: float | None
    gate_action: str
    gate_reason: str
    regime: str
    exit_action: str
    exit_reason: str
    gross_r: float | None
    mfe_r: float | None
    mae_r: float | None
    valid_entry: bool
    valid_outcome: bool | None


def in_day_utc(ts: str, day: str) -> bool:
    return ts.startswith(day)


def to_et(iso: str) -> str:
    if not iso:
        return ""
    iso = iso.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ET).strftime("%H:%M:%S")
    except ValueError:
        return iso


def row_to_signal(row: dict) -> PineSignal:
    return PineSignal(
        schema_version=row["schema_version"],
        strategy=row["strategy"],
        pine_hash=row["pine_hash"],
        signal_id=row["signal_id"],
        event=row["event"],
        symbol=row["symbol"],
        timeframe=row["timeframe"],
        signal_time_utc=_parse_ts(row["signal_time_utc"]),
        signal_bar_time_utc=_parse_ts(row["signal_bar_time_utc"]),
        signal_price=float(row["signal_price"]),
        atr=float(row["atr"]),
        evidence=int(row.get("evidence") or 5),
        context=row.get("context") or "",
        state=row.get("state") or "",
        received_at_utc=_parse_ts(row["received_at_utc"]),
    )


def load_unique_signals(day: str) -> list[PineSignal]:
    by_id: dict[str, PineSignal] = {}
    with open(LOGS / "signals.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not in_day_utc(row.get("received_at_utc", ""), day):
                continue
            sig = row_to_signal(row)
            by_id[sig.signal_id] = sig
    return sorted(by_id.values(), key=lambda s: s.received_at_utc)


def load_observed_actions() -> dict[str, str]:
    actions: dict[str, str] = {}
    path = LOGS / "errors.jsonl"
    if not path.exists():
        return actions
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if "shadow" in rec and rec.get("signal_id"):
            actions[rec["signal_id"]] = str(rec["shadow"])
    with open(LOGS / "decisions.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = row.get("signal_id") or ""
            if not sid:
                continue
            act = row.get("action") or ""
            if act.startswith("PASS_"):
                actions[sid] = act
    return actions


def load_watch_bars(day: str) -> pd.DataFrame:
    rows: list[dict] = []
    with open(LOGS / "decisions.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("action") != "WATCH":
                continue
            ts = row.get("market_timestamp") or row.get("timestamp_utc") or ""
            if not in_day_utc(ts, day):
                continue
            try:
                close = float(row["current_price"])
            except (TypeError, ValueError, KeyError):
                continue
            rows.append(
                {
                    "timestamp": _parse_ts(ts.replace("Z", "+00:00") if ts.endswith("Z") else ts),
                    "close": close,
                    "atr": float(row["current_atr"]) if row.get("current_atr") else 0.0,
                    "health": row.get("market_data_health") or "",
                }
            )
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    rows.sort(key=lambda r: r["timestamp"])
    out_rows = []
    prev = rows[0]["close"]
    for r in rows:
        o, c = prev, r["close"]
        h, l = max(o, c), min(o, c)
        out_rows.append(
            {
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 100.0,
            }
        )
        prev = c
    idx = pd.DatetimeIndex([r["timestamp"] for r in rows], tz="UTC")
    df = pd.DataFrame(out_rows, index=idx)
    df["atr"] = [r["atr"] for r in rows]
    df["health"] = [r["health"] for r in rows]
    return df


def load_bars_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def nearest_bar_index(df: pd.DataFrame, when: datetime) -> int:
    when = when.astimezone(timezone.utc)
    idx = df.index.searchsorted(when, side="right") - 1
    return max(0, min(int(idx), len(df) - 1))


def market_at_signal(df: pd.DataFrame, sig: PineSignal) -> tuple[float, float, str]:
    i = nearest_bar_index(df, sig.received_at_utc)
    row = df.iloc[i]
    atr = float(row.get("atr", 0)) if "atr" in df.columns else 0.0
    health = str(row.get("health", "DATA_HEALTHY")) if "health" in df.columns else "DATA_HEALTHY"
    return float(row["close"]), atr, health


class _FrozenProvider(ReplayDataProvider):
    """Replay provider pinned at decision time for entry evaluation."""

    def __init__(self, df: pd.DataFrame, index: int, *, health: DataHealth, atr: float) -> None:
        super().__init__(df, start_index=index)
        self._health = health
        self._atr = atr

    def health(self) -> HealthReport:
        last = self.latest_bar()
        now = self.current_time()
        if self._health != DataHealth.DATA_HEALTHY:
            return HealthReport(self._health, last_bar_timestamp=last.timestamp if last else None, current_time=now)
        return HealthReport(
            DataHealth.DATA_HEALTHY,
            last_bar_timestamp=last.timestamp if last else None,
            current_time=now,
            latency_seconds=0.0,
        )

    def atr(self, period: int = 14) -> float:
        return self._atr or super().atr(period)


def classify_regime(df: pd.DataFrame, when: datetime) -> str:
    try:
        from phase75.regime.classifier import compute_regime_frame, regime_at_time

        i = nearest_bar_index(df, when)
        window = df.iloc[max(0, i - 120) : i + 1].copy()
        if len(window) < 35:
            return "UNKNOWN"
        reg = compute_regime_frame(window)
        snap = regime_at_time(reg, window.index[-1])
        return snap.regime
    except Exception:
        return "UNKNOWN"


def replay_trade(
    df: pd.DataFrame,
    sig: PineSignal,
    entry_index: int,
    entry_price: float,
    cfg,
) -> dict:
    tracker = ShadowPositionTracker(cfg)
    entry_time = df.index[entry_index].to_pydatetime()
    if entry_time.tzinfo is None:
        entry_time = entry_time.replace(tzinfo=timezone.utc)
    tracker.open_from_signal(sig, entry_price, entry_time)

    last_action = ""
    last_reason = ""
    for j in range(entry_index + 1, len(df)):
        ts = df.index[j]
        row = df.iloc[j]
        bar = Bar(
            timestamp=ts.to_pydatetime().replace(tzinfo=timezone.utc),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0)),
        )
        now = bar.timestamp
        act = tracker.on_bar(bar, now)
        if act:
            last_action = act.action
            last_reason = act.reason
        if not tracker.is_active and tracker.closed_trades:
            break

    if tracker.is_active and tracker.position:
        mgmt = tracker.position.mgmt
        risk = mgmt.risk or 1.0
        gross_r = mgmt.current_r
        return {
            "exit_action": "OPEN_AT_SESSION_END",
            "exit_reason": "bars_exhausted",
            "gross_r": gross_r,
            "mfe_r": tracker.position.mfe,
            "mae_r": tracker.position.mae,
        }

    if tracker.closed_trades:
        t = tracker.closed_trades[-1]
        risk = cfg.stop_atr * sig.atr
        gross_r = 0.0
        if risk > 0:
            move = (t["exit_price"] - t["entry_price"]) if t["direction"] == "LONG" else (t["entry_price"] - t["exit_price"])
            gross_r = move / risk
        return {
            "exit_action": t["action"],
            "exit_reason": t["exit_reason"],
            "gross_r": gross_r,
            "mfe_r": t["mfe_r"],
            "mae_r": t["mae_r"],
        }

    return {
        "exit_action": last_action or "NO_TRADE",
        "exit_reason": last_reason or "not_entered",
        "gross_r": None,
        "mfe_r": None,
        "mae_r": None,
    }


def validate_day(
    day: str,
    *,
    pass_chase: bool,
    pass_late: bool,
    max_chase_atr: float,
    late_age_seconds: int,
    bars_csv: Path | None = None,
) -> list[ValidationRow]:
    cfg = load_config()
    eq = cfg.raw.setdefault("entry_quality", {})
    eq["pass_chase_enabled"] = pass_chase
    eq["pass_late_enabled"] = pass_late
    eq["max_chase_atr"] = max_chase_atr
    if pass_late:
        eq["max_signal_age_seconds"] = late_age_seconds

    signals = load_unique_signals(day)
    observed = load_observed_actions()
    if bars_csv:
        bars = load_bars_csv(bars_csv)
    else:
        from phase74.replay.sequential import load_bars

        bars = load_bars(day, LOGS)
        if bars.empty:
            bars = load_watch_bars(day)
    if bars.empty:
        raise SystemExit(f"No bar data for {day}. Provide --bars-csv or run bot with WATCH decisions logged.")

    rows: list[ValidationRow] = []
    for sig in signals:
        entry_px, live_atr, health_str = market_at_signal(bars, sig)
        atr = live_atr if live_atr > 0 else sig.atr
        health = DataHealth.DATA_HEALTHY if health_str == "DATA_HEALTHY" else DataHealth.DATA_MISSING
        idx = nearest_bar_index(bars, sig.received_at_utc)
        provider = _FrozenProvider(bars, idx, health=health, atr=atr or sig.atr)
        now = sig.received_at_utc
        entry = evaluate_entry(sig, provider, cfg, position_side="FLAT", now=now)

        chase_pts = entry_px - sig.signal_price
        chase_atr = chase_pts / atr if atr else None
        age_s = (now - sig.signal_time_utc).total_seconds()
        regime = classify_regime(bars, sig.received_at_utc)

        take = entry.action in (TraderAction.TAKE_LONG, TraderAction.TAKE_SHORT)
        outcome = {
            "exit_action": "",
            "exit_reason": "",
            "gross_r": None,
            "mfe_r": None,
            "mae_r": None,
        }
        if take:
            outcome = replay_trade(bars, sig, idx, entry_px, cfg)

        valid_outcome = None
        if take and outcome["gross_r"] is not None:
            valid_outcome = outcome["gross_r"] > 0

        rows.append(
            ValidationRow(
                signal_id=sig.signal_id,
                event=sig.event,
                signal_bar_time_utc=sig.signal_bar_time_utc.isoformat(),
                received_at_utc=sig.received_at_utc.isoformat(),
                signal_price=sig.signal_price,
                atr=atr,
                observed_action=observed.get(sig.signal_id, "UNKNOWN"),
                market_health=health_str or health.value,
                entry_price=entry_px if take else None,
                chase_points=chase_pts if take else None,
                chase_atr=chase_atr,
                signal_age_s=age_s,
                gate_action=entry.action.value,
                gate_reason=entry.reason,
                regime=regime,
                exit_action=str(outcome["exit_action"]),
                exit_reason=str(outcome["exit_reason"]),
                gross_r=outcome["gross_r"],
                mfe_r=outcome["mfe_r"],
                mae_r=outcome["mae_r"],
                valid_entry=take,
                valid_outcome=valid_outcome,
            )
        )
    return rows


def write_reports(day: str, rows: list[ValidationRow], *, pass_chase: bool, pass_late: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / f"{day}_signal_validation.csv"
    fields = [f.name for f in ValidationRow.__dataclass_fields__.values()]  # type: ignore[attr-defined]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r.__dict__)

    entered = [r for r in rows if r.valid_entry]
    skipped = [r for r in rows if not r.valid_entry]
    wins = [r for r in entered if r.valid_outcome]
    losses = [r for r in entered if r.valid_outcome is False]
    chop = [r for r in entered if r.regime == "CHOP"]

    md_path = OUT / f"{day}_SIGNAL_VALIDATION.md"
    lines = [
        f"# Signal Validation — {day}",
        "",
        f"Gates: pass_chase={pass_chase}, pass_late={pass_late}",
        "",
        "## Summary",
        "",
        f"- **Signals analyzed:** {len(rows)}",
        f"- **Would enter (simulated):** {len(entered)}",
        f"- **Skipped by gates:** {len(skipped)}",
        f"- **Winners (gross R > 0):** {len(wins)}",
        f"- **Losers:** {len(losses)}",
        f"- **Entered in CHOP regime:** {len(chop)}",
    ]
    if entered:
        rs = [r.gross_r for r in entered if r.gross_r is not None]
        if rs:
            lines.append(f"- **Total gross R:** {sum(rs):+.2f}")
            lines.append(f"- **Avg gross R:** {sum(rs)/len(rs):+.2f}")

    lines += [
        "",
        "## Per-signal",
        "",
        "| ET | Event | Observed | Gate | Chase ATR | Regime | Exit | Gross R | Valid? |",
        "|----|-------|----------|------|-----------|--------|------|---------|--------|",
    ]
    for r in rows:
        chase = "" if r.chase_atr is None else f"{r.chase_atr:+.2f}"
        gr = "" if r.gross_r is None else f"{r.gross_r:+.2f}"
        valid = ""
        if r.valid_outcome is True:
            valid = "WIN"
        elif r.valid_outcome is False:
            valid = "LOSS"
        elif not r.valid_entry:
            valid = "SKIP"
        lines.append(
            f"| {to_et(r.received_at_utc)} | {r.event} | {r.observed_action} | "
            f"{r.gate_action} | {chase} | {r.regime} | {r.exit_action} | {gr} | {valid} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- Outcomes use M0 management (1.0 ATR stop, 2.5R target, 60m hold) on reconstructed 1m bars.",
        "- Bars from `decisions.csv` WATCH rows when `--bars-csv` is not supplied (close-derived OHLC).",
        "- Regime labels are observational (Phase75); CHOP does not block entry in this report.",
        f"- CSV: `{csv_path.relative_to(ROOT).as_posix()}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")
    print(f"Entered: {len(entered)}, Skipped: {len(skipped)}, W/L: {len(wins)}/{len(losses)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate shadow signals for a UTC calendar day")
    ap.add_argument("day", nargs="?", default=datetime.now(ET).strftime("%Y-%m-%d"))
    ap.add_argument("--bars-csv", type=Path, help="Optional 1m OHLCV CSV (timestamp, open, high, low, close)")
    ap.add_argument("--pass-chase", action="store_true", help="Enable PASS_CHASE gate")
    ap.add_argument("--pass-late", action="store_true", help="Enable PASS_LATE gate")
    ap.add_argument("--max-chase-atr", type=float, default=1.5)
    ap.add_argument("--late-age-seconds", type=int, default=60)
    ap.add_argument(
        "--sequential",
        action="store_true",
        help="One-position-at-a-time R replay (uses phase74/logs/bars.csv when present)",
    )
    args = ap.parse_args()

    if args.sequential:
        from phase74.replay.sequential import sequential_replay

        seq = sequential_replay(
            args.day,
            pass_chase=args.pass_chase or True,
            pass_late=args.pass_late or True,
            late_age_seconds=args.late_age_seconds,
            max_chase_atr=args.max_chase_atr,
        )
        print(f"Sequential replay {args.day}")
        print(f"  signals={seq.signals} trades={seq.trades_taken} skipped={seq.signals_skipped}")
        print(f"  W/L={seq.wins}/{seq.losses} TOTAL R={seq.total_gross_r:+.2f}")
        for t in seq.trades:
            print(f"    {t.event:12} {t.exit_action:22} {t.gross_r:+.2f}R  entry={t.entry_price:.2f} exit={t.exit_price:.2f}")
        return 0

    rows = validate_day(
        args.day,
        pass_chase=args.pass_chase,
        pass_late=args.pass_late,
        max_chase_atr=args.max_chase_atr,
        late_age_seconds=args.late_age_seconds,
        bars_csv=args.bars_csv,
    )
    write_reports(args.day, rows, pass_chase=args.pass_chase, pass_late=args.pass_late)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
