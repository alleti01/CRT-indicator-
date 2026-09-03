"""Build canonical S54 reference streams from frozen Phase53/54 batch pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase53.config import HOLDOUT_END, HOLDOUT_START
from phase53.research.data import load_markets
from phase53.research.metrics import summarize_r
from phase54.research.consolidate import consolidate_time
from phase54.research.parity import add_population_flags, assign_scores, load_events
from phase55.config import P53_REF, P54_REF, REFERENCE, S54_TIME_WINDOW_MIN
from phase55.implementation.s54_execution import simulate_trades


def _holdout_mask(ts: pd.Series) -> pd.Series:
    return (ts >= pd.Timestamp(HOLDOUT_START, tz=ts.dt.tz)) & (ts <= pd.Timestamp(HOLDOUT_END, tz=ts.dt.tz))


def build_reference(*, scored_cache: Path | None = None) -> dict:
    REFERENCE.mkdir(parents=True, exist_ok=True)
    all_ev = load_events()
    ts = pd.to_datetime(all_ev["timestamp_ct"])

    if scored_cache and scored_cache.exists():
        scored = pd.read_parquet(scored_cache)
        scored = add_population_flags(scored)
    else:
        pre = all_ev.loc[~_holdout_mask(ts)]
        scored, _ = assign_scores(pre)
        scored = add_population_flags(scored)

    d10 = scored.loc[scored["top10"]].copy()
    retained, suppressed = consolidate_time(d10, S54_TIME_WINDOW_MIN)

    # WF OOS episodes only (pre-holdout stitched test folds)
    from phase54.run import walkforward_consolidation, _candidate_configs, _holdout_mask as hmask

    m1, _, _ = load_markets()
    ep_oos, wf_sel = walkforward_consolidation(scored, "top10", _candidate_configs(m1["close"].values.astype(float)))

    # Event reference
    ev_ref = scored.copy()
    ev_ref["d10"] = ev_ref["top10"]
    ev_ref["top20_flag"] = ev_ref["top20"]
    ep_map = retained.set_index("event_id")[["episode_id"]].to_dict()["episode_id"]
    sup_set = set(suppressed["event_id"]) if not suppressed.empty else set()
    ev_ref["episode_id"] = ev_ref["event_id"].map(ep_map)
    ev_ref["suppressed"] = ev_ref["event_id"].isin(sup_set)
    ev_ref["s54_entry"] = ev_ref["event_id"].isin(set(retained["event_id"]))
    ev_ref.to_parquet(REFERENCE / "s54_event_reference.parquet", index=False)

    # Episode / trade reference from full D10 Family A (descriptive parity anchor)
    trades = simulate_trades(m1, retained)
    trades["event_id"] = retained["event_id"].values
    trades["episode_id"] = retained["episode_id"].values
    trades["score"] = retained["score"].values
    trades["event_type"] = retained["event_type"].values
    trades["core_authorized"] = retained["core_authorized"].values
    trades.to_csv(REFERENCE / "s54_trade_reference.csv", index=False)

    retained.to_csv(REFERENCE / "s54_episode_reference.csv", index=False)
    ep_oos.to_csv(REFERENCE / "s54_episode_oos_reference.csv", index=False)

    # Bar reference for D10 event bars only (audit trail)
    bar_rows = []
    for _, r in d10.iterrows():
        bar_rows.append(
            {
                "timestamp_ct": r["timestamp_ct"],
                "entry_i": int(r["entry_i"]),
                "event_id": r["event_id"],
                "event_type": r["event_type"],
                "direction": r["direction"],
                "score": r["score"],
                "d10": True,
                "episode_id": ep_map.get(r["event_id"]),
                "suppressed": r["event_id"] in sup_set,
                "s54_entry": r["event_id"] in set(retained["event_id"]),
            }
        )
    pd.DataFrame(bar_rows).to_parquet(REFERENCE / "s54_bar_reference.parquet", index=False)

    # Fixtures — sample episodes
    fixtures = []
    for label, sub in [
        ("long_stop", trades.loc[(trades["direction"] == "LONG") & (trades["exit_reason"] == "STOP")].head(1)),
        ("long_target", trades.loc[(trades["direction"] == "LONG") & (trades["exit_reason"] == "TARGET")].head(1)),
        ("short_time", trades.loc[(trades["direction"] == "SHORT") & (trades["exit_reason"] == "TIME")].head(1)),
        ("core_unauth", trades.loc[trades["core_authorized"] == 0].head(1)),
    ]:
        if not sub.empty:
            fixtures.append({"label": label, "event_id": sub.iloc[0]["event_id"], "episode_id": sub.iloc[0]["episode_id"]})
    (REFERENCE / "parity_fixtures.json").write_text(json.dumps(fixtures, indent=2, default=str) + "\n")

    sm = summarize_r(ep_oos if not ep_oos.empty else retained)
    meta = {
        "total_events": len(all_ev),
        "scored_events": len(scored),
        "d10_events": len(d10),
        "episodes_full": len(retained),
        "episodes_oos": len(ep_oos),
        "p53_ref": P53_REF,
        "p54_ref": P54_REF,
        "episode_perf_oos": sm,
        "wf_selection": wf_sel.to_dict(orient="records"),
    }
    (REFERENCE / "reference_manifest.json").write_text(json.dumps(meta, indent=2, default=str) + "\n")
    return meta


if __name__ == "__main__":
    print(json.dumps(build_reference(), indent=2, default=str))
