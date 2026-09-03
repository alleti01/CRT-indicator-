#!/usr/bin/env python3
"""Phase73 production trader entry point."""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase73.config.loader import load_config
from phase73.replay.runner import ReplayRunner
from phase73.webhook.receiver import WebhookReceiver
from phase73.webhook.schemas import make_test_signal


def _cfg_with_trading(enabled: bool = True):
    cfg = load_config()
    raw = copy.deepcopy(cfg.raw)
    raw.setdefault("execution", {})["trading_enabled"] = enabled
    raw.setdefault("execution", {})["paper_mode"] = True
    from phase73.config.loader import Phase73Config

    return Phase73Config(raw=raw)


def mode_replay(args: argparse.Namespace) -> int:
    cfg = _cfg_with_trading(True)
    runner = ReplayRunner(cfg=cfg)
    bar = runner.provider.latest_bar()
    sig = make_test_signal(
        "SIGNAL_LONG",
        signal_bar_time_utc=bar.timestamp if bar else None,
        signal_time_utc=bar.timestamp if bar else None,
        signal_price=bar.close if bar else 20000.0,
    )
    print("Injecting test SIGNAL_LONG...")
    print(runner.inject_signal(sig))
    print(f"Running {args.bars} bars...")
    runner.run_bars(args.bars)
    print(f"Final state: {runner.engine.state.value}")
    print(f"Logs: {cfg.log_dir}")
    return 0


def mode_local_webhook(args: argparse.Namespace) -> int:
    cfg = _cfg_with_trading(True)
    runner = ReplayRunner(cfg=cfg)

    def on_signal(signal, reason):
        result = runner.engine.on_webhook_signal(signal, reason)
        print(f"Signal {signal.signal_id}: {result}")

    def on_reject(payload, reason, detail):
        print(f"Rejected {reason.value}: {detail}")

    receiver = WebhookReceiver(cfg, on_signal, on_reject)
    host = cfg.section("webhook").get("host", "127.0.0.1")
    port = int(cfg.section("webhook").get("port", 8787))
    receiver.start(host, port)
    print(f"Webhook listening on http://{host}:{port}/webhook")
    print("Press Ctrl+C to stop")
    try:
        import time

        while True:
            runner.run_bars(1)
            time.sleep(0.1)
    except KeyboardInterrupt:
        receiver.stop()
    return 0


def mode_paper(_args: argparse.Namespace) -> int:
    print("PHASE73: paper mode stub — broker adapter not connected")
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase73 production trader")
    ap.add_argument("--mode", choices=["replay", "local-webhook", "paper"], default="replay")
    ap.add_argument("--bars", type=int, default=120)
    args = ap.parse_args()
    if args.mode == "replay":
        return mode_replay(args)
    if args.mode == "local-webhook":
        return mode_local_webhook(args)
    return mode_paper(args)


if __name__ == "__main__":
    raise SystemExit(main())
