"""Offline inspection of a saved chart image. Does not place orders."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from cdx_vision.config import VisionConfig
from cdx_vision.models import OCRToken, VisionCaptureRequest
from cdx_vision.service import VisionBridge


def tokens_from_sidecar(image_path: Path) -> list[list[OCRToken]]:
    sidecar = image_path.with_suffix(".tokens.json")
    if not sidecar.exists():
        return []
    raw = json.loads(sidecar.read_text(encoding="utf-8"))
    frames = raw if isinstance(raw, list) and raw and isinstance(raw[0], list) else [raw]
    out = []
    for frame in frames:
        out.append([OCRToken(**token) for token in frame])
    return out


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python -m cdx_vision.inspect_capture path/to/image.png")
        return 2
    image = Path(argv[0])
    frames = tokens_from_sidecar(image)
    now = datetime.now(timezone.utc)
    request = VisionCaptureRequest(
        signal_id=image.stem,
        direction="SHORT",
        ticker="NQ",
        webhook_received_at=now,
        webhook_price=Decimal("30909.50"),
    )
    bridge = VisionBridge(VisionConfig(enabled=True, save_debug_images=False))
    result = bridge.process_frames(request, frames, now=now, window_title="fixture")
    print(result.state.value)
    print("entry", result.entry, result.entry_source)
    print("stop", result.stop)
    print("tp1", result.tp1)
    print("tp2", result.tp2)
    print("reasons", ",".join(result.reasons))
    return 0 if result.confirmed else 1


if __name__ == "__main__":
    raise SystemExit(main())
