"""Evidence-pinned Wet Nurse combat in Blood-starved Beast's arena.

The Blood-starved Beast terminal, rewards, fog flow, camera, and map-sound
controllers remain destination-owned.  Wet Nurse's core/support/proxy health
graph, six authored core warp regions, and model-point Object are transplanted
as reviewed source records.  This is static evidence, not runtime validation.
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
WET_NURSE_SOURCE = "event/m26_00_00_00.emevd.dcx.js"
BSB_SOURCE = "event/m23_00_00_00.emevd.dcx.js"

BSB = 2300800
WET_CORE = 2600800
WET_SUPPORT = 2600801
WET_PROXY = 2600802
WET_OBJECT = 2601857
BSB_ARCHETYPE = Archetype("c2090", 209000, 209000, 0)
WET_ARCHETYPE = Archetype("c5510", 551000, 551000, 0)

PROJECT_MIN = 12992100
PROJECT_MAX = 12992199
DONOR_HASHES = {
    0: "bead3d1536484484169804138a1649d272cba5793b92b73179c6046c48aad1a0",
    12601802: "52825c64ffb75fcaf36996c80617c618c58182e0f0b34b74f7f5dc33dcf64864",
    12601803: "6c248a79ee0473faab7ffcb083c74d7395e9ad30fddddb5efad198bbfd8db06f",
    12604802: "09f0500c2acc77660cba27ac95235805b5410e652171616e9f07f3b2f401ae5f",
    12604806: "abb36c87f40649e655c35dec16d046f58dc1c79b5e9aba3a456b58f51437dbae",
    12604810: "15e07a67e931dee231546741125aa97edeb8148b70ae4c975b1da2b75ec59277",
    12604815: "abcbb89ce93449ced754f1b5ce7733182a52eebe1fc14581c259b7d3e53124a7",
    12604820: "033223280a6c9ae639d560a796a9a172d2f8eb5fe40339e19040a52d4f87159e",
    12604830: "4440653d16d290874d8e396c8ceb581a78d0a6990388f0e1f94888e671ba4c2b",
    12604840: "f7f166e1072f4217a0ba93afb13fc8158def71c21f29d8b1c4810d97c5f5fed9",
}
ARENA_HASHES = {
    0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    12301800: "e9eed714540eab5058a6553eb5b11b28f2edcb6d4236679efaafafb9c4e8f1a4",
    12301801: "04732cb4245a537ebbb26833250f04d4164b4a22d41237977235a98726c5b9aa",
    12301802: "c8e1b3b8b94fe800a158228a1b177c944c90883fc45826b5060488a064ca145d",
    12301803: "62fb078e77c476dc5d9d3631843895197d9974e67a15880b5ca133dd870f299c",
    12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
    12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
    12304804: "86edb06de9efdc94365fb640741ce4d62620363a3c37ebb99d37ef2b9d3f3521",
    12304805: "85da4e5deb89a2513ecbdf56d536370512f8e2caf89be3698138ba225f1f4046",
    12304807: "7e9c22292f41da758876cceffe70b61ad51cf0f86e7b5e250e3c8514f179d780",
    12304808: "8ccea02a7829f43788cf77ec24ea5b524643f9ab6d55681f492f1afa588e31f5",
}

BSB_PINS = {
    "m23_00_00_00": "55d69ae3862270c13509c2842a52f10a036713d21e24ba3d7f2cba2d3e884891",
    "m23_00_00_01": "38ae3c392bf19848f3a0bb0b213358eb52e9f9bf327ebcaa8efc3c4a89b8b84d",
}
WET_PINS = {
    WET_CORE: "8ec99e63d52ac0ada984adabd723cce20900448cce7c041522cf90ac4b98faac",
    WET_SUPPORT: "01f71e6d7cc177feca59a4290ea3972aa2ace57dca81913aee136f4cc1b24bf8",
    WET_PROXY: "089c3c9baa7b41536b5dc68f02208b1b2287bf2aeac64c1c0135a089882400b3",
}
OBJECT_PIN = "2d537771b0a931183951612e991e3d4ba99e708e87d04bb92d600dac2903d572"
REGION_PINS = {
    2602830: (
        "Event_ボスのワープ先00",
        "e02b9834c6062d53380ee5bceacca9cd00f27157b4a9f8654441cdaea371c358",
    ),
    2602831: (
        "Event_ボスのワープ先01",
        "c8e9ba8ac4429cd145596d522cc4f691d4aad5b35e97cae8440ab18dccd56497",
    ),
    2602832: (
        "Event_ボスのワープ先02",
        "07a9b781644d1cf0576eb3ab270b5b4032172dd57c74dbc806b3d4dc10c36701",
    ),
    2602833: (
        "Event_ボスのワープ先03",
        "071dfc336a744ce2cdaf0adbb6c16ef2c97f8389f84d2b3c56d7fc3787c400c4",
    ),
    2602834: (
        "Event_ボスのワープ先04",
        "2580bb6c59e0e043ddc932c931b7685dfad951e942b2d87557f035c17a7c79b9",
    ),
    2602835: (
        "Event_ボスのワープ先05",
        "7b5db88b31148933e0383cca490418df4f49eb8cd4fac7e86c787a7a0312a1e3",
    ),
}


@dataclass(frozen=True)
class WetNurseBsbIds:
    # The health controller replaces destination event 12304802; only these
    # project-owned IDs are appended to Event(0).
    support_setup: int = 12992100
    core_command: int = 12992101
    route_selector: int = 12992102
    core_warp: int = 12992103
    support_emergence: int = 12992104
    proxy_death_bridge: int = 12992105
    helper_cleanup: int = 12992106
    support_entity: int = 980200
    proxy_entity: int = 980201
    warp_region_first_entity: int = 980202
    object_entity: int = 980208
    health_entered_flag: int = 12992120
    warp_flag_first: int = 12992121
    support_flag_first: int = 12992127

    def event_ids(self) -> tuple[int, ...]:
        return (
            self.support_setup,
            self.core_command,
            self.route_selector,
            self.core_warp,
            self.support_emergence,
            self.proxy_death_bridge,
            self.helper_cleanup,
        )

    def all_project_ids(self) -> tuple[int, ...]:
        return self.event_ids() + (
            self.health_entered_flag,
            *(self.warp_flag_first + index for index in range(6)),
            *(self.support_flag_first + index for index in range(4)),
        )

    def helper_ids(self) -> tuple[int, ...]:
        return (
            self.support_entity,
            self.proxy_entity,
            *(self.warp_region_first_entity + index for index in range(6)),
            self.object_entity,
        )


DEFAULT_IDS = WetNurseBsbIds()


def _verify(text: str, pins: Mapping[int, str], label: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event, digest in pins.items():
        body = blocks.get(event)
        if body is None or hashlib.sha256(body.encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {label} event {event}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Wet Nurse/BSB expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])", lambda m: str(values.get(int(m[0]), int(m[0]))), text
    )


def _end_event(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            (
                name.strip()
                if name.strip().startswith("unused_")
                else "unused_" + name.strip()
            )
            for name in match[1].split(",")
            if name.strip()
        )
        + ")",
        declaration,
    )
    return declaration + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _all_original_literals() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            int(value)
            for value in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
        )
    return values


def _validate_ids(ids: WetNurseBsbIds, destination: str) -> None:
    values = ids.all_project_ids()
    helpers = ids.helper_ids()
    destination_values = {
        int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)
    }
    original_values = _all_original_literals()
    if (
        len(values) != len(set(values))
        or any(not PROJECT_MIN <= value <= PROJECT_MAX for value in values)
        or set(values).intersection(destination_values | original_values)
    ):
        raise ValueError(
            "Wet Nurse/BSB IDs must be collision-free project-owned 129921xx values"
        )
    if (
        len(helpers) != len(set(helpers))
        or any(not 980200 <= value <= 980299 for value in helpers)
        or set(helpers).intersection(destination_values | original_values | set(values))
    ):
        raise ValueError(
            "Wet Nurse/BSB helper IDs must be collision-free reserved 980200-range values"
        )


def _source_initializers(
    event_zero: str, source_event: int, expected_count: int, remap: Mapping[int, int]
) -> list[str]:
    calls = [
        line
        for line in event_zero.splitlines()
        if re.match(
            r"\s*\$InitializeEvent\([^,]+,\s*" + str(source_event) + r"(?:,|\))", line
        )
    ]
    if len(calls) != expected_count:
        raise ValueError(
            f"Wet Nurse Event(0) lacks {expected_count} initializer witnesses for {source_event}"
        )
    return [_remap(line, remap) for line in calls]


def _mapping(ids: WetNurseBsbIds) -> dict[int, int]:
    mapping = {
        WET_CORE: BSB,
        WET_SUPPORT: ids.support_entity,
        WET_PROXY: ids.proxy_entity,
        WET_OBJECT: ids.object_entity,
        12601800: 12301800,
        12604800: 12304800,
        12604803: 12304803,
        12604732: ids.health_entered_flag,
        2600010: 2300010,
        # Health has a reviewed destination Event(0) initializer already, so
        # its source body replaces that existing destination controller.
        12604802: 12304802,
        12604806: ids.support_setup,
        12604810: ids.core_command,
        12604820: ids.route_selector,
        12604830: ids.core_warp,
        12604840: ids.support_emergence,
    }
    mapping.update(
        {2602830 + index: ids.warp_region_first_entity + index for index in range(6)}
    )
    mapping.update(
        {12605880 + index: ids.warp_flag_first + index for index in range(6)}
    )
    mapping.update(
        {12604841 + index: ids.support_flag_first + index for index in range(4)}
    )
    return mapping


def patch_wet_nurse_at_bsb(
    destination: str, donor_source: str, ids: WetNurseBsbIds = DEFAULT_IDS
) -> str:
    """Install Wet Nurse's reviewed multi-actor combat in the BSB arena."""
    arena = _verify(destination, ARENA_HASHES, "BSB arena")
    donor = _verify(donor_source, DONOR_HASHES, "Wet Nurse donor")
    _validate_ids(ids, destination)
    remap = _mapping(ids)
    health = _remap(donor[12604802], remap)
    health = _replace_once(
        health, "CreatePlaylog(88);", "CreatePlaylog(86);", "destination playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2300010, 104, Enabled);",
        "StartTimeMeasurement(2300010, 102, Enabled);",
        "destination time measurement",
    )
    imported = {
        ids.support_setup: _remap(donor[12604806], remap),
        ids.core_command: _remap(donor[12604810], remap),
        ids.route_selector: _remap(donor[12604820], remap),
        ids.core_warp: _remap(donor[12604830], remap),
        ids.support_emergence: _remap(donor[12604840], remap),
        ids.proxy_death_bridge: f"""$Event({ids.proxy_death_bridge}, Default, function() {{
    EndIf(EventFlag(12301800));
    WaitFor(HPRatio({ids.proxy_entity}) <= 0);
    EndIf(EventFlag(12301800));
    RequestCharacterAnimationReset(2300800, Interpolation.Uninterpolated);
    RequestCharacterAnimationReset({ids.support_entity}, Interpolation.Uninterpolated);
    ForceCharacterDeath(2300800, false);
    ForceCharacterDeath({ids.support_entity}, false);
    WaitFor(CharacterDead(2300800));
    ClearSpEffect(10000, 5630);
}});""",
        ids.helper_cleanup: f"""$Event({ids.helper_cleanup}, Default, function() {{
    WaitFor(EventFlag(12301800));
    ChangeCharacterEnableState({ids.support_entity}, Disabled);
    ChangeCharacterEnableState({ids.proxy_entity}, Disabled);
}});""",
    }
    initializers: list[str] = []
    # Destination Event(0) already initializes its changed health controller
    # 12304802. Copy only new controller witnesses from Wet Nurse Event(0).
    for event, count in (
        (12604820, 1),
        (12604830, 6),
        (12604806, 1),
        (12604810, 1),
        (12604840, 1),
    ):
        initializers.extend(_source_initializers(donor[0], event, count, remap))
    initializers.extend(
        f"    $InitializeEvent(0, {event});"
        for event in (ids.proxy_death_bridge, ids.helper_cleanup)
    )
    entry = _replace_once(
        arena[12301802],
        "    EndIf(ThisEvent());\n",
        "    EndIf(ThisEvent());\n    ChangeCharacterEnableState(2300800, Disabled);\n",
        "Wet Nurse pre-entry visibility",
    )
    entry = _replace_once(
        entry,
        "    ForceAnimationPlayback(2300800, 7001, false, false, false);\n",
        "    ChangeCharacterEnableState(2300800, Enabled);\n",
        "BSB-only entry animation",
    )
    coop = _replace_once(
        arena[12301803],
        "    SetEventFlag(12304800, ON);\n",
        "    ChangeCharacterEnableState(2300800, Enabled);\n"
        "    SetEventFlag(12304800, ON);\n",
        "Wet Nurse co-op visibility restore",
    )
    edits = {
        0: _replace_once(
            arena[0],
            "    $InitializeEvent(0, 12304808);",
            "    $InitializeEvent(0, 12304808);\n" + "\n".join(initializers),
            "project controller anchor",
        ),
        12301802: entry,
        12301803: coop,
        12304802: health,
        # BSB's phase-one routine issues BSB-only animation/AI commands.
        12304807: _end_event(arena[12304807]),
        # Destination music waits for this event's flag. Do not complete it
        # early: defer its completion until Wet Nurse's proxy reaches the
        # source transition ratio, while omitting BSB animation/AI commands.
        12304808: f"""$Event(12304808, Default, function() {{
    EndIf(EventFlag(12301800));
    EndIf(ThisEvent());
    WaitFor(HPRatio({ids.proxy_entity}) < 0.7);
}});""",
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(imported[event] for event in ids.event_ids())
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.event_ids()):
        raise ValueError("Wet Nurse/BSB patch changed event identities")
    for event, body in arena.items():
        if event not in edits and output[event] != body:
            raise ValueError(f"Wet Nurse/BSB changed unrelated BSB event {event}")
    for event in (12301800, 12301801, 12304803, 12304804, 12304805):
        if output[event] != arena[event]:
            raise ValueError(
                "Wet Nurse/BSB changed destination terminal, progression, music, or camera"
            )
    copied = "\n".join((health, *imported.values()))
    if re.search(r"(?<!\d)(?:126|260)\d+(?!\d)", copied) or "2600803" in copied:
        raise ValueError(
            "Wet Nurse/BSB copied combat retains donor-map or unresolved opaque literals"
        )
    if (
        "CreateReferredDamagePair(2300800, 980201)" not in output[12304802]
        or f"CreateReferredDamagePair({ids.support_entity}, {ids.proxy_entity})"
        not in output[12304802]
    ):
        raise ValueError(
            "Wet Nurse/BSB lost required core/support proxy health redirection"
        )
    return result


def _require(
    slots: Sequence[Slot],
    entity: int,
    archetype: Archetype,
    map_name: str | None = None,
) -> list[Slot]:
    found = [
        slot
        for slot in slots
        if slot.entity_id == entity
        and slot.archetype == archetype
        and (map_name is None or slot.map_name == map_name)
    ]
    if not found or any(slot.dummy or slot.talk_id for slot in found):
        raise ValueError(f"Wet Nurse/BSB requires pinned ordinary actor {entity}")
    return sorted(found, key=lambda slot: slot.key)


def _initialization(source: Slot, target: Slot) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": WET_PINS[WET_CORE],
        },
        "source_initialization": {
            "talk_id": 0,
            "unk_t18": -1,
            "init_anim_id": -1,
            "damage_anim_id": -1,
        },
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


def native_plan_wet_nurse_at_bsb(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: WetNurseBsbIds = DEFAULT_IDS,
) -> dict:
    """Return the source-pinned map/event construction request; not builder-wired."""
    donor_text = read_blob(BUNDLE, WET_NURSE_SOURCE).decode("utf-8-sig")
    arena_text = read_blob(BUNDLE, BSB_SOURCE).decode("utf-8-sig")
    _verify(donor_text, DONOR_HASHES, "Wet Nurse donor")
    _verify(arena_text, ARENA_HASHES, "BSB arena")
    _validate_ids(ids, arena_text)
    core = _require(slots, WET_CORE, WET_ARCHETYPE, "m26_00_00_00")
    support = _require(slots, WET_SUPPORT, WET_ARCHETYPE, "m26_00_00_00")
    proxy = _require(slots, WET_PROXY, WET_ARCHETYPE, "m26_00_00_00")
    targets = _require(slots, BSB, BSB_ARCHETYPE)
    if (
        len(core) != 1
        or len(support) != 1
        or len(proxy) != 1
        or len(targets) != 2
        or {target.map_name for target in targets} != set(BSB_PINS)
    ):
        raise ValueError(
            "Wet Nurse/BSB requires one Wet Nurse roster and two BSB map states"
        )
    swap = Swap(
        targets[0].logical_key,
        [target.key for target in targets],
        {target.key: target.archetype for target in targets},
        BSB_ARCHETYPE,
        WET_ARCHETYPE,
        warnings=[
            "experimental Wet Nurse-at-BSB contract; runtime arena fit, model-point warps, and proxy terminal bridge are unobserved"
        ],
        destinations={
            target.key: {
                "map_name": target.map_name,
                "entity_id": target.entity_id,
                "x": target.x,
                "y": target.y,
                "z": target.z,
            }
            for target in targets
        },
    )
    changes, skips = plan_scaling(
        [swap], list(targets), dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError(
            "Wet Nurse/BSB primary swap has an ambiguous normalization plan"
        )
    additions, regions, objects, primary = [], [], [], []
    for target in targets:
        anchor_pin = BSB_PINS[target.map_name]
        primary.append(_initialization(core[0], target))
        for source, entity, part in (
            (support[0], ids.support_entity, "ap_wet_nurse_support"),
            (proxy[0], ids.proxy_entity, "ap_wet_nurse_proxy"),
        ):
            additions.append(
                {
                    "source_map": source.map_name,
                    "source_part": source.part_name,
                    "source_anchor_part": core[0].part_name,
                    "source_entity_id": source.entity_id,
                    "source_archetype": asdict(source.archetype),
                    "source_part_kind": "enemy",
                    "source_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": WET_PINS[source.entity_id],
                        "anchor_sha256": WET_PINS[WET_CORE],
                    },
                    "source_initialization": {
                        "talk_id": 0,
                        "unk_t18": -1,
                        "init_anim_id": -1,
                        "damage_anim_id": -1,
                    },
                    "destination_map": target.map_name,
                    "destination_anchor_part": target.part_name,
                    "destination_part": part,
                    "destination_entity_id": entity,
                    "allocation_evidence": "project-reserved helper ID; native writer checks all Part/Region/Event collisions",
                }
            )
        for index, (source_entity, (source_name, fingerprint)) in enumerate(
            REGION_PINS.items()
        ):
            regions.append(
                {
                    "source_map": core[0].map_name,
                    "source_region": source_name,
                    "source_entity_id": source_entity,
                    "source_provenance": {
                        "format": "bb-boss-region-pin-v1",
                        "region_sha256": fingerprint,
                    },
                    "source_anchor_part": core[0].part_name,
                    "source_anchor_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": WET_PINS[WET_CORE],
                    },
                    "destination_map": target.map_name,
                    "destination_region": f"ap_wet_nurse_warp_{index + 1}",
                    "destination_entity_id": ids.warp_region_first_entity + index,
                    "destination_anchor_part": target.part_name,
                    "destination_anchor_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": anchor_pin,
                    },
                }
            )
        objects.append(
            {
                "source_map": core[0].map_name,
                "source_part": "o269800_0000",
                "source_entity_id": WET_OBJECT,
                "source_provenance": {
                    "format": "bb-boss-object-pin-v1",
                    "part_sha256": OBJECT_PIN,
                },
                "source_anchor_part": core[0].part_name,
                "source_anchor_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": WET_PINS[WET_CORE],
                },
                "destination_map": target.map_name,
                "destination_part": "ap_wet_nurse_model_point",
                "destination_entity_id": ids.object_entity,
                "destination_anchor_part": target.part_name,
                "destination_anchor_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": anchor_pin,
                },
            }
        )
    remap = _mapping(ids)
    source_events = (
        (12604806, ids.support_setup),
        (12604810, ids.core_command),
        (12604820, ids.route_selector),
        (12604830, ids.core_warp),
        (12604840, ids.support_emergence),
    )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {
            "experimental_boss_contract": "blood-starved-beast<-mergos-wet-nurse"
        },
        "boss_actor_additions": additions,
        "boss_region_additions": regions,
        "boss_object_additions": objects,
        "primary_init_source_bindings": primary,
        "boss_contract": {
            "format": "bb-wet-nurse-bsb-contract-v1",
            "arena": "blood-starved-beast",
            "donor": "mergos-wet-nurse",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(DONOR_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "preserved_destination_events": [
                12301800,
                12301801,
                12304803,
                12304804,
                12304805,
            ],
            "opaque_actor_policy": "2600803 is absent from all original MSBB tables and is not materialized or copied",
            "destination_music_policy": "retain byte-identical BSB map sounds and proxy-ratio phase transition",
            "source_map_ambience_not_transplanted": {
                "event_id": 12604815,
                "source_sha256": DONOR_HASHES[12604815],
                "sound_id": 260000003,
                "bank": "sprj_m26.fev",
                "policy": "destination_owned_environmental_audio",
            },
            "model_point_object": {
                "source_part": "o269800_0000",
                "source_entity_id": WET_OBJECT,
                "destination_part": "ap_wet_nurse_model_point",
                "destination_entity_id": ids.object_entity,
                "policy": "source-pinned ordinary Object clone; Object target/model-point behavior runtime unobserved",
            },
            "event_patch": {
                "changed_events": [
                    {
                        "destination_event_id": 12301802,
                        "source_event_id": 12601802,
                        "source_sha256": DONOR_HASHES[12601802],
                        "kind": "retain_bsb_trigger_with_wet_nurse_visibility",
                    },
                    {
                        "destination_event_id": 12301803,
                        "source_event_id": 12601803,
                        "source_sha256": DONOR_HASHES[12601803],
                        "kind": "wet_nurse_client_visibility_restore",
                    },
                    {
                        "destination_event_id": 12304802,
                        "source_event_id": 12604802,
                        "source_sha256": DONOR_HASHES[12604802],
                    },
                    {
                        "destination_event_id": 12304807,
                        "source_event_id": None,
                        "kind": "disable_bsb_phase_one",
                    },
                    {
                        "destination_event_id": 12304808,
                        "source_event_id": None,
                        "kind": "disable_bsb_phase_two",
                    },
                ],
                "added_events": [
                    {
                        "source_event_id": source,
                        "destination_event_id": destination,
                        "source_sha256": DONOR_HASHES[source],
                        "literal_remap": remap,
                    }
                    for source, destination in source_events
                ]
                + [
                    {
                        "source_event_id": None,
                        "destination_event_id": event,
                        "kind": "destination_bridge",
                    }
                    for event in (ids.proxy_death_bridge, ids.helper_cleanup)
                ],
            },
        },
        # Same-NPC helper normalization needs the generic allocator's reviewed
        # same-source-NPC path; do not claim a clone allocation here.
        "boss_actor_scaling_requirements": [
            {
                "destination_map": target.map_name,
                "destination_part": part,
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": 551000,
                "strategy": "reviewed_same_source_npc_helper_clone_required",
            }
            for target in targets
            for part in ("ap_wet_nurse_support", "ap_wet_nurse_proxy")
        ],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
