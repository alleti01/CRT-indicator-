"""Resume Phase53 from saved event_dataset.parquet."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import phase53.run as run  # noqa: E402
import pandas as pd  # noqa: E402
from phase53.config import RESULTS  # noqa: E402


def main() -> None:
    p = RESULTS / "event_dataset.parquet"
    if not p.exists():
        raise SystemExit("event_dataset.parquet missing — run phase53/run.py first")
    events = pd.read_parquet(p)
    # Patch run.main to skip generation — call analysis-only path
    original_load = None

    class _Skip:
        pass

    # Inline analysis from run.py starting at train split
    from phase53.run import main as full_main

    # Monkeypatch: inject preloaded events
    import phase53.run as rmod

    def _patched():
        t0 = __import__("time").time()
        RESULTS.mkdir(parents=True, exist_ok=True)
        events = pd.read_parquet(p)
        doc = __import__("json").loads((RESULTS / "research_manifest.json").read_text())["data"] if (RESULTS / "research_manifest.json").exists() else {}
        if not doc:
            from phase53.research.data import document_data, load_markets

            m1, m5, m15 = load_markets()
            doc = document_data(m1, m5, m15)
        rmod._run_analysis(events, doc, t0)

    if hasattr(rmod, "_run_analysis"):
        _patched()
    else:
        # Fallback: re-run full (slow)
        full_main()


if __name__ == "__main__":
    main()
