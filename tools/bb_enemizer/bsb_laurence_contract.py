"""Pinned BSB combat overlay for Laurence's one-actor destination arena."""

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

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
BSB = 2300800
LAURENCE = 3400850
COMPLETE = 13401850
BSB_ARCHETYPE = Archetype("c2090", 209000, 209000, 0)
LAURENCE_ARCHETYPE = Archetype("c4500", 450000, 450000, 0)


@dataclass(frozen=True)
class BsbLaurenceIds:
    phase_one: int
    phase_two: int
    camera: int

    def values(self):
        return self.phase_one, self.phase_two, self.camera


DEFAULT_IDS = BsbLaurenceIds(12990800, 12990801, 12990802)
ARENA = {
    0: "3772e9c2957d38bcdbc984631dab0033deaef57c1d092a8c77005cdd4d7c1d55",
    13401800: "15c6ba33b2df44b9fdc67ea470d1f32281bac11a588ba6c876de7ac85df5d8dd",
    13401850: "dc390d680718c54d8a214a4d1ed0def18b7c110df7dd19a6862b436a2dcd6b44",
    13401851: "c9bb7c19e16ebdc391bc1552e9328dd41d25bdc968701b2e1182506f940f255d",
    13404824: "19b82e96f8a880da845bf09c977b9d116da91584069edb0a3f630271ae119c70",
    13404825: "b64ae6b68f0a7dc4d922328fa23659be54219fd7010465f03493a141858e16f2",
    13404852: "a55956b498c3908a0febf99daf2013e6d59eea5885a5ac837a3735f09d356470",
    13404853: "6d373eb2995d299bd4008cbc5c7fa72a0d77823ed62129af6916a4ad0235ce7a",
    13404854: "67283d0f1600a008235ffc109219ab98ee5028814738d45724c397bf4519430f",
    13404861: "7888497bc33ab25bdc668813a50cbc6a3ad44c2d6321b05fecdf4c500a297f7e",
    13404870: "237a55077776ca3b72ea95aee40b8da9655bf8f93d15315400b3d1f1eb8471be",
    13404875: "e5fb7120dd1c7759f763c39f7c04a1b01ba966dcb2ce48f9bc4f5e1331a57822",
}
DONOR = {
    0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
    12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
    12304804: "86edb06de9efdc94365fb640741ce4d62620363a3c37ebb99d37ef2b9d3f3521",
    12304807: "7e9c22292f41da758876cceffe70b61ad51cf0f86e7b5e250e3c8514f179d780",
    12304808: "8ccea02a7829f43788cf77ec24ea5b524643f9ab6d55681f492f1afa588e31f5",
}


def _verify(b, p, r):
    for e, h in p.items():
        if e not in b or hashlib.sha256(b[e].encode()).hexdigest() != h:
            raise ValueError(f"unsupported original {r} event {e}")


def _once(s, o, n, l):
    if s.count(o) != 1:
        raise ValueError(f"BSB/Laurence expected one {l}")
    return s.replace(o, n, 1)


def _end(b):
    h = b.splitlines()[0]
    h = re.sub(
        r"function\(([^)]*)\)",
        lambda m: "function("
        + ", ".join(
            x.strip() if x.strip().startswith("unused_") else "unused_" + x.strip()
            for x in m[1].split(",")
            if x.strip()
        )
        + ")",
        h,
    )
    return h + "\n    EndEvent();\n});"


def _replace(s, edits):
    lines = s.splitlines()
    for e in reversed(parse_events(s)):
        if e.event_id in edits:
            lines[e.first_line - 1 : e.last_line] = edits[e.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _all():
    r = set()
    for b in read_prefix(BUNDLE, "event/").values():
        r.update(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", b.decode("utf-8-sig"))))
    return r


def _ids(i, d):
    vals = i.values()
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", d)))
    if (
        len(set(vals)) != len(vals)
        or any(x <= 0 for x in vals)
        or set(vals) & (local | _all())
    ):
        raise ValueError("BSB/Laurence ID collides with original EMEVD literal")


def _calls(z, e, n):
    r = [
        x
        for x in z.splitlines()
        if re.match(r"\s*\$InitializeEvent\([^,]+,\s*" + str(e) + r"(?:,|\))", x)
    ]
    if len(r) != n:
        raise ValueError(f"BSB Event(0) lacks {n} initializer witnesses for {e}")
    return r


def _init(x, o, n):
    return re.sub(
        r"(\$InitializeEvent\([^,]+,\s*)" + str(o) + r"(?=,|\))",
        r"\g<1>" + str(n),
        x,
        count=1,
    )


def _map(b, event, target, flags=()):
    m = {BSB: LAURENCE, 12301800: COMPLETE, event: target}
    m.update(flags)
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])", lambda x: str(m.get(int(x[0]), int(x[0]))), b
    )


def _constructor(arena, donor, ids):
    add = [
        _init(_calls(donor, 12304807, 1)[0], 12304807, ids.phase_one),
        _init(_calls(donor, 12304808, 1)[0], 12304808, ids.phase_two),
        _init(_calls(donor, 12304804, 1)[0], 12304804, ids.camera),
    ]
    anchor = "    $InitializeEvent(0, 13404875);"
    return _once(
        arena,
        anchor,
        anchor + "\n" + "\n".join(add),
        "Laurence combat initializer anchor",
    )


def patch_bsb_at_laurence(destination, donor_source, ids=DEFAULT_IDS):
    a, d = event_blocks(destination), event_blocks(donor_source)
    _verify(a, ARENA, "Laurence arena")
    _verify(d, DONOR, "BSB donor")
    _ids(ids, destination)
    entry = _once(
        a[13401851],
        "ForceAnimationPlayback(3400850, 3029, false, false, false);",
        "ForceAnimationPlayback(3400850, 7001, false, false, false);",
        "BSB entry animation",
    )
    activation = _once(
        a[13404861],
        "    ForceAnimationPlayback(3400850, 7002, true, false, false);\n",
        "",
        "Laurence-only pre-entry animation",
    )
    health = _once(
        a[13404852],
        "DisplayBossHealthBar(Enabled, 3400850, 0, 450000)",
        "DisplayBossHealthBar(Enabled, 3400850, 0, 209000)",
        "BSB health label",
    )
    music = _once(
        a[13404853],
        "chrFlagArea &= CharacterHasEventMessage(3400850, 400);",
        f"chrFlagArea &= EventFlag({ids.phase_two});",
        "BSB phase-two music trigger",
    )
    cam = _map(
        d[12304804], 12304804, ids.camera, ((12304800, 13404858), (12304801, 13404859))
    )
    cam = _once(
        cam,
        "SetLockcamSlotNumber(23, 0,",
        "SetLockcamSlotNumber(34, 0,",
        "BSB camera map binding",
    )
    # 13404820--25 drive Ludwig's two-body encounter in this shared m34 script.
    cam = _once(
        cam,
        "    SetNetworkSyncState(Disabled);",
        "    SetNetworkSyncState(Disabled);\n    EndIf(EventFlag(13401850));",
        "completed arena camera guard",
    )
    # Leave those bodies untouched: only Laurence's own phase/part routines use
    # actor 3400850 and may be retired for this single-actor overlay.
    edits = {
        0: _constructor(a[0], d[0], ids),
        13401851: entry,
        13404861: activation,
        13404852: health,
        13404853: music,
        13404854: _end(a[13404854]),
        13404870: _end(a[13404870]),
        13404875: _end(a[13404875]),
    }
    result = (
        _replace(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(
            (
                _map(d[12304807], 12304807, ids.phase_one),
                _map(
                    d[12304808], 12304808, ids.phase_two, ((12304807, ids.phase_one),)
                ),
                cam,
            )
        )
        + "\n"
    )
    out = event_blocks(result)
    if set(out) != set(a) | set(ids.values()):
        raise ValueError("BSB/Laurence changed event identities")
    for e, b in a.items():
        if e not in edits and out[e] != b:
            raise ValueError(f"BSB/Laurence changed unrelated event {e}")
    if out[13401800] != a[13401800] or out[13401850] != a[13401850]:
        raise ValueError("BSB/Laurence changed shared completion progression")
    return result


def native_plan_bsb_at_laurence(slots, npcs, effects, seed, ids=DEFAULT_IDS):
    b = [s for s in slots if s.entity_id == BSB and s.archetype == BSB_ARCHETYPE]
    a = [
        s
        for s in slots
        if s.entity_id == LAURENCE and s.archetype == LAURENCE_ARCHETYPE
    ]
    if (
        len(b) != 2
        or {s.map_name for s in b} != {"m23_00_00_00", "m23_00_00_01"}
        or any(s.talk_id for s in b)
        or len(a) != 1
        or a[0].map_name != "m34_00_00_00"
    ):
        raise ValueError(
            "BSB/Laurence requires pinned BSB sources and one Laurence destination"
        )
    src = next(s for s in b if s.map_name == "m23_00_00_00")
    dst = a[0]
    sw = Swap(
        dst.logical_key,
        [dst.key],
        {dst.key: dst.archetype},
        dst.archetype,
        BSB_ARCHETYPE,
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
        [sw], [dst], dict(npcs), dict(effects), boss_tiers=True
    )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [sw.json()],
        "boss_contract": {
            "format": "bb-bsb-laurence-contract-v1",
            "arena": "laurence",
            "donor": "blood-starved-beast",
            "attachment_event_ids": asdict(ids),
            "preserved_destination_events": [13401800, 13401850],
            "health_bar": {
                "event": 13404852,
                "label": 209000,
                "evidence": "literal DisplayBossHealthBar operand in BSB event 12304802",
            },
            "runtime_status": "unobserved arena fit",
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
