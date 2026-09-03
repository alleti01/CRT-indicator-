"""Phase73 test helpers."""
from __future__ import annotations

import copy
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

from phase73.config.loader import Phase73Config, load_config
from phase73.replay.runner import ReplayRunner, _synthetic_bars
from phase73.webhook.schemas import make_test_signal, PineSignal, WebhookReason
from phase73.webhook.validator import validate_webhook_payload
from phase73.webhook.deduplicator import SignalDeduplicator
from phase73.webhook.receiver import WebhookReceiver
from phase73.market_data.cache import BarCache
from phase73.market_data.bar import Bar
from phase73.market_data.provider import ReplayDataProvider
from phase73.execution.orders import Order, OrderSide
from phase73.execution.positions import PositionBook, PositionSnapshot
from phase73.execution.sim_router import SimOrderRouter
from phase73.trader.management import build_management, evaluate_exit
from phase73.trader.engine import TraderEngine
from phase73.logging.decision_logger import DecisionLogger
from phase73.logging.event_store import EventStore
from phase73.persistence.state import StatePersistence
from phase73.risk.reconciliation import reconcile


def test_cfg(**overrides) -> Phase73Config:
    raw = copy.deepcopy(load_config().raw)
    raw.setdefault("execution", {})["trading_enabled"] = True
    raw.setdefault("execution", {})["paper_mode"] = True
    for k, v in overrides.items():
        if "." in k:
            section, key = k.split(".", 1)
            raw.setdefault(section, {})[key] = v
        else:
            raw[k] = v
    return Phase73Config(raw=raw)


def temp_runner(n_bars: int = 200, **cfg_overrides) -> tuple[ReplayRunner, tempfile.TemporaryDirectory]:
    td = tempfile.TemporaryDirectory()
    log_dir = Path(td.name) / "logs"
    cfg = test_cfg(**{f"logging.log_dir": str(log_dir), f"persistence.state_file": str(log_dir / "state.json"), **cfg_overrides})
    df = _synthetic_bars(n_bars)
    return ReplayRunner(cfg=cfg, df=df, log_dir=log_dir), td
