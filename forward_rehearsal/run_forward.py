#!/usr/bin/env python3
"""Forward rehearsal — Shadow → Local Paper → External Paper."""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forward_rehearsal.freeze import verify_manifest, write_manifest
from forward_rehearsal.market_data.databento_live import DatabentoLiveProvider
from forward_rehearsal.runtime.forward_session import (
    ForwardSession,
    load_forward_config,
    shadow_gate_passed,
)
from phase73.replay.runner import _synthetic_bars
from phase74.market_data.live_provider import StreamLiveDataProvider
from phase74.runtime.live_stack import LiveStack

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("forward.run")


def _build_market_data(cfg, *, use_databento: bool, on_bar=None):
    md_cfg = cfg.section("market_data")
    if use_databento:
        return DatabentoLiveProvider(
            dataset=str(md_cfg.get("databento_dataset", "GLBX.MDP3")),
            schema=str(md_cfg.get("databento_schema", "ohlcv-1m")),
            symbol=str(md_cfg.get("databento_symbol", "NQ.v.0")),
            staleness_limit_seconds=int(md_cfg.get("staleness_limit_seconds", 90)),
            on_bar=on_bar,
        )
    df = _synthetic_bars(500)
    stream = StreamLiveDataProvider(df, staleness_limit_seconds=int(md_cfg.get("staleness_limit_seconds", 90)))
    stream.connect()
    return stream


def main() -> int:
    ap = argparse.ArgumentParser(description="Forward rehearsal runner")
    ap.add_argument("--stage", choices=["shadow", "local-paper", "infra-test"], default="shadow")
    ap.add_argument("--duration-minutes", type=int, default=0, help="0 = run until interrupted")
    ap.add_argument("--max-seconds", type=int, default=0, help="Alternative stop after N seconds")
    ap.add_argument("--verify-freeze", action="store_true", help="Verify FREEZE_MANIFEST and exit")
    ap.add_argument("--write-freeze", action="store_true", help="Regenerate FREEZE_MANIFEST.json")
    ap.add_argument("--use-databento", action="store_true", help="Use Databento live (requires DATABENTO_API_KEY)")
    ap.add_argument("--restart-test", action="store_true", help="Simulate restart during session")
    ap.add_argument("--disconnect-test", action="store_true", help="Simulate data/webhook disconnect")
    ap.add_argument("--finalize-only", type=str, help="Finalize existing session_id")
    args = ap.parse_args()

    if args.write_freeze:
        manifest = write_manifest()
        print(json.dumps({"ok": True, "pine_sha256": manifest["pine"]["sha256"]}, indent=2))
        return 0

    ok, errs = verify_manifest()
    if not ok:
        print("FREEZE_MANIFEST_MISMATCH", errs)
        return 2
    if args.verify_freeze:
        print("FREEZE_MANIFEST_OK")
        return 0

    if args.stage == "local-paper" and not shadow_gate_passed():
        print("BLOCKED: FORWARD_SHADOW_PASS gate not set. Complete Stage A shadow rehearsal first.")
        print("Run shadow session, then: forward_rehearsal/gates/FORWARD_SHADOW_PASS will be written on pass.")
        return 3

    cfg = load_forward_config(args.stage)
    allow_synthetic = args.stage == "infra-test"

    session_holder: dict = {}

    def on_bar(bar):
        sess = session_holder.get("session")
        if sess:
            sess.on_closed_bar()

    md = _build_market_data(cfg, use_databento=args.use_databento, on_bar=on_bar if args.use_databento else None)
    if not args.use_databento:
        md.connect()

    stack = LiveStack(cfg, md)
    session = ForwardSession(cfg, stack, stage=args.stage, allow_synthetic=allow_synthetic)
    session_holder["session"] = session

    secret = cfg.webhook_secret
    if not secret and args.stage != "infra-test":
        log.warning("PHASE74_WEBHOOK_SECRET not set — webhook server not started")
    elif secret:
        session.start_webhook(secret)

    stop = False

    def _handle_sig(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    print(f"FORWARD REHEARSAL stage={args.stage} session={session.session_id}")
    print(f"  data={'Databento live' if args.use_databento else 'simulated stream (infra only)'}")
    print(f"  synthetic_allowed={allow_synthetic}")
    print(f"  session_dir={session.session_dir}")

    started = time.time()
    restart_done = False
    disconnect_done = False

    try:
        while not stop:
            if args.duration_minutes and (time.time() - started) > args.duration_minutes * 60:
                break
            if args.max_seconds and (time.time() - started) > args.max_seconds:
                break

            if args.restart_test and not restart_done and (time.time() - started) > 5:
                session.persist_checkpoint()
                session.simulate_disconnect("data")
                time.sleep(1)
                session.simulate_reconnect("data")
                session.restore_checkpoint()
                restart_done = True

            if args.disconnect_test and not disconnect_done and (time.time() - started) > 8:
                session.simulate_disconnect("data")
                time.sleep(2)
                session.simulate_reconnect("data")
                disconnect_done = True

            if not args.use_databento:
                if hasattr(md, "advance") and md.advance():
                    session.on_closed_bar()
                else:
                    time.sleep(0.05)
            else:
                time.sleep(0.5)
    finally:
        session.stop_webhook()
        summary = session.finalize()
        passed, failures = session.evaluate_shadow_gate()

        if args.stage == "shadow" and passed:
            session.write_gate("FORWARD_SHADOW_PASS")
            verdict = "FORWARD_SHADOW_PASS"
        elif args.stage == "shadow":
            verdict = "FORWARD_SHADOW_FAIL"
        elif args.stage == "local-paper" and passed:
            session.write_gate("LOCAL_PAPER_PASS")
            verdict = "LOCAL_PAPER_PASS"
        elif args.stage == "local-paper":
            verdict = "LOCAL_PAPER_FAIL"
        else:
            verdict = "INFRA_TEST_COMPLETE"

        summary["verdict"] = verdict
        summary["gate_failures"] = failures
        (session.session_dir / "session_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
        print(json.dumps(summary, indent=2, default=str))
        print("VERDICT:", verdict)
        if failures:
            print("GATE_FAILURES:", failures)

    return 0 if verdict.endswith("PASS") or verdict == "INFRA_TEST_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
