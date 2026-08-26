"""Initial conservative Bloodborne progression slice.

Keys are our stable design identifiers. Display names can be corrected without
changing generated IDs. This file must never contain memory addresses, game item
IDs, event flags, or serial-specific values; those belong in runtime_bindings.py.

This is a vertical-slice model, not a claim that all listed checks or gate effects
have been runtime validated.
"""

from .model import Entrance, Item, ItemKind, Location, Rule, WorldModel
from .fixed_locations import FIXED_LOCATIONS
from .location_names import location_name

P = ItemKind.PROGRESSION
U = ItemKind.USEFUL
F = ItemKind.FILLER
E = ItemKind.EVENT

ITEMS = (
    # Shufflable inventory/key items. Runtime grant semantics remain unvalidated.
    Item("hunter_chief_emblem", "Hunter Chief Emblem", P),
    Item("oedon_tomb_key", "Oedon Tomb Key", P),
    Item("cainhurst_summons", "Cainhurst Summons", P),
    Item("tonsil_stone", "Tonsil Stone", P),
    Item("upper_cathedral_key", "Upper Cathedral Key", P),
    Item("orphanage_key", "Orphanage Key", P),
    Item("eye_of_blood_drunk_hunter", "Eye of a Blood-drunk Hunter", P),
    Item("eye_pendant", "Eye Pendant", P),
    Item("astral_clocktower_key", "Astral Clocktower Key", P),
    Item("celestial_dial", "Celestial Dial", P),
    Item("laurences_skull", "Laurence's Skull", P),
    # Equipment is admitted only after its runtime descriptor has been
    # observed through the native grant path and allowlisted separately from
    # the ItemLot identity. Torch deliberately remains excluded.
    Item("saw_spear", "Saw Spear", U),
    # Live category-4 grant canaries promoted into the vertical-slice pool.
    # Quantities are part of the AP item contract and are granted atomically.
    Item("augur_of_ebrietas", "Augur of Ebrietas", U),
    Item("quicksilver_bullets", "Quicksilver Bullets x3", F, 3),
    Item("pebbles", "Pebbles x3", F, 3),
    Item("molotov_cocktails", "Molotov Cocktails x2", F, 2),
    Item("blood_stone_shards", "Blood Stone Shards x2", F, 2),
    # Uncanny variants of pooled weapons (bb-archipelago#205). Each is its own
    # EquipParamWeapon row with its own gem-slot layout, so it is a distinct
    # named item rather than a second copy of its base weapon. They are listed
    # LAST on purpose: build_item_pool_names sheds the tail first when a pool
    # has no filler slack, so a small seed drops Uncanny copies deterministically
    # instead of overflowing the location count.
    Item("uncanny_saw_spear", "Uncanny Saw Spear", U),
    # Locked local events. These are never placed in the random item pool.
    Item("event_cleric_beast_defeated", "Cleric Beast Defeated", E),
    Item("event_gascoigne_defeated", "Father Gascoigne Defeated", E),
    Item("event_blood_starved_beast_defeated", "Blood-starved Beast Defeated", E),
    Item("event_amelia_defeated", "Vicar Amelia Defeated", E),
    Item("event_forbidden_woods_password", "Forbidden Woods Password Learned", E),
    Item("event_shadows_defeated", "Shadows of Yharnam Defeated", E),
    Item("event_rom_defeated", "Rom Defeated", E),
    Item("event_one_reborn_defeated", "The One Reborn Defeated", E),
    Item("event_micolash_defeated", "Micolash Defeated", E),
    Item("event_mergos_wet_nurse_defeated", "Mergo's Wet Nurse Defeated", E),
    Item("event_ludwig_defeated", "Ludwig Defeated", E),
    Item("event_living_failures_defeated", "Living Failures Defeated", E),
    Item("event_lady_maria_defeated", "Lady Maria Defeated", E),
    Item("event_orphan_of_kos_defeated", "Orphan of Kos Defeated", E),
    Item("event_laurence_defeated", "Laurence Defeated", E),
)

REGIONS = (
    "Menu", "Hunter's Dream", "Central Yharnam", "Cathedral Ward", "Old Yharnam",
    "Healing Church Workshop", "Grand Cathedral", "Hemwick Charnel Lane", "Forbidden Woods",
    "Iosefka's Clinic", "Byrgenwerth", "Yahar'gul", "Lecture Building 1F",
    "Lecture Building 2F", "Nightmare Frontier", "Nightmare of Mensis",
    "Upper Cathedral Ward", "Castle Cainhurst",
    "Hunter's Nightmare", "Underground Corpse Pile", "Research Hall",
    "Lumenwood Garden", "Astral Clocktower", "Fishing Hamlet",
    "Nightmare Grand Cathedral",
)

ENTRANCES = (
    Entrance("Begin the Hunt", "Menu", "Hunter's Dream"),
    Entrance("Awaken in Central Yharnam", "Hunter's Dream", "Central Yharnam"),
    # Two requirements, both real. The door out of the Tomb of Oedon (object
    # 2411304) is the generic key door: m24_01_00_00 event 12410110 slot 5 is
    # initialized with objParameterId 2410080, so the item requirement lives in
    # ObjActParam row 2410080 rather than in any EMEVD condition -- no
    # PlayerHasItem(Goods, 4000) test exists in the event files. And the door
    # sits behind Gascoigne's arena, so beating him is a physical prerequisite
    # for standing at it. Vanilla hid the coupling by handing the key out on
    # his death (event 12411800 -> AwardItemLot(31000)); with the key shuffled,
    # the two stop being the same requirement.
    Entrance("Tomb of Oedon gate", "Central Yharnam", "Cathedral Ward",
             Rule.all("oedon_tomb_key", "event_gascoigne_defeated")),
    Entrance("Road into Old Yharnam", "Cathedral Ward", "Old Yharnam"),
    Entrance("Healing Church Workshop door", "Cathedral Ward", "Healing Church Workshop",
             Rule.all("event_blood_starved_beast_defeated")),
    # The audited edge is "Hunter Chief Emblem OR the Healing Church Workshop
    # route". Collapsing that into one two-clause rule on a single entrance is
    # what made the emblem vacuous: the workshop route's own prerequisite
    # (Blood-starved Beast) is free from Cathedral Ward, so the emblem clause
    # could never be the required one. The route is two hops in the game and is
    # now two hops here — the emblem opens the gate directly, the workshop
    # reaches the same plaza the long way round. Slice 3 seeds Cathedral Ward,
    # Old Yharnam and the Grand Cathedral but not the Healing Church Workshop,
    # so inside a slice-3 seed the emblem is the only route to the plaza.
    Entrance("Cathedral Ward plaza gate", "Cathedral Ward", "Grand Cathedral",
             Rule.all("hunter_chief_emblem")),
    Entrance("Healing Church Workshop plaza route", "Healing Church Workshop",
             "Grand Cathedral"),
    # The road to Hemwick starts left of the Grand Cathedral entrance, so it is
    # behind the plaza, not free from Cathedral Ward.
    Entrance("Road to Hemwick", "Grand Cathedral", "Hemwick Charnel Lane"),
    Entrance("Forbidden Woods password door", "Cathedral Ward", "Forbidden Woods",
             Rule.all("event_forbidden_woods_password")),
    Entrance("Forbidden Woods clinic passage", "Forbidden Woods", "Iosefka's Clinic"),
    Entrance("Path to Byrgenwerth", "Forbidden Woods", "Byrgenwerth", Rule.all("event_shadows_defeated")),
    Entrance("Blood Moon transition", "Byrgenwerth", "Yahar'gul", Rule.all("event_rom_defeated")),
    Entrance("Advent Plaza mummy", "Yahar'gul", "Lecture Building 2F", Rule.all("event_one_reborn_defeated")),
    Entrance("Lecture Hall giant door", "Lecture Building 2F", "Nightmare of Mensis"),
    Entrance("Amygdala's grasp", "Cathedral Ward", "Lecture Building 1F", Rule.all("tonsil_stone")),
    Entrance("Lecture Building frontier door", "Lecture Building 1F", "Nightmare Frontier"),
    # The chapel side doors that reach the Upper Cathedral only open after
    # Blood-starved Beast; the key alone is not sufficient.
    Entrance("Upper Cathedral door", "Cathedral Ward", "Upper Cathedral Ward",
             Rule.all("upper_cathedral_key", "event_blood_starved_beast_defeated")),
    Entrance("Cainhurst carriage", "Hemwick Charnel Lane", "Castle Cainhurst", Rule.all("cainhurst_summons")),
    Entrance("Amygdala's DLC grasp", "Cathedral Ward", "Hunter's Nightmare",
             Rule.all("event_forbidden_woods_password", "eye_of_blood_drunk_hunter")),
    Entrance("Ludwig's arena exit", "Hunter's Nightmare", "Underground Corpse Pile",
             Rule.all("event_ludwig_defeated")),
    Entrance("Surgery altar", "Underground Corpse Pile", "Research Hall", Rule.all("eye_pendant")),
    Entrance("Research Hall summit", "Research Hall", "Lumenwood Garden"),
    Entrance("Astral Clocktower door", "Lumenwood Garden", "Astral Clocktower",
             Rule.all("event_living_failures_defeated", "astral_clocktower_key")),
    Entrance("Astral clock", "Astral Clocktower", "Fishing Hamlet",
             Rule.all("event_lady_maria_defeated", "celestial_dial")),
    Entrance("Nightmare Grand Cathedral", "Hunter's Nightmare", "Nightmare Grand Cathedral"),
)

LOCATIONS = (
    Location("boss_cleric_beast", location_name(12411700), "Central Yharnam",
             locked_item="event_cleric_beast_defeated"),
    Location("boss_father_gascoigne", location_name(12411800), "Central Yharnam", locked_item="event_gascoigne_defeated"),
    Location("boss_blood_starved_beast", location_name(12301800), "Old Yharnam",
             locked_item="event_blood_starved_beast_defeated"),
    Location("boss_vicar_amelia", location_name(12401800), "Grand Cathedral", locked_item="event_amelia_defeated"),
    Location("interaction_laurences_skull", location_name(12401803), "Grand Cathedral",
             Rule.all("event_amelia_defeated"), locked_item="event_forbidden_woods_password"),
    Location("boss_shadows_of_yharnam", location_name(12701800), "Forbidden Woods", locked_item="event_shadows_defeated"),
    Location("boss_rom", location_name(13201800), "Byrgenwerth", locked_item="event_rom_defeated"),
    Location("boss_the_one_reborn", location_name(12801800), "Yahar'gul", locked_item="event_one_reborn_defeated"),
    Location("boss_micolash", location_name(12601850), "Nightmare of Mensis", locked_item="event_micolash_defeated"),
    Location("boss_mergos_wet_nurse", location_name(12601800), "Nightmare of Mensis", Rule.all("event_micolash_defeated"), locked_item="event_mergos_wet_nurse_defeated"),
    # Scripted checks and bosses with committed flags (runtime_bindings.py);
    # every name comes from the location-name table
    # (docs/LOCATION-NAMING.md).
    Location("pickup_cainhurst_summons", location_name(52410990), "Iosefka's Clinic"),
    Location("pickup_upper_cathedral_key", location_name(52800290), "Yahar'gul"),
    Location("script_award_orphanage_key", location_name(52420900), "Upper Cathedral Ward"),
    Location("pickup_eye_of_blood_drunk_hunter", location_name(50000100), "Hunter's Dream",
             Rule.all("event_forbidden_woods_password")),
    Location("pickup_eye_pendant", location_name(9470), "Hunter's Nightmare"),
    Location("boss_ludwig", location_name(13401800), "Hunter's Nightmare",
             locked_item="event_ludwig_defeated"),
    Location("boss_living_failures", location_name(13501850), "Lumenwood Garden",
             locked_item="event_living_failures_defeated"),
    Location("boss_lady_maria", location_name(13501800), "Astral Clocktower",
             locked_item="event_lady_maria_defeated"),
    Location("boss_orphan_of_kos", location_name(13601800), "Fishing Hamlet",
             locked_item="event_orphan_of_kos_defeated"),
    Location("pickup_laurences_skull", location_name(53502000), "Research Hall"),
    # Catalog-backed fixed treasures. These make the previously empty optional
    # regions contribute checks without inventing placement or flag IDs.
    Location("treasure_radiant_sword_hunter_badge", location_name(52400480), "Cathedral Ward"),
    Location("treasure_old_hunter_bone", location_name(52110000), "Healing Church Workshop"),
    Location("treasure_rune_workshop_tool", location_name(52200360), "Hemwick Charnel Lane"),
    Location("treasure_augur_of_ebrietas", location_name(53200600), "Lecture Building 1F"),
    Location("treasure_lecture_theatre_key", location_name(53200720), "Lecture Building 2F"),
    Location("treasure_messengers_gift", location_name(53300330), "Nightmare Frontier"),
    Location("treasure_executioners_gloves", location_name(52500250), "Castle Cainhurst"),
    Location("treasure_underground_jail_chunk", location_name(53500630), "Research Hall"),
    # Keeps the Underground Corpse Pile contributing a check now that the jail
    # chunk is ruled Research Hall (#82); the Inner Chamber Key is the pile's
    # evidenced key-item treasure (event tag 宝死体_地下牢の鍵).
    Location("treasure_underground_cell_inner_chamber_key", location_name(50002360),
             "Underground Corpse Pile"),
    Location("treasure_cosmic_eye_watcher_badge", location_name(52420270),
             "Upper Cathedral Ward", Rule.all("orphanage_key")),
    Location("boss_laurence", location_name(13401850), "Nightmare Grand Cathedral",
             Rule.all("laurences_skull"), locked_item="event_laurence_defeated"),
) + tuple(
    Location(
        location.key,
        location.name,
        location.region,
        classification=location.classification,
        vanilla_award_suppressed=location.vanilla_award_suppressed,
    )
    for location in FIXED_LOCATIONS
)

MODEL = WorldModel(ITEMS, REGIONS, ENTRANCES, LOCATIONS)

# The generated player exposes one honest, bounded slice. The broader model
# above remains research scaffolding; none of its later regions enters
# multidata until its runtime contracts are ready.
#
# Slice 3 (Cathedral Ward -> Old Yharnam -> Blood-starved Beast) adds three
# regions to slice 1's Central Yharnam:
#  - Cathedral Ward, entered with the Oedon Tomb Key after Gascoigne's defeat
#    (slice 1 already seeded its Tomb of Oedon strip for exactly this reason);
#    the key is shuffled, so this edge is what makes Central Yharnam a real
#    sphere 0 rather than a corridor the seed starts on the far side of;
#  - Old Yharnam, reached freely from the Cathedral Ward lamp, ending at the
#    Blood-starved Beast, which is the slice goal;
#  - the Grand Cathedral, behind the Hunter Chief Emblem. The emblem is the
#    only in-slice route to it: the game's alternative runs through the
#    Healing Church Workshop, which slice 3 does not seed. That is what stops
#    the emblem from being a decorative pool item.
SLICE_REGIONS = (
    "Menu", "Hunter's Dream", "Central Yharnam", "Cathedral Ward",
    "Old Yharnam", "Grand Cathedral",
)
_SLICE_ENTRANCE_NAMES = (
    "Begin the Hunt",
    "Awaken in Central Yharnam",
    "Tomb of Oedon gate",
    "Road into Old Yharnam",
    "Cathedral Ward plaza gate",
)
SLICE_ENTRANCES = tuple(
    entrance for entrance in ENTRANCES if entrance.name in _SLICE_ENTRANCE_NAMES
)
# Both endpoints of every seeded entrance must be a seeded region, or the
# generator would build an exit into a region that does not exist.
assert {e.source for e in SLICE_ENTRANCES} | {e.target for e in SLICE_ENTRANCES} <= set(SLICE_REGIONS)
assert len(SLICE_ENTRANCES) == len(_SLICE_ENTRANCE_NAMES)

# The reduced pool the first live sessions validated, plus the Hunter Chief
# Emblem and the Oedon Tomb Key: with the plaza gate emblem-only and the Tomb
# of Oedon gate key-only, a seed that cannot place either cannot reach the
# checks behind it at all. Both are in every pool the world can build.
SLICE_ITEM_KEYS = frozenset({
    "hunter_chief_emblem",
    "oedon_tomb_key",
    "saw_spear",
    "augur_of_ebrietas",
    "quicksilver_bullets",
    "pebbles",
    "molotov_cocktails",
    "blood_stone_shards",
})
# Pool membership and global vanilla-item suppression are different contracts.
# Repeatable consumables may remain elsewhere in the game; the Saw Spear's
# in-slice vanilla copy must not coexist with its randomized AP copy. The
# Hunter Chief Emblem needs no entry here: its vanilla copy sits on a fixed
# manifest row (flag 52400450) whose award the location plan already replaces.
# The Oedon Tomb Key is not here either, for a different reason: its vanilla
# copy comes from an EMEVD script award with no acquisition flag and no
# placement, so it cannot be resolved by the goods -> lot search this set
# drives. It is suppressed by the reviewed declaration in runtime_bindings.py
# (SCRIPT_AWARD_SUPPRESSIONS) instead.
SLICE_POOL_SUPPRESSION_KEYS = frozenset({"saw_spear"})

# bb-archipelago#205. Base weapon key -> its Uncanny variant key. The Uncanny
# rows are shufflable items with permanent network ids like any other, but they
# are NOT part of FULL_POOL_ITEM_KEYS: a seed places them only when the
# `uncanny_weapons` option is on, and only for weapons its own pool already
# contains. Nothing here is a claim about the base item's classification --
# the first copy's kind is untouched.
UNCANNY_WEAPONS = {
    "saw_spear": "uncanny_saw_spear",
}
UNCANNY_ITEM_KEYS = frozenset(UNCANNY_WEAPONS.values())

# data.py checks (bosses, the one evidenced interaction, and the catalog-backed
# treasures) that the slice seeds, named explicitly so that adding a region to
# SLICE_REGIONS never sweeps an unreviewed scripted check into multidata.
SLICE_SCRIPTED_LOCATION_KEYS = frozenset({
    "boss_cleric_beast",
    "boss_father_gascoigne",
    "boss_blood_starved_beast",
    "boss_vicar_amelia",
    "interaction_laurences_skull",
    "treasure_radiant_sword_hunter_badge",
})
# Fixed rows whose region sits outside the slice (today: the two Iosefka's
# Clinic back-yard pickups, gated behind the Amelia -> Laurence's-skull
# password chain) stay in the TSV for the full world but do not enter slice
# seeds. Their vanilla awards remain suppressed, so they are inert pickups —
# documented in docs/VERTICAL-SLICE.md.
# A second exclusion class is quest-gated rows whose region IS in the slice:
# the White Messenger Ribbon is the little-girl quest reward that can only be
# collected after Rom's blood moon (brooch -> pig's red ribbon -> the sister),
# which is far past the slice's goal. When the full world models the quest,
# this row needs an event_rom_defeated rule, not just a region.
SLICE_EXCLUDED_FIXED_KEYS = frozenset({
    "fixed_white_messenger_ribbon",
})
SLICE_LOCATION_KEYS = frozenset({
    *SLICE_SCRIPTED_LOCATION_KEYS,
    *(location.key for location in FIXED_LOCATIONS
      if location.region in SLICE_REGIONS
      and location.key not in SLICE_EXCLUDED_FIXED_KEYS),
})
