"""Pinned Gehrman combat in Micolash's Nightmare of Mensis arena.

The adapter keeps Micolash's entry, fog, terminal rewards and post-boss
progression.  Micolash's chase graph is made inert and Gehrman's health,
camera and two combat phases run at the original Micolash placement beside
the witnessed fight-start region.  Runtime behavior remains unobserved.
"""

from __future__ import annotations

import hashlib
import re
from functools import cache
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_canary import event_blocks
from .bosses import parse_events
from .final_boss_contracts import GEHRMAN_PACKAGE, PINS as GEHRMAN_HASHES
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
DONOR_SOURCE = "event/m21_00_00_00.emevd.dcx.js"
ARENA_SOURCE = "event/m26_00_00_00.emevd.dcx.js"

GEHRMAN, GEHRMAN_OWNER, MICOLASH = 2100800, 2100801, 2600850
COMPLETION = 12601850
OWNER_ARCHETYPE = Archetype("c9010", 901010, 1, 0)
MICOLASH_ARCHETYPE = Archetype("c0000", 6380, 6380, 0)
GEHRMAN_PIN = "1c42091a9cacab2c22f7bc0056deafca140095a619fd1c68716158257427abc0"
OWNER_PIN = "87508ce80a4eccf3c5637e7db80b080791f6ce1e8e7ffa2ab41c3bcb7e958352"
MICOLASH_PIN = "ab37480d123ba5807ace745e2238c7891782479dec1fc3222267f62040460d35"

ARENA_HASHES = {
    0: "bead3d1536484484169804138a1649d272cba5793b92b73179c6046c48aad1a0",
    12601850: "58e6aaf6d2a11e3d11f5f37a16be64242d8e146355a09f948aa05f3c33055e7b",
    12601851: "6297191a3366ba5d1730e01eac26e6f07b555047eebc9cd35618c9820c72392c",
    12601852: "1f584b3150d603147023e28cf6ad672b63c8ed4397b7d976e9e2017bfa397aef",
    12601854: "f4e6994f3152aa603daacd52ca3047cc99a17ee608fe0c11ff578bd93cad62f3",
    12601855: "b28156b0f577a1f3650b48d6949326c28399721c94ad015e13b9b7536b7c9c1c",
    12604852: "112297fc525671f09775db60260f66099231acb795864747771e0482071abc97",
    12604853: "d1f257fd7d39dfee586737b765bc62d760471d2f4cc79b2448ccfe920e513548",
    12604854: "99021f5ff8f2aa2738f277b7cc42f8573673ce6cfbb786237772af751d9e5a54",
    12604855: "0eaac9d83b145c5ba7e4b690122586e1e5e0f5d1351abbaeb348eedb6225497d",
    12604860: "da7c46680f3e14f09d396a40fac4b1c5120d6d3d37d291d457530824fdaf5ece",
    12604861: "f0d708063d01b0e4c79e720d788961a7ba3b725f144286bb7b71764d9d2e6ab5",
    12604856: "3e34966b4ec1b3c4690c9abf8da6764853dad3f991b699e232805cb677a4831e",
    12604870: "5b7f26252e34e96a22ad98e83f9dac5fb04c5d6c47d390090fafd41c5b1f1409",
    12604877: "8c8cd83c7618d50e648791817d1aff3b3f4b25ff79c9bf669a6b9fffe1bc7f77",
    12604878: "a78c56cedab59e3bda6e73c2271d93568af4e68498dc281357e1ca463ed374ed",
    12604879: "8022c6e0fdea139635bd31ae38b9885ec63981faaf51abc76d67ff80c19c3496",
    12604880: "f30a171640ae2448ba057bee6300c1e6bac20fd4794bb5d3d84ed791faf41c18",
    12604888: "ab96e756c1afbcfa3010498c427431d2778d677bfc6e0f1800821bb76e9a3f8c",
    12604889: "b03c0dc452b70195202f3ee61a2831b020d804892c3422512bcc14ff7e229f0e",
    12604930: "0070ba7c5609d5b16e798b26a1122e8b1832a4c3c48e73edaa0a66e3aec8e1a9",
    12604931: "5429930e894dd7f025a450b9b3305fe7e72688a0c351dd679e704b7f1b8d75d1",
    12604960: "7063a9fc41c42d6d7f8d2c0f7a9562022c12649518194d6526c22c29447f1c37",
    12604970: "e7a3928bf558107f05140bc97db652743724be4baa2826762d68767bad40ebff",
    12604980: "95e1c09d27344c80d361f433fcca2fc380abcbdfff44f37bce1adaf5bb4fac60",
    12604985: "0d5ca72b20d86acf2bbd28962ecc7782cef8f78778b839383fab532f6dd8de9e",
    12604986: "8d6edcc942fa6507194181715ea39da1e95e2289bd73502cd216e5459ce63632",
}

CHASE_EVENTS = (
    12604856,
    12604870,
    12604877,
    12604878,
    12604879,
    12604880,
    12604888,
    12604889,
    12604930,
    12604931,
    12604960,
    12604970,
    12604980,
    12604985,
    12604986,
)


@dataclass(frozen=True)
class GehrmanMicolashIds:
    phase_one: int = 12992900
    phase_cleanup: int = 12992901
    terminal_bridge: int = 12992902
    owner_cleanup: int = 12992903
    owner_entity: int = 980700
    owner_part: str = "ap_gehrman_event_target"
    evidence: str = "Gehrman/Micolash allocation v1; full original EMEVD and MSBB scan"

    def events(self) -> tuple[int, ...]:
        return (
            self.phase_one,
            self.phase_cleanup,
            self.terminal_bridge,
            self.owner_cleanup,
        )


DEFAULT_IDS = GehrmanMicolashIds()


def _verify(blocks: Mapping[int, str], pins: Mapping[int, str], role: str) -> None:
    for event, digest in pins.items():
        actual = hashlib.sha256(blocks.get(event, "").encode()).hexdigest()
        if actual != digest:
            raise ValueError(f"unsupported original {role} event {event}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Gehrman/Micolash expected one {label}")
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


def _inert_event(block: str) -> str:
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
    # Region 0 is the original script's own permanent-wait idiom.  Keeping
    # these event slots running avoids setting their ThisEvent flags; notably,
    # destination post-boss event 12601854 branches on 12604879.
    return header + "\n    WaitFor(InArea(10000, 0));\n    EndEvent();\n});"


@cache
def _original_literals() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
        )
    rows = read_prefix(BUNDLE, "mined/")
    for name in ("mined/msb_enemies.tsv", "mined/msb_regions.tsv"):
        for row in rows.get(name, b"").decode("utf-8-sig").splitlines()[1:]:
            for value in row.split("\t"):
                if value.lstrip("-").isdigit():
                    values.add(int(value))
    return values


def _validate(ids: GehrmanMicolashIds, destination: str) -> None:
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    if (
        len(set(ids.events())) != len(ids.events())
        or any(not 12992900 <= event <= 12992999 for event in ids.events())
        or set(ids.events()).intersection(local | _original_literals())
        or ids.owner_entity != 980700
        or ids.owner_entity in local | _original_literals()
        or not ids.evidence.strip()
    ):
        raise ValueError("Gehrman/Micolash allocation collides with original inputs")


def _mapping(ids: GehrmanMicolashIds) -> dict[int, int]:
    return {
        GEHRMAN: MICOLASH,
        GEHRMAN_OWNER: ids.owner_entity,
        12101800: COMPLETION,
        12104800: 12604850,
        12104801: 12604851,
        12104802: 12604852,
        12104804: 12604854,
        12104807: ids.phase_one,
        12104808: ids.phase_cleanup,
        2100010: 2601010,
    }


def patch_gehrman_at_micolash(
    destination: str,
    donor_source: str,
    ids: GehrmanMicolashIds = DEFAULT_IDS,
) -> str:
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, ARENA_HASHES, "Micolash arena")
    _verify(donor, GEHRMAN_HASHES, "Gehrman donor")
    _validate(ids, destination)
    mapping = _mapping(ids)
    health = _remap(donor[12104802], mapping)
    health = _replace_once(
        health, "CreatePlaylog(64);", "CreatePlaylog(88);", "destination playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2601010, 80, Enabled);",
        "StartTimeMeasurement(2601010, 232, Enabled);",
        "destination time measurement",
    )
    music = _replace_once(
        arena[12604853],
        "        WaitFor(EventFlag(72600300));",
        "        WaitFor(CharacterHasEventMessage(2600850, 100));",
        "Gehrman phase music message",
    )
    lockcam = _remap(donor[12104804], mapping)
    lockcam = lockcam.replace(
        "SetLockcamSlotNumber(21, 0,", "SetLockcamSlotNumber(26, 0,"
    )
    phase_one = _remap(donor[12104807], mapping)
    phase_cleanup = _remap(donor[12104808], mapping)
    terminal_bridge = f"""$Event({ids.terminal_bridge}, Default, function() {{
    EndIf(EventFlag({COMPLETION}));
    SetEventFlag(72600301, OFF);
    WaitFor(CharacterDead({MICOLASH}));
    SetEventFlag(72600301, ON);
}});"""
    owner_cleanup = f"""$Event({ids.owner_cleanup}, Default, function() {{
    WaitFor(EventFlag({COMPLETION}));
    ChangeCharacterEnableState({ids.owner_entity}, Disabled);
    ForceCharacterDeath({ids.owner_entity}, false);
}});"""
    init = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 12604855);",
        "    $InitializeEvent(0, 12604855);\n"
        f"    $InitializeEvent(0, {ids.phase_one});\n"
        f"    $InitializeEvent(0, {ids.phase_cleanup});\n"
        f"    $InitializeEvent(0, {ids.terminal_bridge});\n"
        f"    $InitializeEvent(0, {ids.owner_cleanup});",
        "Micolash controller anchor",
    )
    additions = {
        ids.phase_one: phase_one,
        ids.phase_cleanup: phase_cleanup,
        ids.terminal_bridge: terminal_bridge,
        ids.owner_cleanup: owner_cleanup,
    }
    edits = {
        0: init,
        12604852: health,
        12604853: music,
        12604854: lockcam,
        **{event: _inert_event(arena[event]) for event in CHASE_EVENTS},
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions[event] for event in ids.events())
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.events()):
        raise ValueError("Gehrman/Micolash changed event identities")
    for event, original in arena.items():
        if event not in edits and output[event] != original:
            raise ValueError(f"Gehrman/Micolash changed unrelated event {event}")
    for event in (12601850, 12601852, 12601854, 12601855, 12604855, 12604860, 12604861):
        if output[event] != arena[event]:
            raise ValueError("Gehrman/Micolash changed destination progression")
    copied = "\n".join(output[event] for event in (12604852, 12604854, *ids.events()))
    if re.search(r"(?<!\d)(?:121|210)\d+(?!\d)", copied):
        raise ValueError("Gehrman/Micolash retains donor-map literals")
    return result


def _require(
    slots: Sequence[Slot], entity: int, archetype: Archetype, talk: int
) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.entity_id == entity and slot.archetype == archetype
    ]
    if len(found) != 1 or found[0].dummy or found[0].talk_id != talk:
        raise ValueError(f"Gehrman/Micolash requires pinned actor {entity}")
    return found[0]


def native_plan_gehrman_at_micolash(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: GehrmanMicolashIds = DEFAULT_IDS,
) -> dict:
    arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
    donor = read_blob(BUNDLE, DONOR_SOURCE).decode("utf-8-sig")
    _verify(event_blocks(arena), ARENA_HASHES, "Micolash arena")
    _verify(event_blocks(donor), GEHRMAN_HASHES, "Gehrman donor")
    _validate(ids, arena)
    source = _require(slots, GEHRMAN, GEHRMAN_PACKAGE.archetype, 210306)
    owner = _require(slots, GEHRMAN_OWNER, OWNER_ARCHETYPE, 0)
    target = _require(slots, MICOLASH, MICOLASH_ARCHETYPE, 260311)
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        source.archetype,
        warnings=["runtime direct-fight fit and talk suppression require validation"],
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
        raise ValueError("Gehrman/Micolash primary normalization is ambiguous")
    owner_addition = {
        "source_map": owner.map_name,
        "source_part": owner.part_name,
        "source_anchor_part": owner.part_name,
        "source_entity_id": owner.entity_id,
        "source_archetype": asdict(owner.archetype),
        "source_part_kind": "enemy",
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": OWNER_PIN,
            "anchor_sha256": OWNER_PIN,
        },
        "source_initialization": {
            "talk_id": 0,
            "unk_t18": -1,
            "init_anim_id": -1,
            "damage_anim_id": -1,
        },
        "destination_map": target.map_name,
        "destination_anchor_part": target.part_name,
        "destination_part": ids.owner_part,
        "destination_entity_id": ids.owner_entity,
        "allocation_evidence": ids.evidence,
    }
    primary = {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": GEHRMAN_PIN,
        },
        "source_initialization": {
            "talk_id": 210306,
            "unk_t18": -1,
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
        "boss_actor_additions": [owner_addition],
        "primary_init_source_bindings": [primary],
        "boss_contract": {
            "format": "bb-gehrman-micolash-contract-v1",
            "arena": "micolash",
            "donor": "gehrman",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "preserved_destination_events": [
                12601850,
                12601852,
                12601854,
                12601855,
                12604855,
                12604860,
                12604861,
            ],
            "terminal_policy": "retain byte-identical terminal and set its talk-owned 72600301 gate only after donor death",
            "talk_evidence": "t260311_x3 self-death -> x5 dialogue2100300 ends -> flag72600301; replaced by pinned death bridge because destination TalkID is suppressed",
            "placement_evidence": "original actor (176.82,1037.98,-37.82) is adjacent to original fight-start region2602851 (163.21,1032.58,-37); no placement override",
            "disabled_destination_chase_events": list(CHASE_EVENTS),
            "source_hash_pins": dict(GEHRMAN_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
        },
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
