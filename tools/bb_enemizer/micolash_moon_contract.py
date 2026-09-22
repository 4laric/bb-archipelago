"""Pinned Micolash direct combat in the Moon Presence arena.

The adapter retains the Moon Presence entry, terminal, final-game progression,
camera and arena music.  Micolash starts in ordinary combat AI instead of the
Mensis chase command, while a source-witnessed half-health phase marker drives
the music change without importing labyrinth navigation or dialogue.
Runtime behavior remains unobserved.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_canary import event_blocks
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
DONOR_SOURCE = "event/m26_00_00_00.emevd.dcx.js"
ARENA_SOURCE = "event/m21_00_00_00.emevd.dcx.js"

MICOLASH, MOON = 2600850, 2100810
COMPLETION = 12101850
MICOLASH_ARCHETYPE = Archetype("c0000", 6380, 6380, 0)
MOON_ARCHETYPE = Archetype("c5400", 540000, 540000, 0)
MICOLASH_PIN = "ab37480d123ba5807ace745e2238c7891782479dec1fc3222267f62040460d35"
MOON_PIN = "fb6b3c45b1c16ec4aa7bc8ff6cb2107caa06f98a4e6c26bd7f0d3064f84f4e67"
TALK_SOURCE_SHA256 = "afb70280a2420792066af1f6602c2202576d649d891609662e8e53303af2c56b"

DONOR_HASHES = {
    0: "bead3d1536484484169804138a1649d272cba5793b92b73179c6046c48aad1a0",
    12604852: "112297fc525671f09775db60260f66099231acb795864747771e0482071abc97",
    12604853: "d1f257fd7d39dfee586737b765bc62d760471d2f4cc79b2448ccfe920e513548",
    12604856: "3e34966b4ec1b3c4690c9abf8da6764853dad3f991b699e232805cb677a4831e",
    12604877: "8c8cd83c7618d50e648791817d1aff3b3f4b25ff79c9bf669a6b9fffe1bc7f77",
    12604879: "8022c6e0fdea139635bd31ae38b9885ec63981faaf51abc76d67ff80c19c3496",
    12604980: "95e1c09d27344c80d361f433fcca2fc380abcbdfff44f37bce1adaf5bb4fac60",
}

ARENA_HASHES = {
    0: "fa40b334c1c2f7972b424b1332d9d23d4ed68c2c120f463c194431e46533df26",
    50: "047fb05a53f37ca562dbfc2dfefdc6d66a7dbb3d610e2af2ea9db11609623603",
    12100800: "8e6939c8f1c87e2c89440a45bf91b739eed45158c03556b491f66b86a2bd4552",
    12101850: "ae1a5ecc4c0d2149f20d20a414cb8e374db9de618aa264ec226d48bedc738fdb",
    12101851: "dfcd61e16f66078bb9b3684bd34d54bf53b8ce8d9e39006252839a9ee296051f",
    12101852: "0bde50f079f63078dd127d785f34e8ebdd8fce5cdaf44f5f5581fb69c01df3fb",
    12101853: "0af3db4f4d7710d985b8ba674edfab6f39eabc18607485974b22df59f295d425",
    12104852: "a4022f49059e7bc5cb6a076481065f8418a885876121ec9a8f731120ccfe395e",
    12104853: "38b0df8eb0fb98bdf5e9e5f2c752f5220ffe23b35e5645e53eebad46e42adce4",
    12104854: "32ebde44a49a6b7a58b9ab4bc6b84e3187e8d3fb5721ef6ab19bab853ba65fe4",
    12104855: "99b339663849ea8bc818155aa85dfded02f8a7c6ebf7b04360f40b071749815b",
    12104860: "5b91d32d18d586cd20510e5157b5ca35b7783efe137e6120dfd2c60d62cd6af9",
    12104870: "dc32a765534443ea5b41c0d1646f0d658417d29c359357cfb6daf1d00d483ad6",
}


@dataclass(frozen=True)
class MicolashMoonIds:
    phase_state: int = 12993100
    phase_marker: int = 12993120
    evidence: str = "Micolash/Moon allocation v1; full original EMEVD and MSBB scan"

    def events(self) -> tuple[int, ...]:
        return (self.phase_state,)


DEFAULT_IDS = MicolashMoonIds()


def _verify(blocks: Mapping[int, str], pins: Mapping[int, str], role: str) -> None:
    for event, digest in pins.items():
        actual = hashlib.sha256(blocks.get(event, "").encode()).hexdigest()
        if actual != digest:
            raise ValueError(f"unsupported original {role} event {event}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Micolash/Moon expected one {label}")
    return text.replace(old, new, 1)


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(values.get(int(match[0]), int(match[0]))),
        text,
    )


def _end_event(block: str) -> str:
    header = block.splitlines()[0]
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            "unused_" + name.strip() for name in match[1].split(",") if name.strip()
        )
        + ")",
        header,
    )
    return header + "\n    EndEvent();\n});"


@cache
def _original_literals() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            map(
                int,
                re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")),
            )
        )
    rows = read_prefix(BUNDLE, "mined/")
    for name in ("mined/msb_enemies.tsv", "mined/msb_regions.tsv"):
        for row in rows.get(name, b"").decode("utf-8-sig").splitlines()[1:]:
            for value in row.split("\t"):
                if value.lstrip("-").isdigit():
                    values.add(int(value))
    return values


def _validate(ids: MicolashMoonIds, destination: str) -> None:
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    allocated = (*ids.events(), ids.phase_marker)
    if (
        len(set(allocated)) != len(allocated)
        or any(not 12993100 <= value <= 12993199 for value in allocated)
        or set(allocated).intersection(local | _original_literals())
        or not ids.evidence.strip()
    ):
        raise ValueError("Micolash/Moon allocation collides with original inputs")


def direct_combat_health(
    source: str,
    *,
    actor: int,
    completion: int,
    start_flag: int,
    coop_flag: int,
    health_event: int,
    time_event: int,
    playlog: int,
    measurement: int,
) -> str:
    """Adapt pinned Micolash health setup without importing chase or dialogue."""
    mapping = {
        MICOLASH: actor,
        12601850: completion,
        12604850: start_flag,
        12604851: coop_flag,
        12604852: health_event,
        2601010: time_event,
    }
    health = _remap(source, mapping)
    health = _replace_once(
        health,
        "        if (!HasMultiplayerState(MultiplayerState.Client)) {\n"
        "            if (!EventFlag(12604731)) {\n"
        "                IssueBossRoomEntryNotification(0);\n"
        "            }\n"
        f"            SetNetworkUpdateAuthority({actor}, AuthorityLevel.Forced);\n"
        "        }",
        "        if (!HasMultiplayerState(MultiplayerState.Client)) {\n"
        "            IssueBossRoomEntryNotification(0);\n"
        f"            SetNetworkUpdateAuthority({actor}, AuthorityLevel.Forced);\n"
        "        }",
        "destination boss-room notification",
    )
    health = _replace_once(
        health,
        "    SetEventFlag(12604731, ON);\n",
        "",
        "donor boss-room notification flag",
    )
    health = _replace_once(
        health,
        f"    SetDistanceLimitForConversationStateProcessing({actor}, 100);\n",
        "",
        "donor dialogue processing",
    )
    health = _replace_once(
        health,
        f"    RequestCharacterAICommand({actor}, 10, 0);",
        f"    RequestCharacterAICommand({actor}, -1, 0);\n"
        f"    RequestCharacterAIReplan({actor});",
        "source chase command release",
    )
    health = _replace_once(
        health,
        "CreatePlaylog(88);",
        f"CreatePlaylog({playlog});",
        "destination playlog",
    )
    health = _replace_once(
        health,
        f"StartTimeMeasurement({time_event}, 232, Enabled);",
        f"StartTimeMeasurement({time_event}, {measurement}, Enabled);",
        "destination time measurement",
    )
    return health


def patch_micolash_at_moon(
    destination: str,
    donor_source: str,
    ids: MicolashMoonIds = DEFAULT_IDS,
) -> str:
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, ARENA_HASHES, "Moon Presence arena")
    _verify(donor, DONOR_HASHES, "Micolash donor")
    _validate(ids, destination)
    health = direct_combat_health(
        donor[12604852],
        actor=MOON,
        completion=COMPLETION,
        start_flag=12104850,
        coop_flag=12104851,
        health_event=12104852,
        time_event=2100011,
        playlog=128,
        measurement=146,
    )
    music = _replace_once(
        arena[12104853],
        "WaitFor(CharacterHasEventMessage(2100810, 500));",
        f"WaitFor(EventFlag({ids.phase_marker}));",
        "source-witnessed second-phase state",
    )
    phase = f"""$Event({ids.phase_state}, Default, function() {{
    EndIf(EventFlag({COMPLETION}));
    if (!ThisEvent()) {{
        SetEventFlag({ids.phase_marker}, OFF);
        WaitFor(EventFlag(12104852) && HPRatio({MOON}) <= 0.5);
    }}
L0:
    SetEventFlag({ids.phase_marker}, ON);
    RequestCharacterAICommand({MOON}, -1, 0);
    RequestCharacterAIReplan({MOON});
}});"""
    constructor = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 12104870);",
        "    $InitializeEvent(0, 12104870);\n"
        f"    $InitializeEvent(0, {ids.phase_state});",
        "Moon combat initializer anchor",
    )
    edits = {
        0: constructor,
        12104852: health,
        12104853: music,
        12104860: _end_event(arena[12104860]),
        12104870: _end_event(arena[12104870]),
    }
    result = _replace_events(destination, edits).rstrip() + "\n\n" + phase + "\n"
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.events()):
        raise ValueError("Micolash/Moon changed event identities")
    for event, original in arena.items():
        if event not in edits and output[event] != original:
            raise ValueError(f"Micolash/Moon changed unrelated event {event}")
    for event in (
        50,
        12100800,
        12101850,
        12101851,
        12101852,
        12101853,
        12104854,
        12104855,
    ):
        if output[event] != arena[event]:
            raise ValueError("Micolash/Moon changed destination progression")
    copied = "\n".join(output[event] for event in (12104852, ids.phase_state))
    if re.search(r"(?<!\d)(?:126|260)\d+(?!\d)", copied):
        raise ValueError("Micolash/Moon retains donor-map literals")
    return result


def _require(
    slots: Sequence[Slot], entity: int, archetype: Archetype, talk_id: int
) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.entity_id == entity and slot.archetype == archetype
    ]
    if len(found) != 1 or found[0].dummy or found[0].talk_id != talk_id:
        raise ValueError(f"Micolash/Moon requires pinned actor {entity}")
    return found[0]


def primary_native_plan(slots, npcs, effects, seed, target, contract) -> dict:
    """Build source-pinned Micolash primary state for a reviewed arena contract."""
    source = _require(slots, MICOLASH, MICOLASH_ARCHETYPE, 260311)
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        source.archetype,
        warnings=[
            "runtime direct-combat AI and source phase-state behavior require validation"
        ],
        destinations={
            target.key: {
                "map_name": target.map_name,
                "entity_id": target.entity_id,
                "x": target.x,
                "y": target.y,
                "z": target.z,
            }
        },
    )
    changes, skips = plan_scaling(
        [swap], [target], dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError("Micolash/Moon primary normalization is ambiguous")
    binding = {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": MICOLASH_PIN,
        },
        "source_initialization": {
            "talk_id": 260311,
            "unk_t18": 6380,
            "init_anim_id": -1,
            "damage_anim_id": -1,
        },
        "destination_map": target.map_name,
        "destination_part": target.part_name,
        "destination_entity_id": target.entity_id,
        "destination_original_talk_id": target.talk_id,
        "destination_talk_id_override": 0,
        "required_native_fields": [
            "talk_id",
            "unk_t18",
            "init_anim_id",
            "damage_anim_id",
            "provenance",
            "destination_talk_id_override",
        ],
    }
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "primary_init_source_bindings": [binding],
        "boss_contract": contract,
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }


def native_plan_micolash_at_moon(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: MicolashMoonIds = DEFAULT_IDS,
) -> dict:
    arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
    donor = read_blob(BUNDLE, DONOR_SOURCE).decode("utf-8-sig")
    _verify(event_blocks(arena), ARENA_HASHES, "Moon Presence arena")
    _verify(event_blocks(donor), DONOR_HASHES, "Micolash donor")
    _validate(ids, arena)
    target = _require(slots, MOON, MOON_ARCHETYPE, 0)
    return primary_native_plan(
        slots,
        npcs,
        effects,
        seed,
        target,
        {
            "format": "bb-micolash-moon-contract-v1",
            "arena": "moon-presence",
            "donor": "micolash",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "preserved_destination_events": [
                50,
                12100800,
                12101850,
                12101851,
                12101852,
                12101853,
                12104854,
                12104855,
            ],
            "terminal_policy": "retain Moon terminal and final-game progression byte-identical",
            "navigation_policy": "exclude all Mensis chase, warp and labyrinth-area controllers; source events12604877 and12604879 witness AI command -1 as direct combat release",
            "phase_policy": f"source12604856 begins the half-health transition and pinned t260311 then sets72600300; direct adapter maps that timing to project flag{ids.phase_marker} for destination phase music without mutating donor dialogue/progression state",
            "spell_policy": "source12604980 observes model event messages10/20 and only schedules dialogue flags; it issues no spell or AI command. Original c0000 NPC/Think remains responsible for move choice after source-witnessed AI command -1; runtime behavior is unobserved",
            "ai_flag_audit": {
                "source_binder_sha256": "08d8f72ba3701bbabeea4bda471fff40817f21bcce9599bd76ed479b050e69bc",
                "required_goals": [
                    {"id": 6380, "logic": False},
                    {"id": 6380, "logic": True},
                ],
                "goal_chunks": {
                    "006380_battle.lua": "a97cc3d77ad479fd80a322c177c1c5f3b2d0771cc65f13f8bb5f0074f715f6c3",
                    "006380_logic.lua": "e6e68d54547e3e776e2bb8aa841dc61aeaf1688c6b5ab6b63b2731b071e06422",
                },
                "lua50_numeric_constant": 72600300,
                "occurrences": {
                    "006380_battle.lua": 0,
                    "006380_logic.lua": 0,
                },
                "finding": "original Think6380 goal bytecode has no direct dependency on donor phase flag72600300; move selection remains opaque/runtime-unobserved",
            },
            "source_map_dialogue_not_transplanted": {
                "talk_id": 260311,
                "source_sha256": TALK_SOURCE_SHA256,
                "policy": "donor_dialogue_and_progression_excluded",
            },
            "placement_policy": "retain original Moon actor position in the destination combat arena; no source labyrinth geometry",
            "source_hash_pins": dict(DONOR_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
        },
    )
