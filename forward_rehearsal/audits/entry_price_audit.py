"""Shadow entry price observational audit — no threshold tuning."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class EntryPriceObservation:
    signal_id: str
    pine_signal_price: float
    market_price_at_webhook: float
    market_price_at_decision: float
    next_tradable_price: float | None
    signal_to_decision_points: float
    signal_to_decision_atr: float
    estimated_slippage_points: float
    atr: float
    timestamp_utc: str


@dataclass
class EntryPriceAuditor:
    observations: list[EntryPriceObservation] = field(default_factory=list)

    def record(
        self,
        *,
        signal_id: str,
        pine_signal_price: float,
        market_price_at_webhook: float,
        market_price_at_decision: float,
        next_tradable_price: float | None,
        atr: float,
        when: datetime,
    ) -> EntryPriceObservation:
        move = market_price_at_decision - pine_signal_price
        atr_norm = move / atr if atr else 0.0
        slip = (market_price_at_decision - pine_signal_price) if market_price_at_decision else 0.0
        obs = EntryPriceObservation(
            signal_id=signal_id,
            pine_signal_price=pine_signal_price,
            market_price_at_webhook=market_price_at_webhook,
            market_price_at_decision=market_price_at_decision,
            next_tradable_price=next_tradable_price,
            signal_to_decision_points=move,
            signal_to_decision_atr=atr_norm,
            estimated_slippage_points=slip,
            atr=atr,
            timestamp_utc=when.isoformat(),
        )
        self.observations.append(obs)
        return obs

    def write_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = [f.name for f in EntryPriceObservation.__dataclass_fields__.values()]  # type: ignore[attr-defined]
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for obs in self.observations:
                w.writerow(obs.__dict__)

    def summary(self) -> dict[str, Any]:
        if not self.observations:
            return {"count": 0}
        moves = [abs(o.signal_to_decision_atr) for o in self.observations]
        return {
            "count": len(self.observations),
            "median_atr_move": sorted(moves)[len(moves) // 2],
            "max_atr_move": max(moves),
        }
