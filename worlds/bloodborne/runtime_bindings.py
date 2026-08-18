"""Runtime-facing IDs, kept strictly separate from game-design data.

``None`` means unknown, not zero. Fixed-location acquisition flags are derived
from their actual MSB or EMEVD award source and its ItemLotParam row. They
identify the correct save flag, but do not imply that a live flag-manager
accessor has been validated.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeItemBinding:
    normalized_item_id: int | None
    raw_descriptor: int | None
    evidence: str


@dataclass(frozen=True)
class RuntimeLocationBinding:
    event_flag: int | None
    evidence: str
    item_lot_id: int
    source_kind: str
    source_ref: str


ITEM_BINDINGS: dict[str, RuntimeItemBinding] = {
    # Category-4 goods descriptors. The formula is validated against four live inventory records;
    # key-item gate side effects still require end-to-end runtime testing.
    "hunter_chief_emblem": RuntimeItemBinding(0x40000FAB, 0xB0000FAB, "FMG/param + validated goods formula"),
    "cainhurst_summons": RuntimeItemBinding(0x40000FA3, 0xB0000FA3, "FMG/param + validated goods formula"),
    "tonsil_stone": RuntimeItemBinding(0x400010D6, 0xB00010D6, "FMG/param + validated goods formula"),
    "upper_cathedral_key": RuntimeItemBinding(0x40000FAA, 0xB0000FAA, "FMG/param + validated goods formula"),
    "orphanage_key": RuntimeItemBinding(0x40000FA6, 0xB0000FA6, "FMG/param + validated goods formula"),
    "eye_of_blood_drunk_hunter": RuntimeItemBinding(0x400010D7, 0xB00010D7, "FMG/param + validated goods formula"),
    "eye_pendant": RuntimeItemBinding(0x40000FB1, 0xB0000FB1, "FMG/param + validated goods formula"),
    "astral_clocktower_key": RuntimeItemBinding(0x40000FB4, 0xB0000FB4, "FMG/param + validated goods formula"),
    "celestial_dial": RuntimeItemBinding(0x40000FB5, 0xB0000FB5, "FMG/param + validated goods formula"),
    "laurences_skull": RuntimeItemBinding(0x40000FAE, 0xB0000FAE, "FMG/param + validated goods formula"),
}

LOCATION_BINDINGS: dict[str, RuntimeLocationBinding] = {
    "pickup_cainhurst_summons": RuntimeLocationBinding(
        52410990, "EMEVD award m24_01_00_00:2310 + ItemLotParam 2410990 acquisition flag",
        2410990, "script_award", "m24_01_00_00.emevd.dcx.js:2310"),
    "pickup_upper_cathedral_key": RuntimeLocationBinding(
        52800290, "MSB treasure m28_00_00_00/m28_00_00_01 + ItemLotParam 2800290 acquisition flag",
        2800290, "treasure", "m28_00_00_00;m28_00_00_01"),
    "script_award_orphanage_key": RuntimeLocationBinding(
        52420900, "EMEVD award m24_02_00_00:252 + ItemLotParam 2420900 acquisition flag",
        2420900, "script_award", "m24_02_00_00.emevd.dcx.js:252"),
    "pickup_eye_of_blood_drunk_hunter": RuntimeLocationBinding(
        50000100, "EMEVD award m21_00_00_00:3002 + ItemLotParam 10040 acquisition flag",
        10040, "script_award", "m21_00_00_00.emevd.dcx.js:3002"),
    "pickup_eye_pendant": RuntimeLocationBinding(
        9470, "EMEVD award m34_00_00_00:1725 + ItemLotParam 3401810 acquisition flag",
        3401810, "script_award", "m34_00_00_00.emevd.dcx.js:1725"),
    "pickup_laurences_skull": RuntimeLocationBinding(
        53502000, "EMEVD award m35_00_00_00:1832 + ItemLotParam 3502000 acquisition flag",
        3502000, "script_award", "m35_00_00_00.emevd.dcx.js:1832"),
}

# Known delivery fixtures, not currently part of the randomized design pool.
DELIVERY_FIXTURES: dict[str, RuntimeItemBinding] = {
    "quicksilver_bullet": RuntimeItemBinding(0x40000384, 0xB0000384, "validated/observed"),
    "blood_vial": RuntimeItemBinding(0x400003E8, 0xB00003E8, "inferred/observed"),
    "pebble": RuntimeItemBinding(0x400004CE, 0xB00004CE, "observed"),
    "augur_of_ebrietas": RuntimeItemBinding(0x400007D0, 0xB00007D0, "observed"),
}
