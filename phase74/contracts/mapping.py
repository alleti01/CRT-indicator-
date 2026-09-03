"""Contract symbol mapping — explicit, no silent inference."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContractSpec:
    pine_symbol: str
    market_data_symbol: str
    broker_symbol: str
    contract_month: str
    multiplier: float
    tick_size: float
    tick_value: float
    default_quantity: int = 1

    def resolve_broker_price(self, price: float) -> float:
        ticks = round(price / self.tick_size)
        return ticks * self.tick_size

    def slippage_ticks(self, signal_price: float, fill_price: float) -> float:
        return (fill_price - signal_price) / self.tick_size


def load_contract_spec(cfg: dict[str, Any]) -> ContractSpec:
    c = cfg.get("contracts", {})
    month = str(c.get("contract_month", ""))
    if not month:
        # explicit unresolved — caller must set contract_month for live orders
        month = "UNRESOLVED"
    return ContractSpec(
        pine_symbol=str(c.get("pine_symbol", "NQ")),
        market_data_symbol=str(c.get("market_data_symbol", "NQ.v.0")),
        broker_symbol=str(c.get("broker_symbol", "NQ")),
        contract_month=month,
        multiplier=float(c.get("multiplier", 2.0)),
        tick_size=float(c.get("tick_size", 0.25)),
        tick_value=float(c.get("tick_value", 0.5)),
        default_quantity=int(c.get("default_quantity", 1)),
    )


def validate_contract_for_order(spec: ContractSpec) -> str | None:
    if spec.contract_month in ("", "UNRESOLVED"):
        return "CONTRACT_MAPPING_UNRESOLVED"
    return None
