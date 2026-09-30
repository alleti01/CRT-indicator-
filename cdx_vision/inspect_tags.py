"""Inspect right-edge CDX tags in a saved image. Does not place orders."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from cdx_vision.tesseract_cmd import resolve_tesseract
from cdx_vision.visible_levels import read_visible_tags


class _Engine:
    def __init__(self, executable: str) -> None:
        self.executable = executable

    def recognize(self, image):
        return []


def format_tags(image: Image.Image) -> str:
    exe = resolve_tesseract()
    if not exe:
        return "tesseract missing"
    tags, lines = read_visible_tags(image, _Engine(exe))
    lines_out = [f"lines {len(lines)}", f"tags {len(tags)}"]
    for tag in tags:
        lines_out.append(
            f"  color={tag.color} price={tag.price} text={tag.text!r} "
            f"box=({tag.x1},{tag.y1},{tag.x2},{tag.y2}) line_y={tag.line_y} reject={tag.reject or 'ASSOCIATED'}"
        )
    return "\n".join(lines_out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect CDX price tags. Does not place orders.")
    parser.add_argument("image")
    args = parser.parse_args(argv)
    print(format_tags(Image.open(args.image)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
