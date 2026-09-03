"""Phase 49 market loaders — development + forward with firewall."""

from __future__ import annotations

import pandas as pd

from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import add_base_indicators, pine_sma
from phase31.config import frozen_config_15m
from phase36.data import load_replay_market_15m
from phase45.execution.data_1m import load_market_1m

from phase49.config import TIMEZONE

from .firewall import (
    assert_development_only,
    assert_forward_only,
    assert_no_overlap,
    assert_research_safe,
    development_cutoff_ts,
    forward_start_ts,
    split_development_forward,
)
from .ingest import ingest_forward_data
from .paths import BRIDGE_1M_SOURCES, FORWARD_15M_PROCESSED, FORWARD_1M_PROCESSED


def _load_bridge_1m() -> pd.DataFrame:
    """Load pre-forward bridge 1m bars (includes cutoff-adjacent gap fill)."""
    parts: list[pd.DataFrame] = []
    for source in BRIDGE_1M_SOURCES:
        if source.is_file():
            parts.append(load_ohlcv_csv(str(source), source_timezone="UTC"))
        elif source.is_dir():
            for path in sorted(source.glob("*.csv")):
                parts.append(load_ohlcv_csv(str(path), source_timezone="UTC"))
    if not parts:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    bridge = pd.concat(parts).sort_index()
    bridge = bridge[~bridge.index.duplicated(keep="last")]
    bridge = bridge.loc[bridge.index < forward_start_ts()]
    assert_development_only(bridge)
    return bridge


def _attach_1m_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    atr = (out["high"] - out["low"]).rolling(14).mean()
    out["atr"] = atr
    vol_sma = pine_sma(out["volume"].astype(float), 20)
    out["rel_volume"] = out["volume"].astype(float) / vol_sma.replace(0, pd.NA)
    out["vol_ma5"] = out["volume"].astype(float).rolling(5).mean()
    return out


def load_development_1m() -> pd.DataFrame:
    """Development-only 1m bars for parity-safe research paths (<= cutoff)."""
    base = load_market_1m()
    bridge = _load_bridge_1m()
    if bridge.empty:
        df = base
    else:
        df = pd.concat([base, bridge]).sort_index()
        df = df[~df.index.duplicated(keep="last")]
    df = df.loc[df.index <= development_cutoff_ts()]
    assert_research_safe(df)
    return _attach_1m_features(df)


def load_pre_forward_1m() -> pd.DataFrame:
    """All 1m bars strictly before forward_start (includes cutoff-adjacent bridge)."""
    base = load_market_1m()
    bridge = _load_bridge_1m()
    if bridge.empty:
        df = base
    else:
        df = pd.concat([base, bridge]).sort_index()
        df = df[~df.index.duplicated(keep="last")]
    df = df.loc[df.index < forward_start_ts()]
    assert_development_only(df)
    return _attach_1m_features(df)


def load_forward_1m(*, ingest: bool = True) -> pd.DataFrame:
    if ingest:
        ingest_forward_data()
    if not FORWARD_1M_PROCESSED.exists() or FORWARD_1M_PROCESSED.stat().st_size <= 60:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    raw = pd.read_csv(FORWARD_1M_PROCESSED)
    if raw.empty or "timestamp" not in raw.columns:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    fwd = load_ohlcv_csv(str(FORWARD_1M_PROCESSED), source_timezone=TIMEZONE)
    assert_forward_only(fwd)
    return _attach_1m_features(fwd)


def load_market_1m_phase49(*, ingest: bool = True) -> pd.DataFrame:
    """Stitched pre-forward + forward 1m for Phase 49 forward validation."""
    dev = load_pre_forward_1m()
    fwd = load_forward_1m(ingest=ingest)
    if fwd.empty:
        return dev
    assert_no_overlap(dev, fwd)
    combined = pd.concat([dev, fwd]).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    return _attach_1m_features(combined)


def load_forward_15m(*, ingest: bool = True) -> pd.DataFrame:
    if ingest:
        ingest_forward_data()
    if not FORWARD_15M_PROCESSED.exists() or FORWARD_15M_PROCESSED.stat().st_size <= 60:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    raw = pd.read_csv(FORWARD_15M_PROCESSED)
    if raw.empty or "timestamp" not in raw.columns:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    fwd = load_ohlcv_csv(str(FORWARD_15M_PROCESSED), source_timezone=TIMEZONE)
    assert_forward_only(fwd)
    return add_base_indicators(fwd, frozen_config_15m())


def load_market_15m_phase49(*, ingest: bool = True) -> pd.DataFrame:
    """Replay development 15m + forward 15m derived from forward 1m."""
    dev = load_replay_market_15m()
    dev = dev.loc[dev.index <= development_cutoff_ts()]
    assert_development_only(dev)
    fwd = load_forward_15m(ingest=ingest)
    if fwd.empty:
        return dev
    assert_no_overlap(dev, fwd)
    combined = pd.concat([dev, fwd]).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined


def verify_research_loaders_firewalled() -> None:
    """Ensure default Phase45 research loader cannot see forward rows."""
    research = load_market_1m()
    assert_research_safe(research.loc[research.index <= development_cutoff_ts()])
