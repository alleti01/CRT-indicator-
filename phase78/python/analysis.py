"""Random direction, ablation helpers, splits."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .config import MIN_EFFECT_FP11, MIN_N_ENTRIES, RANDOM_SEED_COUNT, RANDOM_SEED_START, TRAIN_FRAC, VAL_FRAC


def deterministic_flip(direction: str) -> str:
    return "SHORT" if direction == "LONG" else "LONG"


def random_directions(entry_id: str, n: int = RANDOM_SEED_COUNT) -> list[str]:
    out = []
    for seed in range(RANDOM_SEED_START, RANDOM_SEED_START + n):
        h = hashlib.sha256(f"{entry_id}|{seed}".encode()).hexdigest()
        out.append("LONG" if int(h[:8], 16) % 2 == 0 else "SHORT")
    return out


def fp_rate(results: pd.Series) -> float:
    return float(results.mean()) if len(results) else np.nan


def directional_gate(real_fp: float, random_fps: list[float], flipped_fp: float) -> dict:
    rand_mean = float(np.mean(random_fps)) if random_fps else np.nan
    rand_p95 = float(np.percentile(random_fps, 95)) if random_fps else np.nan
    pass_random = bool(np.isfinite(real_fp) and np.isfinite(rand_mean) and real_fp >= rand_mean + MIN_EFFECT_FP11)
    pass_flip = bool(np.isfinite(real_fp) and np.isfinite(flipped_fp) and real_fp > flipped_fp + MIN_EFFECT_FP11)
    percentile = float(np.mean([r <= real_fp for r in random_fps])) if random_fps else np.nan
    return {
        "real_fp": real_fp,
        "random_mean_fp": rand_mean,
        "random_p95_fp": rand_p95,
        "flipped_fp": flipped_fp,
        "real_percentile_among_random": percentile,
        "pass_random": pass_random,
        "pass_flip": pass_flip,
        "pass": pass_random and pass_flip and len(random_fps) > 0,
    }


def chronological_splits(n: int) -> tuple[slice, slice, slice]:
    train_end = int(n * TRAIN_FRAC)
    val_end = int(n * (TRAIN_FRAC + VAL_FRAC))
    return slice(0, train_end), slice(train_end, val_end), slice(val_end, n)


def summary_stats(outcomes: pd.Series) -> dict:
    if len(outcomes) == 0:
        return {"n": 0, "avg_r": np.nan, "pf": np.nan, "win_rate": np.nan}
    wins = outcomes[outcomes > 0]
    losses = outcomes[outcomes < 0]
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else np.nan
    return {
        "n": len(outcomes),
        "avg_r": float(outcomes.mean()),
        "pf": pf,
        "win_rate": float((outcomes > 0).mean()),
    }
