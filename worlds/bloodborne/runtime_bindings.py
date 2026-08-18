"""Runtime-facing IDs, kept strictly separate from game-design data.

``None`` means unknown, not zero. Fixed-pickup acquisition flags are statically
derived from MSB treasure -> ItemLotParam joins. They identify the correct save
flag, but do not imply that a live flag-manager accessor has been validated.
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
    "pickup_cainhurst_summons": RuntimeLocationBinding(52410990, "MSB treasure + ItemLotParam acquisition flag"),
    "pickup_upper_cathedral_key": RuntimeLocationBinding(52800290, "MSB treasure + ItemLotParam acquisition flag"),
    "pickup_orphanage_key": RuntimeLocationBinding(52420900, "MSB treasure + ItemLotParam acquisition flag"),
    "pickup_eye_of_blood_drunk_hunter": RuntimeLocationBinding(50000100, "scripted treasure + ItemLotParam acquisition flag"),
    "pickup_eye_pendant": RuntimeLocationBinding(9470, "scripted treasure + ItemLotParam acquisition flag"),
    "pickup_laurences_skull": RuntimeLocationBinding(53502000, "scripted treasure + ItemLotParam acquisition flag"),
}

# Known delivery fixtures, not currently part of the randomized design pool.
DELIVERY_FIXTURES: dict[str, RuntimeItemBinding] = {
    "quicksilver_bullet": RuntimeItemBinding(0x40000384, 0xB0000384, "validated/observed"),
    "blood_vial": RuntimeItemBinding(0x400003E8, 0xB00003E8, "inferred/observed"),
    "pebble": RuntimeItemBinding(0x400004CE, 0xB00004CE, "observed"),
    "augur_of_ebrietas": RuntimeItemBinding(0x400007D0, 0xB00007D0, "observed"),
}
