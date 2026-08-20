#!/usr/bin/env python3
"""Optional Databento NQ downloader with a pre-download cost gate."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Download Databento NQ OHLCV-1m")
    command.add_argument("--start", required=True)
    command.add_argument("--end", required=True, help="Exclusive end accepted by Databento")
    command.add_argument("--symbols", default="NQ.v.0", help="Comma-separated symbols")
    command.add_argument("--dataset", default="GLBX.MDP3")
    command.add_argument("--schema", default="ohlcv-1m")
    command.add_argument(
        "--stype-in",
        default="continuous",
        choices=["continuous", "raw_symbol", "parent", "instrument_id"],
    )
    command.add_argument("--output", default="data/nq_1m.csv")
    command.add_argument("--estimate-only", action="store_true")
    command.add_argument(
        "--chunk-days",
        type=int,
        default=7,
        help="Days per request (default: 7; smaller values reduce gateway timeouts)",
    )
    command.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retries per failed chunk (default: 3)",
    )
    command.add_argument(
        "--max-cost-usd",
        type=float,
        help="Abort unless the API estimate is at or below this amount",
    )
    return command


def _client():
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise RuntimeError("set DATABENTO_API_KEY in your environment")
    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError("install the optional databento dependency first") from exc
    return db.Historical(key)


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid ISO date/time: {value}") from exc


def _chunks(start: str, end: str, days: int):
    if days < 1:
        raise ValueError("--chunk-days must be at least 1")
    current = _parse_datetime(start)
    finish = _parse_datetime(end)
    if finish <= current:
        raise ValueError("--end must be after --start")
    while current < finish:
        next_end = min(current + timedelta(days=days), finish)
        yield current, next_end
        current = next_end


def _normalize_frame(store) -> pd.DataFrame:
    frame = store.to_df().reset_index()
    if "ts_event" in frame.columns:
        frame = frame.rename(columns={"ts_event": "timestamp"})
    elif "index" in frame.columns and "timestamp" not in frame.columns:
        frame = frame.rename(columns={"index": "timestamp"})
    return frame


def _part_path(parts_directory: Path, start: datetime, end: datetime) -> Path:
    start_label = start.strftime("%Y%m%dT%H%M%S")
    end_label = end.strftime("%Y%m%dT%H%M%S")
    return parts_directory / f"part_{start_label}_{end_label}.csv"


def _download_chunk(client, request: dict, retries: int) -> pd.DataFrame:
    if retries < 1:
        raise ValueError("--retries must be at least 1")
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return _normalize_frame(client.timeseries.get_range(**request))
        except Exception as exc:  # SDK exposes HTTP errors through version-specific classes.
            last_error = exc
            if attempt == retries:
                break
            delay = 2**attempt
            print(
                f"Chunk attempt {attempt}/{retries} failed: {exc}. Retrying in {delay}s...",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(f"chunk failed after {retries} attempts: {last_error}")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]
    client = _client()
    request = {
        "dataset": args.dataset,
        "symbols": symbols,
        "schema": args.schema,
        "stype_in": args.stype_in,
        "start": args.start,
        "end": args.end,
    }
    cost = float(client.metadata.get_cost(**request))
    print(f"Estimated Databento cost: ${cost:.4f}")
    if args.estimate_only:
        return 0
    if args.max_cost_usd is None:
        raise RuntimeError(
            "download blocked: rerun with --max-cost-usd after reviewing the estimate"
        )
    if cost > args.max_cost_usd:
        raise RuntimeError(
            f"download blocked: estimate ${cost:.4f} exceeds --max-cost-usd ${args.max_cost_usd:.4f}"
        )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    parts_directory = destination.parent / f"{destination.name}.parts"
    parts_directory.mkdir(parents=True, exist_ok=True)
    ranges = list(_chunks(args.start, args.end, args.chunk_days))
    part_paths = []
    for number, (chunk_start, chunk_end) in enumerate(ranges, start=1):
        part = _part_path(parts_directory, chunk_start, chunk_end)
        part_paths.append(part)
        if part.exists():
            print(
                f"Chunk {number}/{len(ranges)} already saved; resuming: {part.name}",
                flush=True,
            )
            continue
        chunk_request = {
            **request,
            "start": chunk_start.isoformat(),
            "end": chunk_end.isoformat(),
        }
        print(
            f"Downloading chunk {number}/{len(ranges)}: "
            f"{chunk_start.isoformat()} to {chunk_end.isoformat()}",
            flush=True,
        )
        frame = _download_chunk(client, chunk_request, args.retries)
        frame.to_csv(part, index=False)
        print(f"Saved chunk {number}: {len(frame):,} rows", flush=True)

    frames = [pd.read_csv(part) for part in part_paths]
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        identity = ["timestamp"]
        for candidate in ("instrument_id", "symbol", "contract"):
            if candidate in frame.columns:
                identity.append(candidate)
                break
        frame = frame.sort_values(identity).drop_duplicates(identity, keep="last")
    if destination.suffix.lower() in {".parquet", ".pq"}:
        frame.to_parquet(destination, index=False)
    else:
        frame.to_csv(destination, index=False)
    print(f"Saved {len(frame):,} total rows to {destination.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
