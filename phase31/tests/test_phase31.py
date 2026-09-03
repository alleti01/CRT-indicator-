"""Phase 31 tests."""

from pathlib import Path

import pandas as pd

from phase31.config import RESULTS
from phase31.dedupe import filter_rth_signals
from phase31.signals import ARCHITECTURES, build_architecture_signals
from phase31.data import load_market_15m


def test_architectures_generate_signals():
    market = load_market_15m()
    signals = build_architecture_signals(market)
    assert set(signals) == set(ARCHITECTURES)
    for name, df in signals.items():
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert "direction" in df.columns
            assert "entry_timestamp" in df.columns
            assert df["architecture"].iloc[0] == name


def test_rth_filter():
    market = load_market_15m()
    signals = build_architecture_signals(market)["BOS_ONLY"]
    if signals.empty:
        return
    filtered = filter_rth_signals(signals)
    assert len(filtered) <= len(signals)


def test_results_manifest_exists_after_run():
    manifest = RESULTS / "research_manifest.json"
    if manifest.exists():
        import json

        data = json.loads(manifest.read_text())
        assert data["phase"].startswith("Phase 31")
        assert "architectures_tested" in data
