"""Pinned experimental BSB combat in Orphan of Kos's destination arena.

This retains Orphan's entry cutscene/fog, two-actor terminal predicate and
post-fight shadow flow.  Only its combat controller is replaced by BSB's
single-actor health, phase, music and camera graph.  Runtime behavior is
unobserved.
"""

from __future__ import annotations
import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence
from tools.bb_inputs import read_blob, read_prefix
from .boss_canary import event_blocks
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
BSB_SOURCE = "event/m23_00_00_00.emevd.dcx.js"
ORPHAN_SOURCE = "event/m36_00_00_00.emevd.dcx.js"
BSB = 2300800
ORPHAN_CORE = 3600800
ORPHAN_PHASE = 3600801
ORPHAN_SUPPORT = 3600803
BSB_ARCHETYPE = Archetype("c2090", 209000, 209000, 0)
ORPHAN_ARCHETYPE = Archetype("c4540", 454000, 454000, 0)
MIN_ID = 12991100
MAX_ID = 12991199
DONOR = {
    0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
    12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
    12304804: "86edb06de9efdc94365fb640741ce4d62620363a3c37ebb99d37ef2b9d3f3521",
    12304807: "7e9c22292f41da758876cceffe70b61ad51cf0f86e7b5e250e3c8514f179d780",
    12304808: "8ccea02a7829f43788cf77ec24ea5b524643f9ab6d55681f492f1afa588e31f5",
}
ARENA = {
    0: "a6c55dfa6a26dbb4d086f2eb73a12d3956a1dec570699dfbc6c63d0f51fb54b3",
    13601800: "5423c79a2613f564aecbc24658b5b30152c08acb21ede1e817a15abeb5c66c38",
    13601801: "a1e52549f15c53a6e55e4aeafb2f21cf863e1a267d58b9121695241118f2de78",
    13601802: "e2396aaa1c6e9082e71baa1689195eb8c4afbb79870aec7ba85532fd8c053476",
    13601803: "43c5a2c33491090c42c2efa1913c15aadd1208c9ad1440502b7c36876a273593",
    13604800: "d8efed8f21a583997c86a38b91bde6ca110890b9c5ec3a524307fe2fa2544774",
    13604801: "4bcad3d039946f79a7fb0463c4b3355b0b8d1cab30c3f0c8dfda35922e992fe6",
    13604802: "8d7b309380f51d2933c573d286cee4ecdb4dc2797376c16dead9078df7f28fb9",
    13604803: "f6754136d8003799fd8c001053980bb67f25b033108b690852d0b0aedd128e72",
    13604804: "1360cbaab6065617a103ca2668dc2e601b10ea73bb97099a59055ad48f074d4e",
    13604805: "0c4495a2403778481467bef908cb72ff5c7cea94f50d25a1ee6e66ea8aa50cdc",
    13604820: "81c25057e062e5cf3d4728af2ba34359bc8b7c75ee28ded6ea7eb8519decd443",
    13604830: "fcec0fd932510a899f0e1a31433ee06438f56f0e0ec27b0ae5e24dc539de57ec",
    13604840: "027beee553830c6635d9452f708c0bcb95ca95fb53239bd6e12d5e764c32f75c",
    13604850: "de7acf9de30e70460a229e9f489b52eb00ab51289317a6b81d80382a67e6ddf1",
}
# Exact DarkScript 3.6.3 output for the installed originals.  Event 0 has two
# unrelated constructor arguments, 13601802 adds gravity to the preserved
# shadow actor, and 13604802 carries the source proximity/update-rate fix.
ARENA_ALTERNATES = {
    0: "d9c76c6c7fcd7efe7eb641d470519cd217d70561ec8a81962f5248a76e316cb7",
    13601802: "db7835c85dcca96716065d5b2106299bcb821db64c506fb931dc3dae0e0de757",
    13604802: "54cb28efcdc5dbf46afd69ebfa6155d8635a61770e8f2375c6be127a8fb44004",
}


@dataclass(frozen=True)
class BsbOrphanIds:
    phase_one: int
    phase_two: int
    helper_cleanup: int

    def values(self):
        return self.phase_one, self.phase_two, self.helper_cleanup


DEFAULT_IDS = BsbOrphanIds(12991100, 12991101, 12991102)


def _blocks(text, pins, label, alternates=()):
    out = event_blocks(text)
    for event, digest in pins.items():
        actual = (
            hashlib.sha256(out[event].encode()).hexdigest() if event in out else None
        )
        allowed = (digest, alternates.get(event)) if alternates else (digest,)
        if actual not in allowed:
            raise ValueError(f"unsupported original {label} event {event}")
    return out


def _once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f"BSB/Orphan expected one {label}")
    return text.replace(old, new, 1)


def _remap(text, values):
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])", lambda m: str(values.get(int(m[0]), int(m[0]))), text
    )


def _end(text):
    header = text.splitlines()[0]
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda m: "function("
        + ", ".join("unused_" + x.strip() for x in m[1].split(",") if x.strip())
        + ")",
        header,
    )
    return header + "\n    EndEvent();\n});"


def _replace(text, edits):
    lines = text.splitlines()
    for e in reversed(parse_events(text)):
        if e.event_id in edits:
            lines[e.first_line - 1 : e.last_line] = edits[e.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _all_literals():
    output = set()
    for body in read_prefix(BUNDLE, "event/").values():
        output.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
        )
    return output


def _validate(ids, destination):
    values = ids.values()
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    if (
        len(set(values)) != 3
        or any(not MIN_ID <= x <= MAX_ID for x in values)
        or set(values) & (local | _all_literals())
    ):
        raise ValueError("BSB/Orphan ID collides with original EMEVD literal")


def _init_calls(z, event, new):
    calls = [
        line
        for line in z.splitlines()
        if re.match(r"\s*\$InitializeEvent\([^,]+,\s*" + str(event) + r"(?:,|\))", line)
    ]
    if len(calls) != 1:
        raise ValueError(f"BSB Event(0) lacks one initializer witness for {event}")
    return re.sub(
        r"(\$InitializeEvent\([^,]+,\s*)" + str(event) + r"(?=,|\))",
        r"\g<1>" + str(new),
        calls[0],
        count=1,
    )


def patch_bsb_at_orphan(
    destination: str, donor_source: str, ids: BsbOrphanIds = DEFAULT_IDS
) -> str:
    """Keep Orphan arena/progression while installing BSB's single-actor combat."""
    arena = _blocks(destination, ARENA, "Orphan arena", ARENA_ALTERNATES)
    donor = _blocks(donor_source, DONOR, "BSB donor")
    _validate(ids, destination)
    remap = {
        BSB: ORPHAN_CORE,
        12301800: 13601800,
        12304800: 13604808,
        12304801: 13604809,
        12304802: 13604802,
        12304803: 13604803,
        12304804: 13604804,
        12304807: ids.phase_one,
        12304808: ids.phase_two,
        2303802: 3603802,
        2303803: 3603803,
        2302801: 3602802,
        2300010: 9360010,
    }
    health = _remap(donor[12304802], remap)
    health = _once(
        health,
        "    SetCharacterHPBarDisplay(3600800, Disabled);\n",
        "    SetCharacterHPBarDisplay(3600800, Disabled);\n    SetCharacterAIState(3600801, Disabled);\n    SetCharacterHPBarDisplay(3600801, Disabled);\n    SetCharacterAIState(3600803, Disabled);\n    SetCharacterHPBarDisplay(3600803, Disabled);\n",
        "Orphan helper initial disable",
    )
    # The original phase controller hid these actors before the fight.  Keep
    # them alive (the terminal accepts either body's death), but absent.
    health = _once(
        health,
        "    SetCharacterAIState(3600801, Disabled);",
        "    ChangeCharacterEnableState(3600801, Disabled);\n    ChangeCharacterEnableState(3600803, Disabled);\n    SetCharacterAIState(3600801, Disabled);",
        "unused actor visibility",
    )
    # Destination multiplayer controllers consume this flag on repeat entry.
    health = _once(
        health,
        "    SetEventFlag(13604808, ON);",
        "    SetEventFlag(13604810, ON);\n    SetEventFlag(13604808, ON);",
        "destination battle state",
    )
    music = _remap(donor[12304803], remap)
    camera = _remap(donor[12304804], remap)
    camera = _once(
        camera,
        "    SetNetworkSyncState(Disabled);",
        "    SetNetworkSyncState(Disabled);\n    EndIf(EventFlag(13601800));",
        "completed arena camera guard",
    )
    camera = _once(
        camera,
        "SetLockcamSlotNumber(23, 0, 1)",
        "SetLockcamSlotNumber(36, 0, 1)",
        "BSB camera map binding",
    )
    phase_one = _remap(donor[12304807], remap)
    phase_two = _remap(donor[12304808], remap)
    init = "\n".join(
        (
            "    " + _init_calls(donor[0], 12304807, ids.phase_one).strip(),
            "    " + _init_calls(donor[0], 12304808, ids.phase_two).strip(),
            f"    $InitializeEvent(0, {ids.helper_cleanup});",
        )
    )
    # The original constructor did not start 13604804; the imported BSB camera
    # is now active combat behavior and needs its own initializer.
    if "$InitializeEvent(0, 13604804);" in arena[0]:
        raise ValueError("unexpected Orphan camera initializer")
    init += "\n    $InitializeEvent(0, 13604804);"
    edits = {
        0: _once(
            arena[0],
            "    $InitializeEvent(0, 13601804);",
            "    $InitializeEvent(0, 13601804);\n" + init,
            "BSB initializer anchor",
        ),
        13604802: health,
        13604803: music,
        13604804: camera,
        13604820: _end(arena[13604820]),
        13604830: _end(arena[13604830]),
        13604840: _end(arena[13604840]),
        13604850: _end(arena[13604850]),
        ids.phase_one: phase_one,
        ids.phase_two: phase_two,
        ids.helper_cleanup: f"""$Event({ids.helper_cleanup}, Default, function() {{
    WaitFor(EventFlag(13601800));
    SetCharacterAIState(3600801, Disabled);
    SetCharacterAIState(3600803, Disabled);
    ChangeCharacterEnableState(3600801, Disabled);
    ForceCharacterDeath(3600801, false);
    ChangeCharacterEnableState(3600803, Disabled);
    ForceCharacterDeath(3600803, false);
}});""",
    }
    result = (
        _replace(destination, {e: b for e, b in edits.items() if e in arena}).rstrip()
        + "\n\n"
        + "\n\n".join(edits[e] for e in ids.values())
        + "\n"
    )
    out = event_blocks(result)
    if set(out) != set(arena) | set(ids.values()):
        raise ValueError("BSB/Orphan changed event identities")
    for e, b in arena.items():
        if e not in edits and out[e] != b:
            raise ValueError(f"BSB/Orphan changed unrelated arena event {e}")
    for e in (13601800, 13601801, 13601802, 13601803):
        if out[e] != arena[e]:
            raise ValueError(
                "BSB/Orphan changed Orphan completion or post-fight progression"
            )
    return result


def native_plan_bsb_at_orphan(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: BsbOrphanIds = DEFAULT_IDS,
) -> dict:
    sources = [s for s in slots if s.entity_id == BSB and s.archetype == BSB_ARCHETYPE]
    targets = [
        s
        for s in slots
        if s.entity_id == ORPHAN_CORE and s.archetype == ORPHAN_ARCHETYPE
    ]
    if (
        len(sources) != 2
        or {s.map_name for s in sources} != {"m23_00_00_00", "m23_00_00_01"}
        or len(targets) != 1
        or targets[0].map_name != "m36_00_00_00"
    ):
        raise ValueError(
            "BSB/Orphan requires pinned BSB sources and one Orphan destination core"
        )
    src = next(s for s in sources if s.map_name == "m23_00_00_00")
    dst = targets[0]
    swap = Swap(
        dst.logical_key,
        [dst.key],
        {dst.key: dst.archetype},
        dst.archetype,
        BSB_ARCHETYPE,
        warnings=["experimental BSB-at-Orphan contract; runtime behavior unobserved"],
        destinations={
            dst.key: {
                "map_name": dst.map_name,
                "entity_id": dst.entity_id,
                "x": dst.x,
                "y": dst.y,
                "z": dst.z,
            }
        },
    )
    changes, skips = plan_scaling(
        [swap], [dst], dict(npcs), dict(effects), boss_tiers=True
    )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "boss_contract": {
            "format": "bb-bsb-orphan-contract-v1",
            "arena": "orphan-of-kos",
            "donor": "blood-starved-beast",
            "attachment_event_ids": asdict(ids),
            "runtime_status": "unobserved",
            "preserved_destination_events": [13601800, 13601801, 13601802, 13601803],
            "helper_policy": "phase/support AI disabled until original terminal, then cleaned",
        },
        "primary_init_source_bindings": [
            {
                "source_map": src.map_name,
                "source_part": src.part_name,
                "source_entity_id": src.entity_id,
                "source_archetype": asdict(src.archetype),
                "source_talk_id": src.talk_id,
                "destination_map": dst.map_name,
                "destination_part": dst.part_name,
                "destination_entity_id": dst.entity_id,
                "destination_original_talk_id": dst.talk_id,
                "required_native_fields": [
                    "talk_id",
                    "unk_t18",
                    "init_anim_id",
                    "damage_anim_id",
                    "provenance",
                ],
            }
        ],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [x.json() for x in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
