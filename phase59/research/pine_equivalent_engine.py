"""Phase59 bar-by-bar engine — mirrors Pine state transitions, uses frozen logic."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from phase58.research.trader_engine import TraderEngine
from phase58d.research.engine import run_variant
from phase58d.research.evidence import compute_evidence, decide
from phase58d.research.opportunity_memory import OpportunityMemory, OppState
from phase58f.research.confidence import compute_confidence
from phase58f.research.policies import apply_policy
from phase58g.research.forensics import classify_high_subtype, enrich
from phase58h.research.filters import apply_h_model
from phase58i.research.management import simulate_management, executions_from_trades
from phase58b.research.simulation import simulate_trades


@dataclass
class PendingEntry:
    signal_i: int
    direction: str
    opportunity_id: str
    entry_i: int
    entry_price: float
    evidence: dict
    conf: dict
    p4: str
    h1: str
    reason: str


@dataclass
class BarSnapshot:
    bar_i: int
    timestamp: str
    o: float
    h: float
    l: float
    c: float
    atr: float
    ctx15: str = ""
    ctx5: str = ""
    opp_id: str = ""
    opp_state: str = ""
    direction: str = ""
    phase58d_decision: str = ""
    p4_status: str = ""
    h1_status: str = ""
    final_take: bool = False
    pending_entry: bool = False
    active_trades: int = 0


class Phase59LiveEngine:
    """Sequential causal processor — one closed 1M bar at a time."""

    def __init__(self, m, ma, cfg: dict, system: str = "PE"):
        self.m = m
        self.ma = ma
        self.cfg = cfg
        self.system = system
        self.variant = "E"
        self.trader = TraderEngine(ma, cfg)
        self.memory = OpportunityMemory(
            structural_gap=cfg.get("structural_gap_bars", 30),
            expire_bars=cfg.get("opportunity_expire_bars", 45),
        )
        self.pending: list[PendingEntry] = []
        self.raw_signals: list[dict] = []
        self.bar_snapshots: list[BarSnapshot] = []
        self._trade_counter = 0

    def _atr(self, i: int) -> float:
        val = self.m.m1_atr[i]
        if np.isfinite(val) and val > 0:
            return float(val)
        for k in range(max(0, i - 5), i + 1):
            if np.isfinite(self.m.m1_atr[k]) and self.m.m1_atr[k] > 0:
                return float(self.m.m1_atr[k])
        return 1.0

    def _process_phase58_signal(self, signal_i: int, direction: str, entry_price: float) -> None:
        self.memory.expire_stale(signal_i)
        opp, is_new = self.memory.match_or_create(signal_i, entry_price, direction)
        if not is_new:
            return
        ev = compute_evidence(self.m, signal_i, direction, self.cfg)
        opp.location_score = ev["location_score"]
        opp.direction_score = ev["direction_score"]
        opp.reaction_score = ev["reaction_score"]
        opp.ctx15_state = ev["15m_state"]
        opp.ctx5_dir = ev["5m_state"]
        opp.max_evidence = max(opp.max_evidence, ev["total_evidence"])
        opp.state = OppState.DETECTED
        opp.armed_i = signal_i

        decision, _ = decide(ev, self.variant, self.cfg, 0)
        if decision != "TAKE":
            opp.state = OppState.PASS if decision == "PASS" else OppState.WAIT
            return

        opp.state = OppState.TAKE
        opp.take_i = signal_i
        self.memory.mark_traded(opp.opportunity_id, signal_i)

        conf = compute_confidence(self.m, signal_i, direction, self.cfg)
        row = pd.DataFrame([{
            **conf,
            "original_direction": direction,
            "15m_state": ev["15m_state"],
            "5m_state": ev.get("5m_state", ""),
            "location_score": ev["location_score"],
            "trade_id": f"PE-{signal_i}",
        }])
        row = enrich(row)
        p4 = apply_policy(row, "P4").iloc[0]
        h1 = apply_h_model(row, "H1").iloc[0]
        if h1 != "KEEP":
            return

        entry_i = min(signal_i + 1, self.m.m1_n - 1)
        ep = float(self.m.m1_op[entry_i])
        reason = (
            f"TAKE_{direction} | reaction={ev['reaction_score']} | "
            f"15m={ev['15m_state']} | P4={p4} | H1={h1}"
        )
        self.pending.append(PendingEntry(
            signal_i=signal_i, direction=direction, opportunity_id=opp.opportunity_id,
            entry_i=entry_i, entry_price=ep, evidence=ev, conf=conf,
            p4=p4, h1=h1, reason=reason,
        ))

    def on_bar_close(self, i: int) -> BarSnapshot:
        idx = self.m.m1_idx
        snap = BarSnapshot(
            bar_i=i,
            timestamp=str(idx[i]),
            o=float(self.m.m1_op[i]),
            h=float(self.m.m1_hi[i]),
            l=float(self.m.m1_lo[i]),
            c=float(self.m.m1_cl[i]),
            atr=self._atr(i),
        )

        # Trader engine (Phase58 v1) — emits TAKE at signal bar
        prev_n = len(self.trader.st.trades)
        self.trader.on_bar_close(i)
        if len(self.trader.st.trades) > prev_n:
            t = self.trader.st.trades[-1]
            si = int(t["signal_i"])
            self.raw_signals.append(t)
            self._process_phase58_signal(si, t["direction"], float(t["entry_price"]))

        # Flush pending entries whose entry_i == current bar (open already known at bar start;
        # we record at close of entry bar for parity export)
        executed_today = [p for p in self.pending if p.entry_i == i]
        self.pending = [p for p in self.pending if p.entry_i != i]
        snap.pending_entry = bool(executed_today)

        snap.active_trades = len(self.pending)
        self.bar_snapshots.append(snap)
        return snap

    def run(self, start_i: int | None = None, end_i: int | None = None) -> None:
        warmup = max(100, self.cfg.get("swing_period", 5) * 3)
        s = start_i if start_i is not None else warmup
        e = end_i if end_i is not None else self.m.m1_n - 61
        for i in range(s, e):
            self.on_bar_close(i)

    def canonical_trades_batch_equiv(self) -> pd.DataFrame:
        """Rebuild via frozen batch path for parity check against incremental signals."""
        _, p58_trades = self.trader.results()
        if p58_trades.empty:
            return pd.DataFrame()
        opps, _, dec_e, exec_e, _, _ = run_variant(
            self.m, p58_trades, self.cfg, self.variant, self.system,
        )
        if exec_e.empty:
            return pd.DataFrame()
        d58 = simulate_trades(self.m, exec_e, self.cfg, self.system)
        d58["signal_m1_i"] = exec_e["signal_m1_i"].values
        conf_rows = []
        for _, t in d58.iterrows():
            si = int(t.get("signal_m1_i", t["entry_i"] - 1))
            c = compute_confidence(self.m, si, t["direction"], self.cfg)
            c["trade_id"] = t.get("trade_id", f"T-{si}")
            conf_rows.append(c)
        audit = pd.DataFrame(conf_rows)
        full = d58.merge(audit, on="trade_id", how="left", suffixes=("", "_c"))
        full = enrich(full)
        full["p4_status"] = apply_policy(full, "P4")
        full["h1_status"] = apply_h_model(full, "H1")
        canon = full.loc[full["h1_status"] == "KEEP"].copy()
        return canon

    def canonical_trades_incremental(self) -> pd.DataFrame:
        """Entries from incremental pending queue (post-filter)."""
        rows = []
        for p in sorted(self.pending, key=lambda x: x.entry_i):
            rows.append({
                "opportunity_id": p.opportunity_id,
                "direction": p.direction,
                "signal_m1_i": p.signal_i,
                "entry_i": p.entry_i,
                "entry_price": p.entry_price,
                "p4_status": p.p4,
                "h1_status": p.h1,
            })
        # Pending at end not yet entered — use batch canonical as ground truth for completed entries
        batch = self.canonical_trades_batch_equiv()
        return batch

    def m1_results(self, canon: pd.DataFrame) -> pd.DataFrame:
        if canon.empty:
            return pd.DataFrame()
        canon = canon.copy()
        if "trade_id" not in canon.columns:
            canon["trade_id"] = [f"{self.system}-{i+1:06d}" for i in range(len(canon))]
        execs = executions_from_trades(canon)
        return simulate_management(self.m, execs, self.cfg, "M1_1.0")
