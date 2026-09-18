"""Phase85 fail-closed configuration. Missing/invalid values disable routing."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
FROZEN_PINE_HASH = "d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f"
CRTBARBRIDGE_RELPATH = "phase74/market_data/ninjatrader/CRTBarBridge.cs"
CRTBARBRIDGE_SHA256 = "1a01a3f33c21cb3ac419e3ee7f3ab05448181b81a33bd5796f16ba2c6eeac880"
EXECUTION_MODES = frozenset({"SHADOW", "SIM", "FUNDED"})


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Phase85Config:
    raw: dict[str, Any] = field(default_factory=dict)
    execution_mode: str = "SHADOW"
    shadow_mode: bool = True
    trading_enabled: bool = False
    external_order_routing: bool = False
    nt_execution_bridge_enabled: bool = False
    bind_host: str = "127.0.0.1"
    bind_port: int = 8766
    auth_env_var: str = "NINJATRADER_EXECUTION_BRIDGE_TOKEN"
    expected_account: str = ""
    allowed_funded_account: str = ""
    funded_account_verified: bool = False
    allowed_instrument_root: str = "MNQ"
    expected_contract: str = ""
    tick_size: float = 0.25
    point_value: float = 2.0
    max_quantity: int = 1
    max_open_strategy_positions: int = 1
    stale_signal_seconds: int = 120
    allow_nq_execution: bool = False
    persistence_dir: Path = field(default_factory=lambda: ROOT / "logs")
    sim_gate_path: Path = field(default_factory=lambda: ROOT / "logs" / "sim_activation_gate.json")

    @property
    def execution_token(self) -> str:
        env = os.environ.get(self.auth_env_var, "")
        if env:
            return env
        # Test-only override. Never place a real token in default.json.
        return str(self.raw.get("_test_token", ""))

    @property
    def command_store_path(self) -> Path:
        return self.persistence_dir / "command_ids.jsonl"

    @property
    def ledger_path(self) -> Path:
        return self.persistence_dir / "execution_ledger.jsonl"

    @property
    def audit_path(self) -> Path:
        return self.persistence_dir / "audit.jsonl"

    @property
    def state_path(self) -> Path:
        return self.persistence_dir / "execution_state.json"

    @property
    def latency_path(self) -> Path:
        return self.persistence_dir / "latency.jsonl"

    def routing_enabled(self) -> bool:
        return (
            self.trading_enabled
            and self.external_order_routing
            and self.nt_execution_bridge_enabled
            and not self.shadow_mode
            and self.execution_mode in {"SIM", "FUNDED"}
        )


def load_phase85_config(
    path: Path | None = None,
    *,
    overlay: dict[str, Any] | None = None,
    env: bool = True,
) -> Phase85Config:
    cfg_path = path or (CONFIG_DIR / "default.json")
    raw: dict[str, Any] = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    if overlay:
        raw = {**raw, **overlay}

    mode = str(raw.get("execution_mode", "SHADOW")).upper()
    if env:
        mode = _env_str("EXECUTION_MODE", mode).upper() or "SHADOW"
    if mode not in EXECUTION_MODES:
        mode = "INVALID"

    cfg = Phase85Config(
        raw=raw,
        execution_mode=mode,
        shadow_mode=_env_bool("SHADOW_MODE", bool(raw.get("shadow_mode", True))) if env else bool(raw.get("shadow_mode", True)),
        trading_enabled=_env_bool("TRADING_ENABLED", bool(raw.get("trading_enabled", False))) if env else bool(raw.get("trading_enabled", False)),
        external_order_routing=_env_bool("EXTERNAL_ORDER_ROUTING", bool(raw.get("external_order_routing", False))) if env else bool(raw.get("external_order_routing", False)),
        nt_execution_bridge_enabled=_env_bool("NT_EXECUTION_BRIDGE_ENABLED", bool(raw.get("nt_execution_bridge_enabled", False))) if env else bool(raw.get("nt_execution_bridge_enabled", False)),
        bind_host=str(raw.get("bind_host", "127.0.0.1")),
        bind_port=int(raw.get("bind_port", 8766)),
        auth_env_var=str(raw.get("auth_env_var", "NINJATRADER_EXECUTION_BRIDGE_TOKEN")),
        expected_account=_env_str("EXPECTED_ACCOUNT", str(raw.get("expected_account", ""))) if env else str(raw.get("expected_account", "")),
        allowed_funded_account=_env_str("ALLOWED_FUNDED_ACCOUNT", str(raw.get("allowed_funded_account", ""))) if env else str(raw.get("allowed_funded_account", "")),
        funded_account_verified=_env_bool("FUNDED_ACCOUNT_VERIFIED", bool(raw.get("funded_account_verified", False))) if env else bool(raw.get("funded_account_verified", False)),
        allowed_instrument_root=str(raw.get("allowed_instrument_root", "MNQ")).upper(),
        expected_contract=str(raw.get("expected_contract", "")),
        tick_size=float(raw.get("tick_size", 0.25)),
        point_value=float(raw.get("point_value", 2.0)),
        max_quantity=_env_int("MAX_QUANTITY", int(raw.get("max_quantity", 1))) if env else int(raw.get("max_quantity", 1)),
        max_open_strategy_positions=int(raw.get("max_open_strategy_positions", 1)),
        stale_signal_seconds=int(raw.get("stale_signal_seconds", 120)),
        allow_nq_execution=bool(raw.get("allow_nq_execution", False)),
        persistence_dir=Path(str(raw.get("persistence_dir", ROOT / "logs"))),
        sim_gate_path=Path(str(raw.get("sim_gate_path", ROOT / "logs" / "sim_activation_gate.json"))),
    )
    if cfg.bind_host not in {"127.0.0.1", "localhost", "::1"}:
        # Non-local bind is a config error: fail closed by disabling routing flags.
        cfg.nt_execution_bridge_enabled = False
    return cfg
