"""Online causal opportunity memory — no future outcomes."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class OppState(str, Enum):
    WATCH = "WATCH"
    DETECTED = "DETECTED"
    ARMED = "ARMED"
    REACTION_DEVELOPING = "REACTION_DEVELOPING"
    TAKE = "TAKE"
    WAIT = "WAIT"
    PASS = "PASS"
    IN_TRADE = "IN_TRADE"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    RESET = "RESET"


@dataclass
class OpportunityState:
    opportunity_id: str
    direction: str
    created_i: int
    created_price: float
    state: OppState = OppState.DETECTED
    last_update_i: int = 0
    armed_i: int = -1
    armed_price: float = 0.0
    take_i: int = -1
    pass_i: int = -1
    invalidated_i: int = -1
    signal_count: int = 0
    update_count: int = 0
    traded: bool = False
    location_score: int = 0
    direction_score: int = 0
    reaction_score: int = 0
    total_evidence: int = 0
    max_evidence: int = 0
    ctx15_state: str = "NEUTRAL"
    ctx5_dir: str = "NEUTRAL"
    reason_history: list[str] = field(default_factory=list)
    running_high: float = 0.0
    running_low: float = 0.0
    wait_bars: int = 0


class OpportunityMemory:
    """Online memory — matches Phase58C structural clustering causally."""

    def __init__(self, structural_gap: int = 30, expire_bars: int = 45):
        self.structural_gap = structural_gap
        self.expire_bars = expire_bars
        self._counter = 0
        self.active: dict[str, OpportunityState] = {}
        self.all_opps: list[OpportunityState] = []
        self.updates: list[dict] = []
        # Global stream state — mirrors offline cluster_1m_opportunities
        self._cur_dir = ""
        self._cur_last_si = -1
        self._cur_start_si = -1
        self._cur_opp_id = ""

    def _new_id(self, start_i: int, direction: str) -> str:
        self._counter += 1
        return f"OPP_{start_i:08d}_{direction}"

    def match_or_create(self, i: int, price: float, direction: str, **kwargs) -> tuple[OpportunityState, bool]:
        """Returns (opportunity, is_new)."""
        is_new = False
        if not self._cur_opp_id:
            is_new = True
        elif direction != self._cur_dir:
            is_new = True
        elif i - self._cur_last_si > self.structural_gap:
            is_new = True

        if is_new:
            oid = self._new_id(i, direction)
            opp = OpportunityState(
                opportunity_id=oid,
                direction=direction,
                created_i=i,
                created_price=price,
                last_update_i=i,
                armed_i=i,
                armed_price=price,
                state=OppState.DETECTED,
                signal_count=1,
                running_high=price,
                running_low=price,
                reason_history=["NEW_OPPORTUNITY"],
                **{k: v for k, v in kwargs.items() if k in OpportunityState.__dataclass_fields__},
            )
            self.active[oid] = opp
            self.all_opps.append(opp)
            self._cur_dir = direction
            self._cur_start_si = i
            self._cur_opp_id = oid
            self._cur_last_si = i
            self.updates.append({"opportunity_id": oid, "bar_i": i, "event": "NEW", "direction": direction})
            return opp, True

        oid = self._cur_opp_id
        opp = self.active.get(oid)
        if opp is None:
            # Expired but same cluster window — revive tracking without new ID
            opp = next((o for o in reversed(self.all_opps) if o.opportunity_id == oid), None)
            if opp is None:
                return self.match_or_create(i, price, direction, **kwargs)
            self.active[oid] = opp

        opp.signal_count += 1
        opp.update_count += 1
        opp.last_update_i = i
        opp.running_high = max(opp.running_high, price)
        opp.running_low = min(opp.running_low, price) if opp.running_low else price
        opp.reason_history.append("SAME_OPPORTUNITY_UPDATE")
        self._cur_last_si = i
        self.updates.append({"opportunity_id": oid, "bar_i": i, "event": "UPDATE", "direction": direction})
        return opp, False

    def invalidate(self, oid: str, i: int, reason: str) -> None:
        if oid in self.active:
            opp = self.active[oid]
            opp.state = OppState.INVALIDATED
            opp.invalidated_i = i
            opp.reason_history.append(reason)
            del self.active[oid]

    def expire_stale(self, i: int) -> None:
        stale = [oid for oid, o in self.active.items() if i - o.last_update_i > self.expire_bars and not o.traded]
        for oid in stale:
            self.active[oid].state = OppState.EXPIRED
            del self.active[oid]

    def mark_traded(self, oid: str, i: int) -> None:
        opp = self.active.get(oid)
        if opp is None:
            opp = next((o for o in self.all_opps if o.opportunity_id == oid), None)
        if opp is not None:
            opp.traded = True
            opp.state = OppState.IN_TRADE
            opp.take_i = i
        if oid in self.active:
            del self.active[oid]

    def reset_opposite(self, direction: str, i: int) -> None:
        opp_dir = "SHORT" if direction == "LONG" else "LONG"
        if self._cur_dir == opp_dir and self._cur_opp_id in self.active:
            self.invalidate(self._cur_opp_id, i, "STRUCTURAL_RESET_OPPOSITE")
