"""Build management variant specifications."""

from __future__ import annotations

import pandas as pd

from .config import PARTIAL_SCHEMES
from .entries import entry_index
from .simulate_mgmt import MgmtSpec, simulate_managed
from .stops import structure_target_price


def spec_m0() -> MgmtSpec:
    return MgmtSpec(name="M0")


def spec_fixed_target(target_r: float) -> MgmtSpec:
    return MgmtSpec(name=f"T_{target_r}R", target_mode="fixed_r", target_r=target_r)


def spec_structure_target(cap: tuple[float, float] | None = None) -> MgmtSpec:
    return MgmtSpec(name="Structure_Target", target_mode="structure", structure_target_cap=cap)


def spec_breakeven(trigger: float, dest: str) -> MgmtSpec:
    return MgmtSpec(name=f"BE_{trigger}_{dest}", be_trigger_r=trigger, be_dest=dest)


def spec_partial(scheme: str) -> MgmtSpec:
    return MgmtSpec(name=scheme, partials=list(PARTIAL_SCHEMES.get(scheme, [])))


def spec_trail(activate: float, method: str, param: float) -> MgmtSpec:
    return MgmtSpec(name=f"TR_{method}_{activate}", trail_activate_r=activate, trail_method=method, trail_param=param)


def spec_opposite_bos(min_r: float) -> MgmtSpec:
    return MgmtSpec(name=f"OppBOS_{min_r}", opposite_bos=True, opposite_bos_min_r=min_r)


def spec_time_exit(minutes: int) -> MgmtSpec:
    return MgmtSpec(name=f"TIME_{minutes}", time_exit_bars=minutes)


def spec_stagnation(rule: str, minutes: int = 10) -> MgmtSpec:
    return MgmtSpec(name=rule, stagnation=rule, stagnation_minutes=minutes)


def spec_profit_lock(trigger: float, lock_r: float) -> MgmtSpec:
    return MgmtSpec(name=f"PL_{trigger}_{lock_r}", profit_lock_trigger=trigger, profit_lock_r=lock_r)


def spec_15m_invalidation() -> MgmtSpec:
    return MgmtSpec(name="INV_15M", invalidation_15m=True)


def run_spec_on_entry(row: pd.Series, market: pd.DataFrame, spec: MgmtSpec, *, stop_px: float | None = None, tgt_px: float | None = None) -> dict:
    ei = int(row.get("entry_i", entry_index(market, row["entry_timestamp"])))
    entry = float(row["entry_price"])
    stop = float(stop_px if stop_px is not None else row["initial_stop"])
    target = float(tgt_px if tgt_px is not None else row["initial_target"])
    s = MgmtSpec(**spec.__dict__)
    if s.target_mode == "structure":
        risk = abs(entry - stop) or 1e-9
        st = structure_target_price(market, ei, entry, row["direction"], risk)
        s.target_price = st if st else target
    if s.invalidation_15m:
        s.phase44_entry = float(row.get("phase44_entry", entry))
    return simulate_managed(market, ei, entry, stop, target, row["direction"], row["signal_type"], s)
