"""Forward rehearsal session — wraps Phase74 LiveStack without engine changes."""
from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase73.trader.fsm import TraderAction, TraderState
from phase73.webhook.schemas import PineSignal, WebhookReason
from phase74.config.loader import Phase74Config, load_phase74_config
from phase74.contracts.mapping import load_contract_spec
from phase74.latency.tracker import LatencyTracker
from phase74.runtime.live_stack import LiveStack
from phase74.webhook.secure_receiver import SecureWebhookReceiver

from forward_rehearsal.audits.entry_price_audit import EntryPriceAuditor
from forward_rehearsal.audits.latency_audit import latency_audit_report
from forward_rehearsal.audits.reconciliation import SignalReconciler
from forward_rehearsal.freeze import manifest_snapshot, verify_manifest
from forward_rehearsal.logging.session_logger import SessionLogger
from forward_rehearsal.shadow.position_tracker import ShadowPositionTracker
from forward_rehearsal.shadow.state_auditor import ShadowState, StateMachineAuditor

log = logging.getLogger("forward.session")

GATES_DIR = Path(__file__).resolve().parents[1] / "gates"
REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
SESSIONS_ROOT = Path(__file__).resolve().parents[1] / "sessions"


class ForwardSession:
    """Real-time forward rehearsal orchestrator."""

    def __init__(
        self,
        cfg: Phase74Config,
        stack: LiveStack,
        *,
        stage: str = "shadow",
        session_id: str | None = None,
        allow_synthetic: bool = False,
    ) -> None:
        ok, errs = verify_manifest()
        if not ok:
            raise RuntimeError(f"FREEZE_MANIFEST_MISMATCH: {errs}")

        self.cfg = cfg
        self.stack = stack
        self.stage = stage
        self.allow_synthetic = allow_synthetic
        self.session_id = session_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]

        contract = load_contract_spec(cfg.raw)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.session_dir = SESSIONS_ROOT / day / self.session_id
        self.logger = SessionLogger(
            self.session_dir,
            session_id=self.session_id,
            software_hashes=manifest_snapshot(),
            symbol=cfg.symbol,
            contract=str(contract.contract_month or contract.broker_symbol),
            stage=stage,
        )

        self.reconciler = SignalReconciler()
        self.entry_audit = EntryPriceAuditor()
        self.state_auditor = StateMachineAuditor()
        self.shadow = ShadowPositionTracker(stack.engine.cfg) if stage in ("shadow", "infra-test") else None

        self._pine_to_webhook: list[float] = []
        self._webhook_to_decision: list[float] = []
        self._signal_to_fill: list[float] = []
        self._processed_signal_ids: set[str] = set()
        self._restarts = 0
        self._disconnects = 0
        self._position_mismatches = 0
        self._webhook: SecureWebhookReceiver | None = None
        self._synthetic_count = 0
        self._tv_signal_count = 0

        self._wire_callbacks()

    def _wire_callbacks(self) -> None:
        """Patch stack handlers for session observability."""
        original_on_signal = self.stack.on_webhook_signal

        def wrapped_signal(signal: PineSignal, reason: WebhookReason, tracker: LatencyTracker) -> dict[str, Any]:
            return self._handle_signal(signal, reason, tracker, original_on_signal)

        self.stack.on_webhook_signal = wrapped_signal  # type: ignore[method-assign]

    def _handle_signal(
        self,
        signal: PineSignal,
        reason: WebhookReason,
        tracker: LatencyTracker,
        original,
    ) -> dict[str, Any]:
        bar = self.stack.market_data.latest_bar()
        webhook_ts = tracker.webhook_received_at or datetime.now(timezone.utc)
        is_synthetic = signal.context.startswith("SYNTHETIC") or signal.signal_id.startswith("syn-")

        if is_synthetic:
            self._synthetic_count += 1
            if not self.allow_synthetic and self.stage != "infra-test":
                self.logger.log_error(event="SYNTHETIC_SIGNAL_REJECTED", signal_id=signal.signal_id)
                self.reconciler.record(
                    signal_id=signal.signal_id,
                    tv_timestamp=signal.signal_time_utc,
                    webhook_timestamp=webhook_ts,
                    market_bar_timestamp=bar.timestamp if bar else None,
                    direction=signal.direction,
                    signal_price=signal.signal_price,
                    atr=signal.atr,
                    engine_action="",
                    reason="synthetic not allowed in forward rehearsal",
                    latency_ms=0,
                    rejected=True,
                )
                return {"ok": False, "reason": "SYNTHETIC_NOT_ALLOWED"}
        else:
            self._tv_signal_count += 1

        self.logger.log_signal(
            signal_id=signal.signal_id,
            event=signal.event,
            direction=signal.direction,
            signal_time=signal.signal_time_utc.isoformat(),
            signal_price=signal.signal_price,
            atr=signal.atr,
            pine_hash=signal.pine_hash,
            synthetic=is_synthetic,
        )

        market_at_webhook = bar.close if bar else signal.signal_price
        result = original(signal, reason, tracker)
        lat = tracker.finalize()

        self._pine_to_webhook.append(lat.get("pine_to_webhook_ms", 0))
        self._webhook_to_decision.append(lat.get("decision_ms", 0))
        if lat.get("total_signal_to_fill_ms"):
            self._signal_to_fill.append(lat["total_signal_to_fill_ms"])

        engine_action = str(result.get("action", result.get("reason", "")))
        if result.get("shadow"):
            engine_action = str(result.get("action", "WOULD_ENTER"))

        self.state_auditor.record_engine_state(self.stack.engine.state)
        if self.shadow and reason == WebhookReason.WEBHOOK_VALID:
            self._process_shadow(signal, result, bar, tracker)
        elif self.stage == "local-paper" and result.get("fill_price"):
            self.logger.log_fill(
                signal_id=signal.signal_id,
                fill_price=result["fill_price"],
                action=engine_action,
            )

        status_rejected = reason != WebhookReason.WEBHOOK_VALID or not result.get("ok", False)
        row = self.reconciler.record(
            signal_id=signal.signal_id,
            tv_timestamp=signal.signal_time_utc,
            webhook_timestamp=webhook_ts,
            market_bar_timestamp=bar.timestamp if bar else None,
            direction=signal.direction,
            signal_price=signal.signal_price,
            atr=signal.atr,
            engine_action=engine_action,
            reason=str(result.get("reason", reason.value)),
            latency_ms=lat.get("decision_ms", 0),
            rejected=status_rejected and reason != WebhookReason.WEBHOOK_VALID,
            error=result.get("reason") == "STATE_INVARIANT_FAILURE",
        )

        self.logger.log_decision(
            signal_id=signal.signal_id,
            engine_action=engine_action,
            engine_state=self.stack.engine.state.value,
            shadow_state=self.state_auditor.shadow_state.value,
            latency=lat,
            reconciliation_status=row.status,
        )

        if engine_action.startswith("WOULD_ENTER") and self.shadow:
            decision_px = bar.close if bar else signal.signal_price
            self.entry_audit.record(
                signal_id=signal.signal_id,
                pine_signal_price=signal.signal_price,
                market_price_at_webhook=market_at_webhook,
                market_price_at_decision=decision_px,
                next_tradable_price=decision_px,
                atr=signal.atr,
                when=datetime.now(timezone.utc),
            )

        if signal.signal_id in self._processed_signal_ids and result.get("ok"):
            self.logger.log_error(event="DUPLICATE_EXECUTION_DECISION", signal_id=signal.signal_id)
        if result.get("ok"):
            self._processed_signal_ids.add(signal.signal_id)

        return result

    def _process_shadow(self, signal: PineSignal, result: dict, bar, tracker: LatencyTracker) -> None:
        action = str(result.get("action", ""))
        if self.shadow and self.shadow.is_active and signal.direction != self.shadow.side:
            opp = self.shadow.on_opposite_signal(signal)
            self.state_auditor.apply_action(opp.action, trigger="opposite_signal", direction=signal.direction)
            self.logger.log_shadow(signal_id=signal.signal_id, action=opp.action, reason=opp.reason)
            return

        if action.startswith("WOULD_ENTER") or (result.get("shadow") and "ENTER" in action):
            entry_px = bar.close if bar else signal.signal_price
            entry_time = bar.timestamp if bar else datetime.now(timezone.utc)
            shadow_act = self.shadow.open_from_signal(signal, entry_px, entry_time) if self.shadow else None
            if shadow_act:
                self.state_auditor.apply_action(shadow_act.action, trigger="shadow_entry", direction=signal.direction)
                self.logger.log_shadow(
                    signal_id=signal.signal_id,
                    action=shadow_act.action,
                    reason=shadow_act.reason,
                    entry_price=entry_px,
                )
        elif action.startswith("WOULD_PASS") or action.startswith("WOULD_"):
            self.state_auditor.apply_action(action, trigger="shadow_pass", direction=signal.direction)
            self.logger.log_shadow(signal_id=signal.signal_id, action=action, reason=str(result.get("reason", "")))

    def on_closed_bar(self) -> dict[str, Any]:
        """Process new closed bar — health, shadow management, engine bar tick."""
        md = self.stack.market_data
        health = md.health()
        self.logger.log_market_health(
            state=health.state.value,
            latency_seconds=health.latency_seconds,
            last_bar=str(health.last_bar_timestamp),
        )

        if health.state.value != "DATA_HEALTHY":
            return {"ok": False, "reason": "DATA_UNHEALTHY"}

        bar = md.latest_bar()
        if bar is None:
            return {"ok": False}

        result: dict[str, Any] = {"ok": True}
        if self.stage == "shadow" and self.shadow and self.shadow.is_active:
            now = md.current_time()
            shadow_act = self.shadow.on_bar(bar, now)
            if shadow_act:
                self.state_auditor.apply_action(shadow_act.action, trigger="bar", direction=self.shadow.side)
                self.logger.log_shadow(
                    signal_id=shadow_act.signal_id,
                    action=shadow_act.action,
                    reason=shadow_act.reason,
                    price=shadow_act.exit_price,
                )
                result["shadow_action"] = shadow_act.action
        elif self.stage == "local-paper":
            result = self.stack.on_bar()

        self.state_auditor.record_engine_state(self.stack.engine.state)
        self.logger.log_state_transition(
            engine_state=self.stack.engine.state.value,
            shadow_state=self.state_auditor.shadow_state.value,
            broker_position=self.stack.broker.get_position().side,
        )
        return result

    def start_webhook(self, secret: str) -> None:
        dedup_path = self.session_dir / "signal_ids.jsonl"
        self._webhook = SecureWebhookReceiver(
            self.cfg.to_phase73_config(),
            secret,
            on_signal=lambda s, r, t: self.stack.on_webhook_signal(s, r, t),
            deduplicator=__import__("phase73.webhook.deduplicator", fromlist=["SignalDeduplicator"]).SignalDeduplicator(dedup_path),
            rate_limit=int(self.cfg.section("webhook").get("rate_limit_per_minute", 60)),
        )
        wh = self.cfg.section("webhook")
        self._webhook.start(str(wh.get("host", "127.0.0.1")), int(wh.get("port", 8787)), str(wh.get("path", "/webhook")))
        self.stack.webhook_status = "LISTENING"
        log.info("forward webhook listening")

    def stop_webhook(self) -> None:
        if self._webhook:
            self._webhook.stop()
            self.stack.webhook_status = "STOPPED"

    def simulate_disconnect(self, target: str = "data") -> None:
        self._disconnects += 1
        if target == "data":
            self.stack.market_data.disconnect()
        elif target == "webhook":
            self.stop_webhook()
        self.logger.log_error(event="SIMULATED_DISCONNECT", target=target)

    def simulate_reconnect(self, target: str = "data") -> None:
        if target == "data":
            self.stack.market_data.connect()
        elif target == "webhook":
            secret = self.cfg.webhook_secret or ""
            if secret:
                self.start_webhook(secret)
        self._restarts += 1
        self.logger.log_error(event="SIMULATED_RECONNECT", target=target)

    def persist_checkpoint(self) -> None:
        self.stack.engine.persist()
        (self.session_dir / "checkpoint.json").write_text(
            __import__("json").dumps(
                {
                    "session_id": self.session_id,
                    "processed_signals": sorted(self._processed_signal_ids),
                    "engine_state": self.stack.engine.state.value,
                    "shadow_state": self.state_auditor.shadow_state.value,
                },
                indent=2,
            )
        )

    def restore_checkpoint(self) -> None:
        cp = self.session_dir / "checkpoint.json"
        if not cp.exists():
            return
        data = __import__("json").loads(cp.read_text())
        self._processed_signal_ids = set(data.get("processed_signals", []))

    def finalize(self) -> dict[str, Any]:
        """Write reports and session summary."""
        lat = latency_audit_report(
            pine_to_webhook=self._pine_to_webhook,
            webhook_to_decision=self._webhook_to_decision,
            signal_to_fill=self._signal_to_fill,
        )
        recon_path = REPORTS_DIR / "SHADOW_SIGNAL_RECONCILIATION.csv"
        self.reconciler.write_csv(recon_path)
        entry_path = REPORTS_DIR / "SHADOW_ENTRY_PRICE_AUDIT.csv"
        self.entry_audit.write_csv(entry_path)

        summary = self._build_summary(lat)
        self.logger.write_summary(summary)
        (self.session_dir / "latency_audit.json").write_text(__import__("json").dumps(lat, indent=2) + "\n")
        return summary

    def _build_summary(self, lat: dict[str, Any]) -> dict[str, Any]:
        recon = self.reconciler.summary()
        shadow_actions = [r.engine_action for r in self.reconciler.rows if r.engine_action.startswith("WOULD")]
        return {
            "session_id": self.session_id,
            "stage": self.stage,
            "tv_signals": self._tv_signal_count,
            "synthetic_signals": self._synthetic_count,
            "long_signals": sum(1 for r in self.reconciler.rows if r.direction == "LONG"),
            "short_signals": sum(1 for r in self.reconciler.rows if r.direction == "SHORT"),
            "processed_signals": len(self._processed_signal_ids),
            "reconciliation": recon,
            "would_enter": sum(1 for a in shadow_actions if "ENTER" in a),
            "passes": sum(1 for a in shadow_actions if "PASS" in a),
            "state_errors": len(self.state_auditor.failures),
            "data_errors": 0,
            "execution_errors": 0,
            "latency": lat,
            "restarts": self._restarts,
            "disconnects": self._disconnects,
            "position_mismatches": self._position_mismatches,
            "state_auditor": self.state_auditor.summary(),
            "entry_price_audit": self.entry_audit.summary(),
            "real_orders_sent": self.stage == "local-paper",
        }

    def evaluate_shadow_gate(self) -> tuple[bool, list[str]]:
        """Check FORWARD_SHADOW_PASS criteria from session data."""
        failures: list[str] = []
        if self._tv_signal_count == 0 and not self.allow_synthetic:
            failures.append("no real TV alerts received")
        if self.reconciler.summary().get("duplicates", 0) > 0:
            failures.append("duplicate execution decisions detected")
        if self.state_auditor.failures:
            failures.append("STATE_INVARIANT_FAILURE")
        if self.state_auditor.halted:
            failures.append("state machine halted")
        if self.stage == "shadow" and self.stack.broker.get_position().side != "FLAT":
            failures.append("broker position not flat in shadow mode")
        return len(failures) == 0, failures

    def write_gate(self, verdict: str) -> None:
        GATES_DIR.mkdir(parents=True, exist_ok=True)
        (GATES_DIR / verdict).write_text(datetime.now(timezone.utc).isoformat() + "\n")


def load_forward_config(stage: str = "shadow") -> Phase74Config:
    raw = copy.deepcopy(load_phase74_config().raw)
    raw.setdefault("mode", {})["shadow_mode"] = stage in ("shadow", "infra-test")
    raw.setdefault("mode", {})["paper_mode"] = True
    raw.setdefault("mode", {})["trading_enabled"] = stage == "local-paper"
    if stage == "local-paper":
        raw.setdefault("contracts", {})["contract_month"] = raw.get("contracts", {}).get("contract_month") or "202609"
    log_dir = Path(__file__).resolve().parents[1] / "sessions" / "runtime_logs"
    raw.setdefault("logging", {})["log_dir"] = str(log_dir)
    raw.setdefault("persistence", {})["state_file"] = str(log_dir / "trader_state.json")
    raw["persistence"]["idempotency_file"] = str(log_dir / "order_idempotency.jsonl")
    from phase74.config.loader import Phase74Config

    return Phase74Config(raw=raw)


def shadow_gate_passed() -> bool:
    return (GATES_DIR / "FORWARD_SHADOW_PASS").exists()
