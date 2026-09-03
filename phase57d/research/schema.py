"""Phase57D data schemas — column definitions for all result artifacts."""

from __future__ import annotations

WALL_SNAPSHOT_COLUMNS = [
    "timestamp",
    "underlying",
    "mapping",
    "wall_family",
    "wall_id",
    "strike",
    "wall_value",
    "wall_rank",
    "wall_strength_percentile",
    "expiration_bucket",
    "spot",
    "distance_from_spot",
    "distance_atr",
    "source_snapshot_timestamp",
    "valid_from",
    "valid_until",
    "method_version",
]

WALL_CATALOG_COLUMNS = WALL_SNAPSHOT_COLUMNS + [
    "first_seen",
    "last_seen",
    "persistence_bars",
    "session",
]

WALL_INTERACTION_COLUMNS = [
    "interaction_id",
    "wall_id",
    "episode_id",
    "underlying",
    "mapping",
    "wall_family",
    "interaction_type",
    "direction",
    "signal_timestamp",
    "execution_timestamp",
    "entry_price",
    "stop_price",
    "target_price",
    "strike",
    "spot_at_signal",
    "distance_atr_at_signal",
    "wall_strength_percentile",
    "expiration_bucket",
    "entry_stage",
    "valid_from",
    "source_snapshot_timestamp",
]

DATA_PROVENANCE_COLUMNS = [
    "dataset",
    "provider",
    "underlying",
    "options_product",
    "start_date",
    "end_date",
    "snapshot_frequency",
    "timestamp_timezone",
    "OI_frequency",
    "OI_known_time",
    "IV_source",
    "Greeks_source",
    "volume_type",
    "historical_revision_status",
    "point_in_time_verified",
    "known_latency",
    "limitations",
]

AUDIT_FINDING_COLUMNS = [
    "finding_id",
    "severity",
    "category",
    "description",
    "affected_events",
    "causality_impact",
    "performance_impact",
    "requires_fix",
    "status",
]

RESEARCH_REGISTRY_COLUMNS = [
    "experiment_id",
    "timestamp",
    "wall_family",
    "interaction",
    "mapping",
    "expiration_scope",
    "entry_stage",
    "status",
    "raw_n",
    "distinct_n",
    "avg_r",
    "pf",
    "notes",
]

CONFIG_PROVENANCE_COLUMNS = [
    "config_key",
    "config_value",
    "frozen",
    "source",
]

OPTIONS_CHAIN_COLUMNS = [
    "option_symbol",
    "underlying",
    "timestamp",
    "expiration",
    "strike",
    "call_put",
    "bid",
    "ask",
    "mid",
    "last",
    "iv",
    "oi",
    "volume",
    "delta",
    "gamma",
    "vega",
    "theta",
    "underlying_price",
    "multiplier",
    "snapshot_id",
    "known_at",
]
