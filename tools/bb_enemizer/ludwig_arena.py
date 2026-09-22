"""Pinned Cleric Beast combat adapter for Ludwig's aggregate two-phase arena."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_canary import event_blocks
from .boss_contracts import CLERIC_PACKAGE
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m34_00_00_00.emevd.dcx.js"
LUDWIG_PRIMARY, LUDWIG_PHASE_TWO = 3400800, 3400801
LUDWIG_ARCHETYPE = Archetype("c4510", 451000, 451000, 0)
LUDWIG_COMPLETION, LUDWIG_START = 13401800, 13404808


@dataclass(frozen=True)
class LudwigClericIds:
    phase: int
    cloth_phase: int
    limbs: int
    cloth: int
    phase_two_cleanup: int

    def values(self) -> tuple[int, ...]:
        return (
            self.phase,
            self.cloth_phase,
            self.limbs,
            self.cloth,
            self.phase_two_cleanup,
        )


DEFAULT_IDS = LudwigClericIds(12990700, 12990701, 12990702, 12990703, 12990704)

LUDWIG_ARENA_HASHES = {
    0: "3772e9c2957d38bcdbc984631dab0033deaef57c1d092a8c77005cdd4d7c1d55",
    13401800: "15c6ba33b2df44b9fdc67ea470d1f32281bac11a588ba6c876de7ac85df5d8dd",
    13401801: "512227ef549cf14ead83ae803efb7f73294b7f406abea9c940b8b49a6d5f26bd",
    13401802: "c8f0800e9c10ec30f2d5ed05cd1de7dbdf8d7e93ad2ce180ce22894294e7851b",
    13401803: "318fef613a2babaad1ec9736e5b762c9792a4c5a38ddf62d5297131e9cda25cd",
    13401804: "a1e94cd16c9b9e0a9818732e80da388a1a37b77a0d55b04f1631ba9eea0c21ff",
    13401850: "dc390d680718c54d8a214a4d1ed0def18b7c110df7dd19a6862b436a2dcd6b44",
    13404802: (
        "09b991a95b087e141b27c3e69f2d55e330bf6a8764df7eb475ebdfd9df9e5ac7",
        "02a77d3081f5fa336ec6db647099ef975dd7bca6f38da26b9d6176564ff814ab",
    ),
    13404803: "ee69949f3bf2119d6cb051e41abfed11c5de83b306f9a9e36a6b42df182745ba",
    13404804: "8bb1209c5f08d944570b67e634223c7375b3596fe56f2c44a5712b2d04359d78",
    13404820: "2a1075a99453bacb20f94e697137fe830eb2507ffcf74699ad7707ad62671c14",
    13404821: "a650abcf1dca7030d8d39eb944ef5e3c1ba0a9665dfb4fc8f9fbf3c82280e8bf",
    13404822: "ae620a8fe09a2614d36cc0714743fac5f2e9f7bd7fb888c78fdb738910250968",
    13404823: "3fd2cc74e5e8cf9ed1da11cea82f3244c1228bc4224b1a280431a4a64b519292",
    13404824: "19b82e96f8a880da845bf09c977b9d116da91584069edb0a3f630271ae119c70",
    13404825: "b64ae6b68f0a7dc4d922328fa23659be54219fd7010465f03493a141858e16f2",
    13404830: "e29423935a2cea0e2078da6f93030c835ac884337cfd9a832c055c13b778414f",
    13404835: "e9cafe3d4edfa21eb0c325a480ac17457d6b98d7d485cf2b542998320b07ba32",
    13404840: "3ab3d74eb2c16456051f503cb1e082f4ed769bbbf94e7570ddd4f99393bbe56b",
    13404841: "404a71c4d413e4aef35b1b9eaf683feb881acf4250724e4e5a265123d9a8a14d",
}
CLERIC_SOURCE_HASHES = {
    0: "329450dd4b8ae967cdaf56f5ab65556bb0a453e8f8374d79328848dff72cf89c",
    12414702: "026c305969b19114cc2f678e6d3859542442b35764b658ccfe65c3cb7fe7d422",
    12414703: "115ae8dc85c184a4dfe729eaef337b01ea0bcffc7a34ec0dde3f343dcbeb5c14",
    12414704: "ce143b924eb991b092351eb7641c7ea8349c28296209618f629b3b7c8ac02caa",
    12414707: "196e29870aae5dab2604594ce9ff0047b2ad71294fec48b6aa56c9f87465f73e",
    12414708: "2565484fb6afa230b46708bce4f42e8088d0f062fbafdb50453e078fc2fbf14d",
    12414710: "da624a8c97354a1208ce15fb1619bcb7f21aa74e89e39d22bfe4edac45c2373d",
    12414720: "1196a612c8f3b4d47e502e52fcbd848c9efe3be859b2b25e934e240c210099ea",
}


def _verify(
    blocks: Mapping[int, str], pins: Mapping[int, str | tuple[str, ...]], role: str
) -> None:
    for event, digest in pins.items():
        allowed = (digest,) if isinstance(digest, str) else digest
        if (
            event not in blocks
            or hashlib.sha256(blocks[event].encode()).hexdigest() not in allowed
        ):
            raise ValueError(f"unsupported original {role} event {event}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Ludwig arena expected one {label}")
    return text.replace(old, new, 1)


def _end(block: str) -> str:
    head = block.splitlines()[0]
    head = re.sub(
        r"function\(([^)]*)\)",
        lambda m: "function("
        + ", ".join(
            x.strip() if x.strip().startswith("unused_") else "unused_" + x.strip()
            for x in m[1].split(",")
            if x.strip()
        )
        + ")",
        head,
    )
    return head + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _remap(block: str, source_event: int, destination_event: int) -> str:
    mapping = {
        CLERIC_PACKAGE.actor: LUDWIG_PRIMARY,
        CLERIC_PACKAGE.completion_event: LUDWIG_COMPLETION,
        source_event: destination_event,
    }
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda m: str(mapping.get(int(m[0]), int(m[0]))),
        block,
    )


def _camera(block: str) -> str:
    result = _remap(block, 12414704, 13404804)
    old, new = "SetLockcamSlotNumber(24, 1,", "SetLockcamSlotNumber(34, 0,"
    if result.count(old) != 2:
        raise ValueError("Ludwig arena expected two Cleric camera map bindings")
    return result.replace(old, new)


def _all_numbers() -> set[int]:
    nums = set()
    for body in read_prefix(BUNDLE, "event/").values():
        nums.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
        )
    return nums


def _require_ids(ids: LudwigClericIds, destination: str) -> None:
    vals = ids.values()
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    if (
        len(set(vals)) != len(vals)
        or any(v <= 0 for v in vals)
        or set(vals) & local
        or set(vals) & _all_numbers()
    ):
        raise ValueError("Ludwig/Cleric ID collides with an original EMEVD literal")


def _calls(zero: str, event: int, count: int) -> list[str]:
    calls = [
        line
        for line in zero.splitlines()
        if re.match(r"\s*\$InitializeEvent\([^,]+,\s*" + str(event) + r"(?:,|\))", line)
    ]
    if len(calls) != count:
        raise ValueError(
            f"Cleric Event(0) lacks {count} initializer witnesses for {event}"
        )
    return calls


def _reinit(line: str, old: int, new: int) -> str:
    return re.sub(
        r"(\$InitializeEvent\([^,]+,\s*)" + str(old) + r"(?=,|\))",
        r"\g<1>" + str(new),
        line,
        count=1,
    )


def _constructor(arena_zero: str, cleric_zero: str, ids: LudwigClericIds) -> str:
    added = []
    for source, target, count in (
        (12414707, ids.phase, 1),
        (12414708, ids.cloth_phase, 1),
        (12414710, ids.limbs, 5),
        (12414720, ids.cloth, 5),
    ):
        added.extend(
            _reinit(line, source, target) for line in _calls(cleric_zero, source, count)
        )
    anchor = "    $InitializeEvent(0, 13404841);"
    return _replace_once(
        arena_zero,
        anchor,
        anchor
        + "\n"
        + "\n".join(added)
        + f"\n    $InitializeEvent(0, {ids.phase_two_cleanup});",
        "Ludwig combat initializer anchor",
    )


def _health(original: str) -> str:
    """Remove the second body's wiring while retaining destination lifecycle."""
    # Every removed line is checked in the already hash-pinned original body.
    result = original
    lines = [line for line in original.splitlines() if "3400801" in line]
    for line in set(lines):
        if result.count(line + "\n") != lines.count(line):
            raise ValueError("Ludwig phase-two health instruction count differs")
        result = result.replace(line + "\n", "")
    branch_start = result.index("    if (!EventFlag(13404825)) {")
    branch_end = result.index("    CreatePlaylog(46);", branch_start)
    result = (
        result[:branch_start]
        + (
            "    SetCharacterAIState(3400800, Enabled);\n"
            "    SetNetworkUpdateRate(3400800, true, CharacterUpdateFrequency.AlwaysUpdate);\n"
            "    DisplayBossHealthBar(Enabled, 3400800, 0, 500000);\n"
        )
        + result[branch_end:]
    )
    return result


def _cleanup(ids: LudwigClericIds) -> str:
    return f"""$Event({ids.phase_two_cleanup}, Restart, function() {{
    ChangeCharacterEnableState(3400801, Disabled);
    EndIf(EventFlag(13401800));
    WaitFor(EventFlag(13401800));
    ChangeCharacterEnableState(3400801, Disabled);
    ForceCharacterDeath(3400801, false);
}});"""


def patch_cleric_at_ludwig(
    destination: str, cleric_source: str, ids: LudwigClericIds = DEFAULT_IDS
) -> str:
    arena, donor = event_blocks(destination), event_blocks(cleric_source)
    _verify(arena, LUDWIG_ARENA_HASHES, "Ludwig arena")
    _verify(donor, CLERIC_SOURCE_HASHES, "Cleric donor")
    _require_ids(ids, destination)
    music = _replace_once(
        arena[13404803],
        "flagArea2 &= EventFlag(13404824);",
        "flagArea2 &= CharacterHasEventMessage(3400800, 100);",
        "Cleric phase music trigger",
    )
    edits = {
        0: _constructor(arena[0], donor[0], ids),
        13404802: _health(arena[13404802]),
        13404803: music,
        13404804: _camera(donor[12414704]),
        13404820: _end(arena[13404820]),
        13404821: _end(arena[13404821]),
        13404822: _end(arena[13404822]),
        13404823: _end(arena[13404823]),
        13404824: _end(arena[13404824]),
        13404825: _end(arena[13404825]),
        13404830: _end(arena[13404830]),
        13404835: _end(arena[13404835]),
        13404840: _end(arena[13404840]),
        13404841: _end(arena[13404841]),
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(
            (
                _remap(donor[12414707], 12414707, ids.phase),
                _remap(donor[12414708], 12414708, ids.cloth_phase),
                _remap(donor[12414710], 12414710, ids.limbs),
                _remap(donor[12414720], 12414720, ids.cloth),
                _cleanup(ids),
            )
        )
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena) | set(ids.values()):
        raise ValueError("Ludwig arena contract changed event identities")
    for event, body in arena.items():
        if event not in edits and output[event] != body:
            raise ValueError(f"Ludwig arena contract changed unrelated event {event}")
    if output[13401800] != arena[13401800] or output[13401850] != arena[13401850]:
        raise ValueError("Ludwig arena contract changed shared completion progression")
    return result


def native_plan_cleric_at_ludwig(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: LudwigClericIds = DEFAULT_IDS,
) -> dict:
    cleric = [
        s
        for s in slots
        if s.entity_id == CLERIC_PACKAGE.actor
        and s.archetype == CLERIC_PACKAGE.archetype
    ]
    ludwig = [
        s
        for s in slots
        if s.entity_id == LUDWIG_PRIMARY and s.archetype == LUDWIG_ARCHETYPE
    ]
    states = {"m24_01_00_00", "m24_01_00_01", "m24_01_00_11"}
    if (
        len(cleric) != 3
        or {s.map_name for s in cleric} != states
        or any(s.talk_id != 0 for s in cleric)
        or len(ludwig) != 1
        or ludwig[0].map_name != "m34_00_00_00"
    ):
        raise ValueError(
            "Ludwig arena requires pinned Cleric states and one Ludwig primary"
        )
    source = next(s for s in cleric if s.map_name == "m24_01_00_00")
    target = ludwig[0]
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        CLERIC_PACKAGE.archetype,
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
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "boss_contract": {
            "format": "bb-cleric-ludwig-contract-v1",
            "arena": "ludwig",
            "donor": "cleric-beast",
            "attachment_event_ids": asdict(ids),
            "preserved_destination_events": [13401800, 13401850],
            "runtime_status": "unobserved arena fit",
        },
        "primary_init_source_bindings": [
            {
                "source_map": source.map_name,
                "source_part": source.part_name,
                "source_entity_id": source.entity_id,
                "source_archetype": asdict(source.archetype),
                "source_talk_id": source.talk_id,
                "destination_map": target.map_name,
                "destination_part": target.part_name,
                "destination_entity_id": target.entity_id,
                "destination_original_talk_id": target.talk_id,
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
            "changes": [c.json() for c in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
