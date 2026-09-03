"""Phase69B — partial runner simulation on TRUE_2P5 winners only."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from phase58.research.instrument import NQ
from phase69a.python.path_engine import PathResult, walk_path

M0_TARGET_R = 2.5


@dataclass(frozen=True)
class RunnerConfig:
    split: str
    main_frac: float
    runner_frac: float
    protection_r: float
    runner_target_r: float
    max_hold: int = 60
    optional: bool = False

    @property
    def config_id(self) -> str:
        return f"{self.split}_{self.protection_r:g}R_{self.runner_target_r:g}R_h{self.max_hold}"


def primary_configs(include_optional: bool = True) -> list[RunnerConfig]:
    cfgs: list[RunnerConfig] = []
    for split, mf, rf in [("80/20", 0.80, 0.20), ("75/25", 0.75, 0.25)]:
        for prot in (1.5, 2.0):
            for tgt in (4.0, 5.0, 7.0):
                cfgs.append(RunnerConfig(split, mf, rf, prot, tgt, 60))
    if include_optional:
        for prot in (1.5, 2.0):
            for tgt in (4.0, 5.0, 7.0):
                cfgs.append(RunnerConfig("67/33", 0.67, 0.33, prot, tgt, 60, optional=True))
    return cfgs


def m0_cost(ep: float, risk: float, mult: float = 1.0) -> float:
    return NQ.cost_r(ep, risk, mult)


def partial_cost(ep: float, risk: float, mult: float = 1.0) -> float:
    """Entry + partial exit + runner exit ≈ 1.5× round-turn in R."""
    return m0_cost(ep, risk, mult) * 1.5


def simulate_runner_on_path(
    pr: PathResult,
    hi, lo, cl,
    cfg: RunnerConfig,
    cost_mult: float = 1.0,
) -> dict:
    ep, risk = pr.entry_price, pr.risk
    d = 1 if pr.direction == "LONG" else -1

    if not pr.true_2p5_winner or pr.t_2p5_bar is None:
        gross = pr.m0_gross_r
        cost = m0_cost(ep, risk, cost_mult)
        return _pack(pr, gross, cost, "M0", pr.m0_exit_bar, pr.m0_gross_r, None, None, None)

    t0 = pr.t_2p5_bar
    n = len(hi)
    end_bar = min(pr.entry_i + cfg.max_hold, n - 1)
    prot_px = ep + d * cfg.protection_r * risk
    tgt_px = ep + d * cfg.runner_target_r * risk

    runner_exit_r: Optional[float] = None
    runner_reason = "RUNNER_TIMEOUT"
    exit_bar = end_bar

    for k in range(t0, end_bar + 1):
        h, l = float(hi[k]), float(lo[k])
        hit_tgt = (h >= tgt_px) if d == 1 else (l <= tgt_px)
        hit_prot = (l <= prot_px) if d == 1 else (h >= prot_px)
        if hit_tgt and hit_prot:
            runner_exit_r = cfg.protection_r
            runner_reason = "RUNNER_PROTECTION"
            exit_bar = k
            break
        if hit_prot:
            runner_exit_r = cfg.protection_r
            runner_reason = "RUNNER_PROTECTION"
            exit_bar = k
            break
        if hit_tgt:
            runner_exit_r = cfg.runner_target_r
            runner_reason = "RUNNER_TARGET"
            exit_bar = k
            break

    if runner_exit_r is None:
        c = float(cl[end_bar])
        runner_exit_r = (c - ep) * d / risk
        runner_reason = "RUNNER_TIMEOUT"
        exit_bar = end_bar

    partial_r = cfg.main_frac * M0_TARGET_R
    gross = partial_r + cfg.runner_frac * runner_exit_r
    cost = partial_cost(ep, risk, cost_mult)

    return _pack(
        pr, gross, cost, runner_reason, exit_bar, pr.m0_gross_r,
        runner_exit_r, cfg.protection_r, cfg.runner_target_r,
        partial_r=partial_r, t_2p5=t0,
    )


def _pack(
    pr, gross, cost, reason, exit_bar, m0_gross, runner_exit_r,
    prot_r, tgt_r, partial_r=None, t_2p5=None,
) -> dict:
    net = gross - cost
    m0_cost_v = m0_cost(pr.entry_price, pr.risk)
    m0_net = m0_gross - m0_cost_v
    inc_gross = gross - m0_gross if pr.true_2p5_winner else 0.0
    inc_net = net - m0_net if pr.true_2p5_winner else 0.0
    return {
        "trade_id": pr.trade_id,
        "direction": pr.direction,
        "entry_i": pr.entry_i,
        "entry_ts": pr.entry_ts,
        "entry_price": pr.entry_price,
        "atr": pr.atr,
        "risk": pr.risk,
        "true_2p5_winner": pr.true_2p5_winner,
        "t_2p5_bar": t_2p5 or pr.t_2p5_bar,
        "exit_i": exit_bar,
        "duration": exit_bar - pr.entry_i,
        "gross_R": gross,
        "cost_R": cost,
        "net_R": net,
        "exit_reason": reason,
        "m0_gross_R": m0_gross,
        "m0_net_R": m0_net,
        "m0_cost_R": m0_cost_v,
        "incremental_gross_R": inc_gross,
        "incremental_net_R": inc_net,
        "incremental_cost_R": cost - m0_cost_v if pr.true_2p5_winner else 0.0,
        "partial_r": partial_r,
        "runner_exit_r": runner_exit_r,
        "runner_protection_r": prot_r,
        "runner_target_r": tgt_r,
    }


def simulate_config(
    paths: list[PathResult],
    hi, lo, cl,
    cfg: RunnerConfig,
    cost_mult: float = 1.0,
) -> list[dict]:
    return [simulate_runner_on_path(pr, hi, lo, cl, cfg, cost_mult) for pr in paths]


def precompute_paths(execs, m) -> list[PathResult]:
    paths = []
    for _, ex in execs.iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 65:
            continue
        paths.append(walk_path(
            ex["trade_id"], ex["direction"], ei,
            float(ex["entry_price"]), float(ex["atr_entry"]),
            m.hi, m.lo, m.cl, m.op, entry_ts=ex["entry_ts"],
        ))
    return paths


def classify_winner_outcome(row: dict) -> str:
    if not row["true_2p5_winner"]:
        return "N/A"
    g = row["gross_R"]
    if g > M0_TARGET_R + 0.01:
        return "RUNNER_ADDS_PROFIT"
    if g >= M0_TARGET_R - 0.01:
        return "RUNNER_SAME"
    if g >= 2.0:
        return "RUNNER_GIVES_BACK_SMALL"
    return "RUNNER_GIVES_BACK_LARGE"


def regret_bucket(row: dict) -> str:
    if not row["true_2p5_winner"]:
        return "N/A"
    g = row["gross_R"]
    if g > M0_TARGET_R:
        return "M0_2P5_runner_gt_2P5"
    if g >= 2.25:
        return "M0_2P5_runner_2P25_2P5"
    if g >= 2.0:
        return "M0_2P5_runner_2P0_2P25"
    return "M0_2P5_runner_lt_2P0"


def one_position_filter(trades: list[dict]) -> tuple[list[dict], int]:
    """Take trades sequentially; skip if prior runner still open."""
    taken, skipped = [], 0
    last_exit = -1
    for t in sorted(trades, key=lambda x: (x["entry_i"], x["trade_id"])):
        if t["entry_i"] <= last_exit:
            skipped += 1
            continue
        taken.append(t)
        last_exit = t["exit_i"]
    return taken, skipped


def attribution(trades: list[dict]) -> dict:
    extra_profit = giveback = extra_cost = 0.0
    for t in trades:
        if not t["true_2p5_winner"]:
            continue
        inc_g = t["incremental_gross_R"]
        if inc_g > 0:
            extra_profit += inc_g
        elif inc_g < 0:
            giveback += -inc_g
        extra_cost += t["incremental_cost_R"]
    m0_total = sum(t["m0_net_R"] for t in trades)
    cand_total = sum(t["net_R"] for t in trades)
    net_inc = cand_total - m0_total
    residual = net_inc - (extra_profit - giveback - extra_cost)
    return {
        "m0_totalR": m0_total,
        "candidate_totalR": cand_total,
        "runner_extra_profit": extra_profit,
        "runner_giveback": giveback,
        "extra_transaction_cost": extra_cost,
        "net_increment": net_inc,
        "residual": residual,
    }


def bootstrap_ci(deltas: np.ndarray, n_boot: int = 2000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    deltas = np.asarray(deltas, dtype=float)
    if len(deltas) == 0:
        return {}
    boots_avg, boots_tot = [], []
    for _ in range(n_boot):
        s = rng.choice(deltas, size=len(deltas), replace=True)
        boots_avg.append(float(s.mean()))
        boots_tot.append(float(s.sum()))
    return {
        "avgR_ci_lo": float(np.quantile(boots_avg, 0.025)),
        "avgR_ci_hi": float(np.quantile(boots_avg, 0.975)),
        "totalR_ci_lo": float(np.quantile(boots_tot, 0.025)),
        "totalR_ci_hi": float(np.quantile(boots_tot, 0.975)),
    }
