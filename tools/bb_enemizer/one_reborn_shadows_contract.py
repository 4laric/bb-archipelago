"""Pinned One Reborn multipart combat in the Shadows of Yharnam arena.

The adapter extracts the already source-pinned One Reborn body/caster closure,
then binds it to Shadows' three-body terminal. Source proxy death alone releases
that terminal by killing all three retained Shadow primaries. Arena fit remains
static-only and unobserved.
"""

from __future__ import annotations
import hashlib, re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence
from tools.bb_inputs import read_blob, read_prefix
from .boss_canary import event_blocks
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling
from . import one_reborn_ebrietas_contract as one
from . import ludwig_shadows_contract as shadows

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
ONE_REBORN_SOURCE = one.ONE_REBORN_SOURCE
SHADOWS_SOURCE = shadows.SHADOWS_SOURCE
CORE, BODY, CONTROLLER, PROXY = one.CORE, one.BODY, one.CONTROLLER, one.PROXY
CASTERS = one.CASTERS
TARGET = 2700800
RETAINED_SHADOWS = (
    2700801,
    2700802,
    2700803,
    2700804,
    2700805,
    2700810,
    2700811,
    2700813,
    2700814,
)
RETAINED_SHADOW_ARCH = {
    2700801: Archetype("c2120", 212710, 212710, 0),
    2700802: Archetype("c2120", 212720, 212720, 0),
    2700803: Archetype("c5033", 503300, 503300, 0),
    2700804: Archetype("c5033", 503300, 503300, 0),
    2700805: Archetype("c5033", 503300, 503300, 0),
    2700810: Archetype("c2121", 212750, 1, 0),
    2700811: Archetype("c2121", 212751, 1, 0),
    2700813: Archetype("c2121", 212751, 1, 0),
    2700814: Archetype("c2121", 212750, 1, 0),
}
RETAINED_SHADOW_PINS = {
    "m27_00_00_00": {
        2700801: "8ccbe181a9a9fac58f32b5c433e61303b7616d12c6bb072cfa7c3ab4f7ba6c14",
        2700802: "1c6709b46409807298c98e359b537fd8ff0cf73c88a071ad608441fefe90e004",
        2700803: "bffcc44cd445e14090eff8ef29a1b9d8cdf717efac0e64857bbc7797d4f8c414",
        2700804: "fe48cb5b9c15c3e2c06dce5741c44885479173f5f87d6e25ceb13b22fa4e4c75",
        2700805: "a7e982caff8e1c7e06b6c37904b799f74309a675e87c5f51503df80e6b1faaa5",
        2700810: "3594fbdfd43d55c4ce6c55492bb2d617b4bb7c344365cc5e47dcd991723a5319",
        2700811: "caefa28112ca49b443225f712689082d96756b8ee9adc49c116341af1220dbac",
        2700813: "0e65038d5541f99afca785c76c2a724d9d81be4c787d44c5d3659acb4b7b9743",
        2700814: "a6472d31f6ac74a5e2ba1a22d2d164f8d721224db1cc7729dc220e91ba4b700b",
    },
    "m27_00_00_01": {
        2700801: "4b16e3c84d27cecb4c199f5b15280bf3ae0ff43a3dd25df76a8a37f5fc3c2d54",
        2700802: "38b9927061ff3aa4e608ffabb5c5fdab0cf30157e64722be4438a5d7e7bc2bce",
        2700803: "3e3d623cb736af26c0817953130f4e0539902d128b9cb9055c8b4aa8bbe095d6",
        2700804: "01f6bd46e73554f2501a85597578fbe9cf70e319daf227b1e4ad3de8e6398b3a",
        2700805: "037cbbbd9ec73d136a4385e4308c04a58b798209cd215ecd1289c908096492a5",
        2700810: "c3af02df0a239c62a00c06045f9a0f5542ad5f340073a56e14f8f4e62762b95b",
        2700811: "f8c343f1b2ff9a5fef380d3e7defee1d2930301b00f21d0437c8e5d2bd61d938",
        2700813: "bd0f887ecdbc97e21f64d71fd514a32d1ae870a1c5a5eacc5e0d46d4c329621a",
        2700814: "0be1e518744cc012f86953527188b54cfc3608dc1fcdabe095060a9badda6fbc",
    },
}
PROJECT_MIN, PROJECT_MAX = 12994600, 12994699


@dataclass(frozen=True)
class OneRebornShadowsIds:
    camera: int = 12994600
    tether: int = 12994601
    limb_guard: int = 12994602
    limb_flag: int = 12994603
    limb_first: int = 12994604
    controller_first: int = 12994611
    caster_react: int = 12994619
    caster_count: int = 12994621
    phase_one: int = 12994627
    phase_two: int = 12994628
    bridge: int = 12994629
    cleanup: int = 12994630
    caster_count_flag: int = 12994640
    notification_flag: int = 12994644
    helper_first: int = 982300

    def events(self):
        # Preserve the source initializer-family order.  Do not infer this
        # from the default numeric gap: callers may choose collision-free
        # project IDs, and every named field must participate in remapping and
        # collision checks.
        return (
            self.camera,
            self.tether,
            self.limb_guard,
            *range(self.limb_first, self.limb_first + 7),
            *range(self.controller_first, self.controller_first + 8),
            self.caster_react,
            self.caster_react + 1,
            *range(self.caster_count, self.caster_count + 6),
            self.phase_one,
            self.phase_two,
            self.bridge,
            self.cleanup,
        )

    def values(self):
        return self.events() + (
            self.limb_flag,
            *range(self.caster_count_flag, self.caster_count_flag + 4),
            self.notification_flag,
        )


DEFAULT_IDS = OneRebornShadowsIds()


def _replace(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for e in reversed(parse_events(source)):
        if e.event_id in edits:
            lines[e.first_line - 1 : e.last_line] = edits[e.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _remap(text: str, m: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])", lambda x: str(m.get(int(x[0]), int(x[0]))), text
    )


def _end(block: str) -> str:
    return shadows._end(block)


def _verify(text, pins, label):
    return shadows._verify(text, pins, label)


def _original_ids():
    return {
        int(x)
        for b in read_prefix(BUNDLE, "event/").values()
        for x in re.findall(rb"(?<![\w])-?\d+(?![\w])", b)
    }


def _validate(ids: OneRebornShadowsIds, dest: str) -> None:
    vals = set(ids.values())
    helpers = set(range(ids.helper_first, ids.helper_first + 9))
    used = _original_ids() | set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", dest)))
    if (
        len(vals) != len(ids.values())
        or any(not PROJECT_MIN <= x <= PROJECT_MAX for x in vals)
        or vals & used
        or helpers & used
        or any(not 982300 <= x <= 982399 for x in helpers)
    ):
        raise ValueError(
            "One Reborn/Shadows IDs must be collision-free 129946xx/982300-range values"
        )


def _stage(donor: str):
    # Canonical Ebrietas source is used only to obtain the existing donor-side
    # closure. It is never emitted into the Shadows patch.
    ebrietas = read_blob(BUNDLE, one.EBRIETAS_SOURCE).decode("utf-8-sig")
    return event_blocks(one.patch_one_reborn_at_ebrietas(ebrietas, donor))


def _map(ids: OneRebornShadowsIds):
    old = one.DEFAULT_IDS
    m = {
        2420800: TARGET,
        2800800: TARGET,
        2420801: 2700801,
        12421800: 12701800,
        12421802: 12701802,
        12424800: 12704800,
        12424802: 12704802,
        12424803: 12704803,
        12424804: 12704804,
        2423802: 2703802,
        2423803: 2703803,
        2422802: 2702802,
        2420010: 2700010,
        981000: ids.helper_first,
        981001: ids.helper_first + 1,
        981002: ids.helper_first + 2,
        981003: ids.helper_first + 3,
        981004: ids.helper_first + 4,
        981005: ids.helper_first + 5,
        981006: ids.helper_first + 6,
        981007: ids.helper_first + 7,
        981008: ids.helper_first + 8,
    }
    for src, dst in zip(old.events(), ids.events()):
        m[src] = dst
    for src, dst in zip(old.values(), ids.values()):
        m[src] = dst
    return m


def patch_one_reborn_at_shadows(
    destination: str, donor_source: str, ids: OneRebornShadowsIds = DEFAULT_IDS
) -> str:
    arena = _verify(destination, shadows.SHADOW_HASHES, "Shadows arena")
    one._verify(donor_source, one.DONOR_HASHES, "One Reborn donor")
    _validate(ids, destination)
    staged = _stage(donor_source)
    m = _map(ids)
    old = one.DEFAULT_IDS
    imported = {
        m[e]: _remap(staged[e], m)
        for e in old.events()
        if e not in (old.bridge, old.cleanup)
    }
    # The original Shadows terminal observes all three bodies.  Retain its two
    # non-primary bodies as terminal witnesses, but make them unavailable until
    # the donor proxy bridge releases their authored death path.  Every snake,
    # c2121 helper, and summon generator named by the established Ludwig/Shadows
    # adapter is retired before the donor health event can activate combat.
    retained_terminal = (2700801, 2700802)
    retired_shadow_helpers = (
        2700803,
        2700804,
        2700805,
        2700810,
        2700811,
        2700813,
        2700814,
    )
    precombat_retirement = "\n".join(
        [
            f"    DeactivateGenerator({entity}, Disabled);"
            for entity in (2705001, 2705002, 2705003)
        ]
        + [
            f"    SetCharacterAIState({entity}, Disabled);\n"
            f"    SetCharacterHPBarDisplay({entity}, Disabled);\n"
            f"    SetCharacterImmortality({entity}, Enabled);\n"
            f"    ChangeCharacterEnableState({entity}, Disabled);"
            for entity in retained_terminal
        ]
        + [
            f"    SetCharacterAIState({entity}, Disabled);\n"
            f"    ChangeCharacterEnableState({entity}, Disabled);\n"
            f"    ForceCharacterDeath({entity}, false);"
            for entity in retired_shadow_helpers
        ]
    )
    health = (
        _remap(staged[12424802], m)
        .replace(
            "    SetCharacterAIState(2700800, Disabled);",
            "    SetCharacterAIState(2700800, Disabled);\n" + precombat_retirement,
            1,
        )
        .replace("CreatePlaylog(104);", "CreatePlaylog(82);")
        .replace(
            "StartTimeMeasurement(2700010, 40, Enabled);",
            "StartTimeMeasurement(2700010, 98, Enabled);",
        )
    )
    source_music = event_blocks(donor_source)[12804803]
    if source_music.count("SetMapSoundState(2803804, Disabled);") != 2:
        raise ValueError("One Reborn/Shadows source music ambience witness drift")
    music = _remap(
        source_music.replace(
            "        SetMapSoundState(2803804, Disabled);\n", ""
        ).replace("    SetMapSoundState(2803804, Disabled);\n", ""),
        {
            **m,
            12801800: 12701800,
            12804802: 12704802,
            12804801: 12704801,
            12804803: 12704803,
            2802802: 2702802,
            2803802: 2703802,
            2803803: 2703803,
            2800010: 2700010,
        },
    )
    camera = imported[ids.camera].replace(
        "SetLockcamSlotNumber(24, 2,", "SetLockcamSlotNumber(27, 0,"
    )
    if camera.count("SetLockcamSlotNumber(27, 0,") != 2:
        raise ValueError("One Reborn/Shadows camera mapping lost source writes")
    imported[ids.camera] = camera
    activation = re.sub(
        r"    ForceAnimationPlayback\(270080[012], 700[01], (?:true|false), false, false\);\n",
        "",
        arena[12701802],
    )
    bridge = f"""$Event({ids.bridge}, Default, function() {{
    EndIf(EventFlag(12701800));
    WaitFor(HPRatio({ids.helper_first+2}) <= 0);
    ForceCharacterDeath({ids.helper_first}, false);
    ForceCharacterDeath({ids.helper_first+1}, false);
    ForceCharacterDeath({ids.helper_first+2}, false);
    ForceCharacterDeath({ids.helper_first+3}, false);
    ForceCharacterDeath({ids.helper_first+4}, false);
    ForceCharacterDeath({ids.helper_first+5}, false);
    ForceCharacterDeath({ids.helper_first+6}, false);
    ForceCharacterDeath({ids.helper_first+7}, false);
    ForceCharacterDeath({ids.helper_first+8}, false);
    SetCharacterImmortality(2700801, Disabled);
    SetCharacterImmortality(2700802, Disabled);
    ForceCharacterDeath(2700801, false);
    ForceCharacterDeath(2700802, false);
    ForceCharacterDeath(2700800, false);
}});"""
    cleanup = (
        f"""$Event({ids.cleanup}, Default, function() {{
    WaitFor(EventFlag(12701800));
    DeactivateGenerator(2705001, Disabled);
    DeactivateGenerator(2705002, Disabled);
    DeactivateGenerator(2705003, Disabled);
    ChangeCharacterEnableState(2700801, Disabled);
    ChangeCharacterEnableState(2700802, Disabled);
    ChangeCharacterEnableState(2700803, Disabled);
    ChangeCharacterEnableState(2700804, Disabled);
    ChangeCharacterEnableState(2700805, Disabled);
    ChangeCharacterEnableState(2700810, Disabled);
    ChangeCharacterEnableState(2700811, Disabled);
    ChangeCharacterEnableState(2700813, Disabled);
    ChangeCharacterEnableState(2700814, Disabled);
"""
        + "".join(
            f"    ChangeCharacterEnableState({ids.helper_first+i}, Disabled);\n"
            for i in range(9)
        )
        + "});"
    )
    # Event(0) must retain source initializer argument slots for every imported
    # body/caster routine; stage has already checked those exact source witnesses.
    staged_ctor = staged[0]
    imported_events = set(old.events()) - {old.bridge, old.cleanup}
    rows = []
    for line in staged_ctor.splitlines():
        match = re.search(r"\$InitializeEvent\([^,]+,\s*(\d+)(?:,|\))", line)
        if match and int(match.group(1)) in imported_events:
            rows.append(line)
    translated = [_remap(x, m) for x in rows]
    ctor = arena[0].replace(
        "});",
        "\n"
        + "\n".join(
            translated
            + [
                f"    $InitializeEvent(0, {ids.bridge});",
                f"    $InitializeEvent(0, {ids.cleanup});",
            ]
        )
        + "\n});",
        1,
    )
    edits = {
        0: ctor,
        12701802: activation,
        12704802: health,
        12704803: music,
        12704804: _end(arena[12704804]),
        **{
            e: _end(arena[e])
            for e in (
                12704806,
                12704807,
                12704810,
                12704811,
                12704812,
                12704815,
                12704825,
                12704830,
            )
        },
    }
    out = (
        _replace(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join((*imported.values(), bridge, cleanup))
        + "\n"
    )
    headers = re.findall(r"\$Event\((\d+),", out)
    duplicates = sorted({x for x in headers if headers.count(x) > 1})
    if duplicates:
        raise ValueError("duplicate event definition " + repr(duplicates))
    blocks = event_blocks(out)
    if set(blocks) != set(arena) | set(ids.events()):
        raise ValueError("One Reborn/Shadows changed event identities")
    for e in (12701800, 12701801, 12701803, 12704805):
        if blocks[e] != arena[e]:
            raise ValueError(
                "One Reborn/Shadows changed Shadows terminal, rewards, fog, or progression"
            )
    copied = "\n".join(blocks[e] for e in (12704802, 12704803, 12704804, *ids.events()))
    if re.search(r"(?<!\d)(?:124|128|242|280|981)\d+(?!\d)", copied):
        raise ValueError("One Reborn/Shadows retains donor or staging literals")
    return out


def _rows(slots, e, a, states):
    # Keep the multiplicity check before indexing by map: a duplicate physical
    # part must not be hidden by a dict overwrite.
    rows = [s for s in slots if s.entity_id == e and s.map_name in states]
    x = {state: [s for s in rows if s.map_name == state] for state in states}
    if any(len(matches) != 1 for matches in x.values()):
        raise ValueError(f"One Reborn/Shadows requires pinned actor {e}")
    result = {state: matches[0] for state, matches in x.items()}
    if any(s.dummy or s.talk_id or s.archetype != a for s in result.values()):
        raise ValueError(f"One Reborn/Shadows requires pinned actor {e}")
    return result


def native_plan_one_reborn_at_shadows(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: OneRebornShadowsIds = DEFAULT_IDS,
) -> dict:
    donor = read_blob(BUNDLE, ONE_REBORN_SOURCE).decode("utf-8-sig")
    arena = read_blob(BUNDLE, SHADOWS_SOURCE).decode("utf-8-sig")
    patch_one_reborn_at_shadows(arena, donor, ids)
    sources = _rows(slots, CORE, one.ARCH[CORE], one.SOURCE_STATES)
    states = ("m27_00_00_00", "m27_00_00_01")
    targets = _rows(slots, TARGET, shadows.SHADOW_ARCH[TARGET], states)
    retained_targets = {
        entity: _rows(slots, entity, RETAINED_SHADOW_ARCH[entity], states)
        for entity in RETAINED_SHADOWS
    }
    donors = {
        e: _rows(slots, e, one.ARCH[e], one.SOURCE_STATES)
        for e in (BODY, CONTROLLER, PROXY, *CASTERS)
    }
    swap = Swap(
        targets["m27_00_00_00"].logical_key,
        [x.key for x in targets.values()],
        {x.key: x.archetype for x in targets.values()},
        shadows.SHADOW_ARCH[TARGET],
        one.ARCH[CORE],
        warnings=[
            "experimental One Reborn-at-Shadows contract; static source positions and arena fit are unobserved"
        ],
        destinations={
            x.key: {
                "map_name": x.map_name,
                "entity_id": x.entity_id,
                "x": x.x,
                "y": x.y,
                "z": x.z,
            }
            for x in targets.values()
        },
    )
    changes, skips = plan_scaling(
        [swap], list(targets.values()), dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError("One Reborn/Shadows primary normalization is ambiguous")
    additions = []
    bindings = []
    req = []
    helpers = (BODY, CONTROLLER, PROXY, *CASTERS)
    for ss, ts in zip(one.SOURCE_STATES, states):
        core, target = sources[ss], targets[ts]
        bindings.append(
            {
                "source_map": ss,
                "source_part": core.part_name,
                "source_entity_id": CORE,
                "source_archetype": asdict(one.ARCH[CORE]),
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": one.PINS[ss][CORE],
                },
                "source_initialization": {
                    "talk_id": 0,
                    "unk_t18": -1,
                    "init_anim_id": -1,
                    "damage_anim_id": -1,
                },
                "destination_map": ts,
                "destination_part": target.part_name,
                "destination_entity_id": TARGET,
            }
        )
        for i, e in enumerate(helpers):
            src = donors[e][ss]
            part = (
                "body",
                "controller",
                "proxy",
                "caster_0",
                "caster_1",
                "caster_2",
                "caster_3",
                "caster_4",
                "caster_5",
            )[i]
            additions.append(
                {
                    "source_map": ss,
                    "source_part": src.part_name,
                    "source_anchor_part": core.part_name,
                    "source_entity_id": e,
                    "source_archetype": asdict(one.ARCH[e]),
                    "source_part_kind": "enemy",
                    "source_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": one.PINS[ss][e],
                        "anchor_sha256": one.PINS[ss][CORE],
                    },
                    "source_initialization": {
                        "talk_id": 0,
                        "unk_t18": -1,
                        "init_anim_id": -1,
                        "damage_anim_id": -1,
                    },
                    "destination_map": ts,
                    "destination_anchor_part": target.part_name,
                    "destination_part": "ap_one_reborn_shadows_" + part,
                    "destination_entity_id": ids.helper_first + i,
                    "allocation_evidence": "project-reserved helper ID; native writer checks collisions",
                }
            )
            req.append(
                {
                    "destination_map": ts,
                    "destination_part": "ap_one_reborn_shadows_" + part,
                    "parent_logical_key": swap.logical_key,
                    "source_npc_param_id": one.ARCH[e].npc_param_id,
                    "strategy": (
                        "reviewed_same_source_npc_helper_clone_required"
                        if e in (BODY, PROXY)
                        else "allocate_distinct_verified_helper_clone"
                    ),
                }
            )
    retained = []
    for entity, rows in retained_targets.items():
        for state in states:
            slot = rows[state]
            retained.append(
                {
                    "map": state,
                    "part": slot.part_name,
                    "entity_id": entity,
                    "archetype": asdict(RETAINED_SHADOW_ARCH[entity]),
                    "source_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": RETAINED_SHADOW_PINS[state][entity],
                    },
                    "source_initialization": {
                        "talk_id": 0,
                        "unk_t18": -1,
                        "init_anim_id": -1,
                        "damage_anim_id": -1,
                    },
                    "policy": "disabled before combat; bridge force-kills this retained Shadows actor before the original terminal observes all three primaries",
                }
            )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "shadows-of-yharnam<-the-one-reborn"},
        "boss_actor_additions": additions,
        "primary_init_source_bindings": bindings,
        "boss_actor_scaling_requirements": req,
        "boss_contract": {
            "format": "bb-one-reborn-shadows-contract-v1",
            "arena": "shadows-of-yharnam",
            "donor": "the-one-reborn",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(one.DONOR_HASHES),
            "arena_hash_pins": dict(shadows.SHADOW_HASHES),
            "preserved_destination_events": [12701800, 12701801, 12701803, 12704805],
            "retained_destination_helpers": retained,
            "retired_shadow_controllers": [
                12704806,
                12704807,
                12704810,
                12704811,
                12704812,
                12704815,
                12704825,
                12704830,
            ],
            "retired_precombat_helpers": {
                "generators": [2705001, 2705002, 2705003],
                "enemies": [
                    2700803,
                    2700804,
                    2700805,
                    2700810,
                    2700811,
                    2700813,
                    2700814,
                ],
                "terminal_witnesses": [2700801, 2700802],
            },
            "destination_operand_policy": {
                "source_music_region": 2802802,
                "destination_region": 2702802,
                "evidence": "original m27 event 12704803 gates Shadows boss music on InArea(10000, 2702802); both donor combat-area checks use that existing destination combat region",
            },
            "geometry_risk": "One Reborn core/body/casters use source anchor-relative MSBB placement; source-to-Shadows arena fit is unobserved",
        },
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [x.json() for x in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
