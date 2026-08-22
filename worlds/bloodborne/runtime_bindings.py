"""Runtime-facing IDs, kept strictly separate from game-design data.

``None`` means unknown, not zero. Fixed-location acquisition flags are derived
from their actual MSB or EMEVD award source and its ItemLotParam row. They
identify the correct save flag, but do not imply that a live flag-manager
accessor has been validated.
"""

from dataclasses import dataclass

from .fixed_locations import FIXED_LOCATIONS


@dataclass(frozen=True)
class RuntimeItemBinding:
    normalized_item_id: int | None
    raw_descriptor: int | None
    evidence: str
    item_category: int = 4
    descriptor_evidence: str = "goods_formula_observed"
    # Address-free receive policy. Every equipment row must declare these
    # fields rather than asking the client to infer semantics from an ID.
    feed_effect: str = "not_equippable"
    reinforcement_level: int | None = None


@dataclass(frozen=True)
class RuntimeEquipmentExclusion:
    item_lot_id: int
    catalog_item_id: int
    attempted_raw_descriptor: int
    observed_normalized_item_id: int
    evidence: str


def validate_runtime_item_binding(key: str, binding: RuntimeItemBinding, quantity: int) -> None:
    """Reject runtime rows that do not carry the evidence their category needs."""
    if binding.normalized_item_id is None or binding.raw_descriptor is None:
        raise ValueError(f"{key}: runtime descriptor is not mapped")
    if not 1 <= quantity <= 99:
        raise ValueError(f"{key}: quantity {quantity} is outside the grant contract")
    if binding.item_category == 4:
        compatible = (
            binding.normalized_item_id & 0xF0000000 == 0x40000000
            and binding.raw_descriptor & 0xF0000000 == 0xB0000000
            and binding.normalized_item_id & 0x0FFFFFFF
            == binding.raw_descriptor & 0x0FFFFFFF
        )
        if not compatible or binding.descriptor_evidence != "goods_formula_observed":
            raise ValueError(f"{key}: category-4 descriptor lacks observed formula evidence")
        if binding.reinforcement_level is not None:
            raise ValueError(f"{key}: category-4 goods cannot have a reinforcement level")
        return
    if binding.item_category == 0:
        compatible = (
            binding.normalized_item_id & 0xF0000000 == 0
            and binding.raw_descriptor & 0xF0000000 == 0x80000000
            and binding.normalized_item_id & 0x0FFFFFFF
            == binding.raw_descriptor & 0x0FFFFFFF
        )
        if not compatible or binding.descriptor_evidence != "live_grant_inventory_ui":
            raise ValueError(f"{key}: category-0 descriptor is not live-validated")
        if quantity != 1 or binding.reinforcement_level is None:
            raise ValueError(f"{key}: category-0 weapon policy is incomplete")
        if binding.feed_effect not in {"right_hand_weapon", "left_hand_weapon"}:
            raise ValueError(f"{key}: category-0 weapon has incompatible feed policy")
        return
    raise ValueError(f"{key}: unsupported item category {binding.item_category}")


@dataclass(frozen=True)
class RuntimeLocationBinding:
    event_flag: int | None
    evidence: str
    item_lot_id: int | None
    source_kind: str
    source_ref: str
    item_category: int | None
    item_id: int | None


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
    # Category-0 equipment has no ItemLot-to-runtime formula. Each row here is
    # a live canary, not a derivation from fixed_locations.tsv.
    "saw_spear": RuntimeItemBinding(
        0x006C5660,
        0x806C5660,
        "clean-save native grant returned slot 77 and appeared in inventory UI",
        item_category=0,
        descriptor_evidence="live_grant_inventory_ui",
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "quicksilver_bullets": RuntimeItemBinding(
        0x40000384, 0xB0000384, "live grant and decrement observed"
    ),
    "pebbles": RuntimeItemBinding(
        0x400004CE, 0xB00004CE, "live grant and inventory persistence observed"
    ),
    "molotov_cocktails": RuntimeItemBinding(
        0x400004B0, 0xB00004B0, "catalog id + validated category-4 goods formula"
    ),
    "blood_stone_shards": RuntimeItemBinding(
        0x40000BB8, 0xB0000BB8, "catalog id + validated category-4 goods formula"
    ),
    "augur_of_ebrietas": RuntimeItemBinding(
        0x400007D0, 0xB00007D0, "live grant and inventory persistence observed"
    ),
}

# Negative canaries are executable exclusions. Keeping them next to the
# allowlist makes it impossible for generation code to quietly reintroduce the
# rejected ItemLot-ID inference.
EQUIPMENT_EXCLUSIONS: dict[str, RuntimeEquipmentExclusion] = {
    "torch": RuntimeEquipmentExclusion(
        item_lot_id=2410520,
        catalog_item_id=20100000,
        attempted_raw_descriptor=0x8132B3A0,
        observed_normalized_item_id=0x0032B3A0,
        evidence=(
            "r5 native call allocated a record but no Torch appeared in the UI; "
            "the throwaway save was discarded"
        ),
    ),
}

LOCATION_BINDINGS: dict[str, RuntimeLocationBinding] = {
    "boss_cleric_beast": RuntimeLocationBinding(
        12411700,
        "EMEVD boss-completion flag; m24_01_00_00 event 12411700 is paired with 12411800",
        None,
        "boss_defeat",
        "m24_01_00_00.emevd.dcx.js:1047",
        None,
        None,
    ),
    "boss_father_gascoigne": RuntimeLocationBinding(
        12411800,
        "EMEVD boss-completion flag; event 12411800 gates the arena, key award, and world state",
        None,
        "boss_defeat",
        "m24_01_00_00.emevd.dcx.js:1394-1417",
        None,
        None,
    ),
    # Boss-completion flags mapped 2026-08-22 from the committed EMEVD
    # decompiles (research/bb_inputs.db): each event waits CharacterDead on the
    # boss entity and calls HandleBossDefeat on it; the event ID is the defeat
    # flag, same convention as 12411700/12411800 above. The dev name strings in
    # each map's string table identify the boss (Cleric Beast is 教区長, so the
    # strings are internal names, not the shipped ones).
    "boss_blood_starved_beast": RuntimeLocationBinding(
        12301800,
        "EMEVD boss-completion flag; event 12301800 defeats entity 2300800 (血に渇いた獣)",
        None,
        "boss_defeat",
        "m23_00_00_00.emevd.dcx.js:497-537",
        None,
        None,
    ),
    "boss_vicar_amelia": RuntimeLocationBinding(
        12401800,
        "EMEVD boss-completion flag; event 12401800 defeats entity 2400800 (聖女ビースト)",
        None,
        "boss_defeat",
        "m24_00_00_00.emevd.dcx.js:4287-4331",
        None,
        None,
    ),
    "boss_shadows_of_yharnam": RuntimeLocationBinding(
        12701800,
        "EMEVD boss-completion flag; event 12701800 defeats entity 2700800 (闇の旅団)",
        None,
        "boss_defeat",
        "m27_00_00_00.emevd.dcx.js:386-442",
        None,
        None,
    ),
    "boss_rom": RuntimeLocationBinding(
        13201800,
        "EMEVD boss-completion flag; event 13201800 defeats entity 3200800 (白痴の蜘蛛)",
        None,
        "boss_defeat",
        "m32_00_00_00.emevd.dcx.js:664-705",
        None,
        None,
    ),
    "boss_the_one_reborn": RuntimeLocationBinding(
        12801800,
        "EMEVD boss-completion flag; event 12801800 defeats entity 2800803 (なりそこないの邪神)",
        None,
        "boss_defeat",
        "m28_00_00_00.emevd.dcx.js:1571-1638",
        None,
        None,
    ),
    "boss_micolash": RuntimeLocationBinding(
        12601850,
        "EMEVD boss-completion flag; event 12601850 defeats entity 2600850 (悪夢の主)",
        None,
        "boss_defeat",
        "m26_00_00_00.emevd.dcx.js:929-983",
        None,
        None,
    ),
    "boss_mergos_wet_nurse": RuntimeLocationBinding(
        12601800,
        "EMEVD boss-completion flag; event 12601800 defeats entity 2600803 (死と闇レッサー)",
        None,
        "boss_defeat",
        "m26_00_00_00.emevd.dcx.js:537-587",
        None,
        None,
    ),
    "boss_ludwig": RuntimeLocationBinding(
        13401800,
        "EMEVD boss-completion flag; event 13401800 defeats entities 3400800/3400801 (ルドウイーク)",
        None,
        "boss_defeat",
        "m34_00_00_00.emevd.dcx.js:793-854",
        None,
        None,
    ),
    "boss_living_failures": RuntimeLocationBinding(
        13501850,
        "EMEVD boss-completion flag; event 13501850 defeats entity 3500850 (患者B)",
        None,
        "boss_defeat",
        "m35_00_00_00.emevd.dcx.js:1053-1106",
        None,
        None,
    ),
    "boss_lady_maria": RuntimeLocationBinding(
        13501800,
        "EMEVD boss-completion flag; event 13501800 defeats entity 3500800 (女性ハンター)",
        None,
        "boss_defeat",
        "m35_00_00_00.emevd.dcx.js:700-743",
        None,
        None,
    ),
    "boss_orphan_of_kos": RuntimeLocationBinding(
        13601800,
        "EMEVD boss-completion flag; event 13601800 defeats entities 3600800/3600801 (ラスボス)",
        None,
        "boss_defeat",
        "m36_00_00_00.emevd.dcx.js:715-761",
        None,
        None,
    ),
    "boss_laurence": RuntimeLocationBinding(
        13401850,
        "EMEVD boss-completion flag; event 13401850 defeats entity 3400850 (教区長Ω)",
        None,
        "boss_defeat",
        "m34_00_00_00.emevd.dcx.js:1312-1358",
        None,
        None,
    ),
    "pickup_cainhurst_summons": RuntimeLocationBinding(
        52410990, "EMEVD award m24_01_00_00:2310 + ItemLotParam 2410990 acquisition flag",
        2410990, "script_award", "m24_01_00_00.emevd.dcx.js:2310", 4, 4003),
    "pickup_upper_cathedral_key": RuntimeLocationBinding(
        52800290, "MSB treasure m28_00_00_00/m28_00_00_01 + ItemLotParam 2800290 acquisition flag",
        2800290, "treasure", "m28_00_00_00;m28_00_00_01", 4, 4010),
    "script_award_orphanage_key": RuntimeLocationBinding(
        52420900, "EMEVD award m24_02_00_00:252 + ItemLotParam 2420900 acquisition flag",
        2420900, "script_award", "m24_02_00_00.emevd.dcx.js:252", 4, 4006),
    "pickup_eye_of_blood_drunk_hunter": RuntimeLocationBinding(
        50000100, "EMEVD award m21_00_00_00:3002 + ItemLotParam 10040 acquisition flag",
        10040, "script_award", "m21_00_00_00.emevd.dcx.js:3002", 4, 4311),
    "pickup_eye_pendant": RuntimeLocationBinding(
        9470, "EMEVD award m34_00_00_00:1725 + ItemLotParam 3401810 acquisition flag",
        3401810, "script_award", "m34_00_00_00.emevd.dcx.js:1725", 4, 4017),
    "pickup_laurences_skull": RuntimeLocationBinding(
        53502000, "EMEVD award m35_00_00_00:1832 + ItemLotParam 3502000 acquisition flag",
        3502000, "script_award", "m35_00_00_00.emevd.dcx.js:1832", 4, 4014),
    "treasure_old_hunter_bone": RuntimeLocationBinding(
        52110000, "MSB treasure m21_01_00_00 + ItemLotParam 2110000 acquisition flag",
        2110000, "treasure", "m21_01_00_00", 4, 2060),
    "treasure_rune_workshop_tool": RuntimeLocationBinding(
        52200360, "MSB treasure m22_00_00_00 + ItemLotParam 2200360 acquisition flag",
        2200360, "treasure", "m22_00_00_00", 4, 4104),
    "treasure_radiant_sword_hunter_badge": RuntimeLocationBinding(
        52400480, "MSB treasure m24_00_00_00/m24_00_00_01 + ItemLotParam 2400480 acquisition flag",
        2400480, "treasure", "m24_00_00_00;m24_00_00_01", 4, 4115),
    "treasure_cosmic_eye_watcher_badge": RuntimeLocationBinding(
        52420270, "MSB treasure m24_02_00_00/m24_02_00_01 + ItemLotParam 2420270 acquisition flag",
        2420270, "treasure", "m24_02_00_00;m24_02_00_01", 4, 4119),
    "treasure_executioners_gloves": RuntimeLocationBinding(
        52500250, "MSB treasure m25_00_00_00 + ItemLotParam 2500250 acquisition flag",
        2500250, "treasure", "m25_00_00_00", 4, 2080),
    "treasure_augur_of_ebrietas": RuntimeLocationBinding(
        53200600, "MSB treasure m32_00_00_00/m32_00_00_01 + ItemLotParam 3200600 acquisition flag",
        3200600, "treasure", "m32_00_00_00;m32_00_00_01", 4, 2000),
    "treasure_lecture_theatre_key": RuntimeLocationBinding(
        53200720, "MSB treasure m32_00_00_00/m32_00_00_01 + ItemLotParam 3200720 acquisition flag",
        3200720, "treasure", "m32_00_00_00;m32_00_00_01", 4, 4012),
    "treasure_messengers_gift": RuntimeLocationBinding(
        53300330, "MSB treasure m33_00_00_00 + ItemLotParam 3300230 acquisition flag",
        3300230, "treasure", "m33_00_00_00", 4, 2110),
    "treasure_underground_jail_chunk": RuntimeLocationBinding(
        53500630, "MSB treasure m35_00_00_00 + ItemLotParam 3500630 acquisition flag",
        3500630, "treasure", "m35_00_00_00", 4, 3020),
    "treasure_underground_cell_inner_chamber_key": RuntimeLocationBinding(
        50002360, "MSB treasure m36_00_00_00 + ItemLotParam 43221 acquisition flag",
        43221, "treasure", "m36_00_00_00", 4, 4015),
}

for location in FIXED_LOCATIONS:
    if location.key in LOCATION_BINDINGS:
        raise ValueError(f"duplicate runtime location binding: {location.key}")
    LOCATION_BINDINGS[location.key] = RuntimeLocationBinding(
        location.event_flag,
        f"fixed location catalog + ItemLotParam {location.item_lot_id} acquisition flag",
        location.item_lot_id,
        location.source_kind,
        location.source_ref,
        location.item_category,
        location.item_id,
    )

# Known delivery fixtures, not currently part of the randomized design pool.
DELIVERY_FIXTURES: dict[str, RuntimeItemBinding] = {
    "quicksilver_bullet": ITEM_BINDINGS["quicksilver_bullets"],
    "blood_vial": RuntimeItemBinding(0x400003E8, 0xB00003E8, "inferred/observed"),
    "pebble": ITEM_BINDINGS["pebbles"],
    "augur_of_ebrietas": ITEM_BINDINGS["augur_of_ebrietas"],
}
