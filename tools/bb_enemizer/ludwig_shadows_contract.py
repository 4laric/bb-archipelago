"""Evidence-pinned Ludwig two-phase combat in Shadows of Yharnam's arena.

The three Shadow primaries are retained, disabled destination parts.  Ludwig's
phase graph runs on the first slot and a pinned phase-two clone; a bridge only
releases the original Shadows terminal after both donor forms are dead. Runtime
arena behavior remains unobserved.
"""

from __future__ import annotations
import hashlib, re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence
from tools.bb_inputs import read_blob, read_prefix
from .boss_canary import event_blocks
from .bosses import parse_events
from .ludwig_contract import EVENTS, P1, P2, SOURCE_HASHES
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
LUDWIG_SOURCE = "event/m34_00_00_00.emevd.dcx.js"
SHADOWS_SOURCE = "event/m27_00_00_00.emevd.dcx.js"
LUDWIG_ONE, LUDWIG_TWO = 3400800, 3400801
SHADOWS = (2700800, 2700801, 2700802)
SHADOW_ARCH = {
    2700800: Archetype("c2120", 212700, 212700, 0),
    2700801: Archetype("c2120", 212710, 212710, 0),
    2700802: Archetype("c2120", 212720, 212720, 0),
}
SHADOW_PINS = {
    "m27_00_00_00": {
        2700800: "f91f3492e77e0bfe20d4fa74b00229042b67404c4e8549b9ce49060579424388",
        2700801: "8ccbe181a9a9fac58f32b5c433e61303b7616d12c6bb072cfa7c3ab4f7ba6c14",
        2700802: "1c6709b46409807298c98e359b537fd8ff0cf73c88a071ad608441fefe90e004",
    },
    "m27_00_00_01": {
        2700800: "9c63e91372ea1cf3093643f4d35c5db431459c5b7282ac67fd2da36ddf236c76",
        2700801: "4b16e3c84d27cecb4c199f5b15280bf3ae0ff43a3dd25df76a8a37f5fc3c2d54",
        2700802: "38b9927061ff3aa4e608ffabb5c5fdab0cf30157e64722be4438a5d7e7bc2bce",
    },
}
SHADOW_HASHES = {
    0: "5eb47b935baa6e9e53251c01e15322d10a36025601e67617a3624ab975e5071a",
    12701800: "cd44f8e4d12d4b7851212b338cf92b0507aa9a7ef7a9584e61961bb3d7ebfa07",
    12701801: "94f19133e42357f7f839445e097195431141f65924a93de2cc052db99dabc40e",
    12701802: "44f2363adb49d6ce98ba68186988c55b9d086770fb4c8e99759f1f48dbfcc28b",
    12701803: "53ba2a173c8aff960d5dffddbdc26da3300cbc97832bba4ac3c84728f19eefb0",
    12704802: "d25c72b2ce42007c119cafcbafbe84c16b5d71dcfb19f938ae0020a08e9ad1e8",
    12704803: "7ad45bce51000cc00388884064813e4c082ec40c1b66d137450910d8c1adac42",
    12704804: "e327421106416287d3ddba66344720877da0ac544f7796fb6a3bb14b458ec60c",
    12704805: "4b5d0e7a8f9bf349d1b2f69277857fef5517a016cf635b1d4f57a3ce59765eac",
    12704806: "3fe1f420f7e6f700a83d4c525abd8ff4612497693f931a817fd3e819469c0d34",
    12704807: "808daf264c202bda492e3ecf3d53a8949842be943306b69394f53d2d35715263",
    12704810: "7f9cc850816d93614c0c7e74376595595397ebed03752c186a71e4a269e67319",
    12704811: "533c1800e81c196c21b004f8689593ad0d681e217e211a028451388799826037",
    12704812: "f163cafc6cb33e9b151016cf914ee23cc26b8daf74567988c32f5bfa5abb9aaf",
    12704815: "a2a4722c6b05e8c46b161de5b190b2b94e2e8165797a6a17a21f25aced454539",
    12704825: "c2cf31fbd2f5312e363fc7cb4e7dab038b062b2d28c019ce054bb7b4c6d84ca7",
    12704830: "d4cad144bb2531d7824f6abcd69804c523e7d1e64f5bf3bafb05aeb1e17f9532",
}
LUDWIG_PINS = {
    LUDWIG_ONE: "79c5c55b1660c9ca6d517e25fe5ab685bb7b6ec8e53bad5406b3433bf9c798a8",
    LUDWIG_TWO: "6ff68750b7bed265be44daed1a4d6522a1d4fb0563519693d2cde4035d04c296",
}


@dataclass(frozen=True)
class LudwigShadowsIds:
    phase_entity: int = 981200
    bridge: int = 12993410
    cleanup: int = 12993411
    phase_flag: int = 12993440
    entry_notified_flag: int = 12993441

    def event_ids(self):
        return {e: 12993420 + i for i, e in enumerate(EVENTS)}

    def values(self):
        return (
            *self.event_ids().values(),
            self.bridge,
            self.cleanup,
            self.phase_flag,
            self.entry_notified_flag,
        )


DEFAULT_IDS = LudwigShadowsIds()
# Installed CUSA03173 source has a witnessed AlwaysUpdate variant for the hidden phase actor.
SOURCE_ALTERNATES = {
    13404802: "02a77d3081f5fa336ec6db647099ef975dd7bca6f38da26b9d6176564ff814ab"
}
# Installed CUSA03173 replaces the unrelated 12700907 quest initializer with
# 12700910; the boss constructors and all pinned combat events are identical.
ARENA_ALTERNATES = {
    0: "5b0e8366a437736280662cf2a12428b122b69b510cead07c45a9fc67f7492b42"
}


def _verify(text, pins, label):
    b = event_blocks(text)
    for e, h in pins.items():
        actual = hashlib.sha256(b.get(e, "").encode()).hexdigest()
        alternates = ARENA_ALTERNATES if label == "Shadows arena" else SOURCE_ALTERNATES
        if actual not in {h, alternates.get(e)}:
            raise ValueError(f"unsupported original {label} event {e}")
    return b


def _replace(text, edits):
    lines = text.splitlines()
    for e in reversed(parse_events(text)):
        if e.event_id in edits:
            lines[e.first_line - 1 : e.last_line] = edits[e.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _remap(text, m):
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])", lambda x: str(m.get(int(x[0]), int(x[0]))), text
    )


def _end(block):
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda m: "function("
        + ", ".join("unused_" + x.strip() for x in m[1].split(",") if x.strip())
        + ")",
        block.splitlines()[0],
    )
    return header + "\n    EndEvent();\n});"


def _original_ids():
    return {
        int(x)
        for b in read_prefix(BUNDLE, "event/").values()
        for x in re.findall(rb"(?<![\w])-?\d+(?![\w])", b)
    }


def _check(ids, dest):
    if (
        len(set(ids.values())) != len(ids.values())
        or any(x < 12993400 or x > 12993499 for x in ids.values())
        or set(ids.values())
        & (_original_ids() | set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", dest))))
    ):
        raise ValueError("Ludwig/Shadows IDs must be collision-free 129934xx values")
    if ids.phase_entity in _original_ids():
        raise ValueError("Ludwig/Shadows helper ID collides")


def patch_ludwig_at_shadows(destination, donor, ids=DEFAULT_IDS):
    arena = _verify(destination, SHADOW_HASHES, "Shadows arena")
    source = _verify(donor, SOURCE_HASHES, "Ludwig donor")
    _check(ids, destination)
    ev = ids.event_ids()
    m = {
        LUDWIG_ONE: 2700800,
        LUDWIG_TWO: ids.phase_entity,
        9471: 12701800,
        13401800: 12701800,
        13404802: 12704802,
        13404810: ids.entry_notified_flag,
        13404804: 12704804,
        13404808: 12704800,
        13404825: ids.phase_flag,
        3403802: 2703802,
        3403803: 2703803,
        3402802: 2702802,
        3400010: 2700010,
        34: 27,
        **ev,
    }
    # All source normal-phase events are retained with their authored bodies/constructor slots.
    imported = {ev[e]: _remap(source[e], m) for e in EVENTS}
    normal = source[0].split(
        "    if (!EventFlag(13400999)) {\n        $InitializeEvent(0, 13404824);", 1
    )
    if len(normal) != 2:
        raise ValueError("Ludwig/Shadows normal constructor witness drift")
    normal = normal[1].split("    } else {", 1)[0]
    ctor = []
    for e in EVENTS:
        constructor = normal if e in (13404830, 13404835, 13404841) else source[0]
        rows = [
            line
            for line in constructor.splitlines()
            if re.search(r"\$InitializeEvent\([^,]+,\s*" + str(e) + r"(?:,|\))", line)
        ]
        if len(rows) != (3 if e == 13404830 else 1):
            raise ValueError(f"Ludwig/Shadows missing source initializer witness {e}")
        ctor.extend(_remap(row, m) for row in rows)
    source_health = source[13404802].replace(
        "    if (EventFlag(13400999)) {\n        SetSpEffect(3400800, 8040, false);\n        SetSpEffect(3400801, 8040, false);\n    }\n",
        "",
    )
    health = _remap(source_health, m)
    disabled = "\n".join(
        [
            f"    DeactivateGenerator({entity}, Disabled);"
            for entity in (2705001, 2705002, 2705003)
        ]
        + [
            f"    SetCharacterAIState({entity}, Disabled);\n    ChangeCharacterEnableState({entity}, Disabled);\n    ForceCharacterDeath({entity}, false);"
            for entity in (
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
        ]
    )
    health = health.replace(
        f"    SetCharacterAIState({ids.phase_entity}, Disabled);",
        f"    SetCharacterAIState({ids.phase_entity}, Disabled);\n    ChangeCharacterEnableState({ids.phase_entity}, Disabled);\n"
        + disabled,
    )
    health = health.replace(
        "    CreatePlaylog(46);\n    StartTimeMeasurement(2700010, 62, Enabled);",
        "    CreatePlaylog(82);\n    StartTimeMeasurement(2700010, 98, Enabled);",
    )
    bridge = f"""$Event({ids.bridge}, Default, function() {{
    EndIf(EventFlag(12701800));
    WaitFor(CharacterDead(2700800) || CharacterDead({ids.phase_entity}));
    ForceCharacterDeath({ids.phase_entity}, false);
    ForceCharacterDeath(2700801, false);
    ForceCharacterDeath(2700802, false);
    ForceCharacterDeath(2700800, false);
}});"""
    cleanup = f"""$Event({ids.cleanup}, Default, function() {{
    WaitFor(EventFlag(12701800));
    DeactivateGenerator(2705001, Disabled);
    DeactivateGenerator(2705002, Disabled);
    DeactivateGenerator(2705003, Disabled);
    ChangeCharacterEnableState({ids.phase_entity}, Disabled);
    ForceCharacterDeath({ids.phase_entity}, false);
    ChangeCharacterEnableState(2700801, Disabled);
    ChangeCharacterEnableState(2700802, Disabled);
    ChangeCharacterEnableState(2700803, Disabled);
    ChangeCharacterEnableState(2700804, Disabled);
    ChangeCharacterEnableState(2700805, Disabled);
    ChangeCharacterEnableState(2700810, Disabled);
    ChangeCharacterEnableState(2700811, Disabled);
    ChangeCharacterEnableState(2700813, Disabled);
    ChangeCharacterEnableState(2700814, Disabled);
}});"""
    edits = {
        0: arena[0].replace(
            "});",
            "\n"
            + "\n".join(
                ctor
                + [
                    f"    $InitializeEvent(0, {ids.bridge});",
                    f"    $InitializeEvent(0, {ids.cleanup});",
                ]
            )
            + "\n});",
            1,
        ),
        12701802: re.sub(
            r"    ForceAnimationPlayback\(270080[012], 700[01], (?:true|false), false, false\);\n",
            "",
            arena[12701802],
        ),
        12704802: health,
        12704803: arena[12704803].replace(
            "EventFlag(12704808)", f"EventFlag({ids.phase_flag})"
        ),
        12704804: _remap(source[13404804], m),
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
    result = (
        _replace(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join((*imported.values(), bridge, cleanup))
        + "\n"
    )
    out = event_blocks(result)
    if out[12701800] != arena[12701800] or out[12701801] != arena[12701801]:
        raise ValueError("Ludwig/Shadows changed terminal or rewards")
    if set(out) != set(arena) | set(ev.values()) | {ids.bridge, ids.cleanup}:
        raise ValueError(
            f"Ludwig/Shadows changed event identities added={sorted(set(out)-set(arena))} missing={sorted(set(arena)-set(out))}"
        )
    return result


def _need(slots, e, a):
    r = [s for s in slots if s.entity_id == e]
    if len(r) != 1 or r[0].dummy or r[0].talk_id or r[0].archetype != a:
        raise ValueError(f"Ludwig/Shadows requires pinned actor {e}")
    return r[0]


def native_plan_ludwig_at_shadows(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids=DEFAULT_IDS,
):
    donor = read_blob(BUNDLE, LUDWIG_SOURCE).decode("utf-8-sig")
    arena = read_blob(BUNDLE, SHADOWS_SOURCE).decode("utf-8-sig")
    patch_ludwig_at_shadows(arena, donor, ids)
    source = _need(slots, LUDWIG_ONE, P1)
    phase = _need(slots, LUDWIG_TWO, P2)
    targets = [
        s
        for s in slots
        if s.entity_id == 2700800
        and s.archetype == SHADOW_ARCH[2700800]
        and not s.dummy
        and not s.talk_id
    ]
    retained = {
        entity: [
            s
            for s in slots
            if s.entity_id == entity
            and s.archetype == SHADOW_ARCH[entity]
            and not s.dummy
            and not s.talk_id
        ]
        for entity in (2700801, 2700802)
    }
    states = {"m27_00_00_00", "m27_00_00_01"}
    if {s.map_name for s in targets} != states or any(
        {s.map_name for s in rows} != states for rows in retained.values()
    ):
        raise ValueError("Ludwig/Shadows requires all two-state Shadows primaries")
    swap = Swap(
        targets[0].logical_key,
        [s.key for s in targets],
        {s.key: s.archetype for s in targets},
        SHADOW_ARCH[2700800],
        P1,
        warnings=[
            "experimental Ludwig-at-Shadows contract; runtime arena behavior is unobserved"
        ],
        destinations={
            s.key: {
                "map_name": s.map_name,
                "entity_id": s.entity_id,
                "x": s.x,
                "y": s.y,
                "z": s.z,
            }
            for s in targets
        },
    )
    changes, skips = plan_scaling(
        [swap], targets, dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError("Ludwig/Shadows primary normalization is ambiguous")
    pin = lambda p: {"format": "bb-boss-actor-pin-v1", "part_sha256": p}
    additions = []
    bindings = []
    requirements = []
    for target in targets:
        additions.append(
            {
                "source_map": phase.map_name,
                "source_part": phase.part_name,
                "source_anchor_part": source.part_name,
                "source_entity_id": LUDWIG_TWO,
                "source_archetype": asdict(P2),
                "source_part_kind": "enemy",
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": LUDWIG_PINS[LUDWIG_TWO],
                    "anchor_sha256": LUDWIG_PINS[LUDWIG_ONE],
                },
                "source_initialization": {
                    "talk_id": 0,
                    "unk_t18": -1,
                    "init_anim_id": -1,
                    "damage_anim_id": -1,
                },
                "destination_map": target.map_name,
                "destination_anchor_part": target.part_name,
                "destination_part": "ap_ludwig_shadows_phase",
                "destination_entity_id": ids.phase_entity,
                "allocation_evidence": "project-reserved helper ID; native writer checks collisions",
            }
        )
        bindings.append(
            {
                "source_map": source.map_name,
                "source_part": source.part_name,
                "source_entity_id": LUDWIG_ONE,
                "source_archetype": asdict(P1),
                "source_provenance": pin(LUDWIG_PINS[LUDWIG_ONE]),
                "source_initialization": {
                    "talk_id": 0,
                    "unk_t18": -1,
                    "init_anim_id": -1,
                    "damage_anim_id": -1,
                },
                "destination_map": target.map_name,
                "destination_part": target.part_name,
                "destination_entity_id": target.entity_id,
            }
        )
        requirements.append(
            {
                "destination_map": target.map_name,
                "destination_part": "ap_ludwig_shadows_phase",
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": P2.npc_param_id,
                "strategy": "allocate_distinct_verified_helper_clone",
            }
        )
    retained_rows = []
    for entity, rows in retained.items():
        for row in rows:
            retained_rows.append(
                {
                    "map": row.map_name,
                    "part": row.part_name,
                    "entity_id": row.entity_id,
                    "archetype": asdict(row.archetype),
                    "source_provenance": pin(SHADOW_PINS[row.map_name][entity]),
                    "source_initialization": {
                        "talk_id": 0,
                        "unk_t18": -1,
                        "init_anim_id": -1,
                        "damage_anim_id": -1,
                    },
                    "policy": "disabled and force-killed by Ludwig death bridge before retained terminal observes all three",
                }
            )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "shadows-of-yharnam<-ludwig"},
        "boss_actor_additions": additions,
        "primary_init_source_bindings": bindings,
        "boss_actor_scaling_requirements": requirements,
        "boss_contract": {
            "format": "bb-ludwig-shadows-contract-v1",
            "arena": "shadows-of-yharnam",
            "donor": "ludwig",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(SOURCE_HASHES),
            "arena_hash_pins": dict(SHADOW_HASHES),
            "preserved_destination_events": [
                12701800,
                12701801,
                12701803,
                12704805,
            ],
            "retained_destination_helpers": retained_rows,
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
            "event_patch": {
                "changed_events": [
                    0,
                    12701802,
                    12704802,
                    12704803,
                    12704804,
                    *[
                        e
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
                    ],
                ],
                "added_events": [*ids.event_ids().values(), ids.bridge, ids.cleanup],
            },
        },
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [c.json() for c in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
