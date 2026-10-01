"""Pinned Chalice humanoids at four arenas with multipart destination terminals."""

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import re

from tools.bb_inputs import read_blob, read_prefix
from . import chalice_humanoid_donors as humanoid
from . import ludwig_shadows_contract as shadows
from . import one_reborn_shadows_contract as shadow_parts
from . import chalice_one_reborn as reborn
from . import amelia_witch_contract as witch
from . import bsb_living_failures_contract as failures
from .boss_canary import event_blocks
from .boss_contracts import CLERIC_ARENA
from .encounter_recipes import EncounterRecipe
from .model import Swap, slot_placement
from .scaling import plan_scaling


@dataclass(frozen=True)
class ComplexArena:
    arena: object
    states: tuple
    retired: tuple
    helpers: tuple
    terminal_helpers: tuple
    generators: tuple
    bridge: int
    preserved: tuple


SHADOWS = ComplexArena(
    replace(
        CLERIC_ARENA,
        key="shadows-of-yharnam",
        event_file="m27_00_00_00.emevd.dcx.js",
        map_prefix="m27_00_",
        actor=2700800,
        archetype=shadows.SHADOW_ARCH[2700800],
        destination_count=2,
        completion_event=12701800,
        start_flag=12704800,
        health_bar_event=12704802,
        activation_event=12701802,
        music_event=12704803,
        lockcam_event=12704804,
        lockcam_map=27,
        expected=shadows.SHADOW_HASHES,
    ),
    tuple(shadows.SHADOW_PINS),
    (12704806, 12704807, 12704810, 12704811, 12704812, 12704815, 12704825, 12704830),
    shadow_parts.RETAINED_SHADOWS,
    (2700801, 2700802),
    (2705001, 2705002, 2705003),
    12997420,
    (12701800, 12701801, 12701803, 12704805),
)
ONE_REBORN = ComplexArena(
    reborn.ARENA,
    tuple(reborn.one.STATES),
    tuple(reborn.one.RETIRED_EVENTS),
    tuple(reborn.one.RETAINED),
    (2800803,),
    (),
    12997421,
    reborn.PRESERVED,
)
WITCH = ComplexArena(
    replace(
        CLERIC_ARENA,
        key="witch-of-hemwick",
        event_file="m22_00_00_00.emevd.dcx.js",
        map_prefix="m22_00_",
        actor=2200800,
        archetype=witch.WITCH_ARCHETYPE,
        destination_count=1,
        completion_event=12201800,
        start_flag=12204800,
        health_bar_event=12204802,
        activation_event=12201802,
        music_event=12204803,
        lockcam_event=12204804,
        lockcam_map=22,
        expected=witch.ARENA_HASHES,
    ),
    ("m22_00_00_00",),
    (
        12204807,
        12204808,
        12204810,
        12204811,
        12204812,
        12204814,
        12204820,
        12204830,
        12204832,
        12204835,
        12204838,
        12204839,
        12204840,
        12204841,
        12204842,
        12204843,
    ),
    (2200801, 2200810, 2200811, 2200812),
    (2200801,),
    witch.GENERATORS,
    12997422,
    (12201800, 12201801, 12201803, 12201804, 12204805),
)
FAILURES = ComplexArena(
    replace(
        CLERIC_ARENA,
        key="living-failures",
        event_file="m35_00_00_00.emevd.dcx.js",
        map_prefix="m35_00_",
        actor=failures.PRIMARY,
        archetype=failures.PRIMARY_ARCHETYPE,
        destination_count=1,
        completion_event=13501850,
        start_flag=13504858,
        health_bar_event=13504852,
        activation_event=13501851,
        music_event=13504853,
        lockcam_event=13504854,
        lockcam_map=35,
        expected=failures.ARENA_HASHES,
    ),
    ("m35_00_00_00",),
    failures.SUPPRESSED_EVENTS,
    (failures.PROXY, *failures.RETIRED_BODIES, failures.SUPPORT),
    (failures.PROXY,),
    (3503814, 3503815, 3503816, 3503817),
    12997423,
    (13501850, 13501852, 13504850, 13504851, 13504855, *failures.MARIA_EVENTS),
)
SPECS = {s.arena.key: s for s in (SHADOWS, ONE_REBORN, WITCH, FAILURES)}
PIN_FILE = Path(__file__).with_name("chalice_complex_arena_pins.json")
PIN_SHA256 = "b3290d8e7d8252791cc5821f1f701036055d9331a396266f7285d070ba7fc718"


def _pins():
    raw = PIN_FILE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PIN_SHA256:
        raise ValueError("complex arena actor pins changed")
    return json.loads(raw)["maps"]


def _verify(spec, destination, common):
    if spec.arena.key not in SPECS or SPECS[spec.arena.key] != spec:
        raise ValueError("unsupported complex Chalice arena")
    if spec is SHADOWS:
        original = shadows._verify(destination, spec.arena.expected, "Shadows arena")
    elif spec is FAILURES:
        original = event_blocks(destination)
        failures._verify(original, spec.arena.expected, "Living Failures arena")
    else:
        original = witch._verify(destination, spec.arena.expected, spec.arena.key)
    source = event_blocks(common)
    for eid, pin in humanoid.COMMON_EVENT_PINS.items():
        if hashlib.sha256(source.get(eid, "").encode()).hexdigest() != pin:
            raise ValueError("Chalice common source drift")
    used = {
        int(x)
        for blob in read_prefix(shadows.BUNDLE, "event/").values()
        for x in re.findall(rb"(?<![\w])-?\d+(?![\w])", blob)
    }
    if spec.bridge in used or re.search(rf"(?<!\d){spec.bridge}(?!\d)", destination):
        raise ValueError("complex Chalice bridge ID collision")
    return original, source


def _retirement(spec):
    lines = [f"    DeactivateGenerator({e}, Disabled);" for e in spec.generators]
    for e in spec.helpers:
        lines += [
            f"    SetCharacterAIState({e}, Disabled);",
            f"    SetCharacterHPBarDisplay({e}, Disabled);",
            f"    ChangeCharacterEnableState({e}, Disabled);",
            f"    SetCharacterInvincibility({e}, Enabled);",
        ]
        if e in spec.terminal_helpers:
            lines.append(f"    SetCharacterGravity({e}, Disabled);")
    return "\n".join(lines) + "\n"


def patch(spec, donor, destination, common):
    original, source = _verify(spec, destination, common)
    a = spec.arena
    health = humanoid._health(a, donor, source[12906806], original[a.health_bar_event])
    health = health.replace(
        "    EndIf(EventFlag", _retirement(spec) + "    EndIf(EventFlag", 1
    )
    health = humanoid._replace_once(
        health,
        "L4:\n",
        f"L4:\n    EndIf(EventFlag({a.completion_event}));\n",
        "combat completion guard",
    )
    if donor.wake_animation is not None:
        anchor = f"    SetCharacterAIState({a.actor}, Enabled);"
        health = humanoid._replace_once(
            health,
            anchor,
            f"    ForceAnimationPlayback({a.actor}, {donor.wake_animation}, false, false, false);\n"
            + anchor,
            "source wake before combat",
        )
    if spec is FAILURES or spec is ONE_REBORN:
        flag = 13504860 if spec is FAILURES else 12804223
        health = humanoid._replace_once(
            health,
            "            IssueBossRoomEntryNotification(0);",
            f"            if (!EventFlag({flag})) {{\n                IssueBossRoomEntryNotification(0);\n            }}",
            "destination notification owner",
        )
        health = humanoid._replace_once(
            health,
            "L0:\n",
            f"L0:\n    SetEventFlag({flag}, ON);\n    SetEventFlag({a.start_flag}, ON);",
            "battle notification flag",
        )
    activation = original[a.activation_event]
    if spec is SHADOWS:
        for actor in shadows.SHADOWS:
            for anim, loop in ((7001, "true"), (7000, "false")):
                activation = humanoid._replace_once(
                    activation,
                    f"    ForceAnimationPlayback({actor}, {anim}, {loop}, false, false);\n",
                    "",
                    "displaced Shadow animation",
                )
    elif spec is ONE_REBORN:
        activation = humanoid._replace_once(
            activation,
            "    ChangeCharacterEnableState(2800801, Enabled);\n",
            "",
            "displaced body activation",
        )
    elif spec is WITCH:
        activation = humanoid._replace_once(
            activation,
            "    if (!(PlayerInsightAmount() == 0 && CharacterType(10000, TargetType.Alive))) {\n"
            "        ForceAnimationPlayback(2200800, 3011, false, false, false);\n    }\n",
            "",
            "displaced Witch animation",
        )
    else:
        activation = failures._entry_without_failure_animation(activation)
    music = original[a.music_event]
    witness = {
        SHADOWS.arena.key: "EventFlag(12704808)",
        ONE_REBORN.arena.key: "CharacterHasEventMessage(2800800, 300)",
        WITCH.arena.key: "CharacterHPValue(2200800) == 1 || CharacterHPValue(2200801) == 1",
        FAILURES.arena.key: "EventFlag(13504870)",
    }[a.key]
    music = humanoid._replace_once(
        music,
        witness,
        f"CharacterHasEventMessage({a.actor}, 500)",
        "source phase music",
    )
    if spec is FAILURES:
        music = humanoid._replace_once(
            music,
            "    EndIf(EventFlag(13501800));",
            "    EndIf(EventFlag(13501850));",
            "Living Failures music completion",
        )
    camera = f"""$Event({a.lockcam_event}, Default, function() {{
    SetNetworkSyncState(Disabled);
    EndIf(EventFlag({a.completion_event}));
    WaitFor(EventFlag({a.health_bar_event}) || EventFlag({a.completion_event}));
    EndIf(EventFlag({a.completion_event}));
    SetLockcamSlotNumber({a.lockcam_map}, 0, 1);
    WaitFor(EventFlag({a.completion_event}));
    SetLockcamSlotNumber({a.lockcam_map}, 0, 0);
}});"""
    anchor = f"    $InitializeEvent(0, {a.health_bar_event});"
    constructor = humanoid._replace_once(
        original[0],
        anchor,
        anchor + f"\n    $InitializeEvent(0, {spec.bridge});",
        "terminal bridge initializer",
    )
    deaths = "\n".join(
        f"    SetCharacterInvincibility({e}, Disabled);\n"
        f"    ForceCharacterDeath({e}, false);"
        for e in spec.terminal_helpers
    )
    cleanup = ""
    if spec is FAILURES:
        cleanup = "    ClearSpEffect(10000, 8035);\n" + "".join(
            f"    DeleteMapSFX({e}, false);\n" for e in range(3503850, 3503855)
        )
    bridge = f"""$Event({spec.bridge}, Default, function() {{
{_retirement(spec)}{cleanup}    if (EventFlag({a.completion_event})) {{
{deaths}
        EndEvent();
    }}
    WaitFor(CharacterDead({a.actor}) || EventFlag({a.completion_event}));
    EndIf(EventFlag({a.completion_event}));
{cleanup}{deaths}
}});"""
    edits = {
        0: constructor,
        a.health_bar_event: health,
        a.activation_event: activation,
        a.music_event: music,
        a.lockcam_event: camera,
        **{eid: humanoid._noop(original[eid]) for eid in spec.retired},
    }
    if spec is ONE_REBORN:
        edits[12801803] = humanoid._replace_once(
            original[12801803],
            "    ChangeCharacterEnableState(2800801, Enabled);\n",
            "",
            "guest displaced body activation",
        )
    result = (
        humanoid._replace_events(destination, edits).rstrip() + "\n\n" + bridge + "\n"
    )
    after = event_blocks(result)
    if set(after) != set(original) | {spec.bridge}:
        raise ValueError("complex Chalice event identities changed")
    for eid, body in original.items():
        if (eid not in edits or eid in spec.preserved) and after[eid] != body:
            raise ValueError("complex Chalice progression changed")
    return result


def native_plan(spec, donor, slots, npcs, effects, seed):
    a = spec.arena
    maps = _pins()
    sources = [
        r
        for r in slots
        if r.map_name == donor.map_name
        and r.part_name == donor.part_name
        and r.entity_id == donor.actor
        and r.archetype == donor.archetype
        and not r.dummy
        and not r.talk_id
    ]
    if len(sources) != 1:
        raise ValueError("complex Chalice source actor drift")
    by_id = {(r.map_name, r.entity_id): r for r in slots}
    targets = []
    retained = []
    for state in spec.states:
        for eid in (a.actor, *spec.helpers):
            witness = maps[state][str(eid)]
            row = by_id.get((state, eid))
            if (
                sum(r.map_name == state and r.entity_id == eid for r in slots) != 1
                or row is None
                or row.dummy
                or row.part_name != witness["name"]
                or asdict(row.archetype) != witness["source_archetype"]
                or row.talk_id
            ):
                raise ValueError("complex Chalice destination actor roster drift")
            if eid == a.actor:
                targets.append(row)
            else:
                retained.append(
                    {
                        "map": state,
                        "part": row.part_name,
                        "entity_id": eid,
                        "archetype": asdict(row.archetype),
                        "source_provenance": {
                            "format": "bb-boss-actor-pin-v1",
                            "part_sha256": witness["fingerprint"],
                        },
                        "source_initialization": witness["source_initialization"],
                        "policy": "disabled; terminal helpers invincible until replacement death",
                    }
                )
    if len({r.logical_key for r in targets}) != 1:
        raise ValueError("complex Chalice logical destination drift")
    target = targets[0]
    source = sources[0]
    swap = Swap(
        target.logical_key,
        [r.key for r in targets],
        {r.key: r.archetype for r in targets},
        target.archetype,
        source.archetype,
        destinations={r.key: slot_placement(r) for r in targets},
    )
    changes, skips = plan_scaling(
        [swap], targets, dict(npcs), dict(effects), boss_tiers=True
    )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "primary_init_source_bindings": [
            {
                "source_event_file": "event/" + donor.event_file,
                "source_map": source.map_name,
                "source_part": source.part_name,
                "source_entity_id": source.entity_id,
                "source_archetype": asdict(source.archetype),
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": donor.part_sha256,
                },
                "source_initialization": dict(humanoid.SOURCE_INITIALIZATION),
                "destination_map": r.map_name,
                "destination_part": r.part_name,
                "destination_entity_id": r.entity_id,
                "required_native_fields": [
                    "talk_id",
                    "unk_t18",
                    "init_anim_id",
                    "damage_anim_id",
                    "provenance",
                ],
            }
            for r in targets
        ],
        "boss_contract": {
            "format": "bb-chalice-complex-arena-v1",
            "arena": a.key,
            "donor": donor.key,
            "runtime_status": "unobserved",
            "added_event_ids": [spec.bridge],
            "preserved_destination_events": list(spec.preserved),
            "retained_destination_helpers": retained,
            "source_map_event_zero_sha256": donor.map_event_zero_sha256,
            "source_map_initializers": [
                donor.health_initializer,
                donor.music_initializer,
                donor.wake_initializer,
            ],
        },
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [r.json() for r in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }


def recipes():
    for spec in SPECS.values():
        for donor in humanoid.DONORS.values():
            yield EncounterRecipe(
                spec.arena,
                donor,
                "chalice-complex-arena:source-combat",
                lambda destination, source, s=spec, d=donor: patch(
                    s, d, destination, source
                ),
                lambda slots, npcs, effects, seed, s=spec, d=donor: native_plan(
                    s, d, slots, npcs, effects, seed
                ),
                lambda slots: [],
            )
