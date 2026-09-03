"""Phase74 configuration loader."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Phase74Config:
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def shadow_mode(self) -> bool:
        return bool(self.raw.get("mode", {}).get("shadow_mode", True))

    @property
    def paper_mode(self) -> bool:
        return bool(self.raw.get("mode", {}).get("paper_mode", True))

    @property
    def trading_enabled(self) -> bool:
        return bool(self.raw.get("mode", {}).get("trading_enabled", False))

    @property
    def pine_hash(self) -> str:
        return str(self.raw.get("strategy", {}).get("pine_hash", ""))

    @property
    def log_dir(self) -> Path:
        return Path(str(self.raw.get("logging", {}).get("log_dir", "phase74/logs")))

    @property
    def webhook_secret(self) -> str:
        env_key = str(self.raw.get("webhook", {}).get("auth_env_var", "PHASE74_WEBHOOK_SECRET"))
        return os.environ.get(env_key, "")

    @property
    def kill_switch(self) -> bool:
        env_key = str(self.raw.get("safety", {}).get("kill_switch_env_var", "PHASE74_KILL_SWITCH"))
        return os.environ.get(env_key, "0") in ("1", "true", "TRUE")

    @property
    def symbol(self) -> str:
        return str(self.raw.get("strategy", {}).get("symbol", "NQ"))

    def section(self, name: str) -> dict[str, Any]:
        return dict(self.raw.get(name, {}))

    def to_phase73_config(self):
        from phase73.config.loader import Phase73Config

        p73 = dict(self.raw)
        p73.setdefault("execution", {})["paper_mode"] = self.paper_mode
        p73.setdefault("execution", {})["trading_enabled"] = self.trading_enabled or self.shadow_mode
        return Phase73Config(raw=p73)


def load_phase74_config(path: Path | None = None) -> Phase74Config:
    p73_path = CONFIG_DIR.parent / "phase73" / "config" / "default.json"
    if not p73_path.exists():
        p73_path = Path(__file__).resolve().parents[2] / "phase73" / "config" / "default.json"
    base = json.loads(p73_path.read_text()) if p73_path.exists() else {}
    p74_path = path or (CONFIG_DIR / "default.json")
    overlay = json.loads(p74_path.read_text())
    extends = overlay.pop("extends", None)
    if extends:
        pass  # already merged from p73 base
    merged = _deep_merge(base, overlay)
    return Phase74Config(raw=merged)


def verify_phase73_freeze() -> tuple[bool, list[str]]:
    freeze = json.loads((CONFIG_DIR / "PHASE73_ENGINE_FREEZE.json").read_text())
    root = CONFIG_DIR.parents[1]
    errors: list[str] = []
    for rel, expected in freeze["critical_modules"].items():
        path = root / rel
        if not path.exists():
            errors.append(f"missing {rel}")
            continue
        import hashlib

        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"hash mismatch {rel}: expected {expected[:12]} got {actual[:12]}")
    return len(errors) == 0, errors
