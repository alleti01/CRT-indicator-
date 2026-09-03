"""Research experiment registry."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from phase57d.config import RESULTS
from phase57d.research.schema import RESEARCH_REGISTRY_COLUMNS


def load_registry() -> pd.DataFrame:
    path = RESULTS / "research_registry.csv"
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame(columns=RESEARCH_REGISTRY_COLUMNS)


def register_experiment(
    experiment_id: str,
    wall_family: str,
    interaction: str,
    mapping: str,
    expiration_scope: str,
    entry_stage: str,
    status: str,
    notes: str = "",
    raw_n: int = 0,
    distinct_n: int = 0,
    avg_r: float = float("nan"),
    pf: float = float("nan"),
) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    reg = load_registry()
    row = {
        "experiment_id": experiment_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wall_family": wall_family,
        "interaction": interaction,
        "mapping": mapping,
        "expiration_scope": expiration_scope,
        "entry_stage": entry_stage,
        "status": status,
        "raw_n": raw_n,
        "distinct_n": distinct_n,
        "avg_r": avg_r,
        "pf": pf,
        "notes": notes,
    }
    reg = pd.concat([reg, pd.DataFrame([row])], ignore_index=True)
    reg.to_csv(RESULTS / "research_registry.csv", index=False)
