"""S56 forward engine — optimized batch feature scoring + sequential bar replay."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from phase53.config import MAX_HOLD_MIN, STOP_ATR, TARGET_R
from phase53.research.data import load_markets
from phase54.research.parity import add_population_flags
from phase55.implementation.s54_episodes import S54EpisodeState, episode_event_order
from phase55.implementation.s54_events import S54EventDetector
from phase55.implementation.s54_features import attach_event_features, build_feature_context
from phase56.config import (
    FORWARD_START_TIMESTAMP_CT,
    HOLDOUT_END,
    LOGS,
    MODEL_HASH,
    P54_SCORED_CACHE,
    WARMUP_BARS,
)
from phase56.forward.logs import (
    AUDIT_FIELDS,
    AppendOnlyLog,
    DAILY_HASH_FIELDS,
    EVENT_FIELDS,
    SIGNAL_FIELDS,
    TRADE_FIELDS,
)
from phase56.forward.scoring import d10_pass, load_forward_model, load_score_spec, score_event_row
from phase56.forward.state import save_open_position, save_runtime_state
from phase56.forward.trades import PaperTradeManager


@dataclass
class S56ForwardEngine:
    m1: pd.DataFrame
    m5: pd.DataFrame
    m15: pd.DataFrame
    forward_start: pd.Timestamp
    forward_end: pd.Timestamp
    model_hash: str = MODEL_HASH
    event_log: AppendOnlyLog = field(init=False)
    signal_log: AppendOnlyLog = field(init=False)
    trade_log: AppendOnlyLog = field(init=False)
    audit_log: AppendOnlyLog = field(init=False)
    daily_hash_log: AppendOnlyLog = field(init=False)
    detector: S54EventDetector = field(init=False)
    episode_state: S54EpisodeState = field(default_factory=S54EpisodeState)
    trade_mgr: PaperTradeManager = field(init=False)
    p44: pd.Series = field(init=False)
    core_ctx: pd.DataFrame = field(init=False)
    m5a: pd.DataFrame = field(init=False)
    m15a: pd.DataFrame = field(init=False)
    forward_model: dict = field(init=False)
    score_spec: dict = field(init=False)
    event_counter: int = 0
    signal_counter: int = 0
    _scored_by_bar: dict[int, list[dict]] = field(default_factory=dict)
    _event_buffer: list[dict] = field(default_factory=list)
    _signal_buffer: list[dict] = field(default_factory=list)
    _trade_buffer: list[dict] = field(default_factory=list)
    _last_save_day: object = None

    def __post_init__(self) -> None:
        LOGS.mkdir(parents=True, exist_ok=True)
        self.event_log = AppendOnlyLog(LOGS / "s54_forward_events.csv", EVENT_FIELDS)
        self.signal_log = AppendOnlyLog(LOGS / "s54_forward_signals.csv", SIGNAL_FIELDS)
        self.trade_log = AppendOnlyLog(LOGS / "s54_forward_trades.csv", TRADE_FIELDS)
        self.audit_log = AppendOnlyLog(LOGS / "audit_log.csv", AUDIT_FIELDS)
        self.daily_hash_log = AppendOnlyLog(LOGS / "daily_checkpoint_hash.csv", DAILY_HASH_FIELDS)
        self.detector = S54EventDetector(self.m1, start_i=WARMUP_BARS)
        self.trade_mgr = PaperTradeManager(self.m1)
        self.p44, self.core_ctx, self.m5a, self.m15a = build_feature_context(self.m1, self.m5, self.m15)
        self.forward_model = load_forward_model()
        self.score_spec = load_score_spec()

    def warm_episode_from_history(self) -> None:
        if not P54_SCORED_CACHE.exists():
            return
        scored = pd.read_parquet(P54_SCORED_CACHE)
        scored = add_population_flags(scored)
        d10 = scored.loc[scored["top10"]].copy()
        ordered = episode_event_order(d10)
        pre = ordered.loc[pd.to_datetime(ordered["timestamp_ct"]) < self.forward_start]
        for _, r in pre.iterrows():
            self.episode_state.process(r["timestamp_ct"], r["direction"])

    def _collect_forward_events(self, i0: int, i1: int) -> pd.DataFrame:
        rows: list[dict] = []
        for i in range(WARMUP_BARS, i0):
            self.detector.step(i)
        for i in range(i0, i1 + 1):
            ts = pd.Timestamp(self.m1.index[i])
            if ts < self.forward_start or ts > self.forward_end:
                continue
            for ev in self.detector.step(i):
                rows.append({**ev, "entry_i": i})
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["timestamp_ct"] = pd.to_datetime(df["timestamp_ct"])
        df = df.sort_values(["timestamp_ct", "event_type", "direction"]).reset_index(drop=True)
        return df

    def _batch_score_events(self, events: pd.DataFrame) -> pd.DataFrame:
        featured = attach_event_features(
            events,
            self.m1,
            self.m5,
            self.m15,
            p44_state=self.p44,
            core_ctx=self.core_ctx,
            m5a=self.m5a,
            m15a=self.m15a,
        )
        scores = []
        for _, row in featured.iterrows():
            scores.append(score_event_row(row, self.forward_model))
        featured["quality_score"] = scores
        featured["D10_pass"] = featured["quality_score"].apply(lambda s: d10_pass(s, self.score_spec))
        return featured

    def _build_bar_index(self, scored: pd.DataFrame) -> None:
        self._scored_by_bar.clear()
        for k, row in scored.iterrows():
            i = int(row["entry_i"])
            self._scored_by_bar.setdefault(i, []).append(row.to_dict())

    def _flush_buffers(self) -> None:
        for row in self._event_buffer:
            self.event_log.append(row)
        for row in self._signal_buffer:
            self.signal_log.append(row)
        for row in self._trade_buffer:
            self.trade_log.append(row)
        self._event_buffer.clear()
        self._signal_buffer.clear()
        self._trade_buffer.clear()

    def _suppression_until(self, direction: str) -> str:
        ts = self.episode_state.last_start.get(direction)
        return str(pd.Timestamp(ts) + pd.Timedelta(minutes=30)) if ts is not None else ""

    def _process_scored_event(self, row: dict, i: int) -> None:
        self.event_counter += 1
        fwd_event_id = f"F56-{self.event_counter:07d}"
        ts = pd.Timestamp(row["timestamp_ct"])
        score = row.get("quality_score")
        is_d10 = bool(row.get("D10_pass"))
        ep_status = "NOT_D10"
        episode_id = ""
        suppressed = False
        if is_d10:
            act = self.episode_state.process(ts, row["direction"])
            suppressed = act["suppressed"]
            ep_status = "SUPPRESSED" if suppressed else "NEW_EPISODE"
            episode_id = act.get("episode_id") or ""
            if act["s54_entry"]:
                self._emit_signal(row, score, act, fwd_event_id, i)
        self._event_buffer.append(
            {
                "event_id": fwd_event_id,
                "timestamp_ct": ts,
                "timestamp_utc": ts.tz_convert("UTC"),
                "direction": row["direction"],
                "event_type": row["event_type"],
                "quality_score": score if score is not None else "",
                "D10_pass": is_d10,
                "episode_status": ep_status,
                "episode_id": episode_id,
                "suppressed_same_direction": suppressed,
                "suppression_until": self._suppression_until(row["direction"]) if is_d10 else "",
                "core_authorized": int(row.get("core_authorized", 0)),
                "core_b1_active": int(row.get("core_b1_active", 0)),
                "model_hash": self.model_hash,
            }
        )

    def _emit_signal(self, row: dict, score: float, act: dict, fwd_event_id: str, i: int) -> None:
        self.signal_counter += 1
        ts = pd.Timestamp(row["timestamp_ct"])
        atr = float(self.m1["atr"].iloc[i])
        ep = float(self.m1["close"].iloc[i])
        d = row["direction"]
        risk = STOP_ATR * atr
        stop = ep - risk if d == "LONG" else ep + risk
        target = ep + TARGET_R * risk if d == "LONG" else ep - TARGET_R * risk
        sig_id = f"S56-{self.signal_counter:05d}"
        explanation = (
            f"S54 {d} | {row['event_type']} | score={score:.4f} | D10 | "
            f"new_episode={act['episode_id']} | entry={ep:.2f} stop={stop:.2f} target={target:.2f}"
        )
        sig_row = {
            "signal_id": sig_id,
            "episode_id": act["episode_id"],
            "timestamp_ct": ts,
            "timestamp_utc": ts.tz_convert("UTC"),
            "direction": d,
            "initiating_event_id": fwd_event_id,
            "event_type": row["event_type"],
            "quality_score": score,
            "entry_timestamp": ts,
            "entry_price": ep,
            "atr": atr,
            "stop_price": stop,
            "target_price": target,
            "planned_max_hold_minutes": MAX_HOLD_MIN,
            "core_authorized": int(row.get("core_authorized", 0)),
            "core_signal_active": int(row.get("core_b1_active", 0)),
            "model_hash": self.model_hash,
            "explanation": explanation,
        }
        self._signal_buffer.append(sig_row)
        self.trade_mgr.open_from_signal({**sig_row, "entry_i": i})

    def _maybe_daily_checkpoint(self, ts: pd.Timestamp, impl_hash: str) -> None:
        day = ts.date()
        if self._last_save_day == day:
            return
        self._flush_buffers()
        save_runtime_state(
            bar_index=int(self.m1.index.searchsorted(ts)),
            event_counter=self.event_counter,
            signal_counter=self.signal_counter,
            episode_state=self.episode_state,
            last_bar_timestamp=str(ts),
        )
        self.daily_hash_log.append(
            {
                "date": str(day),
                "model_hash": self.model_hash,
                "implementation_hash": impl_hash,
                "data_end_timestamp": str(ts),
                "event_count": self.event_counter,
                "signal_count": self.signal_counter,
                "trade_count": self.trade_log.count() + len(self._trade_buffer),
                "cumulative_net_R": "",
            }
        )
        self._last_save_day = day

    def run(self, *, fresh: bool = False, impl_hash: str = "") -> dict:
        i0 = int(self.m1.index.searchsorted(self.forward_start))
        i1 = int(self.m1.index.searchsorted(self.forward_end, side="right")) - 1
        if fresh:
            self.event_counter = 0
            self.signal_counter = 0
            self.episode_state = S54EpisodeState()
            for p in (
                LOGS / "s54_forward_events.csv",
                LOGS / "s54_forward_signals.csv",
                LOGS / "s54_forward_trades.csv",
            ):
                if p.exists():
                    p.unlink()
            self.event_log = AppendOnlyLog(LOGS / "s54_forward_events.csv", EVENT_FIELDS)
            self.signal_log = AppendOnlyLog(LOGS / "s54_forward_signals.csv", SIGNAL_FIELDS)
            self.trade_log = AppendOnlyLog(LOGS / "s54_forward_trades.csv", TRADE_FIELDS)
        else:
            self.event_counter = self.event_log.count()
            self.signal_counter = self.signal_log.count()

        self.warm_episode_from_history()
        print("Collecting forward structural events...")
        raw = self._collect_forward_events(i0, i1)
        print(f"  {len(raw)} events in holdout window")
        print("Batch scoring + D10 qualification...")
        scored = self._batch_score_events(raw)
        self._build_bar_index(scored)

        print("Sequential bar replay (paper trades)...")
        for i in range(i0, i1 + 1):
            ts = pd.Timestamp(self.m1.index[i])
            if ts < self.forward_start or ts > self.forward_end:
                continue
            closed = self.trade_mgr.update_bar(i)
            if closed:
                self._trade_buffer.append({**closed, "model_hash": self.model_hash})
            if not self.trade_mgr.is_flat():
                if i % 60 == 0:
                    save_open_position(self.trade_mgr.open_position_json())
                continue
            save_open_position({"state": "FLAT"})
            for row in self._scored_by_bar.get(i, []):
                self._process_scored_event(row, i)
                if not self.trade_mgr.is_flat():
                    break
            if i % 390 == 0:
                self._maybe_daily_checkpoint(ts, impl_hash)

        self._flush_buffers()
        save_open_position(self.trade_mgr.open_position_json())
        save_runtime_state(
            bar_index=i1,
            event_counter=self.event_counter,
            signal_counter=self.signal_counter,
            episode_state=self.episode_state,
            last_bar_timestamp=str(self.m1.index[i1]),
        )
        return {
            "events": self.event_log.count(),
            "signals": self.signal_log.count(),
            "trades": self.trade_log.count(),
            "d10_events": int(scored["D10_pass"].sum()) if not scored.empty else 0,
            "last_bar": str(self.m1.index[i1]),
        }


def build_engine() -> S56ForwardEngine:
    m1, m5, m15 = load_markets()
    tz = m1.index.tz
    return S56ForwardEngine(
        m1=m1,
        m5=m5,
        m15=m15,
        forward_start=pd.Timestamp(FORWARD_START_TIMESTAMP_CT, tz=tz),
        forward_end=pd.Timestamp(HOLDOUT_END, tz=tz),
    )
