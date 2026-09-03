"""Phase66 — causal local levels at observation bar."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CausalLevels:
    alarm_i: int
    eval_i: int
    origin: float
    alarm_hi: float
    alarm_lo: float
    hi_3: float
    lo_3: float
    hi_5: float
    lo_5: float
    hi_10: float
    lo_10: float


def build_levels(m, alarm_i: int, eval_i: int) -> CausalLevels:
    """Levels known at eval_i bar close. Micro highs/lows EXCLUDE eval_i bar."""
    s3 = max(0, eval_i - 3)
    s5 = max(0, eval_i - 5)
    s10 = max(0, eval_i - 10)
    # Prior bars only for break/rejection references
    hi_3 = float(m.hi[s3:eval_i].max()) if eval_i > s3 else float(m.hi[alarm_i])
    lo_3 = float(m.lo[s3:eval_i].min()) if eval_i > s3 else float(m.lo[alarm_i])
    hi_5 = float(m.hi[s5:eval_i].max()) if eval_i > s5 else float(m.hi[alarm_i])
    lo_5 = float(m.lo[s5:eval_i].min()) if eval_i > s5 else float(m.lo[alarm_i])
    hi_10 = float(m.hi[s10:eval_i].max()) if eval_i > s10 else float(m.hi[alarm_i])
    lo_10 = float(m.lo[s10:eval_i].min()) if eval_i > s10 else float(m.lo[alarm_i])
    return CausalLevels(
        alarm_i=alarm_i,
        eval_i=eval_i,
        origin=float(m.op[alarm_i]),
        alarm_hi=float(m.hi[alarm_i]),
        alarm_lo=float(m.lo[alarm_i]),
        hi_3=hi_3, lo_3=lo_3, hi_5=hi_5, lo_5=lo_5, hi_10=hi_10, lo_10=lo_10,
    )
