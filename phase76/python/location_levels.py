"""Location level specifications — auction vs simple S/R (frozen)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Category = Literal["auction", "simple", "hvn_lvn"]


@dataclass(frozen=True)
class LevelSpec:
    code: str
    category: Category
    column: str | None  # feature column for level price; None for HVN/LVN zone flags
    zone_flag: str | None = None  # in_hvn / in_lvn for zone-based levels


AUCTION_LEVELS: tuple[LevelSpec, ...] = (
    LevelSpec("PRIOR_VAH", "auction", "prior_vah"),
    LevelSpec("PRIOR_VAL", "auction", "prior_val"),
    LevelSpec("DEV_VAH", "auction", "dev_vah"),
    LevelSpec("DEV_VAL", "auction", "dev_val"),
    LevelSpec("PRIOR_POC", "auction", "prior_poc"),
    LevelSpec("DEV_POC", "auction", "dev_poc"),
    LevelSpec("VWAP", "auction", "dev_vwap"),
    LevelSpec("HVN_ZONE", "hvn_lvn", None, zone_flag="in_hvn"),
    LevelSpec("LVN_ZONE", "hvn_lvn", None, zone_flag="in_lvn"),
)

SIMPLE_LEVELS: tuple[LevelSpec, ...] = (
    LevelSpec("PRIOR_SESSION_HIGH", "simple", "prior_high"),
    LevelSpec("PRIOR_SESSION_LOW", "simple", "prior_low"),
    LevelSpec("OVERNIGHT_HIGH", "simple", "overnight_high_session"),
    LevelSpec("OVERNIGHT_LOW", "simple", "overnight_low_session"),
    LevelSpec("OR_HIGH", "simple", "or_high"),
    LevelSpec("OR_LOW", "simple", "or_low"),
    LevelSpec("ROLL_5M_HIGH", "simple", "roll_high_5"),
    LevelSpec("ROLL_5M_LOW", "simple", "roll_low_5"),
    LevelSpec("ROLL_10M_HIGH", "simple", "roll_high_10"),
    LevelSpec("ROLL_10M_LOW", "simple", "roll_low_10"),
    LevelSpec("ROLL_20M_HIGH", "simple", "roll_high_20"),
    LevelSpec("ROLL_20M_LOW", "simple", "roll_low_20"),
    LevelSpec("ROLL_30M_HIGH", "simple", "roll_high_30"),
    LevelSpec("ROLL_30M_LOW", "simple", "roll_low_30"),
)

ALL_LEVELS = AUCTION_LEVELS + SIMPLE_LEVELS

AUCTION_CODES = {s.code for s in AUCTION_LEVELS if s.category == "auction" or s.category == "hvn_lvn"}
