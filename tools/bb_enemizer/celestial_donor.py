"""Reusable source-pinned Celestial Emissary combat donor for base arenas.

The donor retains the original eleven-body, eleven-region, seven-generator
combat graph.  The receiving arena owns entry geometry, music assets, camera
slot geometry, terminal, rewards, and progression.  Character-driven effect
delivery is recorded as a mandatory native integration boundary; this module
does not fabricate an EMEVD effect witness for TAE root 625700.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_prefix

from .boss_canary import event_blocks, parse_events
from .boss_contracts import ARENAS, ArenaContract
from . import celestial_paarl_contract as ce
from .maria_donor import _activation_without_destination_animations
from .model import Slot, Swap
from .scaling import plan_scaling
from .wet_nurse_donor import DESTINATION_PART_PINS

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m24_02_00_00.emevd.dcx.js"
SOURCE_STATES = ("m24_02_00_00", "m24_02_00_01")
PRIMARY = ce.SOURCE_PRIMARY
PRIMARY_ARCHETYPE = ce.PRIMARY_ARCHETYPE
SOURCE_INITIALIZATION = {
    "talk_id": 0,
    "unk_t18": -1,
    "init_anim_id": -1,
    "damage_anim_id": -1,
}
CO_OP_RESTORE = {
    "cleric-beast": 12411703,
    "blood-starved-beast": 12301803,
    "darkbeast-paarl": 12301703,
    "vicar-amelia": 12401804,
    "amygdala": 13301803,
    "ebrietas": 12421803,
}

CHARACTER_EFFECT_EVIDENCE = (
    {
        "model": "c2500",
        "archive_sha256": "362a1fab45839172a483dd25fbe8e4da12e0ff9883d757c6fe64047ab0301c08",
        "tae_sha256": "a255576656fb1e9223af885d1efa86b937a588f33010385fd25aa9e9a3c356bc",
        "decoded_event_types": [96, 100],
        "direct_effect_ids": [
            625000,
            625005,
            625010,
            625011,
            625015,
            1033000,
            1033002,
            1034001,
        ],
    },
    {
        "model": "c2570",
        "archive_sha256": "9ad62f44094ef550c9c219cbcfa70d648c111920fa57598044f7899a82f5a488",
        "tae_sha256": "8b1c49fb2444c82a3feacf2ac9aec1c5c32359667a8ce32fd2707d689cfe1797",
        "source_tae_entry_id": 3000000,
        "source_tae_entry": "chr/c2570/tae/c2570.tae",
        "source_animation_count": 126,
        "decoded_event_types": [96, 100, 118],
        "direct_effect_ids": [
            625190,
            625700,
            625705,
            625706,
            625710,
            625715,
            625716,
            625720,
            625721,
            650090,
            650091,
            1033000,
            1033002,
            1034001,
        ],
    },
    {
        "model": "c2571",
        "archive_sha256": "de2c083e39a61b3d68fcb6ffc46c954ea2ac48e9c8b108d723b6fea44ea0e42b",
        "tae_sha256": "d47c0bc7ac17fd4f65b5dea75237831325463766a2ec7f5c1b5ff9f893a1b111",
        "decoded_event_types": [96, 100],
        "direct_effect_ids": [],
    },
)
SOURCE_FFX_FILE = "frpg_sfxbnd_m24_02.ffxbnd.dcx"
SOURCE_FFX_SHA256 = "6cab7031c5fafba95ed71c4ddb86e590b77b2d669988e8b53bed159e1dbc1015"
REQUIRED_ROOT_SHA256 = "e62c82ede93c0b38ddb3509af309cc4ae5131eb4b113860e128f207ddab89f55"
ROOT_WITNESS_625700 = {
    "animation_id": 3000,
    "event_index": 3,
    "event_type": 96,
    "parameter_offset": 133600,
    "effect_id": 625700,
}
DESTINATION_SUBAREA_FFX = {
    "cleric-beast": (
        "frpg_sfxbnd_m24_01.ffxbnd.dcx",
        "8f918aa398655957eff8b12fc079dc9a1423d6f605bfadb25fcb35423f1154ee",
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
        "frpg_sfxbnd_m24_00.ffxbnd.dcx",
        "890086d51e303165812e005a9eb289435c067dec75369c90a338d0db2f1961a6",
    ),
    "amygdala": (
        "frpg_sfxbnd_m33.ffxbnd.dcx",
        "850e8354601f85e59166aaeceb0dea48018fd21afbad005f78b7732fc3889a29",
    ),
    "ebrietas": (SOURCE_FFX_FILE, SOURCE_FFX_SHA256),
}
CHARACTER_PROOF_FILE = Path(__file__).with_name("celestial_character_ffx.json")
CHARACTER_PROOF_SHA256 = "93055e11779c4a0b74c5674d254509e6421d0e377c5a5eb8c30c43c623b8b33a"
SOURCE_ONLY_LITERALS = {
    12421700,
    12421702,
    12421703,
    12424700,
    12424701,
    *(event for event in ce.SOURCE_HASHES if event),
    *(row[0] for row in ce.SOURCE_ACTORS),
    *(row[1] for row in ce.REGION_SPECS),
    *(row[2] for row in ce.GENERATOR_SPECS),
    *range(2800800, 2800804),
    2800810,
    2800811,
    2703802,
    2703803,
}


@dataclass(frozen=True)
class CelestialDonorAllocation:
    generator_cleanup: int = 12996600
    giant_command: int = 12996601
    giant_ai: int = 12996602
    giant_home: int = 12996603
    giant_phase: int = 12996604
    support_warp: int = 12996605
    support_phase: int = 12996606
    giant_choreography: int = 12996607
    terminal_bridge: int = 12996608
    wave_home: int = 12996609
    lifecycle_cleanup: int = 12996610
    notification_flag: int = 12996611
    helper_first: int = 984000
    region_first: int = 984010
    generator_first: int = 984021
    generator_event_first: int = 984028

    def event_ids(self) -> tuple[int, ...]:
        return (
            self.generator_cleanup,
            self.giant_command,
            self.giant_ai,
            self.giant_home,
            self.giant_phase,
            self.support_warp,
            self.support_phase,
            self.giant_choreography,
            self.terminal_bridge,
            self.wave_home,
            self.lifecycle_cleanup,
        )

    def helper_ids(self) -> tuple[int, ...]:
        return tuple(range(self.helper_first, self.helper_first + 10))

    def region_ids(self) -> tuple[int, ...]:
        return tuple(range(self.region_first, self.region_first + 11))

    def generator_ids(self) -> tuple[int, ...]:
        return tuple(range(self.generator_first, self.generator_first + 7))

    def generator_event_ids(self) -> tuple[int, ...]:
        return tuple(range(self.generator_event_first, self.generator_event_first + 7))

    def values(self) -> tuple[int, ...]:
        return (
            *self.event_ids(),
            self.notification_flag,
            *self.helper_ids(),
            *self.region_ids(),
            *self.generator_ids(),
            *self.generator_event_ids(),
        )


DEFAULT_ALLOCATION = CelestialDonorAllocation()


def _numbers(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values.update(_numbers(body.decode("utf-8-sig")))
    return frozenset(values)


@cache
def _character_proof() -> dict:
    raw = CHARACTER_PROOF_FILE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CHARACTER_PROOF_SHA256:
        raise ValueError("Celestial character FFX proof drift")
    proof = json.loads(raw)
    template = proof.get("requirement_template", {})
    bank = proof.get("bank", {})
    if (
        proof.get("format") != "bb-celestial-character-ffx-source-proof-v1"
        or template.get("format") != "bb-boss-character-ffx-requirement-v1"
        or template.get("source_character") != "c2570"
        or template.get("source_anibnd_sha256")
        != CHARACTER_EFFECT_EVIDENCE[1]["archive_sha256"]
        or template.get("source_tae_sha256")
        != CHARACTER_EFFECT_EVIDENCE[1]["tae_sha256"]
        or template.get("decoded_event_types") != [96, 100, 118]
        or template.get("source_animation_count") != 126
        or bank.get("source_file") != SOURCE_FFX_FILE
        or bank.get("source_sha256") != SOURCE_FFX_SHA256
        or bank.get("required_effect_id") != 625700
        or bank.get("required_effect_sha256") != REQUIRED_ROOT_SHA256
        or bank.get("selected_witness") != ROOT_WITNESS_625700
        or ROOT_WITNESS_625700 not in template.get("typed_event_witnesses", [])
        or 625700 not in template.get("direct_effect_ids", [])
    ):
        raise ValueError("Celestial character FFX proof is not the reviewed source proof")
    return proof


def _validate(allocation: CelestialDonorAllocation, destination: str = "") -> None:
    expected = (
        *range(12996600, 12996612),
        *range(984000, 984035),
    )
    if allocation.values() != expected:
        raise ValueError("Celestial donor requires the exact reviewed allocation")
    if len(set(expected)) != len(expected) or set(expected) & (
        _original_literals() | _numbers(destination)
    ):
        raise ValueError("Celestial donor allocation collides with original inputs")


def _verify(
    blocks: Mapping[int, str], expected: Mapping[int, str], role: str
) -> None:
    for event_id, digest in expected.items():
        if hashlib.sha256(blocks.get(event_id, "").encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Celestial donor expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, mapping: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(mapping.get(int(match[0]), int(match[0]))),
        text,
    )


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _noop(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            value.strip()
            if value.strip().startswith("unused_")
            else "unused_" + value.strip()
            for value in match[1].split(",")
            if value.strip()
        )
        + ")",
        declaration,
    )
    return declaration + "\n    EndEvent();\n});"


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


def _translation(
    arena: ArenaContract, allocation: CelestialDonorAllocation
) -> dict[int, int]:
    result = {
        2300810: arena.actor,
        12301700: arena.completion_event,
        12301702: arena.activation_event,
        12301703: CO_OP_RESTORE[arena.key],
        12304700: arena.start_flag,
        12304702: arena.health_bar_event,
        12304704: arena.lockcam_event,
        12992700: allocation.generator_cleanup,
        12992701: allocation.giant_command,
        12992702: allocation.giant_ai,
        12992703: allocation.giant_home,
        12992704: allocation.giant_phase,
        12992705: allocation.support_warp,
        12992706: allocation.support_phase,
        12992707: allocation.giant_choreography,
        12992708: allocation.terminal_bridge,
        12992709: allocation.wave_home,
        12992710: allocation.lifecycle_cleanup,
    }
    result.update(
        {980600 + index: entity for index, entity in enumerate(allocation.helper_ids())}
    )
    result.update(
        {980610 + index: entity for index, entity in enumerate(allocation.region_ids())}
    )
    result.update(
        {
            980621 + index: entity
            for index, entity in enumerate(allocation.generator_ids())
        }
    )
    result.update(
        {
            980628 + index: entity
            for index, entity in enumerate(allocation.generator_event_ids())
        }
    )
    return result


def _direct_mapping(
    arena: ArenaContract, allocation: CelestialDonorAllocation
) -> dict[int, int]:
    translation = _translation(arena, allocation)
    return {
        source: translation.get(intermediate, intermediate)
        for source, intermediate in ce._mapping(ce.DEFAULT_IDS).items()
    }


def _telemetry(source: str, destination: str) -> str:
    result = source
    for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
        source_lines = [
            line for line in source.splitlines() if line.strip().startswith(instruction + "(")
        ]
        destination_lines = [
            line
            for line in destination.splitlines()
            if line.strip().startswith(instruction + "(")
        ]
        if len(source_lines) != 1 or len(destination_lines) != 1:
            raise ValueError(f"Celestial telemetry lacks unique {instruction}")
        result = _replace_once(
            result, source_lines[0], destination_lines[0], "destination telemetry"
        )
    return result


def _notification_flag(
    destination_health: str, allocation: CelestialDonorAllocation
) -> int:
    match = re.search(
        r"if \(!EventFlag\((\d+)\)\) \{\n\s+IssueBossRoomEntryNotification\(0\);",
        destination_health,
    )
    return allocation.notification_flag if match is None else int(match[1])


def _mark_notification(block: str, flag: int) -> str:
    witness = "        IssueBossRoomEntryNotification(0);\n"
    count = block.count(witness)
    if count > 1:
        raise ValueError("destination entry notification witness is not unique")
    if count == 0:
        return block
    return block.replace(witness, witness + f"        SetEventFlag({flag}, ON);\n", 1)


def _source_activation_parts(source: str, mapping: Mapping[int, int]) -> tuple[str, str]:
    prelude_start = source.index("    ChangeCharacterEnableState(2420810, Disabled);")
    wait_start = source.index("    WaitFor(", prelude_start)
    wake_start = source.index("    SetEventFlag(12424700, ON);")
    prelude = _remap(source[prelude_start:wait_start], mapping).rstrip()
    wake = _remap(source[wake_start : source.rindex("});")], mapping).rstrip()
    return prelude, wake


def _activation(
    arena: ArenaContract,
    destination: str,
    donor_activation: str,
    mapping: Mapping[int, int],
    notification_flag: int,
    fallback_flag: int,
) -> str:
    result = _activation_without_destination_animations(arena, destination)
    prelude, wake = _source_activation_parts(donor_activation, mapping)
    result = _replace_once(result, "    WaitFor(", prelude + "\n    WaitFor(", "entry wait")
    progression = re.search(r"^    EndIf\(EventFlag\(93\d+\)\);", result, re.MULTILINE)
    if progression is None:
        raise ValueError(f"{arena.key} activation lacks discovery progression")
    result = result[: progression.start()] + wake + "\n" + result[progression.start() :]
    if notification_flag == fallback_flag:
        result = _mark_notification(result, notification_flag)
    return result


def _client_restore(
    destination: str, donor_restore: str, mapping: Mapping[int, int]
) -> str:
    wake_start = donor_restore.index("    ChangeCharacterEnableState(2420716, Enabled);")
    wake = _remap(donor_restore[wake_start : donor_restore.rindex("});")], mapping).rstrip()
    return _replace_once(destination, "});", wake + "\n});", "client restore tail")


def _health(
    arena: ArenaContract,
    donor_health: str,
    destination_health: str,
    allocation: CelestialDonorAllocation,
    notification_flag: int,
) -> str:
    intermediate = ce._health(donor_health, ce.DEFAULT_IDS)
    result = _remap(intermediate, _translation(arena, allocation))
    result = _replace_once(
        result,
        "            IssueBossRoomEntryNotification(0);",
        f"            if (!EventFlag({notification_flag})) {{\n"
        "                IssueBossRoomEntryNotification(0);\n"
        "            }\n"
        f"            SetEventFlag({notification_flag}, ON);",
        "notification ownership",
    )
    return _telemetry(result, destination_health)


def _music(
    arena: ArenaContract, destination: str, allocation: CelestialDonorAllocation
) -> str:
    replacement = f"EventFlag({allocation.giant_phase})"
    if arena.phase_music_message is not None:
        witness = f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})"
    else:
        event_flag = arena.phase_music_event_flag or arena.part_routine_event
        if event_flag is None:
            raise ValueError(f"{arena.key} has no declared music phase boundary")
        witness = f"EventFlag({event_flag})"
    return _replace_once(destination, witness, replacement, "destination music phase")


def _camera(
    arena: ArenaContract,
    donor_camera: str,
    allocation: CelestialDonorAllocation,
) -> str:
    intermediate = ce._camera(donor_camera, ce.DEFAULT_IDS)
    result = _remap(intermediate, _translation(arena, allocation))
    return result.replace(
        "SetLockcamSlotNumber(23, 0,",
        f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},",
    )


def _constructor(
    arena: ArenaContract,
    destination: str,
    donor_zero: str,
    mapping: Mapping[int, int],
    allocation: CelestialDonorAllocation,
) -> str:
    transplant = (
        (allocation.generator_cleanup, 12424770, 8),
        (allocation.giant_command, 12424780, 1),
        (allocation.giant_ai, 12424784, 1),
        (allocation.giant_home, 12424785, 2),
        (allocation.wave_home, 12424787, 2),
        (allocation.giant_phase, 12424790, 1),
        (allocation.support_warp, 12424791, 1),
        (allocation.support_phase, 12424792, 2),
        (allocation.giant_choreography, 12424795, 1),
    )
    calls = [
        _remap(line, mapping)
        for destination_event, source_event, count in transplant
        for line in ce._calls(donor_zero, source_event, destination_event, count)
    ]
    always_update = (
        "    SetNetworkUpdateRate(2420811, true, "
        "CharacterUpdateFrequency.AlwaysUpdate);"
    )
    if donor_zero.count(always_update) != 1:
        raise ValueError("Celestial donor lacks exact giant AlwaysUpdate witness")
    calls.extend(
        (
            f"    $InitializeEvent(0, {allocation.terminal_bridge});",
            f"    $InitializeEvent(0, {allocation.lifecycle_cleanup});",
            _remap(always_update, mapping),
        )
    )
    anchors = [
        f"    $InitializeEvent(0, {event});"
        for event in reversed(arena.phase_slots)
        if destination.count(f"    $InitializeEvent(0, {event});") == 1
    ]
    if not anchors:
        raise ValueError(f"{arena.key} lacks a constructor anchor")
    return _replace_once(
        destination, anchors[0], anchors[0] + "\n" + "\n".join(calls), "constructor anchor"
    )


def _bridge(arena: ArenaContract, allocation: CelestialDonorAllocation) -> str:
    giant = allocation.helper_ids()[0]
    supports = allocation.helper_ids()[-2:]
    return f"""$Event({allocation.terminal_bridge}, Default, function() {{
    EndIf(EventFlag({arena.completion_event}));
    WaitFor(CharacterDead({giant}));
    EndIf(EventFlag({arena.completion_event}));
    ChangeCharacterEnableState({supports[0]}, Disabled);
    ChangeCharacterEnableState({supports[1]}, Disabled);
    SetCharacterImmortality({arena.actor}, Disabled);
    ForceCharacterDeath({arena.actor}, false);
    WaitFor(EventFlag({arena.completion_event}));
}});"""


def _cleanup(arena: ArenaContract, allocation: CelestialDonorAllocation) -> str:
    generators = "".join(
        f"    DeactivateGenerator({entity}, Disabled);\n"
        for entity in allocation.generator_ids()
    )
    actors = "".join(
        f"    SetCharacterImmortality({entity}, Disabled);\n"
        f"    SetCharacterAIState({entity}, Disabled);\n"
        f"    SetCharacterHPBarDisplay({entity}, Disabled);\n"
        f"    ChangeCharacterEnableState({entity}, Disabled);\n"
        f"    ForceCharacterDeath({entity}, false);\n"
        for entity in allocation.helper_ids()
    )
    return f"""$Event({allocation.lifecycle_cleanup}, Default, function() {{
    WaitFor(EventFlag({arena.completion_event}));
{generators}{actors}}});"""


def _asset_policy(arena: ArenaContract) -> dict:
    destination_file, destination_hash = DESTINATION_SUBAREA_FFX[arena.key]
    # Existing destination-bank names are retained only as destination
    # evidence.  The source is the independently pinned m24_02 subarea bank,
    # not the broad m24 filename used by older area-union manifests.
    same_bank = arena.key == "ebrietas"
    return {
        "format": "bb-character-effect-delivery-v1",
        "source_proof_file": CHARACTER_PROOF_FILE.name,
        "source_proof_sha256": CHARACTER_PROOF_SHA256,
        "source_file": SOURCE_FFX_FILE,
        "source_sha256": SOURCE_FFX_SHA256,
        "destination_file": destination_file,
        "destination_sha256": destination_hash,
        "required_tae_root": 625700,
        "required_root_sha256": REQUIRED_ROOT_SHA256,
        "root_witness_kind": "typed-character-tae-96-100-118-partial",
        "selected_root_witness": ROOT_WITNESS_625700,
        "same_bank_already_available": same_bank,
        "status": (
            "source-bank-already-present"
            if same_bank
            else "native-typed-witness-union-declared"
        ),
        "strict_refusal": not same_bank,
        "known_conflict": None,
        "original_index_audit": (
            "m24_02 contains 159 entries and has zero byte-different overlaps with "
            "the audited m23 and m33 banks; old f000651217 conflict was a wrong "
            "broad-bank inference"
        ),
        "emevd_witness_fabricated": False,
    }


def celestial_donor_contract(
    arena: ArenaContract,
    allocation: CelestialDonorAllocation = DEFAULT_ALLOCATION,
) -> dict:
    _validate(allocation)
    return {
        "format": "bb-celestial-donor-contract-v1",
        "status": "experimental",
        "arena": arena.key,
        "donor": "celestial-emissary",
        "allocation": asdict(allocation),
        "source_hash_pins": dict(ce.SOURCE_HASHES),
        "preserved_destination_events": [arena.completion_event],
        "adapted_destination_events": [
            arena.activation_event,
            CO_OP_RESTORE[arena.key],
            arena.health_bar_event,
            arena.music_event,
            arena.lockcam_event,
        ],
        "retired_destination_controllers": sorted(_retired(arena)),
        "source_roster": {
            "primary": PRIMARY,
            "helpers": [row[0] for row in ce.SOURCE_ACTORS],
            "regions": [row[1] for row in ce.REGION_SPECS],
            "generators": [row[2] for row in ce.GENERATOR_SPECS],
        },
        "foreign_literal_policy": {
            "literals": list(range(2800800, 2800804)) + [2800810, 2800811],
            "action": "replace with source primary/giant; materialize no foreign actors",
        },
        "character_effect_evidence": CHARACTER_EFFECT_EVIDENCE,
        "asset_delivery": _asset_policy(arena),
        "terminal_policy": "giant death bridges to real destination primary; destination progression remains exact",
        "geometry_risk": "anchor-relative source regions and generator floor fit are runtime-unobserved",
        "runtime_status": "unobserved",
    }


def patch_celestial_donor(
    arena: ArenaContract,
    destination: str,
    donor_source: str,
    allocation: CelestialDonorAllocation = DEFAULT_ALLOCATION,
) -> str:
    original, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(original, arena.expected, f"{arena.key} arena")
    _verify(donor, ce.SOURCE_HASHES, "Celestial donor")
    _validate(allocation, destination)
    notification = _notification_flag(original[arena.health_bar_event], allocation)
    mapping = _direct_mapping(arena, allocation)
    retired = _retired(arena)
    edits = {event: _noop(original[event]) for event in retired}
    edits.update(
        {
            0: _constructor(arena, original[0], donor[0], mapping, allocation),
            arena.activation_event: _activation(
                arena,
                original[arena.activation_event],
                donor[12421702],
                mapping,
                notification,
                allocation.notification_flag,
            ),
            CO_OP_RESTORE[arena.key]: _client_restore(
                original[CO_OP_RESTORE[arena.key]], donor[12421703], mapping
            ),
            arena.health_bar_event: _health(
                arena,
                donor[12424702],
                original[arena.health_bar_event],
                allocation,
                notification,
            ),
            arena.music_event: _music(
                arena, original[arena.music_event], allocation
            ),
            arena.lockcam_event: _camera(arena, donor[12424704], allocation),
        }
    )
    source_events = (
        12424770,
        12424780,
        12424784,
        12424785,
        12424790,
        12424791,
        12424792,
        12424795,
        12424787,
    )
    additions = [
        _remap(donor[source], mapping) for source in source_events
    ]
    # Source events remap to their project IDs; bridge and cleanup are authored.
    additions.extend((_bridge(arena, allocation), _cleanup(arena, allocation)))
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions)
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(original) | set(allocation.event_ids()):
        raise ValueError("Celestial donor changed unexpected event identities")
    for event_id, body in original.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Celestial donor changed unrelated event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("Celestial donor changed destination progression")
    copied = "\n".join(
        output[event]
        for event in (
            arena.activation_event,
            CO_OP_RESTORE[arena.key],
            arena.health_bar_event,
            arena.lockcam_event,
            *allocation.event_ids(),
        )
    )
    if _numbers(copied) & SOURCE_ONLY_LITERALS:
        raise ValueError("Celestial donor copied combat retains a source-map literal")
    return result


def _source_state(destination_map: str) -> str:
    return SOURCE_STATES[1] if destination_map.endswith("_01") else SOURCE_STATES[0]


def _require(
    slots: Sequence[Slot], entity: int, archetype, map_name: str, part: str
) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.map_name == map_name
        and slot.entity_id == entity
        and slot.archetype == archetype
        and slot.part_name == part
    ]
    if len(found) != 1 or found[0].dummy or found[0].talk_id:
        raise ValueError(f"Celestial donor lacks exact source actor {entity} in {map_name}")
    return found[0]


def _pin(part_sha256: str, anchor_sha256: str | None = None) -> dict:
    result = {"format": "bb-boss-actor-pin-v1", "part_sha256": part_sha256}
    if anchor_sha256 is not None:
        result["anchor_sha256"] = anchor_sha256
    return result


def _character_ffx_plan(
    additions: Sequence[dict], arena: ArenaContract
) -> dict[str, list[dict]]:
    proof = _character_proof()
    template = proof["requirement_template"]
    giants = [
        row for row in additions if row["source_archetype"]["model_name"] == "c2570"
    ]
    if len(giants) != arena.destination_count:
        raise ValueError(f"Celestial/{arena.key} lacks one giant per destination state")

    requirements = []
    seen_sources: set[tuple[str, str, int]] = set()
    for row in giants:
        identity = (row["source_map"], row["source_part"], row["source_entity_id"])
        if identity in seen_sources:
            continue
        seen_sources.add(identity)
        requirement = copy.deepcopy(template)
        requirement.update(
            source_map=row["source_map"],
            source_part=row["source_part"],
            source_entity_id=row["source_entity_id"],
        )
        requirements.append(requirement)

    destination_file, destination_sha256 = DESTINATION_SUBAREA_FFX[arena.key]
    result = {"boss_character_ffx_requirements": requirements}
    if destination_file == SOURCE_FFX_FILE:
        return result

    result["boss_character_ffx_bank_requirements"] = [
        {
            "format": "bb-boss-character-ffx-bank-requirement-v1",
            "source_map": row["source_map"],
            "source_part": row["source_part"],
            "source_entity_id": row["source_entity_id"],
            "source_character": "c2570",
            "destination_map": row["destination_map"],
            "destination_part": row["destination_part"],
            "destination_entity_id": row["destination_entity_id"],
            "source_ffx_file": SOURCE_FFX_FILE,
            "destination_ffx_file": destination_file,
            "roots": [
                {
                    "source_tae_entry_id": template["source_tae_entry_id"],
                    "witness": dict(ROOT_WITNESS_625700),
                }
            ],
        }
        for row in giants
    ]
    result["boss_ffx_merges"] = [
        {
            "source_file": SOURCE_FFX_FILE,
            "source_sha256": SOURCE_FFX_SHA256,
            "destination_file": destination_file,
            "destination_sha256": destination_sha256,
            "required_effect_ids": [625700],
            "policy": "preserve_destination_union_source_v1",
        }
    ]
    return result


def native_plan_celestial_donor(
    arena: ArenaContract,
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    allocation: CelestialDonorAllocation = DEFAULT_ALLOCATION,
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
        raise ValueError(f"Celestial/{arena.key} lacks destination state closure")
    sources = {
        state: _require(slots, PRIMARY, PRIMARY_ARCHETYPE, state, "c2500_0000")
        for state in SOURCE_STATES
    }
    helpers = {
        state: {
            entity: _require(slots, entity, archetype, state, part)
            for entity, part, _, _, archetype in ce.SOURCE_ACTORS
        }
        for state in SOURCE_STATES
    }
    swap = Swap(
        destinations[0].logical_key,
        [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations},
        destinations[0].archetype,
        PRIMARY_ARCHETYPE,
        warnings=[
            "runtime generated-wave geometry and typed character-effect delivery require validation"
        ],
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
    bindings, additions, regions, generators, scaling = [], [], [], [], []
    for target in destinations:
        state = _source_state(target.map_name)
        source = sources[state]
        target_pin = DESTINATION_PART_PINS.get((target.map_name, target.entity_id))
        if target_pin is None:
            raise ValueError(f"Celestial/{arena.key} lacks destination anchor pin")
        bindings.append(
            {
                "source_map": state,
                "source_event_file": "event/" + EVENT_FILE,
                "source_part": source.part_name,
                "source_entity_id": source.entity_id,
                "source_archetype": asdict(source.archetype),
                "source_talk_id": source.talk_id,
                "source_provenance": _pin(ce.ACTOR_PINS[state][0]),
                "source_initialization": dict(SOURCE_INITIALIZATION),
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
        )
        for index, (source_entity, source_part, _, destination_part, archetype) in enumerate(
            ce.SOURCE_ACTORS, 1
        ):
            helper = helpers[state][source_entity]
            row = {
                "source_map": state,
                "source_event_file": "event/" + EVENT_FILE,
                "source_part": helper.part_name,
                "source_anchor_part": source.part_name,
                "source_entity_id": source_entity,
                "source_archetype": asdict(archetype),
                "source_part_kind": "enemy",
                "source_provenance": _pin(
                    ce.ACTOR_PINS[state][index], ce.ACTOR_PINS[state][0]
                ),
                "source_initialization": dict(SOURCE_INITIALIZATION),
                "destination_map": target.map_name,
                "destination_anchor_part": target.part_name,
                "destination_part": destination_part,
                "destination_entity_id": allocation.helper_ids()[index - 1],
                "allocation_evidence": "Celestial reusable donor allocation v1; full original/project scan",
                "required_native_fields": [
                    "source_provenance",
                    "source_initialization",
                ],
            }
            additions.append(row)
            scaling.append(
                {
                    "destination_map": target.map_name,
                    "destination_part": destination_part,
                    "parent_logical_key": swap.logical_key,
                    "source_npc_param_id": archetype.npc_param_id,
                    "strategy": "allocate_distinct_verified_helper_clone",
                }
            )
        for index, (source_region, source_entity, destination_region) in enumerate(
            ce.REGION_SPECS
        ):
            regions.append(
                {
                    "source_map": state,
                    "source_region": source_region,
                    "source_entity_id": source_entity,
                    "source_provenance": {
                        "format": "bb-boss-region-pin-v1",
                        "region_sha256": ce.REGION_PINS[state][index],
                    },
                    "source_anchor_part": source.part_name,
                    "source_anchor_provenance": _pin(ce.ACTOR_PINS[state][0]),
                    "destination_map": target.map_name,
                    "destination_region": destination_region,
                    "destination_entity_id": allocation.region_ids()[index],
                    "destination_anchor_part": target.part_name,
                    "destination_anchor_provenance": _pin(target_pin),
                }
            )
        for index, (name, source_event, entity, source_part) in enumerate(
            ce.GENERATOR_SPECS
        ):
            generators.append(
                {
                    "source_map": state,
                    "source_event": name,
                    "source_event_id": source_event,
                    "source_entity_id": entity,
                    "source_fingerprint": ce.GENERATOR_PINS[state][index],
                    "destination_map": target.map_name,
                    "destination_event": f"ap_ce_generator_{index + 1}",
                    "destination_event_id": allocation.generator_event_ids()[index],
                    "destination_entity_id": allocation.generator_ids()[index],
                    "destination_part_name": None,
                    "destination_region_name": None,
                    "spawn_part_map": {source_part: ce.SOURCE_ACTORS[index + 1][3]},
                    "spawn_point_map": {name: ce.REGION_SPECS[index][2]},
                }
            )
    character_ffx = _character_ffx_plan(additions, arena)
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"{arena.key}<-celestial-emissary"},
        "boss_contract": celestial_donor_contract(arena, allocation),
        "primary_init_source_bindings": bindings,
        "boss_actor_additions": additions,
        "boss_region_additions": regions,
        "boss_generator_additions": generators,
        "boss_actor_scaling_requirements": scaling,
        **character_ffx,
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }


def portable_celestial_arenas(
    arenas: Sequence[ArenaContract] = ARENAS,
) -> tuple[ArenaContract, ...]:
    return tuple(arena for arena in arenas if arena.phase_slots)
