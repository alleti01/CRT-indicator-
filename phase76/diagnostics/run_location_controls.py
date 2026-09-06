#!/usr/bin/env python3
"""Phase76 checkpoint 10 — S/R location control (non-directional path behavior)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(line_buffering=True)

from phase76.python.auction_engine import build_auction_features  # noqa: E402
from phase76.python.config import CHECKPOINTS, REPORTS, TRAIN_FRAC, VAL_FRAC  # noqa: E402
from phase76.python.data_loader import load_nq_1m  # noqa: E402
from phase76.python.location_config import (  # noqa: E402
    DISTANCE_BANDS_ATR,
    HEAD_TO_HEAD,
    PRIMARY_BAND_ATR,
    PROFILE_VS_ROLLING,
)
from phase76.python.location_evaluation import (  # noqa: E402
    detect_band_cliff,
    evaluate_level_vs_matched,
    final_phase76_verdict,
    head_to_head_compare,
    summarize_level_result,
)
from phase76.python.location_interactions import (  # noqa: E402
    add_context_columns,
    build_non_level_pool,
    detect_level_interactions,
)
from phase76.python.location_levels import ALL_LEVELS, AUCTION_LEVELS, SIMPLE_LEVELS  # noqa: E402
from phase76.python.location_matching import match_non_level_controls  # noqa: E402
from phase76.python.location_paths import attach_path_metrics  # noqa: E402
from phase76.python.market_states import classify_auction_states  # noqa: E402

FEAT_CACHE = ROOT / "phase76" / "data" / "auction_features.parquet"
INTERACTIONS_CACHE = ROOT / "phase76" / "data" / "location_interactions.parquet"
PATHS_CACHE = ROOT / "phase76" / "data" / "location_paths.parquet"
POOL_PATHS_CACHE = ROOT / "phase76" / "data" / "non_level_pool_paths.parquet"


def _ts_key(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def _load_pool_paths(pool: pd.DataFrame, ohlc: pd.DataFrame) -> dict:
    if POOL_PATHS_CACHE.exists():
        print(f"Loading cached pool paths: {POOL_PATHS_CACHE}")
        df = pd.read_parquet(POOL_PATHS_CACHE)
        return {_ts_key(row["interaction_ts"]): row for _, row in df.iterrows()}

    print(f"Precomputing pool paths ({len(pool):,} bars)...")
    pool_ev = pool.copy()
    pool_ev["interaction_ts"] = pool_ev.index
    pool_ev["price"] = pool_ev["close"]
    pathed = attach_path_metrics(pool_ev, ohlc)
    POOL_PATHS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    pathed.to_parquet(POOL_PATHS_CACHE)
    return {_ts_key(row["interaction_ts"]): row for _, row in pathed.iterrows()}


def _load_or_build_features(ohlc: pd.DataFrame) -> pd.DataFrame:
    if FEAT_CACHE.exists():
        print(f"Loading cached features: {FEAT_CACHE}")
        feat = pd.read_parquet(FEAT_CACHE)
        feat.index = pd.to_datetime(feat.index, utc=True)
        if "auction_state" not in feat.columns:
            feat["auction_state"] = classify_auction_states(feat, value_source="developing")
        return feat
    print("Building auction features (slow, will cache)...")
    feat = build_auction_features(ohlc)
    feat["auction_state"] = classify_auction_states(feat, value_source="developing")
    FEAT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    feat.to_parquet(FEAT_CACHE)
    return feat


def _detect_and_path(feat: pd.DataFrame, ohlc: pd.DataFrame) -> pd.DataFrame:
    if PATHS_CACHE.exists():
        print(f"Loading cached paths: {PATHS_CACHE}")
        return pd.read_parquet(PATHS_CACHE)

    print("Adding context columns...")
    feat = add_context_columns(feat)

    parts: list[pd.DataFrame] = []
    for spec in ALL_LEVELS:
        bands = (PRIMARY_BAND_ATR,) if spec.zone_flag else DISTANCE_BANDS_ATR
        for band in bands:
            print(f"  Detecting {spec.code} @ {band} ATR...")
            ev = detect_level_interactions(feat, spec, band_atr=band)
            if ev.empty:
                continue
            print(f"    {len(ev):,} episodes — computing paths...")
            pathed = attach_path_metrics(ev, ohlc)
            parts.append(pathed)
    if not parts:
        return pd.DataFrame()
    all_paths = pd.concat(parts, ignore_index=True)
    PATHS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    all_paths.to_parquet(PATHS_CACHE)
    if not INTERACTIONS_CACHE.exists():
        all_paths.drop(columns=[c for c in all_paths.columns if c.startswith(("abs_excursion", "mfe_", "two_sided", "largest", "net_displacement", "directional", "time_to", "first_side", "sweep_", "clean_", "rejection", "continuation", "failure"))], errors="ignore").to_parquet(INTERACTIONS_CACHE)
    return all_paths


def _filter(paths: pd.DataFrame, level: str, band: float) -> pd.DataFrame:
    return paths[(paths["level_type"] == level) & (paths["band_atr"] == band)].copy()


def aligned_matched_paths(
    treat: pd.DataFrame,
    pairs: pd.DataFrame,
    ctrl_path_by_ts: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return treat/control path rows in matched pair order."""
    treat_by_ts = {_ts_key(r["interaction_ts"]): r for _, r in treat.iterrows()}
    t_rows, c_rows = [], []
    for _, p in pairs.iterrows():
        tt = _ts_key(p["interaction_ts"])
        ct = _ts_key(p["control_ts"])
        if tt not in treat_by_ts or ct not in ctrl_path_by_ts:
            continue
        t_rows.append(treat_by_ts[tt])
        c_rows.append(ctrl_path_by_ts[ct])
    if not t_rows:
        return pd.DataFrame(), pd.DataFrame()
    return pd.DataFrame(t_rows).reset_index(drop=True), pd.DataFrame(c_rows).reset_index(drop=True)

    return paths[(paths["level_type"] == level) & (paths["band_atr"] == band)].copy()


def _write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            flat = {}
            for k, v in r.items():
                if isinstance(v, dict):
                    flat[k] = json.dumps(v)
                else:
                    flat[k] = v
            w.writerow(flat)


def _write_md(
    *,
    level_results: list[dict],
    h2h: list[dict],
    verdict: str,
    pool_n: int,
) -> None:
    md = REPORTS / "PHASE76_LOCATION_CONTROL.md"
    lines = [
        "# Phase76 — S/R Location Control",
        "",
        f"**Verdict:** `{verdict}`",
        "",
        "## Scope",
        "",
        "- Non-directional path/activity test at auction vs simple S/R vs matched non-level controls",
        "- Distance bands (frozen): " + ", ".join(str(b) for b in DISTANCE_BANDS_ATR) + " ATR",
        f"- Primary band for matching: {PRIMARY_BAND_ATR} ATR",
        "- Directional families A–F **permanently rejected** (checkpoint 14)",
        "",
        f"Non-level control pool: **{pool_n:,}** RTH bars",
        "",
        "## Level results (primary band vs matched non-level)",
        "",
        "| Level | Category | n | Match | max SMD | 2-sided 15m lift | Clean exp lift | Sweep diff | Verdict |",
        "|-------|----------|---|-------|---------|------------------|----------------|------------|---------|",
    ]
    primary = [r for r in level_results if r.get("band_atr") == PRIMARY_BAND_ATR]
    for r in sorted(primary, key=lambda x: x["level_type"]):
        show_lift = r.get("match_status") == "ACCEPT"
        lines.append(
            f"| {r['level_type']} | {r['level_category']} | {r.get('n', 0):,} | "
            f"{r.get('match_status', '—')} | {_fmt(r.get('max_smd'))} | "
            f"{_fmt(r.get('lift_two_sided_15')) if show_lift else '—'} | "
            f"{_fmt(r.get('clean_expansion_lift')) if show_lift else '—'} | "
            f"{_fmt(r.get('sweep_diff')) if show_lift else '—'} | "
            f"**{r.get('verdict')}** |"
        )

    lines.extend(["", "## Head-to-head (profile vs simple S/R)", ""])
    lines.append("| A | B | lift 15m (A−B) | profile beats simple |")
    lines.append("|---|----|----------------|----------------------|")
    for h in h2h:
        lines.append(
            f"| {h['level_a']} | {h['level_b']} | {_fmt(h.get('lift_a_minus_b'))} | "
            f"{'yes' if h.get('profile_beats_simple') else 'no'} |"
        )

    lines.extend(["", "## Answers", ""])
    qa = _build_qa(level_results, h2h, verdict)
    for i, (q, a) in enumerate(qa, 1):
        lines.append(f"{i}. **{q}** — {a}")
        lines.append("")

    md.write_text("\n".join(lines))


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def _build_qa(level_results: list[dict], h2h: list[dict], verdict: str) -> list[tuple[str, str]]:
    primary = [r for r in level_results if r.get("band_atr") == PRIMARY_BAND_ATR and r.get("level_category") == "auction"]
    any_lift = any(abs(r.get("lift_two_sided_15", 0) or 0) >= 0.08 for r in primary if r.get("match_status") == "ACCEPT")
    profile_wins = sum(1 for h in h2h if h.get("profile_beats_simple"))
    return [
        ("Do auction locations produce different path behavior from matched non-level controls?", "Yes only if match ACCEPT and lift exceeds preregistered gates; see table." if any_lift else "No material difference after matching."),
        ("Is the difference practically meaningful?", "See lift/clean-expansion columns; gate requires ≥0.08 ATR two-sided lift or equivalent."),
        ("Do VAH/VAL outperform prior highs/lows?", _h2h_answer(h2h, "PRIOR_VAH", "PRIOR_SESSION_HIGH")),
        ("Does POC outperform VWAP?", _h2h_answer(h2h, "DEV_POC", "VWAP")),
        ("Do profile levels outperform ordinary rolling S/R?", f"{profile_wins}/{len(h2h)} head-to-head pairs favor profile."),
        ("Are reactions cleaner, more volatile, or simply more two-sided?", "Compare clean_expansion_lift vs sweep_diff in CSV."),
        ("Is the effect stable chronologically?", "See split_means and year_means in checkpoint JSON."),
        ("Does any location deserve use as NON-DIRECTIONAL CONTEXT?", "Only WEAK/MODERATE/STRONG verdicts; none imply directional entry."),
        ("Is Phase72A context comparison justified?", "Only if PHASE76_CONTEXT_FOLLOWUP_JUSTIFIED — not if NO_AUCTION_INFORMATION."),
        ("Final Phase76 verdict", f"`{verdict}`"),
    ]


def _h2h_answer(h2h: list[dict], a: str, b: str) -> str:
    for h in h2h:
        if h.get("level_a") == a and h.get("level_b") == b:
            return "yes" if h.get("profile_beats_simple") else "no"
    return "not tested"


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    print("Loading OHLC...")
    ohlc = load_nq_1m()
    feat = _load_or_build_features(ohlc)
    feat = add_context_columns(feat)

    print("Building non-level control pool...")
    pool = build_non_level_pool(feat)
    print(f"  Pool size: {len(pool):,}")

    all_paths = _detect_and_path(feat, ohlc)
    if all_paths.empty:
        print("ERROR: no location interactions detected")
        return 1

    print(f"Total pathed interactions: {len(all_paths):,}")

    # Pre-match auction levels at primary band
    print("Loading non-level pool paths for matching...")
    ctrl_path_by_ts = _load_pool_paths(pool, ohlc)
    auction_specs = [s for s in ALL_LEVELS if s.category in ("auction", "hvn_lvn")]

    print("Matching auction levels to non-level controls...")
    match_cache: dict[str, tuple[pd.DataFrame, dict]] = {}
    for spec in auction_specs:
        treat = _filter(all_paths, spec.code, PRIMARY_BAND_ATR)
        if treat.empty:
            continue
        pairs, _, diag = match_non_level_controls(treat, pool)
        match_cache[spec.code] = (pairs, diag)

    level_results: list[dict] = []
    h2h_rows: list[dict] = []
    simple_primary: dict[str, pd.DataFrame] = {}

    for spec in ALL_LEVELS:
        for band in DISTANCE_BANDS_ATR:
            treat = _filter(all_paths, spec.code, band)
            if treat.empty:
                level_results.append(
                    summarize_level_result(
                        spec.code,
                        spec.category if spec.category != "hvn_lvn" else "auction",
                        band,
                        {"n": 0, "match_status": "DATA_INSUFFICIENT", "max_smd": np.nan},
                        beats_simple=False,
                        band_cliff=False,
                    )
                )
                continue

            if band == PRIMARY_BAND_ATR:
                simple_primary[spec.code] = treat

            eval_dict: dict = {"n": len(treat)}
            match_diag = {"status": "N/A", "max_smd": np.nan}

            if spec.category in ("auction", "hvn_lvn") and band == PRIMARY_BAND_ATR:
                cached = match_cache.get(spec.code)
                if cached is None:
                    eval_dict = {"n": len(treat), "match_status": "DATA_INSUFFICIENT", "max_smd": np.nan}
                else:
                    pairs, match_diag = cached
                    if pairs.empty:
                        eval_dict = {
                            "n": len(treat),
                            "match_status": match_diag.get("status"),
                            "max_smd": match_diag.get("max_smd"),
                        }
                    else:
                        treat_matched, ctrl_sub = aligned_matched_paths(treat, pairs, ctrl_path_by_ts)
                        if treat_matched.empty:
                            eval_dict = {
                                "n": len(treat),
                                "match_status": match_diag.get("status"),
                                "max_smd": match_diag.get("max_smd"),
                            }
                        else:
                            eval_dict = evaluate_level_vs_matched(treat_matched, ctrl_sub, match_diag)
            elif spec.category in ("auction", "hvn_lvn"):
                eval_dict = {
                    "n": len(treat),
                    "match_status": "N/A_BAND",
                    "two_sided_15_treat": float(treat["two_sided_range_15m"].mean()),
                }
            else:
                eval_dict = {
                    "n": len(treat),
                    "match_status": "N/A_SIMPLE",
                    "two_sided_15_treat": float(treat["two_sided_range_15m"].mean()),
                }

            # Band cliff across bands for this level
            by_band = {b: _filter(all_paths, spec.code, b) for b in DISTANCE_BANDS_ATR}
            cliff = detect_band_cliff(by_band)

            beats_simple = True
            if spec.code in ("PRIOR_VAH", "DEV_VAH"):
                ref = simple_primary.get("PRIOR_SESSION_HIGH")
                if ref is not None and not ref.empty:
                    lift = treat["two_sided_range_15m"].mean() - ref["two_sided_range_15m"].mean()
                    beats_simple = lift >= 0
            elif spec.code in ("PRIOR_VAL", "DEV_VAL"):
                ref = simple_primary.get("PRIOR_SESSION_LOW")
                if ref is not None and not ref.empty:
                    lift = treat["two_sided_range_15m"].mean() - ref["two_sided_range_15m"].mean()
                    beats_simple = lift >= 0

            level_results.append(
                summarize_level_result(
                    spec.code,
                    spec.category if spec.category != "hvn_lvn" else "auction",
                    band,
                    eval_dict,
                    beats_simple=beats_simple,
                    band_cliff=cliff,
                )
            )

    # Head-to-head at primary band
    for a, b in HEAD_TO_HEAD + PROFILE_VS_ROLLING:
        pa = simple_primary.get(a, pd.DataFrame())
        pb = simple_primary.get(b, pd.DataFrame())
        if not pa.empty and not pb.empty:
            h2h_rows.append(head_to_head_compare(pa, pb, label_a=a, label_b=b))

    verdict = final_phase76_verdict(
        [r for r in level_results if r.get("band_atr") == PRIMARY_BAND_ATR],
        h2h_rows,
    )

    cp = {
        "checkpoint": "10_sr_location_controls",
        "status": "PASS" if verdict != "PHASE76_NO_AUCTION_INFORMATION" else "FAIL",
        "verdict": verdict,
        "primary_band_atr": PRIMARY_BAND_ATR,
        "distance_bands": list(DISTANCE_BANDS_ATR),
        "non_level_pool_n": len(pool),
        "total_interactions": len(all_paths),
        "level_results": level_results,
        "head_to_head": h2h_rows,
        "splits": {"train_frac": TRAIN_FRAC, "val_frac": VAL_FRAC},
        "directional_gate_14": "ALL_FAILED",
    }
    (CHECKPOINTS / "10_sr_location_controls.json").write_text(json.dumps(cp, indent=2, default=str))

    manifest_path = CHECKPOINTS / "CHECKPOINT_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest["10_sr_controls"] = cp["status"]
    manifest["13_matched_controls"] = "PASS" if any(r.get("match_status") == "ACCEPT" for r in level_results) else "FAIL"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    _write_csv(level_results + [{**h, "row_type": "head_to_head"} for h in h2h_rows], REPORTS / "PHASE76_LOCATION_CONTROL.csv")
    _write_md(level_results=level_results, h2h=h2h_rows, verdict=verdict, pool_n=len(pool))

    # Update final report
    final = REPORTS / "PHASE76_FINAL_REPORT.md"
    final.write_text(
        f"# Phase76 — Final Report\n\n"
        f"**Date:** 2026-09-06  \n"
        f"**Verdict:** `{verdict}`\n\n"
        f"## Summary\n\n"
        f"- Directional gate (CP14): **ALL FAILED** — families A,B,D,E,F rejected; C DATA_INSUFFICIENT\n"
        f"- Location control (CP10): `{verdict}`\n\n"
        f"See `PHASE76_LOCATION_CONTROL.md` for full tables.\n\n"
        f"Phase72A comparison: **{'justified' if verdict == 'PHASE76_CONTEXT_FOLLOWUP_JUSTIFIED' else 'NOT justified'}**\n"
    )

    print(f"\nVerdict: {verdict}")
    print(f"Reports: {REPORTS / 'PHASE76_LOCATION_CONTROL.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
