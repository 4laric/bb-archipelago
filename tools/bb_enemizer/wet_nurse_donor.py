"""Reusable source-pinned Mergo's Wet Nurse combat donor for base arenas.

The receiving arena owns entry geometry, fog, camera, map sounds, completion,
rewards, and progression.  Wet Nurse keeps its three-body health graph,
nightmare commands, six warp routes, support apparition, and model-point object.
Static construction and compilation are verified; no runtime claim is made.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_prefix

from .boss_canary import event_blocks, parse_events
from .boss_contracts import ARENAS, ArenaContract
from .maria_donor import _activation_without_destination_animations
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m26_00_00_00.emevd.dcx.js"
SOURCE_MAP = "m26_00_00_00"
CORE, SUPPORT, PROXY = 2600800, 2600801, 2600802
MODEL_POINT_OBJECT = 2601857
WET_ARCHETYPE = Archetype("c5510", 551000, 551000, 0)
SOURCE_PARTS = {
    CORE: "c5510_0000",
    SUPPORT: "c5510_0001",
    PROXY: "c5510_0002",
}
SOURCE_PART_PINS = {
    CORE: "8ec99e63d52ac0ada984adabd723cce20900448cce7c041522cf90ac4b98faac",
    SUPPORT: "01f71e6d7cc177feca59a4290ea3972aa2ace57dca81913aee136f4cc1b24bf8",
    PROXY: "089c3c9baa7b41536b5dc68f02208b1b2287bf2aeac64c1c0135a089882400b3",
}
SOURCE_INITIALIZATION = {
    "talk_id": 0,
    "unk_t18": -1,
    "init_anim_id": -1,
    "damage_anim_id": -1,
}
SOURCE_HASHES = {
    0: "bead3d1536484484169804138a1649d272cba5793b92b73179c6046c48aad1a0",
    12601802: "52825c64ffb75fcaf36996c80617c618c58182e0f0b34b74f7f5dc33dcf64864",
    12601803: "6c248a79ee0473faab7ffcb083c74d7395e9ad30fddddb5efad198bbfd8db06f",
    12604802: "09f0500c2acc77660cba27ac95235805b5410e652171616e9f07f3b2f401ae5f",
    12604804: "c5a35148c3c7a4b94be4d11608b4ee97f0b79d08fca37fd7dfd15495d1107e4b",
    12604806: "abb36c87f40649e655c35dec16d046f58dc1c79b5e9aba3a456b58f51437dbae",
    12604810: "15e07a67e931dee231546741125aa97edeb8148b70ae4c975b1da2b75ec59277",
    12604815: "abcbb89ce93449ced754f1b5ce7733182a52eebe1fc14581c259b7d3e53124a7",
    12604820: "033223280a6c9ae639d560a796a9a172d2f8eb5fe40339e19040a52d4f87159e",
    12604830: "4440653d16d290874d8e396c8ceb581a78d0a6990388f0e1f94888e671ba4c2b",
    12604840: "f7f166e1072f4217a0ba93afb13fc8158def71c21f29d8b1c4810d97c5f5fed9",
}
SOURCE_EVENT_SHA256 = "ee9a92c839a643513824024cfe9929219e793706c3ba79b13ae8ee590ea79dcf"
SOURCE_FFX_FILE = "frpg_sfxbnd_m26.ffxbnd.dcx"
SOURCE_FFX_SHA256 = "3c6867267f838ed63d7071f95466ba90c3046b302d590ce2780161c32db70bfb"
EMEVD_EFFECT = 655105
MISSING_TAE_EFFECT = 655108
CHARACTER_ARCHIVE_SHA256 = (
    "d2d0c06e3a4fde5d5793894141613bd0b018a59b2717bb0a628630f2c2c07431"
)
CHARACTER_TAE_SHA256 = (
    "f9d50fe4f1fb69201f091acd31453927090dd0da1c07ade5d80d4bab460efaa8"
)
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

# The target actor is the native anchor in each original physical map state.
DESTINATION_PART_PINS = {
    (
        "m23_00_00_00",
        2300800,
    ): "55d69ae3862270c13509c2842a52f10a036713d21e24ba3d7f2cba2d3e884891",
    (
        "m23_00_00_01",
        2300800,
    ): "38ae3c392bf19848f3a0bb0b213358eb52e9f9bf327ebcaa8efc3c4a89b8b84d",
    (
        "m23_00_00_00",
        2300810,
    ): "cac704506e58dfd3f2c57113d919fafe0a70d01b7a40b869deffa3c6e22cc0a2",
    (
        "m23_00_00_01",
        2300810,
    ): "6c8a693b9c846922a1113726ec69a11b47973c5e367a94757ad82d3fbf3081ee",
    (
        "m24_01_00_00",
        2410800,
    ): "0225c170ffac0c48d69f996e361b83c5490069e4a75fdc6b19328458f2fd3848",
    (
        "m24_01_00_01",
        2410800,
    ): "34c019e726003bf86523ef384e74c2fb050c4d7d82ab8012ddfc8ba42d6f0940",
    (
        "m24_01_00_11",
        2410800,
    ): "a8ca2f725b4e7d1c823912bbb0131a17dfba84d50f0c2713b820db78bc8722b3",
    (
        "m24_00_00_00",
        2400800,
    ): "99f32c1296938362bd6d5abbcc073f6179fd9173f18a3a5076391d37ff88c35e",
    (
        "m24_00_00_01",
        2400800,
    ): "ba04891b13b4fff5ad61eebf53c4715c89ef70e9599025d4335cb558b808a4e5",
    (
        "m33_00_00_00",
        3300800,
    ): "4d66ca60f567e2f0ba0ffcc43fb45c5666265fd9649952cc3828185f0ef1bc39",
    (
        "m24_02_00_00",
        2420800,
    ): "5f6ed3a557a24f54151a77bc3de15ce5f8d8645d6ad5cafc94fe4449b91ce5c2",
    (
        "m24_02_00_01",
        2420800,
    ): "6e96e026cb750d840a621e27ec07658b9953c62b061c79ca8d5b95227c87dcbb",
}
DESTINATION_CO_OP = {
    "cleric-beast": (
        12411703,
        "f4982068db5c19d893ac320045e14491832a5722d1fd89a8038ef4cb8b372ce9",
    ),
    "blood-starved-beast": (
        12301803,
        "62fb078e77c476dc5d9d3631843895197d9974e67a15880b5ca133dd870f299c",
    ),
    "darkbeast-paarl": (
        12301703,
        "ca968c9f60d2a495e9f3c87c77083ec5d1524b34792d646aa29a239f7f11b653",
    ),
    "vicar-amelia": (
        12401804,
        "85aa59f873b275cb390675f4f2ef13e4f7b3f00935274a2ce43c23b75070da59",
    ),
    "amygdala": (
        13301803,
        "7613c67c60f7fd94fe8152c96887113aabaeee5cc728f79bd3c2fcfd2bfb0dd9",
    ),
    "ebrietas": (
        12421803,
        "dcbbafd95ebeebce5ddd63d637fc07b93bff8f52c33b77665e0ca21e6d649152",
    ),
}
DESTINATION_FFX = {
    "cleric-beast": (
        "frpg_sfxbnd_m24.ffxbnd.dcx",
        "56103cdfe6b3f9298a32fc515be67c6117f555ae69cb87a8cbbb8bcba2abac99",
    ),
    "blood-starved-beast": (
        "frpg_sfxbnd_m23.ffxbnd.dcx",
        "b92037c5ae58ac81e5e59f7b9596966faf65ea56bf1b9ea9913045097213cfec",
    ),
    "darkbeast-paarl": (
        "frpg_sfxbnd_m23.ffxbnd.dcx",
        "b92037c5ae58ac81e5e59f7b9596966faf65ea56bf1b9ea9913045097213cfec",
    ),
    "vicar-amelia": (
        "frpg_sfxbnd_m24.ffxbnd.dcx",
        "56103cdfe6b3f9298a32fc515be67c6117f555ae69cb87a8cbbb8bcba2abac99",
    ),
    "amygdala": (
        "frpg_sfxbnd_m33.ffxbnd.dcx",
        "850e8354601f85e59166aaeceb0dea48018fd21afbad005f78b7732fc3889a29",
    ),
    "ebrietas": (
        "frpg_sfxbnd_m24.ffxbnd.dcx",
        "56103cdfe6b3f9298a32fc515be67c6117f555ae69cb87a8cbbb8bcba2abac99",
    ),
}


@dataclass(frozen=True)
class WetNurseDonorAllocation:
    support_setup_event: int = 12996400
    core_command_event: int = 12996401
    route_selector_event: int = 12996402
    core_warp_event: int = 12996403
    support_emergence_event: int = 12996404
    terminal_bridge_event: int = 12996405
    helper_cleanup_event: int = 12996406
    notification_flag: int = 12996420
    warp_flag_first: int = 12996421
    support_flag_first: int = 12996427
    support_entity: int = 983900
    proxy_entity: int = 983901
    warp_region_first_entity: int = 983902
    object_entity: int = 983908

    def event_ids(self) -> tuple[int, ...]:
        return (
            self.support_setup_event,
            self.core_command_event,
            self.route_selector_event,
            self.core_warp_event,
            self.support_emergence_event,
            self.terminal_bridge_event,
            self.helper_cleanup_event,
        )

    def values(self) -> tuple[int, ...]:
        return (
            *self.event_ids(),
            self.notification_flag,
            *(self.warp_flag_first + index for index in range(6)),
            *(self.support_flag_first + index for index in range(4)),
            self.support_entity,
            self.proxy_entity,
            *(self.warp_region_first_entity + index for index in range(6)),
            self.object_entity,
        )


DEFAULT_ALLOCATION = WetNurseDonorAllocation()


def _numbers(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values.update(_numbers(body.decode("utf-8-sig")))
    return frozenset(values)


def _validate(allocation: WetNurseDonorAllocation, destination: str = "") -> None:
    expected = (
        *range(12996400, 12996407),
        12996420,
        *range(12996421, 12996431),
        *range(983900, 983909),
    )
    values = allocation.values()
    if values != expected:
        raise ValueError("Wet Nurse donor requires the exact reviewed allocation")
    if len(values) != len(set(values)) or set(values) & (
        _original_literals() | _numbers(destination)
    ):
        raise ValueError("Wet Nurse donor allocation collides with original inputs")


def _verify(blocks: Mapping[int, str], expected: Mapping[int, str], role: str) -> None:
    for event_id, digest in expected.items():
        body = blocks.get(event_id, "")
        if hashlib.sha256(body.encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Wet Nurse donor expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, mapping: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(mapping.get(int(match[0]), int(match[0]))),
        text,
    )


def _noop(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            (
                value.strip()
                if value.strip().startswith("unused_")
                else "unused_" + value.strip()
            )
            for value in match[1].split(",")
            if value.strip()
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


def _retired(arena: ArenaContract) -> set[int]:
    return {
        event
        for event in (
            *arena.phase_slots,
            *arena.retired_combat_events,
            arena.part_routine_event,
            arena.cloth_routine_event,
            arena.attachment_anchor_event,
        )
        if event is not None
    }


def _telemetry(source: str, destination: str) -> str:
    result = source
    for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
        source_lines = [
            line
            for line in source.splitlines()
            if line.strip().startswith(instruction + "(")
        ]
        destination_lines = [
            line
            for line in destination.splitlines()
            if line.strip().startswith(instruction + "(")
        ]
        if len(source_lines) != 1 or len(destination_lines) != 1:
            raise ValueError(f"Wet Nurse telemetry lacks unique {instruction}")
        result = _replace_once(
            result, source_lines[0], destination_lines[0], "destination telemetry"
        )
    return result


def _notification_flag(
    destination_health: str, allocation: WetNurseDonorAllocation
) -> int:
    match = re.search(
        r"if \(!EventFlag\((\d+)\)\) \{\n\s+IssueBossRoomEntryNotification\(0\);",
        destination_health,
    )
    return allocation.notification_flag if match is None else int(match[1])


def _mark_existing_notification(block: str, flag: int) -> str:
    witness = "        IssueBossRoomEntryNotification(0);\n"
    count = block.count(witness)
    if count > 1:
        raise ValueError("destination entry notification witness is not unique")
    if count == 0:
        return block
    return block.replace(witness, witness + f"        SetEventFlag({flag}, ON);\n", 1)


def _mapping(
    arena: ArenaContract,
    allocation: WetNurseDonorAllocation,
    notification_flag: int,
) -> dict[int, int]:
    result = {
        CORE: arena.actor,
        SUPPORT: allocation.support_entity,
        PROXY: allocation.proxy_entity,
        MODEL_POINT_OBJECT: allocation.object_entity,
        12601800: arena.completion_event,
        12604800: arena.start_flag,
        12604802: arena.health_bar_event,
        12604803: arena.music_event,
        12604732: notification_flag,
        12604806: allocation.support_setup_event,
        12604810: allocation.core_command_event,
        12604820: allocation.route_selector_event,
        12604830: allocation.core_warp_event,
        12604840: allocation.support_emergence_event,
    }
    result.update(
        {12605880 + index: allocation.warp_flag_first + index for index in range(6)}
    )
    result.update(
        {12604841 + index: allocation.support_flag_first + index for index in range(4)}
    )
    result.update(
        {
            2602830 + index: allocation.warp_region_first_entity + index
            for index in range(6)
        }
    )
    return result


def _health(
    source: str,
    destination: str,
    mapping: Mapping[int, int],
) -> str:
    return _telemetry(_remap(source, mapping), destination)


def _music(arena: ArenaContract, block: str, proxy_entity: int) -> str:
    replacement = f"HPRatio({proxy_entity}) < 0.7"
    if arena.phase_music_message is not None:
        witness = (
            f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})"
        )
    else:
        event_flag = arena.phase_music_event_flag or arena.part_routine_event
        if event_flag is None:
            raise ValueError(f"{arena.key} has no declared music phase boundary")
        witness = f"EventFlag({event_flag})"
    return _replace_once(block, witness, replacement, "destination music boundary")


def _initializer_calls(event_zero: str, event_id: int, count: int) -> list[str]:
    calls = [
        line
        for line in event_zero.splitlines()
        if re.match(rf"\s*\$InitializeEvent\([^,]+,\s*{event_id}(?:,|\))", line)
    ]
    if len(calls) != count:
        raise ValueError(
            f"Wet Nurse Event(0) lacks {count} initializers for {event_id}"
        )
    return calls


def _constructor(
    arena: ArenaContract,
    destination: str,
    donor_zero: str,
    mapping: Mapping[int, int],
    allocation: WetNurseDonorAllocation,
) -> str:
    anchors = [
        f"    $InitializeEvent(0, {event});"
        for event in reversed(arena.phase_slots)
        if destination.count(f"    $InitializeEvent(0, {event});") == 1
    ]
    if not anchors:
        raise ValueError(f"{arena.key} lacks a constructor anchor")
    calls: list[str] = []
    for source_event, count in (
        (12604820, 1),
        (12604830, 6),
        (12604806, 1),
        (12604810, 1),
        (12604840, 1),
    ):
        calls.extend(
            _remap(line, mapping)
            for line in _initializer_calls(donor_zero, source_event, count)
        )
    calls.extend(
        f"    $InitializeEvent(0, {event});"
        for event in (
            allocation.terminal_bridge_event,
            allocation.helper_cleanup_event,
        )
    )
    return _replace_once(
        destination,
        anchors[0],
        anchors[0] + "\n" + "\n".join(calls),
        "destination constructor anchor",
    )


def _terminal_bridge(arena: ArenaContract, allocation: WetNurseDonorAllocation) -> str:
    return f"""$Event({allocation.terminal_bridge_event}, Default, function() {{
    EndIf(EventFlag({arena.completion_event}));
    WaitFor(HPRatio({allocation.proxy_entity}) <= 0);
    EndIf(EventFlag({arena.completion_event}));
    RequestCharacterAnimationReset({arena.actor}, Interpolation.Uninterpolated);
    RequestCharacterAnimationReset({allocation.support_entity}, Interpolation.Uninterpolated);
    ForceCharacterDeath({arena.actor}, false);
    ForceCharacterDeath({allocation.support_entity}, false);
    WaitFor(CharacterDead({arena.actor}));
    ClearSpEffect(10000, 5630);
    WaitFor(EventFlag({arena.completion_event}));
}});"""


def _helper_cleanup(arena: ArenaContract, allocation: WetNurseDonorAllocation) -> str:
    return f"""$Event({allocation.helper_cleanup_event}, Default, function() {{
    WaitFor(EventFlag({arena.completion_event}));
    SetCharacterAIState({allocation.support_entity}, Disabled);
    SetCharacterHPBarDisplay({allocation.support_entity}, Disabled);
    ChangeCharacterEnableState({allocation.support_entity}, Disabled);
    SetCharacterAIState({allocation.proxy_entity}, Disabled);
    SetCharacterHPBarDisplay({allocation.proxy_entity}, Disabled);
    ChangeCharacterEnableState({allocation.proxy_entity}, Disabled);
    ForceCharacterDeath({allocation.support_entity}, false);
    ForceCharacterDeath({allocation.proxy_entity}, false);
    ClearSpEffect(10000, 5630);
}});"""


def wet_nurse_donor_contract(
    arena: ArenaContract,
    allocation: WetNurseDonorAllocation = DEFAULT_ALLOCATION,
) -> dict:
    _validate(allocation)
    co_op_event, co_op_hash = DESTINATION_CO_OP[arena.key]
    return {
        "format": "bb-wet-nurse-donor-contract-v1",
        "status": "experimental",
        "arena": arena.key,
        "donor": "mergos-wet-nurse",
        "allocation": asdict(allocation),
        "preserved_destination_events": [
            arena.completion_event,
            arena.lockcam_event,
            co_op_event,
        ],
        "destination_co_op_restore": {
            "event": co_op_event,
            "expected_sha256": co_op_hash,
        },
        "adapted_destination_events": [
            arena.activation_event,
            arena.health_bar_event,
            arena.music_event,
        ],
        "retired_destination_controllers": sorted(_retired(arena)),
        "copied_source_events": [
            {
                "source_event": source,
                "destination_event": target,
                "expected_source_sha256": SOURCE_HASHES[source],
            }
            for source, target in (
                (12604802, arena.health_bar_event),
                (12604806, allocation.support_setup_event),
                (12604810, allocation.core_command_event),
                (12604820, allocation.route_selector_event),
                (12604830, allocation.core_warp_event),
                (12604840, allocation.support_emergence_event),
            )
        ],
        "source_owned_not_copied": [
            12601800,
            12601802,
            12601803,
            12604803,
            12604804,
            12604815,
            2600803,
        ],
        "source_map_ambience_not_transplanted": {
            "event": 12604815,
            "source_sha256": SOURCE_HASHES[12604815],
            "sound": 260000003,
            "bank": "sprj_m26.fev",
            "policy": "destination_owned_environmental_audio",
        },
        "character_asset_evidence": {
            "archive_sha256": CHARACTER_ARCHIVE_SHA256,
            "tae_sha256": CHARACTER_TAE_SHA256,
            "observed_direct_effect_ids": [EMEVD_EFFECT, MISSING_TAE_EFFECT],
            "typed_tae_offsets": "unavailable",
            "character_delivery_status": "not-validated",
            "runtime_closure": "unproven",
        },
        "terminal_policy": "proxy death kills destination primary; unchanged destination terminal owns progression",
        "runtime_status": "unobserved",
    }


def patch_wet_nurse_donor(
    arena: ArenaContract,
    destination: str,
    donor_source: str,
    allocation: WetNurseDonorAllocation = DEFAULT_ALLOCATION,
) -> str:
    original, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(original, arena.expected, f"{arena.key} arena")
    _verify(donor, SOURCE_HASHES, "Wet Nurse donor")
    co_op_event, co_op_hash = DESTINATION_CO_OP[arena.key]
    if hashlib.sha256(original.get(co_op_event, "").encode()).hexdigest() != co_op_hash:
        raise ValueError(f"unsupported original {arena.key} co-op restore event")
    _validate(allocation, destination)
    notification = _notification_flag(original[arena.health_bar_event], allocation)
    mapping = _mapping(arena, allocation, notification)
    retired = _retired(arena)
    edits = {event: _noop(original[event]) for event in retired}
    activation = _activation_without_destination_animations(
        arena, original[arena.activation_event]
    )
    if notification == allocation.notification_flag:
        activation = _mark_existing_notification(activation, notification)
    edits.update(
        {
            0: _constructor(arena, original[0], donor[0], mapping, allocation),
            arena.activation_event: activation,
            arena.health_bar_event: _health(
                donor[12604802], original[arena.health_bar_event], mapping
            ),
            arena.music_event: _music(
                arena, original[arena.music_event], allocation.proxy_entity
            ),
        }
    )
    additions = [
        _remap(donor[12604806], mapping),
        _remap(donor[12604810], mapping),
        _remap(donor[12604820], mapping),
        _remap(donor[12604830], mapping),
        _remap(donor[12604840], mapping),
        _terminal_bridge(arena, allocation),
        _helper_cleanup(arena, allocation),
    ]
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions)
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(original) | set(allocation.event_ids()):
        raise ValueError("Wet Nurse donor changed unexpected event identities")
    for event_id, body in original.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Wet Nurse donor changed unrelated event {event_id}")
    for event_id in (arena.completion_event, arena.lockcam_event, co_op_event):
        if output[event_id] != original[event_id]:
            raise ValueError(
                f"Wet Nurse donor changed protected destination event {event_id}"
            )
    copied = "\n".join(output[event] for event in allocation.event_ids())
    if re.search(r"(?<!\d)(?:126|260)\d+(?!\d)", copied) or "2600803" in copied:
        raise ValueError("Wet Nurse donor retained a source-map combat literal")
    health = output[arena.health_bar_event]
    if not all(
        f"CreateReferredDamagePair({entity}, {allocation.proxy_entity})" in health
        for entity in (arena.actor, allocation.support_entity)
    ):
        raise ValueError("Wet Nurse donor lost its three-body health graph")
    return result


def _source_actor(slots: Sequence[Slot], entity: int) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.map_name == SOURCE_MAP
        and slot.entity_id == entity
        and slot.part_name == SOURCE_PARTS[entity]
        and slot.archetype == WET_ARCHETYPE
    ]
    if len(found) != 1 or found[0].dummy or found[0].talk_id:
        raise ValueError(f"Wet Nurse lacks exact source actor {entity}")
    return found[0]


def _native(source: Slot, *, anchored: bool = False) -> dict:
    provenance = {
        "format": "bb-boss-actor-pin-v1",
        "part_sha256": SOURCE_PART_PINS[source.entity_id],
    }
    if anchored:
        provenance["anchor_sha256"] = SOURCE_PART_PINS[CORE]
    return {
        "source_provenance": provenance,
        "source_initialization": dict(SOURCE_INITIALIZATION),
    }


def native_plan_wet_nurse_donor(
    arena: ArenaContract,
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    allocation: WetNurseDonorAllocation = DEFAULT_ALLOCATION,
) -> dict:
    _validate(allocation)
    destinations = sorted(
        [
            slot
            for slot in slots
            if slot.entity_id == arena.actor and slot.archetype == arena.archetype
        ],
        key=lambda slot: slot.map_name,
    )
    if len(destinations) != arena.destination_count:
        raise ValueError(f"Wet Nurse/{arena.key} lacks destination state closure")
    core = _source_actor(slots, CORE)
    support = _source_actor(slots, SUPPORT)
    proxy = _source_actor(slots, PROXY)
    swap = Swap(
        destinations[0].logical_key,
        [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations},
        destinations[0].archetype,
        WET_ARCHETYPE,
        destinations={
            slot.key: {
                "map_name": slot.map_name,
                "entity_id": slot.entity_id,
                "x": slot.x,
                "y": slot.y,
                "z": slot.z,
            }
            for slot in destinations
        },
    )
    changes, skips = plan_scaling(
        [swap], destinations, dict(npcs), dict(effects), boss_tiers=True
    )
    primary, additions, regions, objects, scaling = [], [], [], [], []
    for target in destinations:
        target_pin = DESTINATION_PART_PINS.get((target.map_name, target.entity_id))
        if target_pin is None:
            raise ValueError(f"Wet Nurse/{arena.key} lacks destination anchor pin")
        primary.append(
            {
                "source_map": core.map_name,
                "source_event_file": "event/" + EVENT_FILE,
                "source_part": core.part_name,
                "source_entity_id": core.entity_id,
                "source_archetype": asdict(core.archetype),
                "source_talk_id": core.talk_id,
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
                **_native(core),
            }
        )
        for source, entity, part in (
            (support, allocation.support_entity, "ap_wet_nurse_support"),
            (proxy, allocation.proxy_entity, "ap_wet_nurse_proxy"),
        ):
            additions.append(
                {
                    "source_map": source.map_name,
                    "source_event_file": "event/" + EVENT_FILE,
                    "source_part": source.part_name,
                    "source_anchor_part": core.part_name,
                    "source_entity_id": source.entity_id,
                    "source_archetype": asdict(source.archetype),
                    "source_part_kind": "enemy",
                    "destination_map": target.map_name,
                    "destination_anchor_part": target.part_name,
                    "destination_part": part,
                    "destination_entity_id": entity,
                    "allocation_evidence": "Wet Nurse reusable donor allocation v1; original corpus and project range scan",
                    "required_native_fields": [
                        "source_provenance",
                        "source_initialization",
                    ],
                    **_native(source, anchored=True),
                }
            )
            scaling.append(
                {
                    "destination_map": target.map_name,
                    "destination_part": part,
                    "parent_logical_key": swap.logical_key,
                    "source_npc_param_id": WET_ARCHETYPE.npc_param_id,
                    "strategy": "allocate_distinct_verified_helper_clone",
                }
            )
        for index, (source_entity, (source_name, fingerprint)) in enumerate(
            REGION_PINS.items()
        ):
            regions.append(
                {
                    "source_map": SOURCE_MAP,
                    "source_region": source_name,
                    "source_entity_id": source_entity,
                    "source_provenance": {
                        "format": "bb-boss-region-pin-v1",
                        "region_sha256": fingerprint,
                    },
                    "source_anchor_part": core.part_name,
                    "source_anchor_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": SOURCE_PART_PINS[CORE],
                    },
                    "destination_map": target.map_name,
                    "destination_region": f"ap_wet_nurse_warp_{index + 1}",
                    "destination_entity_id": allocation.warp_region_first_entity
                    + index,
                    "destination_anchor_part": target.part_name,
                    "destination_anchor_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": target_pin,
                    },
                }
            )
        objects.append(
            {
                "source_map": SOURCE_MAP,
                "source_part": "o269800_0000",
                "source_entity_id": MODEL_POINT_OBJECT,
                "source_provenance": {
                    "format": "bb-boss-object-pin-v1",
                    "part_sha256": OBJECT_PIN,
                },
                "source_anchor_part": core.part_name,
                "source_anchor_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": SOURCE_PART_PINS[CORE],
                },
                "destination_map": target.map_name,
                "destination_part": "ap_wet_nurse_model_point",
                "destination_entity_id": allocation.object_entity,
                "destination_anchor_part": target.part_name,
                "destination_anchor_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": target_pin,
                },
            }
        )
    destination_ffx, destination_ffx_hash = DESTINATION_FFX[arena.key]
    destination_event = arena.event_file.removesuffix(".js")
    contract = wet_nurse_donor_contract(arena, allocation)
    contract["helper_scaling_parent"] = {
        f"{row['destination_map']}:{row['destination_part']}": destinations[
            0
        ].logical_key
        for row in additions
    }
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"{arena.key}<-mergos-wet-nurse"},
        "boss_contract": contract,
        "primary_init_source_bindings": primary,
        "boss_actor_additions": additions,
        "boss_region_additions": regions,
        "boss_object_additions": objects,
        "boss_actor_scaling_requirements": scaling,
        "boss_emevd_ffx_requirements": [
            {
                "format": "bb-boss-emevd-ffx-requirement-v1",
                "source_map": SOURCE_MAP,
                "destination_map": destinations[0].map_name,
                "source_event_file": EVENT_FILE.removesuffix(".js"),
                "source_event_sha256": SOURCE_EVENT_SHA256,
                "source_event_id": 12604840,
                "destination_event_file": destination_event,
                "destination_event_id": allocation.support_emergence_event,
                "effect_id": EMEVD_EFFECT,
                "occurrence_count": 2,
            }
        ],
        "boss_ffx_merges": [
            {
                "source_file": SOURCE_FFX_FILE,
                "source_sha256": SOURCE_FFX_SHA256,
                "destination_file": destination_ffx,
                "destination_sha256": destination_ffx_hash,
                # This list exactly covers declared MSB/EMEVD dependencies.
                # The full source bank is still imported, including 655108;
                # typed character-root delivery is separate, unfinished work.
                "required_effect_ids": [EMEVD_EFFECT],
                "policy": "preserve_destination_union_source_v1",
            }
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


def portable_wet_nurse_arenas(
    arenas: Sequence[ArenaContract] = ARENAS,
) -> tuple[ArenaContract, ...]:
    return tuple(arena for arena in arenas if arena.phase_slots)
