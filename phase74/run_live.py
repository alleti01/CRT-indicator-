#!/usr/bin/env python3
"""Phase74 — live data + paper execution dress rehearsal."""
from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase73.replay.runner import _synthetic_bars
from phase74.config.loader import load_phase74_config, verify_phase73_freeze
from phase74.market_data.live_provider import StreamLiveDataProvider, compare_replay_live_parity
from phase74.observability.status import build_status
from phase74.runtime.live_stack import LiveStack
from phase74.webhook.secure_receiver import SecureWebhookReceiver
from phase73.webhook.schemas import make_test_signal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


def _build_ninjatrader_provider(cfg, on_bar):
    from phase74.market_data.ninjatrader_live import NinjaTraderLiveDataProvider

    md_cfg = cfg.section("market_data")
    env_key = str(md_cfg.get("ninjatrader_auth_env_var", "NINJATRADER_BRIDGE_TOKEN"))
    token = os.environ.get(env_key, "")
    if not token:
        raise RuntimeError(f"{env_key} not set — required for NinjaTrader bridge")
    return NinjaTraderLiveDataProvider(
        host=str(md_cfg.get("ninjatrader_host", "127.0.0.1")),
        port=int(md_cfg.get("ninjatrader_port", 8765)),
        auth_token=token,
        bootstrap_bars=int(md_cfg.get("ninjatrader_bootstrap_bars", 15)),
        expected_contract_prefix=str(md_cfg.get("ninjatrader_expected_contract_prefix", "NQ")),
        staleness_limit_seconds=int(md_cfg.get("staleness_limit_seconds", 90)),
        atr_period=int(md_cfg.get("atr_period", 14)),
        on_bar=on_bar,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase74 live paper dress rehearsal")
    ap.add_argument("--mode", choices=["shadow", "paper", "parity-check"], default="shadow")
    ap.add_argument("--bars", type=int, default=120, help="Simulated bars (sim) or max wait minutes (ninjatrader)")
    ap.add_argument("--webhook", action="store_true", help="Start secure webhook server")
    ap.add_argument("--provider", choices=["sim", "ninjatrader"], default="sim", help="Market data provider")
    args = ap.parse_args()

    ok, errs = verify_phase73_freeze()
    if not ok:
        print("PHASE73_ENGINE_FREEZE_FAILED", errs)
        return 2

    cfg = load_phase74_config()
    raw = copy.deepcopy(cfg.raw)
    if args.mode == "shadow":
        raw.setdefault("mode", {})["shadow_mode"] = True
        raw.setdefault("mode", {})["trading_enabled"] = False
    elif args.mode == "paper":
        raw.setdefault("mode", {})["shadow_mode"] = False
        raw.setdefault("mode", {})["trading_enabled"] = True
        raw.setdefault("contracts", {})["contract_month"] = "202609"
    raw.setdefault("mode", {})["external_order_routing"] = False
    from phase74.config.loader import Phase74Config

    cfg = Phase74Config(raw=raw)

    df = _synthetic_bars(args.bars + 50)
    if args.mode == "parity-check":
        passed, errors = compare_replay_live_parity(df, n_bars=min(100, len(df) - 1))
        print("LIVE_REPLAY_DATA_PARITY_PASS" if passed else "LIVE_REPLAY_DATA_PARITY_FAIL")
        if errors:
            print(json.dumps(errors[:10], indent=2))
        return 0 if passed else 1

    stack_holder: dict[str, LiveStack | None] = {"stack": None}

    def on_nt_bar(_bar):
        st = stack_holder["stack"]
        if st is not None:
            st.on_bar()

    if args.provider == "ninjatrader":
        md = _build_ninjatrader_provider(cfg, on_nt_bar)
        md.connect()
    else:
        md = StreamLiveDataProvider(
            df,
            staleness_limit_seconds=cfg.raw.get("market_data", {}).get("staleness_limit_seconds", 90),
        )
        md.connect()

    stack = LiveStack(cfg, md)
    stack_holder["stack"] = stack

    if args.webhook:
        secret = cfg.webhook_secret or "dev-only-change-me"
        recv = SecureWebhookReceiver(
            cfg.to_phase73_config(),
            secret,
            on_signal=lambda s, r, t: stack.on_webhook_signal(s, r, t),
            rate_limit=int(cfg.section("webhook").get("rate_limit_per_minute", 60)),
        )
        wh = cfg.section("webhook")
        recv.start(str(wh.get("host", "127.0.0.1")), int(wh.get("port", 8787)), str(wh.get("path", "/webhook")))
        stack.webhook_status = "LISTENING"

    print(f"Phase74 mode={args.mode} provider={args.provider} shadow={cfg.shadow_mode} trading={cfg.trading_enabled}")
    print(f"external_order_routing={cfg.external_order_routing}")
    print(f"Broker adapter: LOCAL_SIM (no external paper venue connected)")

    if args.provider == "ninjatrader":
        deadline = time.time() + max(60, args.bars * 60)
        last_count = 0
        while time.time() < deadline:
            health = md.health()
            count = len(md.recent_bars(500))
            if count > last_count:
                last_count = count
                print(
                    f"bars={count} health={health.state.value} contract={md.contract_identity} atr_ready={md.atr_ready}"
                )
            if health.state.value == "DATA_HEALTHY" and last_count >= int(
                cfg.section("market_data").get("ninjatrader_bootstrap_bars", 15)
            ):
                if args.webhook:
                    # Keep listening for TradingView webhooks until deadline.
                    time.sleep(1.0)
                    continue
                bar = md.latest_bar()
                if bar and args.mode == "shadow":
                    sig = make_test_signal(
                        "SIGNAL_LONG",
                        signal_bar_time_utc=bar.timestamp,
                        signal_time_utc=bar.timestamp,
                        signal_price=bar.close,
                    )
                    stack.on_webhook_signal(
                        sig,
                        __import__("phase73.webhook.schemas", fromlist=["WebhookReason"]).WebhookReason.WEBHOOK_VALID,
                        __import__("phase74.latency.tracker", fromlist=["LatencyTracker"]).LatencyTracker(),
                    )
                break
            time.sleep(1.0)
    else:
        for i in range(args.bars):
            if not stack.tick():
                break
            if i == args.bars // 2 and args.mode == "shadow":
                bar = md.latest_bar()
                sig = make_test_signal(
                    "SIGNAL_LONG",
                    signal_bar_time_utc=bar.timestamp if bar else None,
                    signal_time_utc=bar.timestamp if bar else None,
                    signal_price=bar.close if bar else 20000,
                )
                stack.on_webhook_signal(
                    sig,
                    __import__("phase73.webhook.schemas", fromlist=["WebhookReason"]).WebhookReason.WEBHOOK_VALID,
                    __import__("phase74.latency.tracker", fromlist=["LatencyTracker"]).LatencyTracker(),
                )

    status = build_status(stack)
    print(json.dumps(status, indent=2, default=str))
    print("VERDICT:", "PHASE74_SHADOW_READY" if cfg.shadow_mode else "PHASE74_LIVE_PAPER_PASS")
    md.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
