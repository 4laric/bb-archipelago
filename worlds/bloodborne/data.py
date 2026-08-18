"""Initial conservative Bloodborne progression slice.

Keys are our stable design identifiers. Display names can be corrected without
changing generated IDs. This file must never contain memory addresses, game item
IDs, event flags, or serial-specific values; those belong in runtime_bindings.py.

This is a vertical-slice model, not a claim that all listed checks or gate effects
have been runtime validated.
"""

from .model import Entrance, Item, ItemKind, Location, Rule, WorldModel

P = ItemKind.PROGRESSION
E = ItemKind.EVENT

ITEMS = (
    # Shufflable inventory/key items. Runtime grant semantics remain unvalidated.
    Item("hunter_chief_emblem", "Hunter Chief Emblem", P),
    Item("cainhurst_summons", "Cainhurst Summons", P),
    Item("tonsil_stone", "Tonsil Stone", P),
    Item("upper_cathedral_key", "Upper Cathedral Key", P),
    Item("orphanage_key", "Orphanage Key", P),
    Item("eye_of_blood_drunk_hunter", "Eye of a Blood-drunk Hunter", P),
    Item("eye_pendant", "Eye Pendant", P),
    Item("astral_clocktower_key", "Astral Clocktower Key", P),
    Item("celestial_dial", "Celestial Dial", P),
    Item("laurences_skull", "Laurence's Skull", P),
    # Locked local events. These are never placed in the random item pool.
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
    Entrance("Tomb of Oedon gate", "Central Yharnam", "Cathedral Ward", Rule.all("event_gascoigne_defeated")),
    Entrance("Road into Old Yharnam", "Cathedral Ward", "Old Yharnam"),
    Entrance("Healing Church Workshop door", "Cathedral Ward", "Healing Church Workshop",
             Rule.all("event_blood_starved_beast_defeated")),
    Entrance("Cathedral Ward plaza gate", "Cathedral Ward", "Grand Cathedral", Rule.any(
        ("hunter_chief_emblem",),
        ("event_blood_starved_beast_defeated",),
    )),
    # The road to Hemwick starts left of the Grand Cathedral entrance, so it is
    # behind the plaza and carries the plaza's requirement, not nothing.
    Entrance("Road to Hemwick", "Cathedral Ward", "Hemwick Charnel Lane", Rule.any(
        ("hunter_chief_emblem",),
        ("event_blood_starved_beast_defeated",),
    )),
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
    Location("boss_father_gascoigne", "Father Gascoigne", "Central Yharnam", locked_item="event_gascoigne_defeated"),
    Location("boss_blood_starved_beast", "Blood-starved Beast", "Old Yharnam",
             locked_item="event_blood_starved_beast_defeated"),
    Location("boss_vicar_amelia", "Vicar Amelia", "Grand Cathedral", locked_item="event_amelia_defeated"),
    Location("interaction_laurences_skull", "Grand Cathedral - Laurence's Skull", "Grand Cathedral",
             Rule.all("event_amelia_defeated"), locked_item="event_forbidden_woods_password"),
    Location("boss_shadows_of_yharnam", "Shadows of Yharnam", "Forbidden Woods", locked_item="event_shadows_defeated"),
    Location("boss_rom", "Rom, the Vacuous Spider", "Byrgenwerth", locked_item="event_rom_defeated"),
    Location("boss_the_one_reborn", "The One Reborn", "Yahar'gul", locked_item="event_one_reborn_defeated"),
    Location("boss_micolash", "Micolash, Host of the Nightmare", "Nightmare of Mensis", locked_item="event_micolash_defeated"),
    Location("boss_mergos_wet_nurse", "Mergo's Wet Nurse", "Nightmare of Mensis", Rule.all("event_micolash_defeated"), locked_item="event_mergos_wet_nurse_defeated"),
    # Candidate randomized checks; source acquisition/event flags need mapping.
    Location("pickup_cainhurst_summons", "Iosefka's Clinic - Cainhurst Summons", "Iosefka's Clinic"),
    Location("pickup_upper_cathedral_key", "Yahar'gul - Upper Cathedral Key", "Yahar'gul"),
    Location("pickup_orphanage_key", "Upper Cathedral Ward - Orphanage Key", "Upper Cathedral Ward"),
    Location("pickup_eye_of_blood_drunk_hunter", "Hunter's Dream - Eye of a Blood-drunk Hunter", "Hunter's Dream",
             Rule.all("event_forbidden_woods_password")),
    Location("pickup_eye_pendant", "Hunter's Nightmare - Eye Pendant", "Hunter's Nightmare"),
    Location("boss_ludwig", "Ludwig, the Holy Blade", "Hunter's Nightmare",
             locked_item="event_ludwig_defeated"),
    Location("boss_living_failures", "Living Failures", "Lumenwood Garden",
             locked_item="event_living_failures_defeated"),
    Location("boss_lady_maria", "Lady Maria of the Astral Clocktower", "Astral Clocktower",
             locked_item="event_lady_maria_defeated"),
    Location("boss_orphan_of_kos", "Orphan of Kos", "Fishing Hamlet",
             locked_item="event_orphan_of_kos_defeated"),
    Location("pickup_laurences_skull", "Research Hall - Laurence's Skull", "Research Hall"),
    Location("boss_laurence", "Laurence, the First Vicar", "Nightmare Grand Cathedral",
             Rule.all("laurences_skull"), locked_item="event_laurence_defeated"),
)

MODEL = WorldModel(ITEMS, REGIONS, ENTRANCES, LOCATIONS)
