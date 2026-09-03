"""Archipelago adapter for the conservative Bloodborne vertical slice."""
from __future__ import annotations
import json
from pathlib import Path
from random import Random
from typing import Any, Iterable
from .data import (
    ALTERNATE_GAOL_ENTRANCE_NAMES,
    ALTERNATE_GAOL_LOCATION_KEYS,
    ALTERNATE_GAOL_REGIONS,
    ATTIRE_ITEM_KEYS,
    DLC_ATTIRE_ITEM_KEYS,
    DLC_ENTRANCE_NAMES,
    DLC_ITEM_KEYS,
    DLC_LOCATION_KEYS,
    DLC_REGIONS,
    SLICE_ENTRANCES,
    SLICE_ITEM_KEYS,
    SLICE_LOCATION_KEYS,
    SLICE_POOL_SUPPRESSION_KEYS,
    SLICE_REGIONS,
    UNCANNY_ITEM_KEYS,
    UNCANNY_WEAPONS,
    MODEL,
    ONE_TIME_ENEMY_LOCATION_KEYS,
)
from .model import ItemKind, Rule
from .resource_data import read_resource_text
from .runtime_bindings import ITEM_BINDINGS, LOCATION_BINDINGS, validate_runtime_item_binding
from .toast_placeholders import ToastPlacement, build_toast_placeholder_plan
from .enemy_drops import build_enemy_drop_assignments
from .category8_awards import CATEGORY8_AWARDS

GAME = "Bloodborne"
WORLD_VERSION = json.loads(read_resource_text("archipelago.json"))["world_version"]
RUNTIME_BUILD = "bb-0.1.0-r10"
SUPPRESSION_MANIFEST_FORMAT = "bb-vanilla-suppression-build-v1"
SUPPRESSION_PLAN_SHA256 = "92c9eb755853f1079c28e8a91b60c0b9112528507cf4e2fbe4f109746f6596d0"
ID_BASE = 0xBB0000
ALL_NETWORK_LOCATIONS = tuple(
    location for location in MODEL.locations
    if location.key in SLICE_LOCATION_KEYS
)
# Historical/default manifest. Opt-in combat checks are published in the
# datapackage but excluded from the seed unless their option is enabled.
NETWORK_LOCATIONS = tuple(
    location for location in ALL_NETWORK_LOCATIONS
    if location.key not in ONE_TIME_ENEMY_LOCATION_KEYS
)
# Everything that can enter the pool: every non-event item has a permanent
# network id and a validated runtime binding. The Yharnam slice option below
# restricts which of them a seed actually places.
SHUFFLABLE_ITEMS = tuple(
    item for item in MODEL.items
    if item.kind is not ItemKind.EVENT
)
STARTING_TOOL_KEYS = frozenset({"blood_gem_workshop_tool", "rune_workshop_tool"})
# Uncanny variants are shufflable (permanent ids, validated bindings) but are
# opt-in: they enter a pool only through the `uncanny_weapons` option, so the
# default pool -- and every seed generated before #205 -- is unchanged.
FULL_POOL_ITEM_KEYS = frozenset(
    item.key for item in SHUFFLABLE_ITEMS
    if item.key not in UNCANNY_ITEM_KEYS
    and item.key not in STARTING_TOOL_KEYS
    and item.key not in ATTIRE_ITEM_KEYS
)
POOL_SUPPRESSION_ITEM_KEYS = SLICE_POOL_SUPPRESSION_KEYS
EVENT_ITEMS = tuple(item for item in MODEL.items if item.kind is ItemKind.EVENT)
FILLER_ITEM_NAME = "Blood Vial"
STARTING_TOOL_KEYS = frozenset({"blood_gem_workshop_tool", "rune_workshop_tool"})
# The full base-game ending: return to the Dream after Wet Nurse, defeat
# Gehrman, then use any three of four shuffled cord pieces to expose Moon Presence.
# The client learns this from slot_data, so no client rebuild is required.
GOAL_LOCATION_KEY = "boss_moon_presence"
GOAL_LOCATION_KEYS = {
    0: "boss_mergos_wet_nurse",
    1: "boss_gehrman",
    2: "boss_moon_presence",
}

STARTING_WEAPON_ROWS = {
    "right_hand": (2000, 2001, 2002),
    "left_hand": (2010, 2011),
}

SHOP_GATE_IDS = tuple(range(12101000, 12101010))


def build_starting_weapon_choices(seed: str) -> dict[str, list[int]]:
    """Choose the native Dream gift lineup independently of the AP item pool."""
    candidates = {
        hand: sorted(
            binding.normalized_item_id
            for key, binding in ITEM_BINDINGS.items()
            if key not in UNCANNY_ITEM_KEYS and binding.feed_effect == f"{hand}_weapon"
            and binding.normalized_item_id is not None
        )
        for hand in STARTING_WEAPON_ROWS
    }
    random = Random(f"bloodborne-starting-weapons:{seed}")
    return {
        hand: random.sample(candidates[hand], len(rows))
        for hand, rows in STARTING_WEAPON_ROWS.items()
    }


def build_weapon_requirement_families(include_uncanny: bool) -> list[int]:
    """Return player weapon variant roots whose four stat gates should be cleared."""
    return sorted(
        binding.normalized_item_id
        for key, binding in ITEM_BINDINGS.items()
        if binding.feed_effect in {"right_hand_weapon", "left_hand_weapon"}
        and binding.normalized_item_id is not None
        and (include_uncanny or key not in UNCANNY_ITEM_KEYS)
    )


def build_shop_gate_permutation(seed: str) -> dict[str, int]:
    """Assign each ordinary Bath stock group to exactly one shuffled badge gate."""
    shuffled = list(SHOP_GATE_IDS)
    Random(f"bloodborne-bath-shops:{seed}").shuffle(shuffled)
    return {str(stock_gate): unlock_gate
            for stock_gate, unlock_gate in zip(SHOP_GATE_IDS, shuffled)}


# bb-archipelago#207 wave 1. The filler top-up used to cycle a five-name list,
# which made every seed's flood log a wall of the same few names in the same
# order. Filler is now a weighted mix: the weights below are relative shares of
# the filler slots, allocated by largest remainder (so the composition is a
# function of the weights and the slot count, never of a draw) and then ordered
# by a Random seeded from the multiworld seed. Same seed, same pool; different
# seed, different arrangement. Blood Vial stays the heaviest share -- it is the
# item a Bloodborne run actually burns -- and remains FILLER_ITEM_NAME, which is
# what get_filler_item_name/create_filler hand back for unexpected top-ups.
FILLER_WEIGHTS: dict[str, int] = {
    "blood_vial": 6,
    "quicksilver_bullets": 4,
    "blood_stone_shards": 3,
    "twin_blood_stone_shards": 3,
    "blood_stone_chunks": 2,
    "pebbles": 2,
    "molotov_cocktails": 2,
    "throwing_knife": 2,
    "bone_marrow_ash": 2,
    "fire_paper": 2,
    "bolt_paper": 2,
    "poison_knife": 1,
    "antidote": 1,
    "sedatives": 1,
    "blue_elixir": 1,
    "beast_blood_pellet": 1,
    "lead_elixir": 1,
    "bold_hunters_mark": 2,
    "oil_urn": 1,
    "numbing_mist": 1,
    "pungent_blood_cocktail": 1,
    "shaman_bone_blade": 1,
    "madmans_knowledge": 1,
    "great_ones_wisdom": 1,
    "coldblood_dew": 1,
    "thick_coldblood": 1,
    "frenzied_coldblood": 1,
    "kin_coldblood": 1,
    "hunters_mark": 1,
    "delayed_molotov_cocktails": 1,
    "rope_molotov_cocktails": 1,
    "delayed_rope_molotov_cocktails": 1,
    "shining_coins": 1,
    "coldblood_dew_1": 1,
    "coldblood_dew_2": 1,
    "thick_coldblood_4": 1,
    "thick_coldblood_5": 1,
    "frenzied_coldblood_7": 1,
    "frenzied_coldblood_9": 1,
    "kin_coldblood_10": 1,
    "kin_coldblood_12": 1,
    "great_one_coldblood": 1,
    "old_great_one_coldblood": 1,
    "blood_of_arianna": 1,
    "blood_of_adella": 1,
    "iosefkas_blood_vial": 1,
    "blood_of_adeline": 1,
}
FILLER_WEIGHT_DEFAULT = 1

# Filler is shed from the lowest numbered tier first.  The ordering is about
# replacement value, not rarity: a single low-value echo packet is the first
# thing a new unique item should replace, while reinforcement materials are the
# last.  Unlisted combat/utility consumables deliberately land in tier 4.
FILLER_SHED_TIER: dict[str, int] = {
    "coldblood_dew": 0,
    "coldblood_dew_1": 0,
    "coldblood_dew_2": 0,
    "thick_coldblood_4": 0,
    "thick_coldblood_5": 0,
    "blood_vial": 1,
    "quicksilver_bullets": 1,
    "pebbles": 2,
    "throwing_knife": 2,
    "poison_knife": 2,
    "oil_urn": 2,
    "pungent_blood_cocktail": 2,
    "hunters_mark": 2,
    "shining_coins": 2,
    "thick_coldblood": 3,
    "frenzied_coldblood": 3,
    "kin_coldblood": 3,
    "frenzied_coldblood_7": 3,
    "frenzied_coldblood_9": 3,
    "kin_coldblood_10": 3,
    "kin_coldblood_12": 3,
    "great_one_coldblood": 3,
    "old_great_one_coldblood": 3,
    "madmans_knowledge": 3,
    "great_ones_wisdom": 3,
    "blood_stone_shards": 5,
    "twin_blood_stone_shards": 5,
    "blood_stone_chunks": 5,
}

# These are modest seed-wide floors, not guarantees when the whole filler
# budget is smaller than their sum.  In that case higher shed tiers win, so a
# tiny pool still favors upgrades and useful combat supplies.
FILLER_MINIMUMS: dict[str, int] = {
    "blood_vial": 8,
    "quicksilver_bullets": 6,
    "blood_stone_shards": 4,
    "twin_blood_stone_shards": 4,
    "blood_stone_chunks": 2,
    "molotov_cocktails": 2,
    "bone_marrow_ash": 2,
    "fire_paper": 2,
    "bolt_paper": 2,
    "antidote": 1,
    "sedatives": 1,
}


def _weighted_filler(
    candidates: list[tuple[str, str]], count: int, seed: str,
    *, envelope: int | None = None,
) -> list[str]:
    """Allocate `count` filler slots across `candidates` by weight, then order them.

    `candidates` is (key, name) in a fixed order, so the allocation is
    reproducible. Largest-remainder rather than a per-slot draw: the counts are
    exact and identical on every machine, and only the ARRANGEMENT depends on
    the seeded Random. A weightless key still gets a share (default 1) rather
    than silently vanishing from the mix.
    """
    if count <= 0 or not candidates:
        return []
    # Allocate the largest possible filler envelope, then shed its disposable
    # tail.  This is what makes adding one unique item remove exactly one item
    # from the earliest non-exhausted shed tier instead of proportionally
    # nibbling every useful supply category.
    envelope = count if envelope is None else max(count, envelope)
    weights = [FILLER_WEIGHTS.get(key, FILLER_WEIGHT_DEFAULT) for key, _ in candidates]
    total = sum(weights)
    quotas = [envelope * weight / total for weight in weights]
    allocation = [int(quota) for quota in quotas]
    remainder = envelope - sum(allocation)
    # Largest fractional part wins the leftover slots; ties break on candidate
    # order, so this is a pure function of (candidates, count).
    ranked = sorted(range(len(candidates)),
                    key=lambda index: (-(quotas[index] - allocation[index]), index))
    for index in ranked[:remainder]:
        allocation[index] += 1
    # Raise useful categories to their floors by transferring slots from the
    # most disposable categories.  Total size remains exactly the envelope.
    by_disposability = sorted(
        range(len(candidates)),
        key=lambda index: (FILLER_SHED_TIER.get(candidates[index][0], 4), index),
    )
    for index in reversed(by_disposability):
        wanted = min(FILLER_MINIMUMS.get(candidates[index][0], 0), envelope)
        while allocation[index] < wanted:
            donor = next((other for other in by_disposability
                          if other != index and allocation[other] > 0), None)
            if donor is None:
                break
            allocation[donor] -= 1
            allocation[index] += 1
    entries: list[tuple[int, int, str]] = []
    for index, ((key, name), share) in enumerate(zip(candidates, allocation)):
        floor = min(share, FILLER_MINIMUMS.get(key, 0))
        tier = FILLER_SHED_TIER.get(key, 4)
        entries.extend((100 + tier, index, name) for _ in range(floor))
        entries.extend((tier, index, name) for _ in range(share - floor))
    # Floors are a protected prefix; beyond them, higher tiers still outlive
    # lower ones. Candidate order is the stable tie-break within a tier.
    entries.sort(key=lambda entry: (-entry[0], entry[1]))
    names = [name for _, _, name in entries[:count]]
    Random(f"bloodborne-filler:{seed}").shuffle(names)
    return names


def build_item_pool_names(
    item_keys: Iterable[str], seed: str = "", capacity: int | None = None
) -> list[str]:
    """Build the varied-grant pool for the live slice's network locations.

    `item_keys` selects which validated items are placed once each; a weighted
    filler mix tops the pool up to the location count either way, so the seed
    size identity (pool == location count) holds in both `full_item_pool`
    modes. `seed` orders that mix and nothing else.

    Placement is three tiers, and the tiers are also the SHED ORDER when a seed
    has fewer locations than one-each items (bb-archipelago#207):

      1. progression -- never shed. A seed that cannot hold its own keys is a
         model error, not a pool to truncate, so it raises.
      2. useful one-each (weapons, the Augur) in data.py order.
      3. Uncanny variants (#205, option-gated) in data.py order.

    Uncanny sheds before base weapons, and each tier sheds from its tail: a
    variant is a second layout of a weapon the seed already has, so it is the
    cheapest thing to lose, and a base weapon the pool drops takes its variant
    with it only in the sense that the variant was already gone. Everything
    below the shed line is deterministic in data.py order, never draw-dependent.
    """
    selected = tuple(item for item in SHUFFLABLE_ITEMS if item.key in item_keys)
    progression = [item.name for item in selected if item.kind is ItemKind.PROGRESSION]
    useful = [item.name for item in selected
              if item.kind is ItemKind.USEFUL and item.key not in UNCANNY_ITEM_KEYS]
    uncanny = [item.name for item in selected if item.key in UNCANNY_ITEM_KEYS]
    # Option-off parity: opt-in combat checks must not silently grow callers
    # that use the historical default capacity rather than a world's active
    # location list. BloodborneWorld passes the active count explicitly.
    capacity = len(NETWORK_LOCATIONS) if capacity is None else capacity
    if len(progression) > capacity:
        raise ValueError(
            f"{len(progression)} progression items do not fit {capacity} locations; "
            "the pool cannot shed a key")
    names = list(progression)
    names.extend(useful[:max(0, capacity - len(names))])
    names.extend(uncanny[:max(0, capacity - len(names))])
    filler_candidates = [("blood_vial", FILLER_ITEM_NAME)]
    filler_candidates.extend(
        (item.key, item.name) for item in selected if item.kind is ItemKind.FILLER)
    filler_count = capacity - len(names)
    # Progression defines the maximum possible filler envelope. Useful and
    # optional unique items consume its disposable end in explicit tier order.
    filler_envelope = capacity - len(progression)
    names.extend(_weighted_filler(
        filler_candidates, filler_count, seed, envelope=filler_envelope))
    return names


class IdRegistryError(RuntimeError):
    """A key has no assigned network id, or the registry is malformed."""


def _load_id_registry(text: str) -> dict[str, dict[str, int]]:
    """Read the append-only key -> network id registry.

    Network ids are a permanent contract: they travel in multidata and in the
    datapackage, so a key's id must never change once released. Deriving them
    from tuple order made every id a function of position, so inserting one row
    in data.py silently renumbered everything after it. They are now looked up.
    """
    registry: dict[str, dict[str, int]] = {"item": {}, "location": {}}
    seen: dict[int, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("kind\t"):
            continue
        try:
            kind, key, raw = line.split("\t")
            value = int(raw, 16)
        except ValueError as exc:
            raise IdRegistryError(f"ids.tsv:{number}: malformed row: {line!r}") from exc
        if kind not in registry:
            raise IdRegistryError(f"ids.tsv:{number}: unknown kind {kind!r}")
        if key in registry[kind]:
            raise IdRegistryError(f"ids.tsv:{number}: duplicate {kind} key {key!r}")
        if value in seen:
            raise IdRegistryError(f"ids.tsv:{number}: id 0x{value:X} already used by {seen[value]!r}")
        seen[value] = key
        registry[kind][key] = value
    return registry


ID_REGISTRY = _load_id_registry(read_resource_text("ids.tsv"))


def _assigned(kind: str, key: str) -> int:
    try:
        return ID_REGISTRY[kind][key]
    except KeyError:
        raise IdRegistryError(
            f"no network id assigned for {kind} {key!r}. Add a row to "
            f"worlds/bloodborne/ids.tsv; never reuse an id and never change an existing one."
        ) from None


ITEM_ID_BY_KEY = {item.key: _assigned("item", item.key) for item in SHUFFLABLE_ITEMS}
ITEM_NAME_TO_ID = {item.name: ITEM_ID_BY_KEY[item.key] for item in SHUFFLABLE_ITEMS}
ITEM_NAME_TO_ID[FILLER_ITEM_NAME] = _assigned("item", "blood_vial")
# Stable network ids exist for the full reviewed manifest (ids.tsv is
# append-only), including rows the bounded slice does not seed. Only slice
# locations enter the datapackage's name->id map.
LOCATION_ID_BY_KEY = {loc.key: _assigned("location", loc.key) for loc in MODEL.locations}
LOCATION_NAME_TO_ID = {
    loc.name: LOCATION_ID_BY_KEY[loc.key] for loc in ALL_NETWORK_LOCATIONS
}


def build_runtime_slot_data(
    item_keys: Iterable[str] | None = None,
    goal_location_key: str = GOAL_LOCATION_KEY,
    location_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return the address-free world/client contract for this seed.

    `item_keys` is the pool actually placed (the full validated pool by
    default, matching the option's default; the Yharnam slice set when the
    option is off). The client only ever receives bindings for items the
    seed can grant.

    AP ids are serialized as object keys because JSON has no integer-keyed
    objects.  The client validates and converts them back to signed 64-bit ids.
    """
    active_keys = FULL_POOL_ITEM_KEYS if item_keys is None else frozenset(item_keys)
    active_location_keys = (
        frozenset(location.key for location in NETWORK_LOCATIONS)
        if location_keys is None else frozenset(location_keys)
    )
    locations_by_key = {
        location.key: location for location in ALL_NETWORK_LOCATIONS
        if location.key in active_location_keys
    }
    items_by_key = {item.key: item for item in SHUFFLABLE_ITEMS if item.key in active_keys}
    active_item_bindings = {
        key: ITEM_BINDINGS[key] for key in items_by_key
    }
    active_location_bindings = {
        key: LOCATION_BINDINGS[key] for key in locations_by_key
    }
    for key, binding in active_item_bindings.items():
        validate_runtime_item_binding(key, binding, items_by_key[key].quantity)
    locations = {
        str(LOCATION_ID_BY_KEY[key]): {
            "event_flag": binding.event_flag,
            "vanilla_award_suppressed": locations_by_key[key].vanilla_award_suppressed,
        }
        for key, binding in active_location_bindings.items()
    }
    items = {
        str(ITEM_ID_BY_KEY[key]): {
            "normalized_item_id": binding.normalized_item_id,
            "raw_descriptor": binding.raw_descriptor,
            "item_category": binding.item_category,
            "descriptor_evidence": binding.descriptor_evidence,
            "quantity": items_by_key[key].quantity,
            "reinforcement_level": binding.reinforcement_level,
            "feed_effect": binding.feed_effect,
            "award_lot_id": binding.award_lot_id,
            "gemgen_id": binding.gemgen_id,
            "award_ack_flag": binding.award_ack_flag,
        }
        for key, binding in active_item_bindings.items()
    }
    items[str(ITEM_NAME_TO_ID[FILLER_ITEM_NAME])] = {
        "normalized_item_id": 0x400003E8,
        "raw_descriptor": 0xB00003E8,
        "item_category": 4,
        "descriptor_evidence": "goods_formula_observed",
        "quantity": 1,
        "reinforcement_level": None,
        "feed_effect": "not_equippable",
    }
    suppression_required = any(
        row["vanilla_award_suppressed"] for row in locations.values()
    )
    return {
        "runtime_locations": locations,
        "runtime_items": items,
        "suppression": {
            "required": suppression_required,
            "manifest_format": SUPPRESSION_MANIFEST_FORMAT,
            "plan_sha256": SUPPRESSION_PLAN_SHA256,
        },
        "goal_location": LOCATION_ID_BY_KEY[goal_location_key],
        "sustain_item": sustain_item_binding(),
    }


def sustain_item_binding() -> dict[str, Any]:
    """The single good the client grants after every location check.

    The client used to hardcode this descriptor and shipped the wrong goods
    id (1100, the Antidote) for a day; publishing it here makes
    `runtime_bindings.py` the only source. Quantity is fixed at one.
    """
    binding = ITEM_BINDINGS["quicksilver_bullets"]
    return {
        "normalized_item_id": binding.normalized_item_id,
        "raw_descriptor": binding.raw_descriptor,
        "item_category": binding.item_category,
        "descriptor_evidence": binding.descriptor_evidence,
        "quantity": 1,
    }

try:
    from BaseClasses import Item as APItem, ItemClassification, Location as APLocation, Region
    from Options import Choice, DefaultOnToggle, PerGameCommonOptions, Range, Toggle
    from worlds.AutoWorld import World
except ImportError:
    __all__ = ["MODEL"]
else:
    from dataclasses import dataclass

    class AutoUpgrade(Toggle):
        """Raise received weapons to the player's validated reinforcement target."""
        display_name = "Auto Upgrade Received Weapons"
        default = 0

    class AutoEquip(Toggle):
        """Equip received gear in deterministic Archipelago feed order."""
        display_name = "Auto Equip Received Gear"
        default = 0

    class DeathLink(Toggle):
        """Receive linked deaths from other players.

        Sending your own deaths remains disabled until Bloodborne's live death
        signal has been validated; enabling this option currently participates
        in the receive half of DeathLink only.
        """
        display_name = "DeathLink (Receive Only)"
        default = 0

    class DeathLinkAmnesty(Range):
        """Forgive this many qualifying local deaths before sending DeathLink.

        The counter resets after a DeathLink is sent. Incoming DeathLinks do
        not consume amnesty. This seed-owned setting is inert while DeathLink
        is disabled and while the client is receive-only.
        """
        display_name = "DeathLink Amnesty (Local Deaths Forgiven per Cycle)"
        range_start = 0
        range_end = 255
        default = 0

    class FullItemPool(Toggle):
        """Place every validated item in the Yharnam slice, not only the six slice items.

        The playable area is unchanged; progression keys whose vanilla homes
        are outside the slice become forward unlocks found in Yharnam."""
        display_name = "Full Item Pool"
        default = 1

    class UncannyWeapons(Toggle):
        """Add the Uncanny variant of every weapon in your item pool.

        Uncanny weapons are normally locked behind Chalice dungeons. They are
        the same weapon with a different blood-gem slot layout, so a second
        find is a real build choice rather than a duplicate. They replace
        filler (Blood Vials and the like), never checks, so the seed keeps
        exactly as many items as it has locations."""
        display_name = "Uncanny Weapon Variants"
        default = 0

    class RandomizeArmor(Toggle):
        """Add each reviewed attire piece once to the general item pool.

        Armor replaces filler and does not create additional checks. This is
        opt-in while most category-1 delivery rows remain inferred; Old
        Hunters attire additionally requires the DLC option.
        """
        display_name = "Randomize Armor"
        default = 0

    class RandomizeStartingWeapons(Toggle):
        """Randomize the independent weapon and firearm choices in Hunter's Dream."""
        display_name = "Randomize Starting Weapons"
        default = 1

    class RemoveWeaponRequirements(Toggle):
        """Remove stat requirements from player weapons while preserving scaling."""
        display_name = "Remove Weapon Requirements"
        default = 1

    class RandomizeShops(Toggle):
        """Shuffle which hunter badge unlocks each ordinary Bath stock group.

        Prices, stock contents, NG-cycle copies, Insight shops, and Chalice
        shops are unchanged. This is opt-in because it deliberately changes
        familiar Bloodborne shop progression.
        """
        display_name = "Randomize Bath Messenger Shops"
        default = 0

    class RandomizeEnemyDrops(Choice):
        """Shuffle safe repeatable enemy consumable and material loot tables.

        This changes local consumable and material drops only. Enemy kills do
        not become Archipelago checks, and equipment, runes, blood gems,
        progression goods, and acquisition-flagged rewards are excluded. The
        balanced mode preserves loot-table cadence and rarity; dropsanity
        shuffles every eligible table together without compatibility grouping.
        """
        display_name = "Randomize Enemy Consumable Drops"
        option_off = 0
        option_balanced = 1
        option_dropsanity = 2
        default = 0

    class Goal(Choice):
        """Choose which of Bloodborne's three endings completes the seed.

        Submit to Gehrman ends after Mergo's Wet Nurse; refusing his offer
        requires defeating Gehrman; Moon Presence additionally requires any
        three of the four shuffled Third Umbilical Cords.
        """
        display_name = "Goal"
        option_submit_to_gehrman = 0
        option_refuse_gehrman = 1
        option_moon_presence = 2
        default = 2

        _display_labels = {
            0: "Submit to Gehrman (Mergo's Wet Nurse)",
            1: "Refuse Gehrman (Gehrman)",
            2: "Moon Presence (Three Umbilical Cords)",
        }

        @classmethod
        def get_option_name(cls, value: int) -> str:
            """Explain the completion trigger without changing YAML keys."""
            return cls._display_labels[value]

    class IncludeDLC(Toggle):
        """Include The Old Hunters regions, checks, and progression items."""
        display_name = "Include The Old Hunters DLC"
        default = 0

    class IncludeDLCGear(DefaultOnToggle):
        """Allow Old Hunters weapons and attire in the pool.

        This is independent of DLC world access: DLC gear can be received and
        used in a base-game route. Disable it to restrict equipment to the base
        game even when The Old Hunters locations are enabled.
        """
        display_name = "Include The Old Hunters Gear"

    class AlternateHypogeanGaolRoutes(Toggle):
        """Enable Snatcher abduction, Darkbeast Paarl, and the rear Old Yharnam gate.

        This intentionally permits nonstandard progression after the Blood
        Moon. It is off by default. Early abduction still requires defeating
        Blood-starved Beast and uses an authored Snatcher that enemy
        randomization is required to preserve.
        """
        display_name = "Alternate Hypogean Gaol Routes"
        default = 0

    class OneTimeEnemyChecks(Toggle):
        """Add checks for reviewed non-respawning hunters and unique enemies.

        Only encounters with a unique, durable, save-backed completion witness
        are eligible. Quest NPCs and composite fights remain excluded until
        their alternate outcomes can be represented safely.
        """
        display_name = "One-Time Hunter and Unique-Enemy Checks"
        default = 0

    @dataclass
    class BloodborneOptions(PerGameCommonOptions):
        auto_upgrade: AutoUpgrade
        auto_equip: AutoEquip
        death_link: DeathLink
        death_link_amnesty: DeathLinkAmnesty
        full_item_pool: FullItemPool
        uncanny_weapons: UncannyWeapons
        randomize_armor: RandomizeArmor
        randomize_starting_weapons: RandomizeStartingWeapons
        remove_weapon_requirements: RemoveWeaponRequirements
        randomize_shops: RandomizeShops
        randomize_enemy_drops: RandomizeEnemyDrops
        goal: Goal
        include_dlc: IncludeDLC
        include_dlc_gear: IncludeDLCGear
        alternate_hypogean_gaol_routes: AlternateHypogeanGaolRoutes
        one_time_enemy_checks: OneTimeEnemyChecks

    class BloodborneItem(APItem):
        game = GAME

    class BloodborneLocation(APLocation):
        game = GAME

    def _rule(rule: Rule, player: int):
        clauses = tuple(tuple(key for key in clause) for clause in rule.any_of)
        names = {item.key: item.name for item in MODEL.items}
        return lambda state: any(all(state.has(names[key], player) for key in clause) for clause in clauses)

    class BloodborneWorld(World):
        game = GAME
        options_dataclass = BloodborneOptions
        options: BloodborneOptions
        item_name_to_id = ITEM_NAME_TO_ID
        location_name_to_id = LOCATION_NAME_TO_ID
        origin_region_name = "Menu"

        def get_filler_item_name(self) -> str:
            """Archipelago's default picks a RANDOM name from item_name_to_id, and
            create_item classifies everything but the filler as progression — so
            without this the world hands out progression-classified keys as filler."""
            return FILLER_ITEM_NAME

        def create_item(self, name: str) -> BloodborneItem:
            if name == FILLER_ITEM_NAME:
                classification = ItemClassification.filler
            else:
                item = next(item for item in SHUFFLABLE_ITEMS if item.name == name)
                classification = {
                    ItemKind.PROGRESSION: ItemClassification.progression,
                    ItemKind.USEFUL: ItemClassification.useful,
                    ItemKind.FILLER: ItemClassification.filler,
                    ItemKind.TRAP: ItemClassification.trap,
                }[item.kind]
            return BloodborneItem(name, classification, ITEM_NAME_TO_ID[name], self.player)

        def create_regions(self) -> None:
            active_regions = set(SLICE_REGIONS)
            if self._alternate_gaol_enabled():
                active_regions |= ALTERNATE_GAOL_REGIONS
            if not self.options.include_dlc:
                active_regions -= DLC_REGIONS
            regions = {
                name: Region(name, self.player, self.multiworld)
                for name in (*SLICE_REGIONS, *sorted(ALTERNATE_GAOL_REGIONS))
                if name in active_regions
            }
            self.multiworld.regions.extend(regions.values())
            for data in self._active_locations():
                location = BloodborneLocation(self.player, data.name, LOCATION_ID_BY_KEY[data.key], regions[data.region])
                location.access_rule = _rule(data.rule, self.player)
                regions[data.region].locations.append(location)
                if data.locked_item:
                    # Boss defeated-events live on their own address-less
                    # event locations, mirroring the boss check's rule: the
                    # real check keeps a pool item, the event location feeds
                    # generation logic (Cathedral Ward behind Gascoigne).
                    event = next(item for item in EVENT_ITEMS if item.key == data.locked_item)
                    event_location = BloodborneLocation(self.player, event.name, None, regions[data.region])
                    event_location.access_rule = location.access_rule
                    event_location.place_locked_item(
                        BloodborneItem(event.name, ItemClassification.progression, None, self.player))
                    regions[data.region].locations.append(event_location)
            for data in SLICE_ENTRANCES:
                if data.name in DLC_ENTRANCE_NAMES and not self.options.include_dlc:
                    continue
                entrance = regions[data.source].create_exit(data.name)
                entrance.access_rule = _rule(data.rule, self.player)
                entrance.connect(regions[data.target])
            if self._alternate_gaol_enabled():
                for data in MODEL.entrances:
                    if data.name not in ALTERNATE_GAOL_ENTRANCE_NAMES:
                        continue
                    entrance = regions[data.source].create_exit(data.name)
                    entrance.access_rule = _rule(data.rule, self.player)
                    entrance.connect(regions[data.target])

        def create_items(self) -> None:
            for key in sorted(STARTING_TOOL_KEYS):
                item = next(item for item in SHUFFLABLE_ITEMS if item.key == key)
                self.multiworld.push_precollected(self.create_item(item.name))
            self.multiworld.itempool.extend(
                self.create_item(name)
                for name in build_item_pool_names(
                    self._pool_item_keys(), f"{self.multiworld.seed_name}:{self.player}",
                    capacity=len(self._active_locations()),
                )
            )

        def _active_locations(self):
            return tuple(
                location for location in ALL_NETWORK_LOCATIONS
                if self.options.include_dlc or location.key not in DLC_LOCATION_KEYS
                if (self._alternate_gaol_enabled()
                    or location.key not in ALTERNATE_GAOL_LOCATION_KEYS)
                if (self._one_time_enemy_checks_enabled()
                    or location.key not in ONE_TIME_ENEMY_LOCATION_KEYS)
            )

        def _alternate_gaol_enabled(self) -> bool:
            # getattr keeps small unit-test world doubles and old generated
            # option objects fail-closed during the transition to this option.
            return bool(getattr(self.options, "alternate_hypogean_gaol_routes", False))

        def _one_time_enemy_checks_enabled(self) -> bool:
            # Fail closed for old generated option objects and small test doubles.
            return bool(getattr(self.options, "one_time_enemy_checks", False))

        def _pool_item_keys(self) -> frozenset[str]:
            base = FULL_POOL_ITEM_KEYS if self.options.full_item_pool else SLICE_ITEM_KEYS
            if not self.options.include_dlc:
                # World access owns DLC progression and DLC-only consumables;
                # equipment has its own default-on pool policy below.
                base -= DLC_ITEM_KEYS - DLC_WEAPON_KEYS
            include_dlc_gear = bool(getattr(self.options, "include_dlc_gear", True))
            if not include_dlc_gear:
                base -= DLC_WEAPON_KEYS
            if bool(getattr(self.options, "randomize_armor", False)):
                armor = ATTIRE_ITEM_KEYS
                if not include_dlc_gear:
                    armor -= DLC_ATTIRE_ITEM_KEYS
                base |= armor
            if not self.options.uncanny_weapons:
                return base
            # One Uncanny variant per weapon this pool already places. A
            # weapon the pool does not carry gets no variant, so the option
            # never introduces an item whose base the seed cannot grant.
            return base | frozenset(
                uncanny for base_key, uncanny in UNCANNY_WEAPONS.items() if base_key in base
            )

        def set_rules(self) -> None:
            # Runtime completion is still authoritative: the client sends
            # CLIENT_GOAL when the debounced goal location flag is reported.
            # But the route to the Blood-starved Beast is no longer free --
            # Cathedral Ward, and therefore Old Yharnam, is behind the shuffled
            # Oedon Tomb Key. Leaving this unconditional would let fill bury the
            # key behind itself in a multiworld and call the seed complete.
            goal_name = next(location.name for location in ALL_NETWORK_LOCATIONS
                             if location.key == self._goal_location_key())
            self.multiworld.completion_condition[self.player] = (
                lambda state: state.can_reach_location(goal_name, self.player))

        def _goal_location_key(self) -> str:
            return GOAL_LOCATION_KEYS[int(self.options.goal)]

        def fill_slot_data(self) -> dict[str, Any]:
            seed = f"{self.multiworld.seed_name}:{self.player}"
            starting_weapons = (
                build_starting_weapon_choices(seed)
                if self.options.randomize_starting_weapons else None
            )
            requirement_families = (
                build_weapon_requirement_families(bool(self.options.uncanny_weapons))
                if self.options.remove_weapon_requirements else None
            )
            shop_gate_permutation = (
                build_shop_gate_permutation(seed)
                if self.options.randomize_shops else None
            )
            enemy_drop_option = getattr(self.options, "randomize_enemy_drops", 0)
            enemy_drop_enabled = bool(enemy_drop_option)
            enemy_drop_mode = (
                "dropsanity" if int(enemy_drop_option) == 2 else "balanced"
            ) if enemy_drop_enabled else None
            enemy_drop_assignments = (
                build_enemy_drop_assignments(seed, enemy_drop_mode)
                if enemy_drop_enabled else None
            )
            return {
                "version": 4,
                "world_version": WORLD_VERSION,
                "runtime_build": RUNTIME_BUILD,
                "auto_upgrade": bool(self.options.auto_upgrade),
                "auto_equip": bool(self.options.auto_equip),
                "death_link": bool(self.options.death_link),
                "death_link_amnesty": int(self.options.death_link_amnesty),
                "full_item_pool": bool(self.options.full_item_pool),
                "randomize_armor": bool(getattr(self.options, "randomize_armor", False)),
                "randomize_starting_weapons": bool(self.options.randomize_starting_weapons),
                "starting_weapons": starting_weapons,
                "remove_weapon_requirements": bool(self.options.remove_weapon_requirements),
                "randomize_shops": bool(self.options.randomize_shops),
                "shop_gate_permutation": shop_gate_permutation,
                "randomize_enemy_drops": enemy_drop_enabled,
                "enemy_drop_mode": enemy_drop_mode,
                "enemy_drop_assignments": enemy_drop_assignments,
                "goal": self.options.goal.current_key,
                "include_dlc": bool(self.options.include_dlc),
                "include_dlc_gear": bool(getattr(self.options, "include_dlc_gear", True)),
                "alternate_hypogean_gaol_routes": bool(
                    self._alternate_gaol_enabled()),
                "one_time_enemy_checks": self._one_time_enemy_checks_enabled(),
                "weapon_requirement_families": requirement_families,
                "enemizer_seed": seed,
                "toast_placeholders": self._toast_placeholder_plan(),
                "category8_awards": {
                    str(ITEM_ID_BY_KEY[row.item_key]): {
                        "item_key": row.item_key,
                        "token_goods_id": row.token_goods_id,
                        "item_lot_id": row.item_lot_id,
                        "gemgen_id": row.gemgen_id,
                        "ack_flag": row.ack_flag,
                        "source_lot_id": row.source_lot_id,
                    }
                    for row in CATEGORY8_AWARDS
                    if row.item_key in self._pool_item_keys()
                },
                **build_runtime_slot_data(
                    self._pool_item_keys() | STARTING_TOOL_KEYS,
                    self._goal_location_key(),
                    (location.key for location in self._active_locations()),
                ),
            }

        def _toast_placeholder_plan(self) -> dict[str, Any]:
            placements = []
            important_mask = ItemClassification.progression | ItemClassification.useful
            for data in self._active_locations():
                binding = LOCATION_BINDINGS[data.key]
                if not data.vanilla_award_suppressed or binding.item_lot_id is None:
                    continue
                placed = self.multiworld.get_location(data.name, self.player).item
                if placed is None:
                    continue
                placements.append(ToastPlacement(
                    location_key=data.key,
                    location_id=LOCATION_ID_BY_KEY[data.key],
                    item_lot_id=binding.item_lot_id,
                    item_name=placed.name,
                    recipient=self.multiworld.player_name[placed.player],
                    important=bool(placed.classification & important_mask),
                ))
            return build_toast_placeholder_plan(placements)

        def generate_output(self, output_directory: str) -> None:
            # The request file is the seed's identity document for the
            # launcher -- slot, player, world/runtime builds, and the
            # suppression plan hash all come from it -- so it is emitted for
            # every slot (#149). Whether
            # enemies are actually randomized is a launch-time decision;
            # `enemizer_seed` is one field of the identity, not its reason
            # to exist.
            request = {"format": "bb-seed-request-v1", **self.fill_slot_data(), "player": self.player,
                       "player_name": self.player_name}
            path = Path(output_directory) / f"{self.multiworld.get_out_file_name_base(self.player)}.bbseed.json"
            path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")

    __all__ = ["MODEL", "BloodborneWorld"]

    try:
        from worlds.LauncherComponents import Component, Type, components
        def _launch_client(*args: str) -> None:
            from .client import launch
            launch(*args)
        components.append(Component("Bloodborne Client", game_name=GAME, func=_launch_client,
                                    component_type=Type.CLIENT, supports_uri=True))
    except ImportError:
        pass
