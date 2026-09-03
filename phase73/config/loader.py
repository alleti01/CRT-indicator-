"""Load Phase73 configuration from JSON/YAML + Pine freeze JSON."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None


@dataclass
class Phase73Config:
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def pine_hash(self) -> str:
        return str(self.raw.get("strategy", {}).get("pine_hash", ""))

    @property
    def symbol(self) -> str:
        return str(self.raw.get("strategy", {}).get("symbol", "NQ"))

    @property
    def timeframe(self) -> str:
        return str(self.raw.get("strategy", {}).get("timeframe", "1m"))

    @property
    def trading_enabled(self) -> bool:
        return bool(self.raw.get("execution", {}).get("trading_enabled", False))

    @property
    def paper_mode(self) -> bool:
        return bool(self.raw.get("execution", {}).get("paper_mode", True))

    @property
    def auto_reverse_enabled(self) -> bool:
        return bool(self.raw.get("execution", {}).get("auto_reverse_enabled", False))

    @property
    def stop_atr(self) -> float:
        return float(self.raw.get("management", {}).get("stop_atr", 1.0))

    @property
    def target_r(self) -> float:
        return float(self.raw.get("management", {}).get("target_r", 2.5))

    @property
    def max_hold_minutes(self) -> int:
        return int(self.raw.get("management", {}).get("max_hold_minutes", 60))

    @property
    def enable_time_progress_exit(self) -> bool:
        return bool(self.raw.get("management", {}).get("enable_time_progress_exit", False))

    @property
    def max_signal_age_seconds(self) -> int:
        return int(self.raw.get("entry_quality", {}).get("max_signal_age_seconds", 120))

    @property
    def staleness_limit_seconds(self) -> int:
        return int(self.raw.get("market_data", {}).get("staleness_limit_seconds", 90))

    @property
    def webhook_staleness_limit_seconds(self) -> int:
        return int(self.raw.get("webhook", {}).get("staleness_limit_seconds", 120))

    @property
    def log_dir(self) -> Path:
        return Path(str(self.raw.get("logging", {}).get("log_dir", "phase73/logs")))

    @property
    def state_file(self) -> Path:
        return Path(str(self.raw.get("persistence", {}).get("state_file", "phase73/logs/trader_state.json")))

    @property
    def same_bar_collision(self) -> str:
        return str(self.raw.get("execution", {}).get("same_bar_collision", "STOP_FIRST"))

    def section(self, name: str) -> dict[str, Any]:
        return dict(self.raw.get(name, {}))


def load_config(path: Path | None = None) -> Phase73Config:
    if path is not None:
        cfg_path = path
    elif (CONFIG_DIR / "default.yaml").exists() and yaml is not None:
        cfg_path = CONFIG_DIR / "default.yaml"
    else:
        cfg_path = CONFIG_DIR / "default.json"
    with cfg_path.open() as f:
        if cfg_path.suffix in {".yaml", ".yml"} and yaml is not None:
            raw = yaml.safe_load(f) or {}
        else:
            raw = json.load(f)
    return Phase73Config(raw=raw)


def load_pine_freeze(path: Path | None = None) -> dict[str, Any]:
    freeze_path = path or (CONFIG_DIR / "PINE_SIGNAL_FREEZE.json")
    return json.loads(freeze_path.read_text())
