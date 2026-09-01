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


# Category-0 descriptors carry their provenance in the binding rather than in a
# comment. `live_grant_inventory_ui` is a witnessed insert. `param_id_inferred`
# is an id read out of community EquipParamWeapon documentation and NOT yet
# witnessed in a live inventory -- the bundle does not pack EquipParamWeapon, so
# nothing in this repo can promote it. Promotion is a first live insert seen in
# the delivery-diagnostics jsonl (clients#446), which turns the row into
# `live_grant_inventory_ui` in the same commit that cites the record.
LIVE_CATEGORY_0_EVIDENCE = "live_grant_inventory_ui"
INFERRED_CATEGORY_0_EVIDENCE = "param_id_inferred"
CATEGORY_0_EVIDENCE = frozenset({LIVE_CATEGORY_0_EVIDENCE, INFERRED_CATEGORY_0_EVIDENCE})


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
        if not compatible or binding.descriptor_evidence not in CATEGORY_0_EVIDENCE:
            raise ValueError(f"{key}: category-0 descriptor is not live-validated")
        if quantity != 1 or binding.reinforcement_level is None:
            raise ValueError(f"{key}: category-0 weapon policy is incomplete")
        if binding.feed_effect not in {"right_hand_weapon", "left_hand_weapon"}:
            raise ValueError(f"{key}: category-0 weapon has incompatible feed policy")
        return
    if binding.item_category == 255:
        if (binding.normalized_item_id != binding.raw_descriptor
                or binding.descriptor_evidence != "event_flag_effect"
                or quantity != 1
                or binding.reinforcement_level is not None):
            raise ValueError(f"{key}: invalid event-flag receive effect")
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
    # Usually the AP check flag is also the ItemLotParam acquisition flag.
    # Scripted replacements can differ: the Eye gift check is the completed
    # EMEVD interaction, while its suppressed lot retains its native flag.
    item_lot_flag: int | None = None


ITEM_BINDINGS: dict[str, RuntimeItemBinding] = {
    "blood_gem_workshop_tool": RuntimeItemBinding(0x40001007, 0xB0001007, "bundled ItemLot + validated category-4 goods formula"),
    "rune_workshop_tool": RuntimeItemBinding(0x40001008, 0xB0001008, "bundled ItemLot + validated category-4 goods formula"),
    # Category-4 goods descriptors. The formula is validated against four live inventory records;
    # key-item gate side effects still require end-to-end runtime testing.
    "hunter_chief_emblem": RuntimeItemBinding(0x40000FAB, 0xB0000FAB, "FMG/param + validated goods formula"),
    # EquipParamGoods 4000 (聖堂街Bの鍵), the Oedon Tomb Key. lot_items.tsv
    # carries the same normalized/raw pair for lot 31000, derived by the same
    # category-4 formula (0x40000000|id, 0xB0000000|id) validated live against
    # four inventory records. `inferred`: no live grant of goods 4000 has been
    # observed, and no live confirmation that an AP-granted copy satisfies
    # ObjActParam 2410080 on door 2411304 -- see docs/VANILLA-SUPPRESSION.md.
    "oedon_tomb_key": RuntimeItemBinding(0x40000FA0, 0xB0000FA0, "FMG/param + validated goods formula"),
    "lunarium_key": RuntimeItemBinding(
        0x40000FAD, 0xB0000FAD,
        "EquipParamGoods 4013 + ItemLotParam 3200810; validated category-4 goods formula"),
    "forbidden_woods_password": RuntimeItemBinding(
        12401803, 12401803,
        "vanilla Grand Cathedral memory event flag; delivered as an idempotent event-flag effect",
        item_category=255, descriptor_evidence="event_flag_effect"),
    "cainhurst_summons": RuntimeItemBinding(0x40000FA3, 0xB0000FA3, "FMG/param + validated goods formula"),
    "tonsil_stone": RuntimeItemBinding(0x400010D6, 0xB00010D6, "FMG/param + validated goods formula"),
    "upper_cathedral_key": RuntimeItemBinding(0x40000FAA, 0xB0000FAA, "FMG/param + validated goods formula"),
    "orphanage_key": RuntimeItemBinding(0x40000FA6, 0xB0000FA6, "FMG/param + validated goods formula"),
    "eye_of_blood_drunk_hunter": RuntimeItemBinding(0x400010D7, 0xB00010D7, "FMG/param + validated goods formula"),
    "eye_pendant": RuntimeItemBinding(0x40000FB1, 0xB0000FB1, "FMG/param + validated goods formula"),
    "astral_clocktower_key": RuntimeItemBinding(0x40000FB4, 0xB0000FB4, "FMG/param + validated goods formula"),
    "celestial_dial": RuntimeItemBinding(0x40000FB5, 0xB0000FB5, "FMG/param + validated goods formula"),
    "sword_hunter_badge": RuntimeItemBinding(
        0x40001012, 0xB0001012,
        "EquipParamGoods 4114 + Cleric Beast lot 50000010; validated category-4 goods formula"),
    "old_hunter_badge": RuntimeItemBinding(
        0x40001011, 0xB0001011,
        "EquipParamGoods 4113 + Gehrman lots 15000/2100500; validated category-4 goods formula"),
    "saw_hunter_badge": RuntimeItemBinding(
        0x4000100E, 0xB000100E,
        "EquipParamGoods 4110 + ItemLotParam 2410290; validated category-4 goods formula"),
    "crow_hunter_badge": RuntimeItemBinding(
        0x4000100F, 0xB000100F,
        "EquipParamGoods 4111 + Eileen lots 35012/35020/35030; validated category-4 goods formula"),
    "powder_keg_hunter_badge": RuntimeItemBinding(
        0x40001010, 0xB0001010,
        "EquipParamGoods 4112 + Djura lots 33000/33010; validated category-4 goods formula"),
    "radiant_sword_hunter_badge": RuntimeItemBinding(
        0x40001013, 0xB0001013,
        "EquipParamGoods 4115 + ItemLotParam 2400480; validated category-4 goods formula"),
    "wheel_hunter_badge": RuntimeItemBinding(
        0x40001014, 0xB0001014,
        "EquipParamGoods 4116 + Alfred lots 34010/34031; validated category-4 goods formula"),
    "cainhurst_badge": RuntimeItemBinding(
        0x40001015, 0xB0001015,
        "EquipParamGoods 4117 + Annalise oath lot 17001; validated category-4 goods formula"),
    "spark_hunter_badge": RuntimeItemBinding(
        0x40001016, 0xB0001016,
        "EquipParamGoods 4118 + Darkbeast Paarl lot 50800000; validated category-4 goods formula"),
    "cosmic_eye_watcher_badge": RuntimeItemBinding(
        0x40001017, 0xB0001017,
        "EquipParamGoods 4119 + ItemLotParam 2420270/2420280; validated category-4 goods formula"),
    "gold_pendant": RuntimeItemBinding(
        0x40000FA1, 0xB0000FA1,
        "EquipParamGoods 4001 + Vicar Amelia lot 50000001; validated category-4 goods formula"),
    "third_umbilical_cord_1": RuntimeItemBinding(
        0x400010E3, 0xB00010E3,
        "EquipParamGoods 4323 + lot 55100000; validated category-4 goods formula"),
    "third_umbilical_cord_2": RuntimeItemBinding(
        0x400010E3, 0xB00010E3,
        "EquipParamGoods 4323 + lot 55100000; validated category-4 goods formula"),
    "third_umbilical_cord_3": RuntimeItemBinding(
        0x400010E3, 0xB00010E3,
        "EquipParamGoods 4323 + lot 55100000; validated category-4 goods formula"),
    "third_umbilical_cord_4": RuntimeItemBinding(
        0x400010E3, 0xB00010E3,
        "EquipParamGoods 4323 + lot 55100000; validated category-4 goods formula"),
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
    "chikage": RuntimeItemBinding(
        0x001E8480,
        0x801E8480,
        "EquipParamWeapon 2000000 (Chikage); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "blade_of_mercy": RuntimeItemBinding(
        0x003D0900,
        0x803D0900,
        "EquipParamWeapon 4000000 (Blade of Mercy); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "hunter_axe": RuntimeItemBinding(
        0x004C4B40,
        0x804C4B40,
        "EquipParamWeapon 5000000 (Hunter Axe); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "burial_blade": RuntimeItemBinding(
        0x004DD1E0,
        0x804DD1E0,
        "EquipParamWeapon 5100000 (Burial Blade); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "saw_cleaver": RuntimeItemBinding(
        0x006ACFC0,
        0x806ACFC0,
        "EquipParamWeapon 7000000 (Saw Cleaver); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "kirkhammer": RuntimeItemBinding(
        0x007A1200,
        0x807A1200,
        "EquipParamWeapon 8000000 (Kirkhammer); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "ludwigs_holy_blade": RuntimeItemBinding(
        0x007B98A0,
        0x807B98A0,
        "EquipParamWeapon 8100000 (Ludwig's Holy Blade); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "beast_claw": RuntimeItemBinding(
        0x00895440,
        0x80895440,
        "EquipParamWeapon 9000000 (Beast Claw); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "rifle_spear": RuntimeItemBinding(
        0x00989680,
        0x80989680,
        "EquipParamWeapon 10000000 (Rifle Spear); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "reiterpallasch": RuntimeItemBinding(
        0x009A1D20,
        0x809A1D20,
        "EquipParamWeapon 10100000 (Reiterpallasch); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "stake_driver": RuntimeItemBinding(
        0x00A7D8C0,
        0x80A7D8C0,
        "EquipParamWeapon 11000000 (Stake Driver); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "logarius_wheel": RuntimeItemBinding(
        0x00B71B00,
        0x80B71B00,
        "EquipParamWeapon 12000000 (Logarius' Wheel); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "tonitrus": RuntimeItemBinding(
        0x00C65D40,
        0x80C65D40,
        "EquipParamWeapon 13000000 (Tonitrus); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "threaded_cane": RuntimeItemBinding(
        0x014FB180,
        0x814FB180,
        "EquipParamWeapon 22000000 (Threaded Cane); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "hunter_blunderbuss": RuntimeItemBinding(
        0x005B8D80,
        0x805B8D80,
        "EquipParamWeapon 6000000 (Hunter Blunderbuss); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="left_hand_weapon",
        reinforcement_level=0,
    ),
    "ludwigs_rifle": RuntimeItemBinding(
        0x005D1420,
        0x805D1420,
        "EquipParamWeapon 6100000 (Ludwig's Rifle); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="left_hand_weapon",
        reinforcement_level=0,
    ),
    "hunter_pistol": RuntimeItemBinding(
        0x00D59F80,
        0x80D59F80,
        "EquipParamWeapon 14000000 (Hunter Pistol); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="left_hand_weapon",
        reinforcement_level=0,
    ),
    "repeating_pistol": RuntimeItemBinding(
        0x00D8ACC0,
        0x80D8ACC0,
        "EquipParamWeapon 14200000 (Repeating Pistol); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="left_hand_weapon",
        reinforcement_level=0,
    ),
    "cannon": RuntimeItemBinding(
        0x00E4E1C0,
        0x80E4E1C0,
        "EquipParamWeapon 15000000 (Cannon); Smithbox BB row names and the Bloodborne "
        "save editor's weapons.json agree on the id. Descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="left_hand_weapon",
        reinforcement_level=0,
    ),
    # bb-archipelago#205. Uncanny Saw Spear, EquipParamWeapon 7110000 = base
    # weapon id 7100000 + 10000. The +10000/+20000 (Uncanny/Lost) offsets are
    # corroborated by two independent community corpora -- Smithbox's BB
    # EquipParamWeapon row names and the Bloodborne save editor's weapons.json --
    # and the same three-row spacing is visible in this repo's own bundle:
    # research/joined/lot_items.tsv has category-0 rows 7100000 (Central Yharnam
    # lot 2410100), 7110000 and 7120000, the latter two only in chalice
    # ("ユニーク【レベルN】トゥメル") lots, which is exactly where the variants live.
    # `inferred`: no live grant of 7110000 has been observed. The descriptor
    # formula itself is the live one validated on the Saw Spear.
    "uncanny_saw_spear": RuntimeItemBinding(
        0x006C7D70,
        0x806C7D70,
        "EquipParamWeapon 7110000 = Saw Spear 7100000 + the Uncanny offset; "
        "id from community param documentation, descriptor formula from the "
        "live Saw Spear grant. Not yet witnessed in a live inventory.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_chikage": RuntimeItemBinding(
        0x001EAB90,
        0x801EAB90,
        "EquipParamWeapon 2010000 = Chikage 2000000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_blade_of_mercy": RuntimeItemBinding(
        0x003D3010,
        0x803D3010,
        "EquipParamWeapon 4010000 = Blade of Mercy 4000000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_hunter_axe": RuntimeItemBinding(
        0x004C7250,
        0x804C7250,
        "EquipParamWeapon 5010000 = Hunter Axe 5000000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_burial_blade": RuntimeItemBinding(
        0x004DF8F0,
        0x804DF8F0,
        "EquipParamWeapon 5110000 = Burial Blade 5100000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_saw_cleaver": RuntimeItemBinding(
        0x006AF6D0,
        0x806AF6D0,
        "EquipParamWeapon 7010000 = Saw Cleaver 7000000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_kirkhammer": RuntimeItemBinding(
        0x007A3910,
        0x807A3910,
        "EquipParamWeapon 8010000 = Kirkhammer 8000000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_ludwigs_holy_blade": RuntimeItemBinding(
        0x007BBFB0,
        0x807BBFB0,
        "EquipParamWeapon 8110000 = Ludwig's Holy Blade 8100000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_beast_claw": RuntimeItemBinding(
        0x00897B50,
        0x80897B50,
        "EquipParamWeapon 9010000 = Beast Claw 9000000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_rifle_spear": RuntimeItemBinding(
        0x0098BD90,
        0x8098BD90,
        "EquipParamWeapon 10010000 = Rifle Spear 10000000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_reiterpallasch": RuntimeItemBinding(
        0x009A4430,
        0x809A4430,
        "EquipParamWeapon 10110000 = Reiterpallasch 10100000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_stake_driver": RuntimeItemBinding(
        0x00A7FFD0,
        0x80A7FFD0,
        "EquipParamWeapon 11010000 = Stake Driver 11000000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_logarius_wheel": RuntimeItemBinding(
        0x00B74210,
        0x80B74210,
        "EquipParamWeapon 12010000 = Logarius' Wheel 12000000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_tonitrus": RuntimeItemBinding(
        0x00C68450,
        0x80C68450,
        "EquipParamWeapon 13010000 = Tonitrus 13000000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
        feed_effect="right_hand_weapon",
        reinforcement_level=0,
    ),
    "uncanny_threaded_cane": RuntimeItemBinding(
        0x014FD890,
        0x814FD890,
        "EquipParamWeapon 22010000 = Threaded Cane 22000000 + the Uncanny offset; both rows named "
        "in Smithbox and in the save editor's weapons.json. Not yet witnessed live.",
        item_category=0,
        descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE,
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
    "twin_blood_stone_shards": RuntimeItemBinding(
        0x40000BC2, 0xB0000BC2, "catalog id + validated category-4 goods formula"
    ),
    "blood_stone_chunks": RuntimeItemBinding(
        0x40000BCC, 0xB0000BCC, "catalog id + validated category-4 goods formula"
    ),
    "blood_rock": RuntimeItemBinding(
        0x40000BD6, 0xB0000BD6, "catalog id + validated category-4 goods formula"
    ),
    "augur_of_ebrietas": RuntimeItemBinding(
        0x400007D0, 0xB00007D0, "live grant and inventory persistence observed"
    ),
    "antidote": RuntimeItemBinding(
        0x4000044C, 0xB000044C,
        "bundled EquipParamGoods row 1100 (毒・出血回復薬) + the live-validated category-4 "
        "formula; English name from the save editor's items.json",
    ),
    "sedatives": RuntimeItemBinding(
        0x4000044D, 0xB000044D,
        "bundled EquipParamGoods row 1101 (狂気・獣化回復薬) + the live-validated category-4 "
        "formula; English name from the save editor's items.json",
    ),
    "beast_blood_pellet": RuntimeItemBinding(
        0x40000456, 0xB0000456,
        "bundled EquipParamGoods row 1110 (獣化薬) + the live-validated category-4 "
        "formula; English name from the save editor's items.json",
    ),
    "blue_elixir": RuntimeItemBinding(
        0x40000460, 0xB0000460,
        "bundled EquipParamGoods row 1120 (石ころ帽子) + the live-validated category-4 "
        "formula; English name from the save editor's items.json",
    ),
    "poison_knife": RuntimeItemBinding(
        0x400004BA, 0xB00004BA,
        "bundled EquipParamGoods row 1210 (毒ナイフ) + the live-validated category-4 "
        "formula; English name from the save editor's items.json",
    ),
    "throwing_knife": RuntimeItemBinding(
        0x400004D8, 0xB00004D8,
        "bundled EquipParamGoods row 1240 (投げナイフ) + the live-validated category-4 "
        "formula; English name from the save editor's items.json",
    ),
    "fire_paper": RuntimeItemBinding(
        0x40000514, 0xB0000514,
        "bundled EquipParamGoods row 1300 (エンチャント【炎】) + the live-validated category-4 "
        "formula; English name from the save editor's items.json",
    ),
    "bolt_paper": RuntimeItemBinding(
        0x40000528, 0xB0000528,
        "bundled EquipParamGoods row 1320 (エンチャント【雷】) + the live-validated category-4 "
        "formula; English name from the save editor's items.json",
    ),
    "bone_marrow_ash": RuntimeItemBinding(
        0x40000532, 0xB0000532,
        "bundled EquipParamGoods row 1330 (銃威力アップ) + the live-validated category-4 "
        "formula; English name from the save editor's items.json",
    ),
    "lead_elixir": RuntimeItemBinding(
        0x400007EE, 0xB00007EE,
        "bundled EquipParamGoods row 2030 (ヌルヌル化) + the live-validated category-4 "
        "formula; English name from the save editor's items.json",
    ),
    "bold_hunters_mark": RuntimeItemBinding(0x40000578, 0xB0000578, "catalog id + validated category-4 goods formula"),
    "oil_urn": RuntimeItemBinding(0x400004C4, 0xB00004C4, "catalog id + validated category-4 goods formula"),
    "numbing_mist": RuntimeItemBinding(0x400004F6, 0xB00004F6, "catalog id + validated category-4 goods formula"),
    "pungent_blood_cocktail": RuntimeItemBinding(0x400004EC, 0xB00004EC, "catalog id + validated category-4 goods formula"),
    "shaman_bone_blade": RuntimeItemBinding(0x4000082A, 0xB000082A, "catalog id + validated category-4 goods formula"),
    "madmans_knowledge": RuntimeItemBinding(0x400005DC, 0xB00005DC, "catalog id + validated category-4 goods formula"),
    "great_ones_wisdom": RuntimeItemBinding(0x400005DD, 0xB00005DD, "catalog id + validated category-4 goods formula"),
    "coldblood_dew": RuntimeItemBinding(0x400005E8, 0xB00005E8, "catalog id + validated category-4 goods formula"),
    "thick_coldblood": RuntimeItemBinding(0x400005EB, 0xB00005EB, "catalog id + validated category-4 goods formula"),
    "frenzied_coldblood": RuntimeItemBinding(0x400005ED, 0xB00005ED, "catalog id + validated category-4 goods formula"),
    "kin_coldblood": RuntimeItemBinding(0x40000636, 0xB0000636, "catalog id + validated category-4 goods formula"),
    "beast_roar": RuntimeItemBinding(0x400007E4, 0xB00007E4, "catalog id + validated category-4 goods formula"),
    "empty_phantasm_shell": RuntimeItemBinding(0x4000051E, 0xB000051E, "catalog id + validated category-4 goods formula"),
    "old_hunter_bone": RuntimeItemBinding(0x4000080C, 0xB000080C, "catalog id + validated category-4 goods formula"),
    "executioners_gloves": RuntimeItemBinding(0x40000820, 0xB0000820, "catalog id + validated category-4 goods formula"),
    "tiny_tonitrus": RuntimeItemBinding(0x40000816, 0xB0000816, "catalog id + validated category-4 goods formula"),
    "a_call_beyond": RuntimeItemBinding(0x400007DA, 0xB00007DA, "catalog id + validated category-4 goods formula"),
    "choir_bell": RuntimeItemBinding(0x40000802, 0xB0000802, "catalog id + validated category-4 goods formula"),
    "blacksky_eye": RuntimeItemBinding(0x40000848, 0xB0000848, "catalog id + validated category-4 goods formula"),
    "messengers_gift": RuntimeItemBinding(0x4000083E, 0xB000083E, "catalog id + validated category-4 goods formula"),
    "beasthunter_saif": RuntimeItemBinding(0x015EF3C0, 0x815EF3C0, "bundled catalog EquipParamWeapon row", item_category=0, descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE, feed_effect="right_hand_weapon", reinforcement_level=0),
    "beast_cutter": RuntimeItemBinding(0x016E3600, 0x816E3600, "bundled catalog EquipParamWeapon row", item_category=0, descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE, feed_effect="right_hand_weapon", reinforcement_level=0),
    "amygdalan_arm": RuntimeItemBinding(0x017D7840, 0x817D7840, "bundled catalog EquipParamWeapon row", item_category=0, descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE, feed_effect="right_hand_weapon", reinforcement_level=0),
    "boom_hammer": RuntimeItemBinding(0x01AB3F00, 0x81AB3F00, "bundled catalog EquipParamWeapon row", item_category=0, descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE, feed_effect="right_hand_weapon", reinforcement_level=0),
    "whirligig_saw": RuntimeItemBinding(0x01D905C0, 0x81D905C0, "bundled catalog EquipParamWeapon row", item_category=0, descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE, feed_effect="right_hand_weapon", reinforcement_level=0),
    "church_cannon": RuntimeItemBinding(0x02160EC0, 0x82160EC0, "bundled catalog EquipParamWeapon row", item_category=0, descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE, feed_effect="left_hand_weapon", reinforcement_level=0),
    "fist_of_gratia": RuntimeItemBinding(0x0206CC80, 0x8206CC80, "bundled catalog EquipParamWeapon row", item_category=0, descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE, feed_effect="left_hand_weapon", reinforcement_level=0),
    "loch_shield": RuntimeItemBinding(0x01237160, 0x81237160, "bundled catalog EquipParamWeapon row", item_category=0, descriptor_evidence=INFERRED_CATEGORY_0_EVIDENCE, feed_effect="left_hand_weapon", reinforcement_level=0),
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
        "EMEVD boss-completion flag; $Event(12411700) waits CharacterDead(2410800) "
        "and calls HandleBossDefeat on it; MSB places 2410800 with NpcParam 500241 "
        "(教区長　聖堂街B)",
        None,
        "boss_defeat",
        "m24_01_00_00.emevd.dcx.js:1052-1094",
        None,
        None,
    ),
    "boss_father_gascoigne": RuntimeLocationBinding(
        12411800,
        "EMEVD boss-completion flag; $Event(12411800) waits CharacterDead(2410810 || "
        "2410811) and calls HandleBossDefeat on both; the host block at :1394 awards "
        "lot 31000 and sets 2412/9457/5910",
        None,
        "boss_defeat",
        "m24_01_00_00.emevd.dcx.js:1362-1412",
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
        "EMEVD boss-completion flag; $Event(12301800) waits CharacterDead(2300800) and "
        "calls HandleBossDefeat(2300800), placed in m23_00_00_00 with NpcParam 209000 "
        "(血に渇いた獣　廃墟). `inferred`: no instruction in the corpus writes this "
        "flag -- the write is the engine's event-end rule, and no live session has "
        "seen it fire. See research/validation/slice3_witness_audit.tsv",
        None,
        "boss_defeat",
        "m23_00_00_00.emevd.dcx.js:497-537",
        None,
        None,
    ),
    "boss_darkbeast_paarl": RuntimeLocationBinding(
        12301700,
        "EMEVD boss-completion flag; $Event(12301700) waits CharacterDead(2300810), "
        "calls HandleBossDefeat(2300810), awards lot 50800000/50800005 and sets "
        "2301/9454. MSB places 2300810 with NpcParam 508000 (Darkbeast Paarl)",
        None,
        "boss_defeat",
        "m23_00_00_00.emevd.dcx.js:756-806",
        None,
        None,
    ),
    "boss_vicar_amelia": RuntimeLocationBinding(
        12401800,
        "EMEVD boss-completion flag; $Event(12401800) waits CharacterDead(2400800) and "
        "calls HandleBossDefeat(2400800), placed in m24_00_00_00 with NpcParam 502000 "
        "(聖女ビースト　聖堂街A). `inferred`: no instruction in the corpus writes this "
        "flag -- the write is the engine's event-end rule, and no live session has "
        "seen it fire. See research/validation/slice3_witness_audit.tsv",
        None,
        "boss_defeat",
        "m24_00_00_00.emevd.dcx.js:4287-4331",
        None,
        None,
    ),
    "boss_witch_of_hemwick": RuntimeLocationBinding(
        12201800,
        "EMEVD boss-completion flag; event 12201800 waits on Witch entities "
        "2200800/2200801 and calls HandleBossDefeat; the event-end flag is also "
        "read by the cited Cainhurst carriage event 12200130",
        None,
        "boss_defeat",
        "m22_00_00_00.emevd.dcx.js:311-361",
        None,
        None,
    ),
    "boss_martyr_logarius": RuntimeLocationBinding(
        12501800,
        "EMEVD boss-completion flag; event 12501800 waits on entity 2500800 and "
        "calls HandleBossDefeat(2500800)",
        None,
        "boss_defeat",
        "m25_00_00_00.emevd.dcx.js:1279-1324",
        None,
        None,
    ),
    "boss_celestial_emissary": RuntimeLocationBinding(
        12421700,
        "EMEVD boss-completion flag 12421700; m24_02 Celestial Emissary event calls HandleBossDefeat",
        None,
        "boss_defeat",
        "m24_02_00_00.emevd.dcx.js:568-614",
        None,
        None,
    ),
    "boss_ebrietas": RuntimeLocationBinding(
        12421800,
        "EMEVD boss-completion flag 12421800; m24_02 Ebrietas event calls HandleBossDefeat",
        None,
        "boss_defeat",
        "m24_02_00_00.emevd.dcx.js:256-311",
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
    "boss_gehrman": RuntimeLocationBinding(
        12101800,
        "EMEVD boss-completion flag; m21_00 event 12101800 (Gehrman)",
        None,
        "boss_defeat",
        "m21_00_00_00.emevd.dcx.js:1423-1460",
        None,
        None,
    ),
    "boss_moon_presence": RuntimeLocationBinding(
        12101850,
        "EMEVD boss-completion flag; m21_00 event 12101850 (Moon Presence)",
        None,
        "boss_defeat",
        "m21_00_00_00.emevd.dcx.js:1665-1690",
        None,
        None,
    ),
    "boss_amygdala": RuntimeLocationBinding(
        13301800,
        "EMEVD boss-completion flag; event 13301800 defeats Amygdala",
        None,
        "boss_defeat",
        "m33_00_00_00.emevd.dcx.js:310-342",
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
    "interaction_laurences_skull": RuntimeLocationBinding(
        12401898,
        "AP overlay witness flag 12401898 set only after the Grand Cathedral altar interaction. "
        "The vanilla $Event(12401803) flag is reserved for the shuffled password receive effect; "
        "$Event(12401803) (学長の記憶ポリ劇) waits on "
        "Amelia (12401800), then on ActionButtonInArea(2400010, 2401801) at the Grand "
        "Cathedral altar, and ends. `inferred` on two counts: nothing writes the flag "
        "explicitly, and the event's `EndIf(HasMultiplayerState(Client))` at :4390 "
        "ends it before the action prompt for a co-op guest, so a guest may hold the "
        "flag without the interaction. See research/validation/slice3_witness_audit.tsv",
        None,
        "interaction",
        "managed m24_00_00_00.emevd.dcx patch of event 12401803",
        None,
        None,
    ),
    "pickup_cainhurst_summons": RuntimeLocationBinding(
        52410990, "EMEVD award m24_01_00_00:2310 + ItemLotParam 2410990 acquisition flag",
        2410990, "script_award", "m24_01_00_00.emevd.dcx.js:2310", 4, 4003),
    "pickup_upper_cathedral_key": RuntimeLocationBinding(
        52800290, "MSB treasure m28_00_00_00/m28_00_00_01 + ItemLotParam 2800290 acquisition flag",
        2800290, "treasure", "m28_00_00_00;m28_00_00_01", 4, 4010),
    "pickup_lunarium_key": RuntimeLocationBinding(
        53200810,
        "EMEVD award m32_00_00_00:636 + ItemLotParam 3200810 acquisition flag",
        3200810, "script_award", "m32_00_00_00.emevd.dcx.js:636", 4, 4013),
    "script_award_orphanage_key": RuntimeLocationBinding(
        52420900, "EMEVD award m24_02_00_00:252 + ItemLotParam 2420900 acquisition flag",
        2420900, "script_award", "m24_02_00_00.emevd.dcx.js:252", 4, 4006),
    "pickup_eye_of_blood_drunk_hunter": RuntimeLocationBinding(
        12101028,
        "EMEVD gift event 12101028 completes after interaction flag 12101029 and award lot "
        "10040; the lot's separate acquisition flag is 50000100",
        10040, "script_award", "m21_00_00_00.emevd.dcx.js:2987-3008", 4, 4311,
        item_lot_flag=50000100),
    "pickup_eye_pendant": RuntimeLocationBinding(
        9470, "EMEVD award m34_00_00_00:1725 + ItemLotParam 3401810 acquisition flag",
        3401810, "script_award", "m34_00_00_00.emevd.dcx.js:1725", 4, 4017),
    "pickup_laurences_skull": RuntimeLocationBinding(
        53502000, "EMEVD award m35_00_00_00:1832 + ItemLotParam 3502000 acquisition flag",
        3502000, "script_award", "m35_00_00_00.emevd.dcx.js:1832", 4, 4014),
    "treasure_old_hunter_bone": RuntimeLocationBinding(
        52110000, "MSB treasure m21_01_00_00 + ItemLotParam 2110000 acquisition flag",
        2110000, "treasure", "m21_01_00_00", 4, 2060),
    "treasure_doll_set_chest": RuntimeLocationBinding(
        52110020,
        "MSB chest m21_01_00_00 + ItemLotParam 2110020-2110023 shared acquisition flag",
        2110020, "treasure", "m21_01_00_00", 1, 220000),
    "pickup_small_hair_ornament": RuntimeLocationBinding(
        52110800,
        "EMEVD event 12110300 cabinet interaction + ItemLotParam 2110800 acquisition flag",
        2110800, "script_award", "m21_01_00_00.emevd.dcx.js:61", 4, 4300),
    "pickup_workshop_umbilical_cord": RuntimeLocationBinding(
        52110810,
        "EMEVD event 12110301 altar interaction + ItemLotParam 2110810 acquisition flag",
        2110810, "script_award", "m21_01_00_00.emevd.dcx.js:72", 4, 4320),
    "treasure_rune_workshop_tool": RuntimeLocationBinding(
        52200360, "MSB treasure m22_00_00_00 + ItemLotParam 2200360 acquisition flag",
        2200360, "treasure", "m22_00_00_00", 4, 4104),
    "treasure_radiant_sword_hunter_badge": RuntimeLocationBinding(
        52400480, "MSB treasure m24_00_00_00/m24_00_00_01 + ItemLotParam 2400480 acquisition flag",
        2400480, "treasure", "m24_00_00_00;m24_00_00_01", 4, 4115),
    "treasure_cosmic_eye_watcher_badge": RuntimeLocationBinding(
        52420270, "MSB treasure m24_02_00_00/m24_02_00_01 + ItemLotParam 2420270 acquisition flag",
        2420270, "treasure", "m24_02_00_00;m24_02_00_01", 4, 4119),
    "award_crow_hunter_badge": RuntimeLocationBinding(
        50001900, "Eileen badge acquisition flag shared by lots 35012/35020/35030",
        None, "npc_or_enemy_award", "ItemLotParam + common event 9910", None, None),
    "award_powder_keg_hunter_badge": RuntimeLocationBinding(
        50001700, "Djura badge acquisition flag shared by lots 33000/33010",
        None, "npc_or_enemy_award", "ItemLotParam + common event 9910", None, None),
    "award_wheel_hunter_badge": RuntimeLocationBinding(
        50001810, "Alfred badge acquisition flag shared by lots 34010/34031",
        None, "npc_or_enemy_award", "ItemLotParam + common event 9910", None, None),
    "award_cainhurst_badge": RuntimeLocationBinding(
        50000205, "Annalise Vileblood-oath badge acquisition flag from lot 17001",
        None, "npc_award", "ItemLotParam 17001 + common event 9910", None, None),
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

@dataclass(frozen=True)
class ScriptAwardSuppression:
    """A vanilla award the goods -> lot search cannot resolve on its own.

    The automatic planner refuses two shapes deliberately: an item awarded by
    more than one ItemLotParam row (editing one leaves the others reachable),
    and a lot with no acquisition flag (nothing can detect the pickup). Both
    refusals ask a contributor to decide, and this is where the decision is
    written down so that it is reviewable rather than implicit in a tool.

    ``item_lot_ids`` are the rows to edit. ``unreferenced_lot_ids`` are rows
    that award the same item but that no committed source reaches; each one
    needs the census that says so recorded in ``evidence``, because "nothing
    references it" is exactly the claim a later corpus can falsify.
    ``acquisition_flag`` is the row's literal ``getItemFlagId`` -- ``-1`` and
    ``0`` mean the row has none, and the planner must emit the literal value so
    that the writers' "the flag did not move" invariant compares like for like
    instead of inventing a flag that does not exist.
    """

    item_key: str
    item_category: int
    item_id: int
    item_lot_ids: tuple[int, ...]
    acquisition_flag: int
    unreferenced_lot_ids: tuple[int, ...]
    evidence: str


@dataclass(frozen=True)
class BossAwardSuppression:
    """One reviewed boss-award lot whose payout has no required side effect.

    Unlike ``ScriptAwardSuppression``, this declaration identifies the exact
    lot row directly. Boss filler, armour, runes and weapons commonly share an
    item with unrelated sources, so a global goods-to-lot census is the wrong
    ownership rule. The planner still verifies every declared field against
    the committed corpus before editing anything.
    """

    boss: str
    item_lot_id: int
    item_category: int
    item_id: int
    acquisition_flag: int
    evidence: str


SCRIPT_AWARD_SUPPRESSIONS: dict[str, ScriptAwardSuppression] = {
    "crow_hunter_badge": ScriptAwardSuppression(
        item_key="crow_hunter_badge", item_category=4, item_id=4111,
        item_lot_ids=(35012, 35020, 35030), acquisition_flag=50001900,
        unreferenced_lot_ids=(),
        evidence="Eileen quest/death alternatives share goods 4111 and acquisition flag 50001900"),
    "powder_keg_hunter_badge": ScriptAwardSuppression(
        item_key="powder_keg_hunter_badge", item_category=4, item_id=4112,
        item_lot_ids=(33000, 33010), acquisition_flag=50001700,
        unreferenced_lot_ids=(),
        evidence="Djura friendship/death alternatives share goods 4112 and acquisition flag 50001700"),
    "wheel_hunter_badge": ScriptAwardSuppression(
        item_key="wheel_hunter_badge", item_category=4, item_id=4116,
        item_lot_ids=(34010, 34031), acquisition_flag=50001810,
        unreferenced_lot_ids=(),
        evidence="Alfred quest/death alternatives share goods 4116 and acquisition flag 50001810"),
    "spark_hunter_badge": ScriptAwardSuppression(
        item_key="spark_hunter_badge", item_category=4, item_id=4118,
        item_lot_ids=(50800000,), acquisition_flag=-1,
        unreferenced_lot_ids=(),
        evidence="m23 Darkbeast Paarl defeat event awards lot 50800000; boss flag 12301700 is the check"),
    "oedon_tomb_key": ScriptAwardSuppression(
        item_key="oedon_tomb_key",
        item_category=4,
        item_id=4000,
        item_lot_ids=(31000,),
        acquisition_flag=-1,
        unreferenced_lot_ids=(27100000,),
        evidence=(
            "m24_01_00_00.emevd.dcx.js:1394 - event 12411800 waits on "
            "CharacterDead(2410810 || 2410811) and, host-only, calls "
            "AwardItemLot(31000) then SetEventFlag(2412/9457/5910). Lot 31000 "
            "awards category 4 item 4000 in slot 01 with getItemFlagId -1 "
            "(ItemLotParam.csv; research/joined/lot_items.tsv), so the award "
            "carries no acquisition flag and the check for this fight is "
            "Gascoigne's own defeat flag 12411800, not the key. Lot 27100000 "
            "awards the same goods and is edited by nothing: it appears in no "
            "MSB treasure (mined/msb_treasures.tsv, 146152 rows), no MSB enemy "
            "drop field (mined/msb_enemies.tsv), no NpcParam itemLot column "
            "(params/NpcParam.csv) and no committed EMEVD decompile, so it is "
            "recorded here as reviewed-and-unreachable rather than edited."
        ),
    ),
    "third_umbilical_cord_wet_nurse": ScriptAwardSuppression(
        item_key="third_umbilical_cord_1",
        item_category=4,
        item_id=4323,
        item_lot_ids=(55100000,),
        acquisition_flag=50000305,
        unreferenced_lot_ids=(),
        evidence=(
            "m26_00_00_00.emevd.dcx.js:565-573 - Wet Nurse defeat event "
            "12601800 calls HandleBossDefeat(2600803), then AwardItemLot(55100000). "
            "That lot awards category 4 item 4323 in slot 01 and carries "
            "getItemFlagId 50000305 (ItemLotParam.csv; research/joined/lot_items.tsv). "
            "All four logical Third Umbilical Cord items use goods 4323, so the "
            "vanilla Wet Nurse copy is removed while the lot flag remains intact."
        ),
    ),
}


# The two boss badges and Amelia's Pendant are AP items: every reviewed natural
# source is suppressed so their shop/consume effects follow AP receipt. The
# BSB Pthumeru Chalice is also suppressed: live playtest.32 proved that it leaks
# alongside the randomized boss reward. Amygdala and Ebrietas chalices remain
# vanilla while Chalice Dungeon progression is outside this world.
BOSS_AWARD_SUPPRESSIONS: dict[str, BossAwardSuppression] = {
    key: BossAwardSuppression(key, lot, category, item, flag, evidence)
    for key, lot, category, item, flag, evidence in (
        ("witch_of_hemwick", 21002950, 4, 7150, -1, "m22 event 12201800 AwardItemLot(21002950)"),
        ("vicar_amelia", 50000001, 4, 4001, -1, "m24_00 event 12401800 AwardItemLot(50000001)"),
        ("cleric_beast_badge", 50000010, 4, 4114, -1, "m24_01 event 12411700 AwardItemLot(50000010)"),
        ("blood_starved_beast_chalice", 80000000, 4, 6109, 5000,
         "m23 event 12301800 AwardItemLot(80000000); live-confirmed vanilla leak in playtest.32"),
        ("cosmic_eye_watcher_badge_alt", 2420280, 4, 4119, 52420280,
         "alternate Upper Cathedral map-state treasure for the Cosmic Eye Watcher Badge"),
        ("gehrman_badge_awake", 15000, 4, 4113, -1, "m21 event 12101800 awards the Old Hunter Badge"),
        ("gehrman_badge_boss", 2100500, 4, 4113, 52100500, "m21 Gehrman defeat reward"),
        ("old_hunter_badge_corpse", 2110015, 4, 4113, 52110030, "m21 Hunter's Dream corpse fallback"),
        ("celestial_emissary_gem", 25700000, 8, 102904, -1, "m24_02 event 12421700 AwardItemLot(25700000)"),
        ("celestial_emissary_insight", 25700005, 4, 1500, -1, "m24_02 event 12421700 AwardItemLot(25700005)"),
        ("micolash", 21000, 1, 190000, -1, "m26 event 12601850 AwardItemLot(21000)"),
        ("shadows_of_yharnam", 2700990, 8, 100601, 52700950, "m27 event 12701800 AwardItemLot(2700990)"),
        ("shadows_of_yharnam_repeat", 2700995, 4, 1500, 52700955, "m27 event 12701800 AwardItemLot(2700995)"),
        ("the_one_reborn", 50700000, 4, 7131, -1, "m28 event 12801800 AwardItemLot(50700000)"),
        ("rom_coldblood", 51001900, 4, 1591, -1, "m32 event 13201800 AwardItemLot(51001900)"),
        ("rom_spawned_reward", 3200800, 8, 102202, 53200800, "common EMEVD AwardItemLot(3200800) after Rom"),
        ("gehrman_repeat", 15005, 4, 1400, -1, "m21 event 12101800 AwardItemLot(15005) when the badge is already owned"),
        ("ludwig", 3401800, 8, 104001, 6674, "m34 event 13401800 AwardItemLot(3401800)"),
        ("ludwig_repeat", 3401802, 4, 1500, -1, "m34 event 13401800 AwardItemLot(3401802)"),
        ("laurence", 3401850, 8, 200040, 6673, "m34 event 13401850 AwardItemLot(3401850)"),
        ("laurence_repeat", 3401852, 4, 1500, -1, "m34 event 13401850 AwardItemLot(3401852)"),
        ("orphan_of_kos", 3601800, 0, 38000000, 53601800, "m36 event 13601800 AwardItemLot(3601800)"),
    )
}


# Known delivery fixtures, not currently part of the randomized design pool.
DELIVERY_FIXTURES: dict[str, RuntimeItemBinding] = {
    "quicksilver_bullet": ITEM_BINDINGS["quicksilver_bullets"],
    "blood_vial": RuntimeItemBinding(0x400003E8, 0xB00003E8, "inferred/observed"),
    "pebble": ITEM_BINDINGS["pebbles"],
    "augur_of_ebrietas": ITEM_BINDINGS["augur_of_ebrietas"],
}
