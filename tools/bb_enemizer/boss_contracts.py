"""Typed encounter contracts for independent boss donors and arenas.

The contract data is derived from the original EMEVD text in the committed
input bundle.  It does not infer a generic numeric map-prefix substitution:
every literal that moves from a donor into an arena is declared as an actor,
completion flag, encounter-start flag, event slot, or initializer binding.
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import asdict, dataclass
from typing import Iterable

from . import boss_canary
from .model import Archetype, Swap
from .scaling import plan_scaling

EventBlocks = dict[int, str]


def event_blocks(text: str) -> EventBlocks:
    return boss_canary.event_blocks(text)


@dataclass(frozen=True)
class PartBinding:
    """One explicit Event(0) initializer slot and its arguments."""

    slot: int
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class EventAttachment:
    """A hash-pinned donor routine copied into a project-owned event ID.

    ``initializers`` are witnessed verbatim in the donor's Event(0).  Target
    IDs are declared by the receiving arena, rather than derived from a map
    prefix, then checked against every original numeric literal before use.
    """

    source_event: int
    initializers: tuple[PartBinding, ...]


@dataclass(frozen=True)
class VirtualEntityBinding:
    """A combat identity initialized by a witnessed Event(0) call.

    Some source IDs are only event-side owners; others name a real MSB actor.
    The latter must be materialized by the native actor-addition path before
    this EMEVD mapping is eligible for a registered encounter contract.
    """

    source_entity: int
    initializer: str
    requires_actor_addition: bool = False
    source_part: str | None = None
    source_anchor_part: str | None = None
    source_archetype: Archetype | None = None
    destination_part: str | None = None
    allocation_evidence: str | None = None
    # Explicit destination-state -> source-state selections.  A donor with
    # fewer map variants may use a reviewed canonical source, but the choice
    # must never be inferred from matching numeric suffixes.
    source_state_bindings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ArenaContract:
    key: str
    event_file: str
    map_prefix: str
    actor: int
    archetype: Archetype
    destination_count: int
    completion_event: int
    start_flag: int
    health_bar_event: int
    health_bar_label: int
    activation_event: int
    music_event: int
    phase_music_message: int | None
    lockcam_event: int
    lockcam_map: int
    lockcam_subarea: int
    phase_slots: tuple[int, ...]
    co_op_entry_event: int
    part_routine_event: int
    cloth_routine_event: int | None
    part_slots: tuple[PartBinding, ...]
    attachment_event_ids: tuple[int, ...]
    virtual_entity_ids: tuple[int, ...]
    attachment_anchor_slot: int | None
    attachment_anchor_event: int | None
    expected: dict[int, str]
    # The original arena's simple post-entry animation operand.  Complex
    # set-pieces have their own source-backed activation adapter.
    activation_idle_animation: int | None = None
    # BSB's native music body gates phase two on an event flag, while the
    # other arenas use CharacterHasEventMessage.  The literal is pinned in
    # ``expected``; this field says which witnessed destination operand the
    # reusable adapter may replace.
    phase_music_event_flag: int | None = None


@dataclass(frozen=True)
class CombatPackage:
    key: str
    event_file: str
    map_prefix: str
    actor: int
    archetype: Archetype
    completion_event: int
    start_flag: int
    activation_event: int
    health_bar_event: int
    health_bar_label: int
    phase_events: tuple[int, ...]
    co_op_entry_event: int | None
    lockcam_event: int | None
    phase_music_message: int | None
    part_routine_event: int | None
    part_bindings: tuple[PartBinding, ...]
    attachments: tuple[EventAttachment, ...]
    virtual_entities: tuple[VirtualEntityBinding, ...]
    entry_animation: int | None
    lockcam_map: int | None
    lockcam_subarea: int | None
    expected: dict[int, str]
    legacy_canary: bool = False
    # A package with a simple witnessed 7001 replacement can use the generic
    # activation adapter.  Complex donor wake-up sequences remain unavailable
    # until their complete source-backed adapter is represented here.
    generic_activation: bool = False
    # Explicit destination-state -> source-state selections for full primary
    # initialization copying.  The native writer pins and transfers TalkID,
    # UnkT18, InitAnimID, and DamageAnimID from this source Part.
    primary_state_bindings: tuple[tuple[str, str], ...] = ()


CLERIC_ARENA = ArenaContract(
    key="cleric-beast",
    event_file="m24_01_00_00.emevd.dcx.js",
    map_prefix="m24_01_",
    actor=2410800,
    archetype=Archetype("c5000", 500241, 500241, 0),
    destination_count=3,
    completion_event=12411700,
    start_flag=12414700,
    health_bar_event=12414702,
    health_bar_label=500000,
    activation_event=12411702,
    music_event=12414703,
    phase_music_message=100,
    lockcam_event=12414704,
    lockcam_map=24,
    lockcam_subarea=1,
    phase_slots=(12414707, 12414708),
    co_op_entry_event=12414708,
    part_routine_event=12414710,
    cloth_routine_event=12414720,
    part_slots=(
        PartBinding(0, ("2410", "2410", "NPCPartType.Part1", "20", "480", "490", "8020")),
        PartBinding(1, ("2411", "2411", "NPCPartType.Part2", "120", "481", "491", "8000")),
        PartBinding(2, ("2412", "2412", "NPCPartType.Part3", "300", "482", "492", "8010")),
        PartBinding(3, ("2413", "2413", "NPCPartType.Part4", "200", "483", "493", "8030")),
        PartBinding(4, ("2414", "2414", "NPCPartType.Part5", "200", "484", "494", "8040")),
    ),
    # 12994800--04 are project-owned append-only attachment IDs.  The
    # full-corpus witness lives with ContractCapabilityMatrixTests.
    attachment_event_ids=(12994800, 12994801, 12994802, 12994803, 12994804),
    # Ebrietas's c9010 bullet owner has no existing Cleric slot.  This
    # project-owned ID is checked against the original corpus and native
    # writer collision checks before it becomes an MSB addition.
    virtual_entity_ids=(982400,),
    attachment_anchor_slot=None,
    attachment_anchor_event=None,
    expected={
        0: "329450dd4b8ae967cdaf56f5ab65556bb0a453e8f8374d79328848dff72cf89c",
        **{key: value for key, value in boss_canary.EXPECTED.items() if key >= 12400000},
    },
    activation_idle_animation=3028,
)

BSB_ARENA = ArenaContract(
    key="blood-starved-beast",
    event_file="m23_00_00_00.emevd.dcx.js",
    map_prefix="m23_00_",
    actor=2300800,
    archetype=Archetype("c2090", 209000, 209000, 0),
    destination_count=2,
    completion_event=12301800,
    start_flag=12304800,
    health_bar_event=12304802,
    health_bar_label=209000,
    activation_event=12301802,
    music_event=12304803,
    phase_music_message=None,
    lockcam_event=12304804,
    lockcam_map=23,
    lockcam_subarea=0,
    phase_slots=(12304807,),
    co_op_entry_event=12301803,
    part_routine_event=12304808,
    cloth_routine_event=None,
    # The one former BSB phase initializer becomes the five explicit Paarl
    # limb initializers when its combat package is selected.
    part_slots=(PartBinding(0, ()),),
    # Project-owned, reviewed IDs for an attached full Cleric package.  These
    # are not inferred from the map prefix and are collision-scanned first.
    attachment_event_ids=(12304907, 12304908, 12304910, 12304920, 12304930),
    virtual_entity_ids=(2300890,),
    attachment_anchor_slot=0,
    attachment_anchor_event=12304808,
    expected={
        0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
        12301800: "e9eed714540eab5058a6553eb5b11b28f2edcb6d4236679efaafafb9c4e8f1a4",
        12301802: "c8e1b3b8b94fe800a158228a1b177c944c90883fc45826b5060488a064ca145d",
        12301803: "62fb078e77c476dc5d9d3631843895197d9974e67a15880b5ca133dd870f299c",
        12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
        12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
        12304804: "86edb06de9efdc94365fb640741ce4d62620363a3c37ebb99d37ef2b9d3f3521",
        12304807: "7e9c22292f41da758876cceffe70b61ad51cf0f86e7b5e250e3c8514f179d780",
        12304808: "8ccea02a7829f43788cf77ec24ea5b524643f9ab6d55681f492f1afa588e31f5",
    },
    phase_music_event_flag=12304808,
    activation_idle_animation=7001,
)

PAARL_ARENA = ArenaContract(
    key="darkbeast-paarl",
    event_file="m23_00_00_00.emevd.dcx.js",
    map_prefix="m23_00_",
    actor=2300810,
    archetype=Archetype("c5080", 508000, 508000, 0),
    destination_count=2,
    completion_event=12301700,
    start_flag=12304700,
    health_bar_event=12304702,
    health_bar_label=508000,
    activation_event=12301702,
    music_event=12304703,
    phase_music_message=20,
    lockcam_event=12304704,
    lockcam_map=23,
    lockcam_subarea=0,
    phase_slots=(12304707, 12304715),
    co_op_entry_event=12301703,
    part_routine_event=12304715,
    cloth_routine_event=None,
    part_slots=(
        PartBinding(0, ("2300", "2300", "NPCPartType.Part1", "480", "490", "8000", "130")),
        PartBinding(1, ("2301", "2301", "NPCPartType.Part2", "481", "491", "8010", "150")),
        PartBinding(2, ("2302", "2302", "NPCPartType.Part3", "482", "492", "8030", "150")),
        PartBinding(3, ("2303", "2303", "NPCPartType.Part4", "483", "493", "8020", "200")),
        PartBinding(4, ("2304", "2304", "NPCPartType.Part5", "484", "494", "8040", "200")),
    ),
    attachment_event_ids=(12304917, 12304918, 12304919, 12304921, 12304922),
    virtual_entity_ids=(2300891,),
    attachment_anchor_slot=0,
    attachment_anchor_event=12304707,
    expected={
        0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
        12301700: "3d8feaac026a84d0e378ba5599fa4e3b60ca424d59a88776434a2e8be0c77d3e",
        12301702: "374db59c960671a66ac7afdd712cc0576d03a554ec7ca3d74f0902799bfd517d",
        12301703: "ca968c9f60d2a495e9f3c87c77083ec5d1524b34792d646aa29a239f7f11b653",
        12304702: "cb57ca1efd9f78db3f35500a83581b90e3101e0d13446d398715faad7383c220",
        12304703: "e425e391e28c7dae502e70533be953a18976657b4ab3f5ba328bf4304840e825",
        12304704: "fc0d014681e349fa969f5746f3ac690ad606d48e1f1c828288547efab3dcd3b7",
        12304707: "c88383d5ab10974eaa968e06dbbd9f92e6d0ca05ae02fe38650490a24445cf3b",
        12304715: "015e8810e6bdab08aa66827c290b554890e0c45be100efe95fcf6730a00ee74e",
    },
    activation_idle_animation=7001,
)

AMELIA_ARENA = ArenaContract(
    key="vicar-amelia",
    event_file="m24_00_00_00.emevd.dcx.js",
    map_prefix="m24_00_",
    actor=2400800,
    archetype=Archetype("c5020", 502000, 502000, 0),
    destination_count=2,
    completion_event=12401800,
    start_flag=12404800,
    health_bar_event=12404802,
    health_bar_label=502000,
    activation_event=12401802,
    music_event=12404803,
    phase_music_message=100,
    lockcam_event=12404804,
    lockcam_map=24,
    lockcam_subarea=0,
    phase_slots=(12404807, 12404808),
    co_op_entry_event=12401804,
    part_routine_event=12404810,
    cloth_routine_event=12404820,
    part_slots=(
        PartBinding(0, ("2400", "2400", "NPCPartType.Part1", "80", "480", "490", "8020")),
        PartBinding(1, ("2401", "2401", "NPCPartType.Part2", "150", "481", "491", "8000")),
        PartBinding(2, ("2402", "2402", "NPCPartType.Part3", "150", "482", "492", "8010")),
        PartBinding(3, ("2403", "2403", "NPCPartType.Part4", "200", "483", "493", "8030")),
        PartBinding(4, ("2404", "2404", "NPCPartType.Part5", "200", "484", "494", "8040")),
    ),
    # Event 12404830 is Amelia's separate self-heal choreographer.  It is a
    # unique Event(0) call and is replaced by declared attached initializers.
    attachment_event_ids=(12404907, 12404908, 12404910, 12404920, 12404930),
    virtual_entity_ids=(2400890,),
    attachment_anchor_slot=0,
    attachment_anchor_event=12404830,
    expected={
        0: "31936ed53ff8d095dcae5257c6d36e321a55bc8cd53ed564a1510363a9a04e27",
        12401800: "98ed01dba0556def27d9679e35114473d9464026a03f45115cb25ed8f02d85ce",
        12401802: "b869911c8ee05015b1b90d6fcac40ae0f492433ce83f0f2629e4973cdfbbcde0",
        12404802: "d9c5e8ef9feaa1758a8ee08e21a8da089b96f5bb7e17a740f8d34770b7c9ea31",
        12404803: "13b0d9be89ea9bd0e8d385c24275a42bb9b6e97891b4caa9e1ee639bd3d09700",
        12404804: "77adf8b72d36b425788c96b1bd697a193a8b81408ccc8e14c071687427f92621",
        12404807: "c1963c0461fe87ebd3a432bc41eaaeebcea3aa82ca86526d4e51da3619714279",
        12404808: "8a8be8efea5f76c0d44a669ddbafc86f1e59b7bdd5ebac85a556619ba3c236ed",
        12404810: "30b2c3b6e19b220396f325beaed9873285c58304d54a2ec2c939477dd1f84830",
        12404820: "dfe2dd42c30b7686b972b2a20eed997ee00660d7592bf1fe7a91ad0602d76b19",
        12404830: "b92005d1b304b616a48dc9f877601a8d024362e8745ffa34282f3c92257e7c9d",
    },
    activation_idle_animation=7001,
)

AMYGDALA_ARENA = ArenaContract(
    key="amygdala",
    event_file="m33_00_00_00.emevd.dcx.js",
    map_prefix="m33_00_",
    actor=3300800,
    archetype=Archetype("c5120", 512000, 512000, 0),
    destination_count=1,
    completion_event=13301800,
    start_flag=13304800,
    health_bar_event=13304802,
    health_bar_label=512000,
    activation_event=13301802,
    music_event=13304803,
    phase_music_message=10,
    lockcam_event=13304804,
    lockcam_map=33,
    lockcam_subarea=0,
    phase_slots=(13304807, 13304808),
    co_op_entry_event=13301803,
    part_routine_event=13304830,
    # This is the native hitmask initializer, not a cosmetic cloth routine.
    cloth_routine_event=13304820,
    part_slots=(
        PartBinding(0, ("3301", "3301", "NPCPartType.Part4", "482", "200", "8020", "1", "1.5")),
        PartBinding(1, ("3302", "3302", "NPCPartType.Part6", "482", "180", "8020", "1", "1.5")),
        PartBinding(2, ("3303", "3303", "NPCPartType.Part8", "482", "150", "8020", "1", "1.5")),
        PartBinding(3, ("3304", "3304", "NPCPartType.Part5", "481", "200", "8010", "1", "1.5")),
        PartBinding(4, ("3305", "3305", "NPCPartType.Part7", "481", "150", "8010", "1", "1.5")),
        PartBinding(5, ("3306", "3306", "NPCPartType.Part9", "481", "120", "8010", "1", "1.5")),
        PartBinding(6, ("3307", "3307", "NPCPartType.Part10", "481", "120", "8010", "1", "1.5")),
        PartBinding(7, ("3308", "3308", "NPCPartType.Part3", "483", "200", "8030", "0.2", "0.3")),
        PartBinding(8, ("3309", "3309", "NPCPartType.Part11", "484", "100", "8040", "0.2", "0.3")),
        PartBinding(9, ("3310", "3310", "NPCPartType.Part12", "483", "100", "8030", "0.2", "0.3")),
    ),
    attachment_event_ids=(13304907, 13304908, 13304920, 13304930, 13304940),
    virtual_entity_ids=(3300890,),
    attachment_anchor_slot=0,
    attachment_anchor_event=13304840,
    expected={
        0: "b86f288c46fc74ddc81530e62437d9497c5a63ec09488c068211d85f4054f934",
        13301800: "d719f46bbaf08f19beebee00dc39b9ee16443c6614faa9689bb9abb6230f0871",
        13301802: "dbf7c452ecf425a41d9c724ba0568db015224bb1a3b1516c9033779c59c1d3ae",
        13304802: "448a7775ab941832e255cbb918acdb25b4ce8dc067f89376ff6404eee9b3ca69",
        13304803: "0f6aa448c5c4af20db4b5069bdce6516c2bc4d4f5b1ed5ccb1653bd47f18ccaf",
        13304804: "ebe1b13a76f981e01d250c845698e7e1625d43a0fb7d0a350beb647256e55155",
        13304807: "32354612205279186043fb283a4c29962803822747e0ffb82fd05bcde48e41d6",
        13304808: "0b9f21dbf5d1f79aa0d6e393c976e3a24f102cfcc25930271ddd0e6d08fa5055",
        13304820: "e2d693a68d6560f3506e2070501ce2a919f1a70640a3145bab556237aac53592",
        13304830: "3ee36ea1ac6d459c45c95aad95bee1e0c3201bc8fdf460a2b3cebae3fa80a9f8",
        13304840: "d3c6246b1286e98ca0f27cb5123d6bdc043982618d533a9aa76a647d3ac5ff68",
    },
    activation_idle_animation=7001,
)

EBRIETAS_ARENA = ArenaContract(
    key="ebrietas",
    event_file="m24_02_00_00.emevd.dcx.js",
    map_prefix="m24_02_",
    actor=2420800,
    archetype=Archetype("c2510", 251000, 251000, 0),
    destination_count=2,
    completion_event=12421800,
    start_flag=12424800,
    health_bar_event=12424802,
    health_bar_label=251000,
    activation_event=12421802,
    music_event=12424803,
    phase_music_message=100,
    lockcam_event=12424804,
    lockcam_map=24,
    lockcam_subarea=2,
    phase_slots=(12424980, 12424990),
    co_op_entry_event=12421803,
    part_routine_event=12424870,
    cloth_routine_event=12424871,
    part_slots=(
        PartBinding(0, ("2420", "2420", "NPCPartType.Part5", "200", "480", "490", "8040")),
        PartBinding(0, ("2421", "2421", "NPCPartType.Part1", "200", "481", "491", "8010")),
        PartBinding(1, ("2422", "2422", "NPCPartType.Part2", "200", "482", "492", "8000")),
        PartBinding(2, ("2423", "2423", "NPCPartType.Part3", "200", "483", "493", "8030")),
        PartBinding(3, ("2424", "2424", "NPCPartType.Part4", "200", "484", "494", "8020")),
    ),
    attachment_event_ids=(12424907, 12424908, 12424920, 12424930, 12424940),
    virtual_entity_ids=(2420890,),
    attachment_anchor_slot=0,
    attachment_anchor_event=12424980,
    expected={
        0: "cda0f114ad3f96b4b93fda3b81ac6d6ed5808bdb0be3f6d16e8225733e729dde",
        12421800: "7cb7c78833c5ef60a5599d35c22964e87b75f980c3165e139d7c28fc8a1bd34b",
        12421802: "9bc79c8e55c2a2c9793a90070de1f76c35a46ebd98c2c79176b2fcc02ae8adc4",
        12424802: "effdc8bf4ca63c0371f209afbd388d0c682793bc2efaf258675e871bcae21ad2",
        12424803: "a487e349f0a416298a26fb93c87c0c57fd7211e7da3da8938d37b6e909130966",
        12424804: "9324596b40c1d5a8ec57a11c71eab66105a1550a81cdcacd4432a86ec366ea74",
        12424870: "4fac0ea46041effd27d59b41752ef9758ba1c6021647ef9831f87de11e5564ba",
        12424871: "50091165e085e178edd4641859d7af08032e2dc4c1be99e7d3631ecbaa07abbc",
        12424980: "cebf5265578c05b598b8c2f9d2c524c852a32e48facb4856db1426185f098cb1",
        12424990: "0b8bf3929d610e3938673ca58072126cbde658e3aa75911c958a1b7e7f43a700",
    },
    activation_idle_animation=7001,
)

BSB_PACKAGE = CombatPackage(
    key="blood-starved-beast",
    event_file=boss_canary.DONOR_EVENT_FILE + ".js",
    map_prefix="m23_00_",
    actor=2300800,
    archetype=Archetype("c2090", 209000, 209000, 0),
    completion_event=12301800,
    start_flag=12304800,
    activation_event=12301802,
    health_bar_event=12304802,
    # This is the literal final operand in DisplayBossHealthBar in 12304802.
    health_bar_label=209000,
    phase_events=(12304807, 12304808),
    co_op_entry_event=None,
    lockcam_event=None,
    phase_music_message=None,
    part_routine_event=None,
    part_bindings=(),
    attachments=(),
    virtual_entities=(),
    entry_animation=7001,
    lockcam_map=None,
    lockcam_subarea=None,
    expected={
        **{key: value for key, value in boss_canary.EXPECTED.items() if key < 12400000},
        12301802: "c8e1b3b8b94fe800a158228a1b177c944c90883fc45826b5060488a064ca145d",
        12301803: "62fb078e77c476dc5d9d3631843895197d9974e67a15880b5ca133dd870f299c",
        12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
        12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
        12304804: "86edb06de9efdc94365fb640741ce4d62620363a3c37ebb99d37ef2b9d3f3521",
    },
    legacy_canary=True,
    primary_state_bindings=(("00", "00"), ("01", "01"), ("11", "00")),
)

PAARL_PACKAGE = CombatPackage(
    key="darkbeast-paarl",
    event_file="m23_00_00_00.emevd.dcx.js",
    map_prefix="m23_00_",
    actor=2300810,
    archetype=Archetype("c5080", 508000, 508000, 0),
    completion_event=12301700,
    start_flag=12304700,
    activation_event=12301702,
    health_bar_event=12304702,
    # Witnessed in source event 12304702, rather than inferred from NpcParam.
    health_bar_label=508000,
    phase_events=(12304707,),
    co_op_entry_event=12301703,
    lockcam_event=12304704,
    phase_music_message=20,
    part_routine_event=12304715,
    part_bindings=(
        PartBinding(0, ("2300", "2300", "NPCPartType.Part1", "480", "490", "8000", "130")),
        PartBinding(1, ("2301", "2301", "NPCPartType.Part2", "481", "491", "8010", "150")),
        PartBinding(2, ("2302", "2302", "NPCPartType.Part3", "482", "492", "8030", "150")),
        PartBinding(3, ("2303", "2303", "NPCPartType.Part4", "483", "493", "8020", "200")),
        PartBinding(4, ("2304", "2304", "NPCPartType.Part5", "484", "494", "8040", "200")),
    ),
    attachments=(),
    virtual_entities=(),
    entry_animation=7001,
    lockcam_map=23,
    lockcam_subarea=0,
    expected={
        0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
        12301700: "3d8feaac026a84d0e378ba5599fa4e3b60ca424d59a88776434a2e8be0c77d3e",
        12301702: "374db59c960671a66ac7afdd712cc0576d03a554ec7ca3d74f0902799bfd517d",
        12301703: "ca968c9f60d2a495e9f3c87c77083ec5d1524b34792d646aa29a239f7f11b653",
        12304702: "cb57ca1efd9f78db3f35500a83581b90e3101e0d13446d398715faad7383c220",
        12304703: "e425e391e28c7dae502e70533be953a18976657b4ab3f5ba328bf4304840e825",
        12304704: "fc0d014681e349fa969f5746f3ac690ad606d48e1f1c828288547efab3dcd3b7",
        12304707: "c88383d5ab10974eaa968e06dbbd9f92e6d0ca05ae02fe38650490a24445cf3b",
        12304715: "015e8810e6bdab08aa66827c290b554890e0c45be100efe95fcf6730a00ee74e",
    },
    primary_state_bindings=(("00", "00"), ("01", "01"), ("11", "00")),
)

CLERIC_PACKAGE = CombatPackage(
    key="cleric-beast",
    event_file="m24_01_00_00.emevd.dcx.js",
    map_prefix="m24_01_",
    actor=2410800,
    archetype=Archetype("c5000", 500241, 500241, 0),
    completion_event=12411700,
    start_flag=12414700,
    activation_event=12411702,
    health_bar_event=12414702,
    # Witnessed in the final DisplayBossHealthBar operand in 12414702.
    health_bar_label=500000,
    phase_events=(12414707, 12414708),
    co_op_entry_event=None,
    lockcam_event=12414704,
    phase_music_message=100,
    part_routine_event=12414710,
    part_bindings=(
        PartBinding(0, ("2410", "2410", "NPCPartType.Part1", "20", "480", "490", "8020")),
        PartBinding(1, ("2411", "2411", "NPCPartType.Part2", "120", "481", "491", "8000")),
        PartBinding(2, ("2412", "2412", "NPCPartType.Part3", "300", "482", "492", "8010")),
        PartBinding(3, ("2413", "2413", "NPCPartType.Part4", "200", "483", "493", "8030")),
        PartBinding(4, ("2414", "2414", "NPCPartType.Part5", "200", "484", "494", "8040")),
    ),
    attachments=(
        EventAttachment(12414707, (PartBinding(0, ()),)),
        EventAttachment(12414708, (PartBinding(0, ()),)),
        EventAttachment(12414710, (
            PartBinding(0, ("2410", "2410", "NPCPartType.Part1", "20", "480", "490", "8020")),
            PartBinding(1, ("2411", "2411", "NPCPartType.Part2", "120", "481", "491", "8000")),
            PartBinding(2, ("2412", "2412", "NPCPartType.Part3", "300", "482", "492", "8010")),
            PartBinding(3, ("2413", "2413", "NPCPartType.Part4", "200", "483", "493", "8030")),
            PartBinding(4, ("2414", "2414", "NPCPartType.Part5", "200", "484", "494", "8040")),
        )),
        EventAttachment(12414720, (
            PartBinding(0, ("480", "490", "5", "10")),
            PartBinding(1, ("481", "491", "6", "11")),
            PartBinding(2, ("482", "492", "7", "12")),
            PartBinding(3, ("483", "493", "8", "13")),
            PartBinding(4, ("484", "494", "9", "14")),
        )),
    ),
    virtual_entities=(),
    entry_animation=3028,
    lockcam_map=24,
    lockcam_subarea=1,
    expected={
        0: "329450dd4b8ae967cdaf56f5ab65556bb0a453e8f8374d79328848dff72cf89c",
        12411702: "702380b92bd2632ce4ff9527009f8c7209fffff89297bc38d8fb8d108655eaff",
        12414702: "026c305969b19114cc2f678e6d3859542442b35764b658ccfe65c3cb7fe7d422",
        12414704: "ce143b924eb991b092351eb7641c7ea8349c28296209618f629b3b7c8ac02caa",
        12414707: "196e29870aae5dab2604594ce9ff0047b2ad71294fec48b6aa56c9f87465f73e",
        12414708: "2565484fb6afa230b46708bce4f42e8088d0f062fbafdb50453e078fc2fbf14d",
        12414710: "da624a8c97354a1208ce15fb1619bcb7f21aa74e89e39d22bfe4edac45c2373d",
        12414720: "1196a612c8f3b4d47e502e52fcbd848c9efe3be859b2b25e934e240c210099ea",
    },
    generic_activation=True,
    primary_state_bindings=(("00", "00"), ("01", "01"), ("11", "11")),
)

AMELIA_PACKAGE = CombatPackage(
    key="vicar-amelia",
    event_file="m24_00_00_00.emevd.dcx.js",
    map_prefix="m24_00_",
    actor=2400800,
    archetype=Archetype("c5020", 502000, 502000, 0),
    completion_event=12401800,
    start_flag=12404800,
    activation_event=12401802,
    health_bar_event=12404802,
    # Witnessed in the final DisplayBossHealthBar operand in 12404802.
    health_bar_label=502000,
    phase_events=(12404807, 12404808),
    co_op_entry_event=None,
    lockcam_event=12404804,
    phase_music_message=100,
    part_routine_event=12404810,
    part_bindings=(
        PartBinding(0, ("2400", "2400", "NPCPartType.Part1", "80", "480", "490", "8020")),
        PartBinding(1, ("2401", "2401", "NPCPartType.Part2", "150", "481", "491", "8000")),
        PartBinding(2, ("2402", "2402", "NPCPartType.Part3", "150", "482", "492", "8010")),
        PartBinding(3, ("2403", "2403", "NPCPartType.Part4", "200", "483", "493", "8030")),
        PartBinding(4, ("2404", "2404", "NPCPartType.Part5", "200", "484", "494", "8040")),
    ),
    attachments=(
        EventAttachment(12404807, (PartBinding(0, ()),)),
        EventAttachment(12404808, (PartBinding(0, ()),)),
        EventAttachment(12404810, (
            PartBinding(0, ("2400", "2400", "NPCPartType.Part1", "80", "480", "490", "8020")),
            PartBinding(1, ("2401", "2401", "NPCPartType.Part2", "150", "481", "491", "8000")),
            PartBinding(2, ("2402", "2402", "NPCPartType.Part3", "150", "482", "492", "8010")),
            PartBinding(3, ("2403", "2403", "NPCPartType.Part4", "200", "483", "493", "8030")),
            PartBinding(4, ("2404", "2404", "NPCPartType.Part5", "200", "484", "494", "8040")),
        )),
        EventAttachment(12404820, (
            PartBinding(0, ("480", "490", "5", "10")),
            PartBinding(1, ("481", "491", "6", "11")),
            PartBinding(2, ("482", "492", "7", "12")),
            PartBinding(3, ("483", "493", "8", "13")),
            PartBinding(4, ("484", "494", "9", "14")),
        )),
        # This self-heal choreography is initialized separately from the
        # limbs and depends on Amelia's 2150/5639 sp-effect pair.
        EventAttachment(12404830, (PartBinding(0, ()),)),
    ),
    virtual_entities=(),
    entry_animation=7001,
    lockcam_map=24,
    lockcam_subarea=0,
    expected={
        0: "31936ed53ff8d095dcae5257c6d36e321a55bc8cd53ed564a1510363a9a04e27",
        12401800: "98ed01dba0556def27d9679e35114473d9464026a03f45115cb25ed8f02d85ce",
        12401802: "b869911c8ee05015b1b90d6fcac40ae0f492433ce83f0f2629e4973cdfbbcde0",
        12404802: "d9c5e8ef9feaa1758a8ee08e21a8da089b96f5bb7e17a740f8d34770b7c9ea31",
        12404804: "77adf8b72d36b425788c96b1bd697a193a8b81408ccc8e14c071687427f92621",
        12404807: "c1963c0461fe87ebd3a432bc41eaaeebcea3aa82ca86526d4e51da3619714279",
        12404808: "8a8be8efea5f76c0d44a669ddbafc86f1e59b7bdd5ebac85a556619ba3c236ed",
        12404810: "30b2c3b6e19b220396f325beaed9873285c58304d54a2ec2c939477dd1f84830",
        12404820: "dfe2dd42c30b7686b972b2a20eed997ee00660d7592bf1fe7a91ad0602d76b19",
        12404830: "b92005d1b304b616a48dc9f877601a8d024362e8745ffa34282f3c92257e7c9d",
    },
    generic_activation=True,
    primary_state_bindings=(("00", "00"), ("01", "01"), ("11", "00")),
)

AMYGDALA_PACKAGE = CombatPackage(
    key="amygdala",
    event_file="m33_00_00_00.emevd.dcx.js",
    map_prefix="m33_00_",
    actor=3300800,
    archetype=Archetype("c5120", 512000, 512000, 0),
    completion_event=13301800,
    start_flag=13304800,
    activation_event=13301802,
    health_bar_event=13304802,
    health_bar_label=512000,
    phase_events=(13304807, 13304808),
    co_op_entry_event=13301803,
    lockcam_event=13304804,
    phase_music_message=10,
    part_routine_event=13304830,
    part_bindings=(
        PartBinding(0, ("3301", "3301", "NPCPartType.Part4", "482", "200", "8020", "1", "1.5")),
        PartBinding(1, ("3302", "3302", "NPCPartType.Part6", "482", "180", "8020", "1", "1.5")),
        PartBinding(2, ("3303", "3303", "NPCPartType.Part8", "482", "150", "8020", "1", "1.5")),
        PartBinding(3, ("3304", "3304", "NPCPartType.Part5", "481", "200", "8010", "1", "1.5")),
        PartBinding(4, ("3305", "3305", "NPCPartType.Part7", "481", "150", "8010", "1", "1.5")),
        PartBinding(5, ("3306", "3306", "NPCPartType.Part9", "481", "120", "8010", "1", "1.5")),
        PartBinding(6, ("3307", "3307", "NPCPartType.Part10", "481", "120", "8010", "1", "1.5")),
        PartBinding(7, ("3308", "3308", "NPCPartType.Part3", "483", "200", "8030", "0.2", "0.3")),
        PartBinding(8, ("3309", "3309", "NPCPartType.Part11", "484", "100", "8040", "0.2", "0.3")),
        PartBinding(9, ("3310", "3310", "NPCPartType.Part12", "483", "100", "8030", "0.2", "0.3")),
    ),
    attachments=(
        EventAttachment(13304807, (PartBinding(0, ()),)),
        EventAttachment(13304808, (PartBinding(0, ()),)),
        EventAttachment(13304820, (
            PartBinding(0, ("3311", "3311", "NPCPartType.Part13", "9", "13")),
            PartBinding(1, ("3322", "3322", "NPCPartType.Part14", "8", "14")),
        )),
        EventAttachment(13304830, (
            PartBinding(0, ("3301", "3301", "NPCPartType.Part4", "482", "200", "8020", "1", "1.5")),
            PartBinding(1, ("3302", "3302", "NPCPartType.Part6", "482", "180", "8020", "1", "1.5")),
            PartBinding(2, ("3303", "3303", "NPCPartType.Part8", "482", "150", "8020", "1", "1.5")),
            PartBinding(3, ("3304", "3304", "NPCPartType.Part5", "481", "200", "8010", "1", "1.5")),
            PartBinding(4, ("3305", "3305", "NPCPartType.Part7", "481", "150", "8010", "1", "1.5")),
            PartBinding(5, ("3306", "3306", "NPCPartType.Part9", "481", "120", "8010", "1", "1.5")),
            PartBinding(6, ("3307", "3307", "NPCPartType.Part10", "481", "120", "8010", "1", "1.5")),
            PartBinding(7, ("3308", "3308", "NPCPartType.Part3", "483", "200", "8030", "0.2", "0.3")),
            PartBinding(8, ("3309", "3309", "NPCPartType.Part11", "484", "100", "8040", "0.2", "0.3")),
            PartBinding(9, ("3310", "3310", "NPCPartType.Part12", "483", "100", "8030", "0.2", "0.3")),
        )),
        EventAttachment(13304840, (PartBinding(0, ()),)),
    ),
    virtual_entities=(),
    # The 7003/7006/7002 entry sequence is represented by the dedicated,
    # pinned Amygdala activation adapter rather than a lossy one-number alias.
    entry_animation=None,
    lockcam_map=33,
    lockcam_subarea=0,
    expected=dict(AMYGDALA_ARENA.expected),
    primary_state_bindings=(("00", "00"), ("01", "00"), ("11", "00")),
)

# Ebrietas' bullet owner is a concrete MSB actor, not an EMEVD-only helper.
# Its reviewed Paarl adapter consequently remains builder-gated on a native,
# source-pinned actor addition before the event overlay is emitted.
EBRIETAS_PACKAGE = CombatPackage(
    key="ebrietas",
    event_file="m24_02_00_00.emevd.dcx.js",
    map_prefix="m24_02_",
    actor=2420800,
    archetype=Archetype("c2510", 251000, 251000, 0),
    completion_event=12421800,
    start_flag=12424800,
    activation_event=12421802,
    health_bar_event=12424802,
    health_bar_label=251000,
    phase_events=(12424980,),
    co_op_entry_event=12421803,
    lockcam_event=12424804,
    phase_music_message=100,
    part_routine_event=12424870,
    part_bindings=(
        PartBinding(0, ("2420", "2420", "NPCPartType.Part5", "200", "480", "490", "8040")),
        PartBinding(0, ("2421", "2421", "NPCPartType.Part1", "200", "481", "491", "8010")),
        PartBinding(1, ("2422", "2422", "NPCPartType.Part2", "200", "482", "492", "8000")),
        PartBinding(2, ("2423", "2423", "NPCPartType.Part3", "200", "483", "493", "8030")),
        PartBinding(3, ("2424", "2424", "NPCPartType.Part4", "200", "484", "494", "8020")),
    ),
    attachments=(
        EventAttachment(12424980, (PartBinding(0, ()),)),
        EventAttachment(12424990, (PartBinding(0, ()),)),
        EventAttachment(12424870, (
            PartBinding(0, ("2420", "2420", "NPCPartType.Part5", "200", "480", "490", "8040")),
        )),
        EventAttachment(12424871, (
            PartBinding(0, ("2421", "2421", "NPCPartType.Part1", "200", "481", "491", "8010")),
            PartBinding(1, ("2422", "2422", "NPCPartType.Part2", "200", "482", "492", "8000")),
            PartBinding(2, ("2423", "2423", "NPCPartType.Part3", "200", "483", "493", "8030")),
            PartBinding(3, ("2424", "2424", "NPCPartType.Part4", "200", "484", "494", "8020")),
        )),
    ),
    # Native source evidence identifies 2420801 as MSB enemy c9010_0003
    # (c9010 / NPC 251001), so EMEVD may not stand in for its actor addition.
    virtual_entities=(VirtualEntityBinding(
        2420801, "CreateBulletOwner", requires_actor_addition=True,
        source_part="c9010_0003", source_anchor_part="c2510_0000",
        source_archetype=Archetype("c9010", 251001, 1, 0),
        destination_part="ap_ebrietas_bullet_owner",
        allocation_evidence="BB Ebrietas bullet-owner actor allocation v1; full corpus collision scan",
        source_state_bindings=(("00", "00"), ("01", "01"), ("11", "00")),
    ),),
    entry_animation=None,
    lockcam_map=24,
    lockcam_subarea=2,
    expected={
        0: "cda0f114ad3f96b4b93fda3b81ac6d6ed5808bdb0be3f6d16e8225733e729dde",
        12421800: "7cb7c78833c5ef60a5599d35c22964e87b75f980c3165e139d7c28fc8a1bd34b",
        12421802: "9bc79c8e55c2a2c9793a90070de1f76c35a46ebd98c2c79176b2fcc02ae8adc4",
        12424802: "effdc8bf4ca63c0371f209afbd388d0c682793bc2efaf258675e871bcae21ad2",
        12424803: "a487e349f0a416298a26fb93c87c0c57fd7211e7da3da8938d37b6e909130966",
        12424804: "9324596b40c1d5a8ec57a11c71eab66105a1550a81cdcacd4432a86ec366ea74",
        12424870: "4fac0ea46041effd27d59b41752ef9758ba1c6021647ef9831f87de11e5564ba",
        12424871: "50091165e085e178edd4641859d7af08032e2dc4c1be99e7d3631ecbaa07abbc",
        12424980: "cebf5265578c05b598b8c2f9d2c524c852a32e48facb4856db1426185f098cb1",
        12424990: "0b8bf3929d610e3938673ca58072126cbde658e3aa75911c958a1b7e7f43a700",
    },
    primary_state_bindings=(("00", "00"), ("01", "01"), ("11", "00")),
)

ARENAS: tuple[ArenaContract, ...] = (
    CLERIC_ARENA, BSB_ARENA, PAARL_ARENA, AMELIA_ARENA, AMYGDALA_ARENA, EBRIETAS_ARENA,
)
PACKAGES: tuple[CombatPackage, ...] = (
    BSB_PACKAGE, PAARL_PACKAGE, CLERIC_PACKAGE, AMELIA_PACKAGE, AMYGDALA_PACKAGE, EBRIETAS_PACKAGE,
)


@dataclass(frozen=True)
class ContractCapability:
    """A complete, source-backed adapter available to a contract pair."""

    adapter: str
    requires_actor_additions: bool = False


# These routines have source-specific activation programs that the generic
# ``ArenaContract``/``CombatPackage`` fields do not yet describe.  Keeping
# their finite set here makes that boundary explicit; it is not the registry
# for ordinary single-actor package compatibility below.
_SPECIALIZED_CAPABILITIES: dict[tuple[str, str], ContractCapability] = {
    (CLERIC_ARENA.key, BSB_PACKAGE.key): ContractCapability("legacy-canary"),
    (CLERIC_ARENA.key, PAARL_PACKAGE.key): ContractCapability("paarl-entry"),
    (BSB_ARENA.key, PAARL_PACKAGE.key): ContractCapability("paarl-entry"),
    (PAARL_ARENA.key, BSB_PACKAGE.key): ContractCapability("bsb-entry"),
    (EBRIETAS_ARENA.key, BSB_PACKAGE.key): ContractCapability("bsb-ebrietas-entry"),
    (CLERIC_ARENA.key, AMYGDALA_PACKAGE.key): ContractCapability("amygdala-entry"),
    (BSB_ARENA.key, AMYGDALA_PACKAGE.key): ContractCapability("amygdala-entry"),
    (PAARL_ARENA.key, AMYGDALA_PACKAGE.key): ContractCapability("amygdala-entry"),
    (AMELIA_ARENA.key, AMYGDALA_PACKAGE.key): ContractCapability("amygdala-entry"),
    (EBRIETAS_ARENA.key, AMYGDALA_PACKAGE.key): ContractCapability("amygdala-entry"),
    (AMELIA_ARENA.key, BSB_PACKAGE.key): ContractCapability("bsb-phase-slots"),
    (AMYGDALA_ARENA.key, BSB_PACKAGE.key): ContractCapability("bsb-phase-slots"),
    (AMELIA_ARENA.key, PAARL_PACKAGE.key): ContractCapability("paarl-entry"),
    (AMYGDALA_ARENA.key, PAARL_PACKAGE.key): ContractCapability("paarl-appended-body"),
    (EBRIETAS_ARENA.key, PAARL_PACKAGE.key): ContractCapability("paarl-appended-body"),
}


def _generic_attachment_capability(arena: ArenaContract,
                                   donor: CombatPackage) -> ContractCapability | None:
    """Return generic single-actor eligibility from declared contract data.

    The adapter has all it needs only when the donor declares a complete,
    simple activation plus copied routines, and the arena has enough declared
    append-only event and virtual-entity capacity.  It deliberately does not
    treat a numeric map prefix or matching model as compatibility evidence.
    """
    if (not donor.generic_activation or donor.entry_animation is None
            or not donor.attachments or donor.lockcam_event is None
            or donor.phase_music_message is None):
        return None
    if (not arena.attachment_event_ids
            or ((arena.attachment_anchor_slot is None)
                != (arena.attachment_anchor_event is None))
            or len(donor.attachments) > len(arena.attachment_event_ids)
            or len(donor.virtual_entities) > len(arena.virtual_entity_ids)):
        return None
    if (arena.phase_music_event_flag is None and arena.phase_music_message is None
            or arena.activation_idle_animation is None):
        return None
    return ContractCapability(
        "generic-attachment",
        requires_actor_additions=any(
            binding.requires_actor_addition for binding in donor.virtual_entities),
    )


def _ebrietas_attachment_capability(arena: ArenaContract,
                                    donor: CombatPackage) -> ContractCapability | None:
    """Return eligibility for Ebrietas's pinned wake-up and bullet-owner graph."""
    if donor is not EBRIETAS_PACKAGE:
        return None
    if (not arena.attachment_event_ids
            or ((arena.attachment_anchor_slot is None)
                != (arena.attachment_anchor_event is None))
            or len(donor.attachments) > len(arena.attachment_event_ids)
            or len(donor.virtual_entities) > len(arena.virtual_entity_ids)):
        return None
    if arena.phase_music_event_flag is None and arena.phase_music_message is None:
        return None
    return ContractCapability("ebrietas-entry", requires_actor_additions=True)


def contract_capability(arena: ArenaContract,
                        donor: CombatPackage) -> ContractCapability | None:
    """Return the exact adapter supported by the two declared contracts.

    A same-identity pair is not a shuffle.  Generic pairs are derived from
    capacities and witnessed activation fields; remaining entries are the
    small set whose source activation body is still individually represented.
    """
    if arena.key == donor.key:
        return None
    ebrietas = _ebrietas_attachment_capability(arena, donor)
    if ebrietas is not None:
        return ebrietas
    generic = _generic_attachment_capability(arena, donor)
    if generic is not None:
        return generic
    return _SPECIALIZED_CAPABILITIES.get((arena.key, donor.key))


COMPATIBILITY: dict[str, tuple[str, ...]] = {
    arena.key: tuple(package.key for package in PACKAGES
                     if contract_capability(arena, package) is not None)
    for arena in ARENAS
}


def _compatible_packages(arena: ArenaContract) -> tuple[CombatPackage, ...]:
    return tuple(package for package in PACKAGES
                 if contract_capability(arena, package) is not None)


# Kept as public conveniences for callers that previously imported these
# names.  They are views of the capability registry, not hand-maintained
# pair lists.
CLERIC_PACKAGES = _compatible_packages(CLERIC_ARENA)
BSB_ARENA_PACKAGES = _compatible_packages(BSB_ARENA)
PAARL_ARENA_PACKAGES = _compatible_packages(PAARL_ARENA)
AMELIA_ARENA_PACKAGES = _compatible_packages(AMELIA_ARENA)
AMYGDALA_ARENA_PACKAGES = _compatible_packages(AMYGDALA_ARENA)
EBRIETAS_ARENA_PACKAGES = _compatible_packages(EBRIETAS_ARENA)


def _verify_pins(label: str, blocks: EventBlocks, expected: dict[int, str]) -> None:
    for event_id, digest in expected.items():
        block = blocks.get(event_id)
        if block is None or hashlib.sha256(block.encode("utf-8")).hexdigest() != digest:
            raise ValueError(f"unsupported original {label} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"contract expected one {label}")
    return text.replace(old, new, 1)


def _end_event(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(r"function\(([^)]*)\)", lambda match: "function(" + ", ".join(
        name.strip() if name.strip().startswith("unused_") else "unused_" + name.strip()
        for name in match[1].split(",") if name.strip()) + ")", declaration)
    return declaration + "\n    EndEvent();\n});"


def _retire_unreused_attachment_anchor(arena: ArenaContract, original: EventBlocks,
                                        edits: dict[int, str]) -> None:
    """No-op a destination-only attachment controller unless a donor reused it."""
    anchor = arena.attachment_anchor_event
    if anchor is None or anchor in edits:
        return
    block = original.get(anchor)
    if block is None:
        raise ValueError(f"{arena.key} attachment controller is absent")
    edits[anchor] = _end_event(block)


def _remap_declared_literals(block: str, *, actor: tuple[int, int],
                             completion: tuple[int, int], event: tuple[int, int],
                             flags: tuple[tuple[int, int], ...] = ()) -> str:
    """Map only an explicitly typed donor literal inside a copied event body."""
    replacements = dict((actor, completion, event, *flags))
    return re.sub(r"(?<![\w])-?\d+(?![\w])",
                  lambda match: str(replacements.get(int(match[0]), int(match[0]))), block)


def _replace_event(source: str, edits: dict[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(boss_canary.parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _attachment_targets(arena: ArenaContract, donor: CombatPackage,
                        destination: str) -> dict[int, int]:
    """Resolve declared attachment IDs after a full numeric collision scan."""
    if len(donor.attachments) > len(arena.attachment_event_ids):
        raise ValueError(f"arena has no declared attachment capacity for {donor.key}")
    if (arena.attachment_anchor_slot is None) != (arena.attachment_anchor_event is None):
        raise ValueError(f"arena has an incomplete attachment initializer anchor for {donor.key}")
    values = {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    targets = dict(zip((attachment.source_event for attachment in donor.attachments),
                       arena.attachment_event_ids))
    for target in targets.values():
        if target in values:
            raise ValueError(f"declared attachment event ID {target} collides with original arena literal")
    return targets


def _virtual_entity_targets(arena: ArenaContract, donor: CombatPackage,
                            destination: str) -> dict[int, int]:
    if len(donor.virtual_entities) > len(arena.virtual_entity_ids):
        raise ValueError(f"arena has no declared virtual-entity capacity for {donor.key}")
    values = {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    targets = dict(zip((binding.source_entity for binding in donor.virtual_entities),
                       arena.virtual_entity_ids))
    for target in targets.values():
        if target in values:
            raise ValueError(f"declared virtual entity ID {target} collides with original arena literal")
    return targets


def _map_state(map_name: str) -> str:
    """The final map component pairs equivalent alternate MSB states."""
    prefix, separator, state = map_name.rpartition("_")
    if not prefix or not separator or not state.isdigit():
        raise ValueError(f"unsupported map state name {map_name}")
    return state


def primary_initialization_requirements(arena: ArenaContract, donor: CombatPackage, slots) -> list[dict]:
    """Declare exact original Parts for native primary initialization copying.

    Cross-map state selection is explicit in the donor contract.  The native
    builder turns each row into an actor-pin provenance record; this planner
    cannot infer MSB initialization from an archetype or a map-name suffix.
    """
    destinations = [slot for slot in slots if slot.entity_id == arena.actor
                    and slot.map_name.startswith(arena.map_prefix)]
    sources = [slot for slot in slots if slot.entity_id == donor.actor
               and slot.map_name.startswith(donor.map_prefix)]
    if len(destinations) != arena.destination_count or not sources:
        raise ValueError(f"unsupported primary initialization provenance for {arena.key} <- {donor.key}")
    by_destination_state = {_map_state(slot.map_name): slot for slot in destinations}
    by_source_state = {_map_state(slot.map_name): slot for slot in sources}
    if len(by_destination_state) != len(destinations) or len(by_source_state) != len(sources):
        raise ValueError(f"ambiguous primary initialization map state for {arena.key} <- {donor.key}")
    bindings = dict(donor.primary_state_bindings)
    if len(bindings) != len(donor.primary_state_bindings):
        raise ValueError(f"{donor.key} primary initialization has ambiguous source state bindings")
    missing_states = set(by_destination_state) - set(bindings)
    if missing_states:
        raise ValueError(f"{donor.key} primary initialization lacks an explicit source state binding")
    requirements = []
    for state, destination in sorted(by_destination_state.items()):
        source = by_source_state.get(bindings[state])
        if source is None:
            raise ValueError(f"{donor.key} primary initialization names a missing source map state")
        if source.archetype != donor.archetype or destination.archetype != arena.archetype:
            raise ValueError(f"primary initialization archetype provenance drift for {arena.key} <- {donor.key}")
        requirements.append({
            "source_map": source.map_name,
            "source_part": source.part_name,
            "source_entity_id": donor.actor,
            "source_archetype": asdict(donor.archetype),
            "destination_map": destination.map_name,
            "destination_part": destination.part_name,
            "destination_entity_id": arena.actor,
        })
    return requirements


def actor_addition_requirements(arena: ArenaContract, donor: CombatPackage, slots) -> list[dict]:
    """Return native-pinnable requirements for donor helpers that need MSB Parts.

    These are deliberately *not* writer-ready ``boss_actor_additions``: the
    builder must obtain native source provenance and initialization pins for
    each source-map state before it promotes a requirement to a mutation.
    """
    requirements: list[dict] = []
    destinations = [slot for slot in slots if slot.entity_id == arena.actor
                    and slot.map_name.startswith(arena.map_prefix)]
    if len(destinations) != arena.destination_count:
        raise ValueError(f"unsupported boss placement provenance for {arena.key}")
    by_destination_state = {_map_state(slot.map_name): slot for slot in destinations}
    if len(by_destination_state) != len(destinations):
        raise ValueError(f"ambiguous destination map state for {arena.key}")
    for index, binding in enumerate(donor.virtual_entities):
        if not binding.requires_actor_addition:
            continue
        if (binding.source_part is None or binding.source_anchor_part is None
                or binding.source_archetype is None or binding.destination_part is None
                or binding.allocation_evidence is None):
            raise ValueError(f"{donor.key} materialized helper lacks typed actor provenance")
        helpers = [slot for slot in slots if slot.entity_id == binding.source_entity
                   and slot.map_name.startswith(donor.map_prefix)]
        anchors = [slot for slot in slots if slot.entity_id == donor.actor
                   and slot.map_name.startswith(donor.map_prefix)]
        helper_states = {_map_state(slot.map_name): slot for slot in helpers}
        anchor_states = {_map_state(slot.map_name): slot for slot in anchors}
        if len(helper_states) != len(helpers) or len(anchor_states) != len(anchors):
            raise ValueError(f"ambiguous source helper map state for {donor.key}")
        bindings = dict(binding.source_state_bindings)
        if len(bindings) != len(binding.source_state_bindings):
            raise ValueError(f"{donor.key} helper has ambiguous source state bindings")
        if bindings:
            missing_states = set(by_destination_state) - set(bindings)
            if missing_states:
                raise ValueError(f"{donor.key} helper lacks an explicit source state binding")
            source_state_for_destination = {
                state: bindings[state] for state in by_destination_state
            }
        else:
            if (set(helper_states) != set(by_destination_state)
                    or set(anchor_states) != set(by_destination_state)):
                raise ValueError(f"{donor.key} helper lacks every destination map state")
            source_state_for_destination = {state: state for state in by_destination_state}
        for state in sorted(by_destination_state):
            source_state = source_state_for_destination[state]
            helper = helper_states.get(source_state)
            anchor = anchor_states.get(source_state)
            destination = by_destination_state[state]
            if helper is None or anchor is None:
                raise ValueError(f"{donor.key} helper binding names a missing source map state")
            if (helper.part_name != binding.source_part or anchor.part_name != binding.source_anchor_part
                    or helper.archetype != binding.source_archetype):
                raise ValueError(f"{donor.key} helper source provenance drift in map state {state}")
            requirements.append({
                "source_map": helper.map_name,
                "source_part": binding.source_part,
                "source_anchor_part": binding.source_anchor_part,
                "source_entity_id": binding.source_entity,
                "source_archetype": asdict(binding.source_archetype),
                "source_part_kind": "enemy",
                "destination_map": destination.map_name,
                "destination_anchor_part": destination.part_name,
                "destination_part": binding.destination_part,
                "destination_entity_id": arena.virtual_entity_ids[index],
                "allocation_evidence": binding.allocation_evidence,
            })
    return requirements


def _initializer_line(slot: int, event_id: int, arguments: tuple[str, ...]) -> str:
    return "    $InitializeEvent(" + ", ".join((str(slot), str(event_id), *arguments)) + ");"


def _attach_initializers(event_zero: str, arena: ArenaContract,
                         donor: CombatPackage, targets: dict[int, int],
                         virtual_targets: dict[int, int], donor_event_zero: str) -> str:
    """Replace a reviewed initializer or append witnessed calls to Event(0)."""
    replacement: list[str] = []
    for attachment in donor.attachments:
        for binding in attachment.initializers:
            witness = _initializer_line(binding.slot, attachment.source_event, binding.arguments)
            if donor_event_zero.count(witness) != 1:
                raise ValueError(f"donor Event(0) lacks unique initializer witness for {attachment.source_event}")
            replacement.append(_initializer_line(binding.slot, targets[attachment.source_event], binding.arguments))
    for binding in donor.virtual_entities:
        if not re.fullmatch(r"[A-Za-z_]\w*", binding.initializer):
            raise ValueError("virtual entity initializer is not a declared instruction name")
        witness = f"    {binding.initializer}({binding.source_entity});"
        if donor_event_zero.count(witness) != 1:
            raise ValueError(f"donor Event(0) lacks unique virtual entity witness for {binding.source_entity}")
        replacement.append(f"    {binding.initializer}({virtual_targets[binding.source_entity]});")
    lines = "\n".join(replacement)
    if arena.attachment_anchor_slot is None:
        if not event_zero.endswith("\n});"):
            raise ValueError("attachment Event(0) has no canonical closing delimiter")
        return event_zero[:-3] + "\n" + lines + "\n});"
    old = _initializer_line(arena.attachment_anchor_slot, arena.attachment_anchor_event, ())
    return _replace_once(event_zero, old, lines, "attachment initializer anchor")


def _append_attachment_events(source: str, donor_blocks: EventBlocks,
                              donor: CombatPackage, arena: ArenaContract,
                              targets: dict[int, int], virtual_targets: dict[int, int]) -> str:
    """Append only hash-pinned, explicitly remapped donor event definitions."""
    mapping = {donor.actor: arena.actor, donor.completion_event: arena.completion_event,
               donor.start_flag: arena.start_flag, **targets, **virtual_targets}
    additions = []
    for attachment in donor.attachments:
        source_block = donor_blocks[attachment.source_event]
        additions.append(re.sub(
            r"(?<![\w])-?\d+(?![\w])",
            lambda match: str(mapping.get(int(match[0]), int(match[0]))), source_block))
    return source.rstrip() + "\n\n" + "\n\n".join(additions) + "\n"


def _paarl_wake_after_entry(arena: ArenaContract) -> str:
    """Paarl's pinned post-trigger wake-up, with a local arena start flag."""
    return (
        f"    ForceAnimationPlayback({arena.actor}, 7001, false, false, false);\n"
        "    WaitFixedTimeFrames(70);\n"
        f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
        f"    SetEventFlag({arena.start_flag}, ON);\n"
    )


def _paarl_activation(arena: ArenaContract, original: str) -> str:
    """Retain a destination set-piece around Paarl's pinned entry lifecycle."""
    pre = (f"    SetCharacterInvincibility({arena.actor}, Enabled);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7000, true, false, false);\n")
    wake = _paarl_wake_after_entry(arena)
    if arena is CLERIC_ARENA:
        activation = _replace_once(
            original, f"    SetCharacterGravity({arena.actor}, Disabled);\n",
            pre, "Paarl pre-entry invincibility")
        activation = _replace_once(
            activation, f"    SetCharacterMaphits({arena.actor}, true);\n", "",
            "arena-only maphit preparation")
        activation = _replace_once(activation,
            f"    IssueShortWarpRequest({arena.actor}, TargetEntityType.Area, 2412831, -1);\n", "",
            "arena-only warp")
        activation = _replace_once(
            activation, f"ForceAnimationPlayback({arena.actor}, 3028,",
            f"ForceAnimationPlayback({arena.actor}, 7001,",
            "declared arena activation animation")
        activation = _replace_once(activation, "    WaitFixedTimeFrames(110);\n",
            "    WaitFixedTimeFrames(70);\n    SetCharacterInvincibility(" + str(arena.actor) + ", Disabled);\n",
            "Paarl entry delay")
        activation = _replace_once(activation, f"    SetCharacterGravity({arena.actor}, Enabled);\n", "",
            "arena-only gravity reset")
        return _replace_once(activation, f"    SetCharacterMaphits({arena.actor}, false);\n", "",
                             "arena-only maphit reset")
    if arena is BSB_ARENA:
        activation = _replace_once(original, "    WaitFor(\n", pre + "    WaitFor(\n",
                                   "Paarl pre-entry sequence")
        return _replace_once(activation,
            f"    ForceAnimationPlayback({arena.actor}, 7001, false, false, false);\n"
            f"    SetEventFlag({arena.start_flag}, ON);\n", wake,
            "Paarl entry wake-up")
    if arena is AMELIA_ARENA:
        activation = _replace_once(
            original, "    SetObjectInvulnerability(2400801, Enabled);\n    WaitFor(\n",
            "    SetObjectInvulnerability(2400801, Enabled);\n" + pre + "    WaitFor(\n",
            "Paarl pre-cutscene sequence")
        old = (f"    ForceAnimationPlayback({arena.actor}, 7000, false, false, false);\n"
               f"    ForceAnimationPlayback({arena.actor}, 7001, false, false, false);\n"
               f"    SetEventFlag({arena.start_flag}, ON);\n")
        return _replace_once(activation, old, wake, "Paarl post-cutscene wake-up")
    if arena is AMYGDALA_ARENA:
        activation = _replace_once(
            original,
            f"    SetCharacterMaphits({arena.actor}, true);\n"
            f"    SetCharacterGravity({arena.actor}, Disabled);\n"
            f"    SetCharacterInvincibility({arena.actor}, Enabled);\n"
            f"    ForceAnimationPlayback({arena.actor}, 7003, true, false, false);\n",
            pre, "Paarl pre-entry sequence")
        old = (f"    SetEventFlag({arena.start_flag}, ON);\n"
               f"    ForceAnimationPlayback({arena.actor}, 7006, false, false, false);\n"
               "    WaitFixedTimeFrames(30);\n"
               f"    ForceAnimationPlayback({arena.actor}, 7002, false, false, false);\n"
               "    WaitFixedTimeFrames(160);\n"
               f"    SetCharacterGravity({arena.actor}, Enabled);\n"
               f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
               f"    SetCharacterMaphits({arena.actor}, false);\n")
        return _replace_once(activation, old, wake, "Paarl post-entry wake-up")
    if arena is EBRIETAS_ARENA:
        for instruction in (
            f"    ForceAnimationPlayback({arena.actor}, 7001, true, false, false);\n",
            f"    SetSpEffect({arena.actor}, 5647, false);\n",
        ):
            original = _replace_once(original, instruction, "", "Ebrietas-only pre-wake state")
        old = (f"    ForceAnimationPlayback({arena.actor}, 7000, false, true, false);\n"
               f"    SetCharacterImmortality({arena.actor}, Disabled);\n"
               f"    ClearSpEffect({arena.actor}, 5647);\n"
               f"    SetEventFlag({arena.start_flag}, ON);\n")
        new = (f"    ForceAnimationPlayback({arena.actor}, 7001, false, false, false);\n"
               "    WaitFixedTimeFrames(70);\n"
               f"    SetCharacterImmortality({arena.actor}, Disabled);\n"
               f"    SetEventFlag({arena.start_flag}, ON);\n")
        return _replace_once(original, old, new, "Paarl post-damage wake-up")
    raise ValueError(f"no Paarl activation contract for arena {arena.key}")


def _replace_part_initializers(event_zero: str, arena: ArenaContract,
                               donor: CombatPackage) -> str:
    if len(arena.part_slots) == len(donor.part_bindings):
        for source_binding, destination_binding in zip(donor.part_bindings, arena.part_slots):
            if source_binding.slot != destination_binding.slot:
                raise ValueError("body-part binding slots are not aligned")
            old = "    $InitializeEvent(" + ", ".join(
                (str(destination_binding.slot), str(arena.part_routine_event), *destination_binding.arguments)) + ");"
            new = "    $InitializeEvent(" + ", ".join(
                (str(source_binding.slot), str(arena.part_routine_event), *source_binding.arguments)) + ");"
            event_zero = _replace_once(event_zero, old, new, f"body-part initializer {source_binding.slot}")
        return event_zero
    if len(arena.part_slots) == 1 and not arena.part_slots[0].arguments:
        slot = arena.part_slots[0]
        old = f"    $InitializeEvent({slot.slot}, {arena.part_routine_event});"
        new = "\n".join("    $InitializeEvent(" + ", ".join(
            (str(binding.slot), str(arena.part_routine_event), *binding.arguments)) + ");"
            for binding in donor.part_bindings)
        return _replace_once(event_zero, old, new, "single body-part initializer")
    raise ValueError("arena and donor body-part contracts do not match")


def _remap_lockcam(block: str, arena: ArenaContract, donor: CombatPackage) -> str:
    """Map exactly the declared source camera pair, not arbitrary map literals."""
    if donor.lockcam_map is None or donor.lockcam_subarea is None:
        raise ValueError("donor has no declared lockcam source")
    old = f"SetLockcamSlotNumber({donor.lockcam_map}, {donor.lockcam_subarea},"
    new = f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},"
    if block.count(old) != 2:
        raise ValueError("lockcam contract expected two declared source camera calls")
    return block.replace(old, new)


def _paarl_patch(arena: ArenaContract, donor: CombatPackage,
                 destination: str, donor_source: str) -> str:
    original, donor_blocks = event_blocks(destination), event_blocks(donor_source)
    _verify_pins("arena", original, arena.expected)
    _verify_pins("donor", donor_blocks, donor.expected)
    if len(donor.phase_events) > len(arena.phase_slots):
        raise ValueError("arena has too few declared phase slots for donor")
    if not donor.part_bindings or donor.part_routine_event is None:
        raise ValueError("arena and donor body-part contracts do not match")

    edits: dict[int, str] = {}
    if arena is CLERIC_ARENA:
        edits[12411701] = _replace_once(original[12411701], "500099999", "0", "destination death cue")
    edits[arena.activation_event] = _paarl_activation(arena, original[arena.activation_event])
    edits[arena.health_bar_event] = _replace_once(
        original[arena.health_bar_event],
        f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label})",
        f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {donor.health_bar_label})", "health-bar label")
    if arena.phase_music_event_flag is not None:
        edits[arena.music_event] = _replace_once(
            original[arena.music_event], f"flagArea2 &= EventFlag({arena.phase_music_event_flag});",
            f"flagArea2 &= CharacterHasEventMessage({arena.actor}, {donor.phase_music_message});",
            "Paarl music phase trigger")
    elif arena.phase_music_message is not None:
        edits[arena.music_event] = _replace_once(
            original[arena.music_event],
            f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})",
            f"CharacterHasEventMessage({arena.actor}, {donor.phase_music_message})",
            "Paarl music phase message")
    else:
        raise ValueError(f"no Paarl music contract for arena {arena.key}")
    if donor.lockcam_event is not None:
        lockcam = _remap_declared_literals(
            donor_blocks[donor.lockcam_event], actor=(donor.actor, arena.actor),
            completion=(donor.completion_event, arena.completion_event), event=(donor.lockcam_event, arena.lockcam_event))
        edits[arena.lockcam_event] = _remap_lockcam(lockcam, arena, donor)

    for source_event, destination_event in zip(donor.phase_events, arena.phase_slots):
        edits[destination_event] = _remap_declared_literals(
            donor_blocks[source_event], actor=(donor.actor, arena.actor),
            completion=(donor.completion_event, arena.completion_event), event=(source_event, destination_event))
    for event_id in arena.phase_slots[len(donor.phase_events):]:
        if event_id not in {arena.co_op_entry_event, arena.part_routine_event}:
            edits[event_id] = _end_event(original[event_id])
    if donor.co_op_entry_event is not None:
        edits[arena.co_op_entry_event] = _remap_declared_literals(
            donor_blocks[donor.co_op_entry_event], actor=(donor.actor, arena.actor),
            completion=(donor.completion_event, arena.completion_event),
            event=(donor.co_op_entry_event, arena.co_op_entry_event),
            flags=((donor.start_flag, arena.start_flag), (donor.activation_event, arena.activation_event)))
    else:
        edits[arena.co_op_entry_event] = _end_event(original[arena.co_op_entry_event])
    edits[arena.part_routine_event] = _remap_declared_literals(
        donor_blocks[donor.part_routine_event], actor=(donor.actor, arena.actor),
        completion=(donor.completion_event, arena.completion_event),
        event=(donor.part_routine_event, arena.part_routine_event))
    if arena.cloth_routine_event is not None:
        edits[arena.cloth_routine_event] = _end_event(original[arena.cloth_routine_event])
    _retire_unreused_attachment_anchor(arena, original, edits)

    edits[0] = _replace_part_initializers(original[0], arena, donor)

    result = _replace_event(destination, edits)
    output = event_blocks(result)
    if original.keys() != output.keys():
        raise ValueError("contract changed arena event identity set")
    for event_id in original:
        if event_id not in edits and original[event_id] != output[event_id]:
            raise ValueError(f"contract touched unrelated arena event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("contract changed destination completion event")
    return result


def _append_paarl_body_routine(event_zero: str, arena: ArenaContract,
                               donor_blocks: EventBlocks) -> tuple[str, int, str]:
    """Append Paarl's witnessed limb event when target slots are incompatible."""
    target = arena.attachment_event_ids[-1]
    values = {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", event_zero)}
    if target in values:
        raise ValueError(f"declared appended body event ID {target} collides with original arena literal")
    donor_zero = donor_blocks[0]
    expected_target_initializers = {
        AMYGDALA_ARENA.key: 10,
        EBRIETAS_ARENA.key: 1,
    }.get(arena.key)
    if expected_target_initializers is None:
        raise ValueError(f"no appended Paarl body initializer contract for {arena.key}")
    pattern = re.compile(
        rf"(?m)^    \$InitializeEvent\([^\n]*, {arena.part_routine_event}(?:, [^\n]*)?\);\n?"
    )
    matches = pattern.findall(event_zero)
    if len(matches) != expected_target_initializers:
        raise ValueError("destination body initializer witness count drift")
    event_zero = pattern.sub("", event_zero)
    for source_binding in PAARL_PACKAGE.part_bindings:
        witness = _initializer_line(source_binding.slot, PAARL_PACKAGE.part_routine_event,
                                    source_binding.arguments)
        if donor_zero.count(witness) != 1:
            raise ValueError("Paarl Event(0) lacks unique body initializer witness")
        if not event_zero.endswith("\n});"):
            raise ValueError("destination Event(0) has no canonical closing delimiter")
        event_zero = event_zero[:-3] + "\n" + _initializer_line(
            source_binding.slot, target, source_binding.arguments) + "\n});"
    copied = _remap_declared_literals(
        donor_blocks[PAARL_PACKAGE.part_routine_event],
        actor=(PAARL_PACKAGE.actor, arena.actor),
        completion=(PAARL_PACKAGE.completion_event, arena.completion_event),
        event=(PAARL_PACKAGE.part_routine_event, target),
    )
    return event_zero, target, copied


def _paarl_appended_body_patch(arena: ArenaContract, donor: CombatPackage,
                               destination: str, donor_source: str) -> str:
    """Use a declared spare ID for Paarl limbs where target part slots differ."""
    original, donor_blocks = event_blocks(destination), event_blocks(donor_source)
    _verify_pins("arena", original, arena.expected)
    _verify_pins("donor", donor_blocks, donor.expected)
    if donor is not PAARL_PACKAGE or arena not in (AMYGDALA_ARENA, EBRIETAS_ARENA):
        raise ValueError(f"no appended Paarl body contract for {arena.key}")
    event_zero, body_event, copied_body = _append_paarl_body_routine(
        original[0], arena, donor_blocks)
    edits = {
        0: event_zero,
        arena.activation_event: _paarl_activation(arena, original[arena.activation_event]),
        arena.health_bar_event: _replace_once(
            original[arena.health_bar_event],
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label})",
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {donor.health_bar_label})",
            "Paarl health-bar label"),
        arena.part_routine_event: _end_event(original[arena.part_routine_event]),
    }
    if arena.cloth_routine_event is not None:
        edits[arena.cloth_routine_event] = _end_event(original[arena.cloth_routine_event])
    if arena.phase_music_message is None:
        raise ValueError(f"{arena.key} has no Paarl phase-music witness")
    edits[arena.music_event] = _replace_once(
        original[arena.music_event],
        f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})",
        f"CharacterHasEventMessage({arena.actor}, {donor.phase_music_message})",
        "Paarl phase-music message")
    lockcam = _remap_declared_literals(
        donor_blocks[donor.lockcam_event], actor=(donor.actor, arena.actor),
        completion=(donor.completion_event, arena.completion_event),
        event=(donor.lockcam_event, arena.lockcam_event))
    edits[arena.lockcam_event] = _remap_lockcam(lockcam, arena, donor)
    edits[arena.phase_slots[0]] = _remap_declared_literals(
        donor_blocks[donor.phase_events[0]], actor=(donor.actor, arena.actor),
        completion=(donor.completion_event, arena.completion_event),
        event=(donor.phase_events[0], arena.phase_slots[0]))
    for event_id in arena.phase_slots[1:]:
        edits[event_id] = _end_event(original[event_id])
    edits[arena.co_op_entry_event] = _remap_declared_literals(
        donor_blocks[donor.co_op_entry_event], actor=(donor.actor, arena.actor),
        completion=(donor.completion_event, arena.completion_event),
        event=(donor.co_op_entry_event, arena.co_op_entry_event),
        flags=((donor.start_flag, arena.start_flag), (donor.activation_event, arena.activation_event)))
    _retire_unreused_attachment_anchor(arena, original, edits)
    result = _replace_event(destination, edits).rstrip() + "\n\n" + copied_body + "\n"
    output = event_blocks(result)
    if set(output) != set(original) | {body_event}:
        raise ValueError("appended Paarl body contract changed event identity")
    for event_id in original:
        if event_id not in edits and output[event_id] != original[event_id]:
            raise ValueError(f"appended Paarl body contract touched unrelated arena event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("appended Paarl body contract changed destination completion event")
    return result


def _bsb_activation(arena: ArenaContract, original: str) -> str:
    if arena is not PAARL_ARENA:
        raise ValueError(f"no BSB activation contract for arena {arena.key}")
    for instruction in (
        "    SetCharacterInvincibility(2300810, Enabled);\n",
        "    ForceAnimationPlayback(2300810, 7000, true, false, false);\n",
        "    WaitFixedTimeFrames(70);\n",
        "    SetCharacterInvincibility(2300810, Disabled);\n",
    ):
        original = _replace_once(original, instruction, "", "Paarl-only activation instruction")
    return original


def _collapse_part_initializers(event_zero: str, arena: ArenaContract) -> str:
    """Replace five exact limb calls with BSB's one zero-argument phase call."""
    bindings = arena.part_slots
    if len(bindings) != 5:
        raise ValueError("BSB contract requires five destination limb initializers")
    for index, binding in enumerate(bindings):
        old = "    $InitializeEvent(" + ", ".join(
            (str(binding.slot), str(arena.part_routine_event), *binding.arguments)) + ");"
        new = f"    $InitializeEvent(0, {arena.part_routine_event});" if index == 0 else ""
        event_zero = _replace_once(event_zero, old, new, f"destination limb initializer {binding.slot}")
    return event_zero


def _bsb_patch(arena: ArenaContract, donor: CombatPackage,
               destination: str, donor_source: str) -> str:
    original, donor_blocks = event_blocks(destination), event_blocks(donor_source)
    _verify_pins("arena", original, arena.expected)
    _verify_pins("donor", donor_blocks, donor.expected)
    if arena is not PAARL_ARENA or donor is not BSB_PACKAGE:
        raise ValueError(f"no typed BSB adapter for {arena.key} <- {donor.key}")
    edits: dict[int, str] = {
        arena.activation_event: _bsb_activation(arena, original[arena.activation_event]),
        arena.health_bar_event: _replace_once(
            original[arena.health_bar_event],
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label})",
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {donor.health_bar_label})", "health-bar label"),
        arena.music_event: _replace_once(
            original[arena.music_event],
            f"chrFlagArea &= CharacterHasEventMessage({arena.actor}, 20);",
            f"chrFlagArea &= EventFlag({arena.part_routine_event});", "BSB phase-two music trigger"),
    }
    for source_event, destination_event in zip(donor.phase_events, arena.phase_slots):
        edits[destination_event] = _remap_declared_literals(
            donor_blocks[source_event], actor=(donor.actor, arena.actor),
            completion=(donor.completion_event, arena.completion_event), event=(source_event, destination_event),
            flags=((12304807, arena.phase_slots[0]),))
    edits[arena.co_op_entry_event] = _remap_declared_literals(
        donor_blocks[12301803], actor=(donor.actor, arena.actor),
        completion=(donor.completion_event, arena.completion_event), event=(12301803, arena.co_op_entry_event),
        flags=((donor.start_flag, arena.start_flag), (donor.activation_event, arena.activation_event)))
    lockcam = _remap_declared_literals(
        donor_blocks[12304804], actor=(donor.actor, arena.actor),
        completion=(donor.completion_event, arena.completion_event), event=(12304804, arena.lockcam_event),
        flags=((donor.start_flag, arena.start_flag), (12304801, 12304701)))
    edits[arena.lockcam_event] = lockcam
    edits[0] = _collapse_part_initializers(original[0], arena)
    result = _replace_event(destination, edits)
    output = event_blocks(result)
    if original.keys() != output.keys():
        raise ValueError("contract changed arena event identity set")
    for event_id in original:
        if event_id not in edits and original[event_id] != output[event_id]:
            raise ValueError(f"contract touched unrelated arena event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("contract changed destination completion event")
    return result


def _bsb_phase_slot_patch(arena: ArenaContract, donor: CombatPackage,
                          destination: str, donor_source: str) -> str:
    """Put BSB's two pinned phases into a compatible arena's existing slots."""
    original, donor_blocks = event_blocks(destination), event_blocks(donor_source)
    _verify_pins("arena", original, arena.expected)
    _verify_pins("donor", donor_blocks, donor.expected)
    if donor is not BSB_PACKAGE or len(arena.phase_slots) != len(donor.phase_events):
        raise ValueError(f"no BSB phase-slot contract for {arena.key}")
    edits = {
        arena.health_bar_event: _replace_once(
            original[arena.health_bar_event],
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label})",
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {donor.health_bar_label})",
            "BSB health-bar label"),
    }
    if arena is AMYGDALA_ARENA:
        edits[arena.activation_event] = _amygdala_arena_activation(
            arena, donor, original[arena.activation_event])
    if arena.phase_music_message is None:
        raise ValueError(f"{arena.key} has no BSB phase-music witness")
    edits[arena.music_event] = _replace_once(
        original[arena.music_event],
        f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})",
        f"CharacterHasEventMessage({arena.actor}, 20)",
        "BSB phase-two music trigger")
    for source_event, destination_event in zip(donor.phase_events, arena.phase_slots):
        edits[destination_event] = _remap_declared_literals(
            donor_blocks[source_event], actor=(donor.actor, arena.actor),
            completion=(donor.completion_event, arena.completion_event),
            event=(source_event, destination_event),
            flags=((12304807, arena.phase_slots[0]),))
    for event_id in (arena.part_routine_event, arena.cloth_routine_event):
        if event_id is not None:
            edits[event_id] = _end_event(original[event_id])
    _retire_unreused_attachment_anchor(arena, original, edits)
    result = _replace_event(destination, edits)
    output = event_blocks(result)
    if set(output) != set(original):
        raise ValueError("BSB phase-slot contract changed event identity")
    for event_id in original:
        if event_id not in edits and output[event_id] != original[event_id]:
            raise ValueError(f"BSB phase-slot contract touched unrelated arena event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("BSB phase-slot contract changed destination completion event")
    return result


def _bsb_at_ebrietas_patch(arena: ArenaContract, donor: CombatPackage,
                            destination: str, donor_source: str) -> str:
    """Use Ebrietas's local fog/camera while replacing her combat-only graph.

    The two declared Ebrietas phase slots are both zero-argument Event(0)
    calls.  They therefore accept BSB's two source phases without adding
    event identities or inventing constructor bindings.  BSB emits messages
    10 and 20, which the retained Ebrietas camera already consumes.
    """
    original, donor_blocks = event_blocks(destination), event_blocks(donor_source)
    _verify_pins("arena", original, arena.expected)
    _verify_pins("donor", donor_blocks, donor.expected)
    if arena is not EBRIETAS_ARENA or donor is not BSB_PACKAGE:
        raise ValueError(f"no typed BSB adapter for {arena.key} <- {donor.key}")
    edits = {
        arena.activation_event: _ebrietas_arena_activation(
            arena, donor, original[arena.activation_event]),
        arena.health_bar_event: _replace_once(
            original[arena.health_bar_event],
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label})",
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {donor.health_bar_label})",
            "BSB health-bar label"),
        # BSB's source music moves to its second (message-20) phase.  Keep the
        # destination map's two sound IDs and all fog/client predicates local.
        arena.music_event: _replace_once(
            original[arena.music_event],
            f"CharacterHasEventMessage({arena.actor}, 100)",
            f"CharacterHasEventMessage({arena.actor}, 20)",
            "BSB phase-two music trigger"),
        arena.part_routine_event: _end_event(original[arena.part_routine_event]),
        arena.cloth_routine_event: _end_event(original[arena.cloth_routine_event]),
    }
    for source_event, destination_event in zip(donor.phase_events, arena.phase_slots):
        edits[destination_event] = _remap_declared_literals(
            donor_blocks[source_event], actor=(donor.actor, arena.actor),
            completion=(donor.completion_event, arena.completion_event),
            event=(source_event, destination_event),
            flags=((12304807, arena.phase_slots[0]),))
    result = _replace_event(destination, edits)
    output = event_blocks(result)
    if original.keys() != output.keys():
        raise ValueError("BSB/Ebrietas contract changed arena event identity set")
    for event_id in original:
        if event_id not in edits and output[event_id] != original[event_id]:
            raise ValueError(f"BSB/Ebrietas contract touched unrelated arena event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("BSB/Ebrietas contract changed Ebrietas completion/progression")
    return result


def _amygdala_wake_after_entry(arena: ArenaContract) -> str:
    """Amygdala's source-pinned post-entry animation and geometry reset."""
    return (
        f"    SetEventFlag({arena.start_flag}, ON);\n"
        f"    ForceAnimationPlayback({arena.actor}, 7006, false, false, false);\n"
        "    WaitFixedTimeFrames(30);\n"
        f"    ForceAnimationPlayback({arena.actor}, 7002, false, false, false);\n"
        "    WaitFixedTimeFrames(160);\n"
        f"    SetCharacterGravity({arena.actor}, Enabled);\n"
        f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
        f"    SetCharacterMaphits({arena.actor}, false);\n"
    )


def _amygdala_at_cleric_activation(arena: ArenaContract, original: str) -> str:
    """Keep Cleric's fog/warp trigger around Amygdala's full wake-up body."""
    pre = (f"    SetCharacterInvincibility({arena.actor}, Enabled);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7003, true, false, false);\n")
    original = _replace_once(original, f"    SetCharacterMaphits({arena.actor}, true);\n",
                             pre, "Amygdala pre-entry sequence")
    old = (f"    ForceAnimationPlayback({arena.actor}, 3028, false, false, false);\n"
           "    WaitFixedTimeFrames(110);\n"
           f"    SetCharacterGravity({arena.actor}, Enabled);\n"
           f"    SetCharacterMaphits({arena.actor}, false);\n"
           f"    SetEventFlag({arena.start_flag}, ON);\n")
    return _replace_once(original, old, _amygdala_wake_after_entry(arena),
                         "Amygdala post-warp wake-up")


def _amygdala_at_bsb_activation(arena: ArenaContract, original: str) -> str:
    """Keep BSB's host/fog predicate around Amygdala's full wake-up body."""
    pre = (f"    SetCharacterMaphits({arena.actor}, true);\n"
           f"    SetCharacterGravity({arena.actor}, Disabled);\n"
           f"    SetCharacterInvincibility({arena.actor}, Enabled);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7003, true, false, false);\n")
    original = _replace_once(original, "    WaitFor(\n", pre + "    WaitFor(\n",
                             "Amygdala pre-entry sequence")
    old = (f"    ForceAnimationPlayback({arena.actor}, 7001, false, false, false);\n"
           f"    SetEventFlag({arena.start_flag}, ON);\n")
    return _replace_once(original, old, _amygdala_wake_after_entry(arena),
                         "Amygdala post-entry wake-up")


def _amygdala_at_paarl_activation(arena: ArenaContract, original: str) -> str:
    """Apply Amygdala's pinned 7003/7006/7002 entry sequence at Paarl."""
    for instruction in (
        f"    SetCharacterInvincibility({arena.actor}, Enabled);\n",
        f"    ForceAnimationPlayback({arena.actor}, 7000, true, false, false);\n",
    ):
        original = _replace_once(original, instruction, "", "Paarl-only activation instruction")
    original = _replace_once(
        original, "    WaitFor(\n",
        f"    SetCharacterMaphits({arena.actor}, true);\n"
        f"    SetCharacterGravity({arena.actor}, Disabled);\n"
        f"    SetCharacterInvincibility({arena.actor}, Enabled);\n"
        f"    ForceAnimationPlayback({arena.actor}, 7003, true, false, false);\n"
        "    WaitFor(\n", "Amygdala pre-entry sequence")
    old = (f"    ForceAnimationPlayback({arena.actor}, 7001, false, false, false);\n"
           "    WaitFixedTimeFrames(70);\n"
           f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
           f"    SetEventFlag({arena.start_flag}, ON);\n")
    new = (f"    SetEventFlag({arena.start_flag}, ON);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7006, false, false, false);\n"
           "    WaitFixedTimeFrames(30);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7002, false, false, false);\n"
           "    WaitFixedTimeFrames(160);\n"
           f"    SetCharacterGravity({arena.actor}, Enabled);\n"
           f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
           f"    SetCharacterMaphits({arena.actor}, false);\n")
    return _replace_once(original, old, new, "Amygdala post-entry sequence")


def _ebrietas_pre_damage_guard(arena: ArenaContract) -> str:
    """Pinned Ebrietas protection which precedes every entry trigger."""
    return (
        f"    ForceAnimationPlayback({arena.actor}, 7001, true, false, false);\n"
        f"    SetCharacterImmortality({arena.actor}, Enabled);\n"
        f"    SetSpEffect({arena.actor}, 5647, false);\n"
    )


def _ebrietas_wake_after_damage(arena: ArenaContract) -> str:
    """Pinned Ebrietas wake-up body following the first player damage."""
    return (
        f"    WaitFor(HasDamageType({arena.actor}, 10000, DamageType.Unspecified));\n"
        f"    ForceAnimationPlayback({arena.actor}, 7000, false, true, false);\n"
        f"    SetCharacterImmortality({arena.actor}, Disabled);\n"
        f"    ClearSpEffect({arena.actor}, 5647);\n"
        f"    SetEventFlag({arena.start_flag}, ON);\n"
    )


def _ebrietas_activation(arena: ArenaContract, original: str) -> str:
    """Keep a destination entry set-piece around Ebrietas's pinned wake-up."""
    pre = _ebrietas_pre_damage_guard(arena)
    wake = _ebrietas_wake_after_damage(arena)
    if arena is BSB_ARENA:
        original = _replace_once(original, "    WaitFor(\n", pre + "    WaitFor(\n",
                                 "BSB-to-Ebrietas pre-entry protection")
        return _replace_once(
            original,
            f"    ForceAnimationPlayback({arena.actor}, 7001, false, false, false);\n"
            f"    SetEventFlag({arena.start_flag}, ON);\n",
            wake,
            "BSB-to-Ebrietas post-entry sequence",
        )
    if arena is PAARL_ARENA:
        for instruction in (
            f"    SetCharacterInvincibility({arena.actor}, Enabled);\n",
            f"    ForceAnimationPlayback({arena.actor}, 7000, true, false, false);\n",
        ):
            original = _replace_once(original, instruction, "", "Paarl-only activation instruction")
        original = _replace_once(original, "    WaitFor(\n", pre + "    WaitFor(\n",
                                 "Paarl-to-Ebrietas pre-entry protection")
        return _replace_once(
            original,
            f"    ForceAnimationPlayback({arena.actor}, 7001, false, false, false);\n"
            "    WaitFixedTimeFrames(70);\n"
            f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
            f"    SetEventFlag({arena.start_flag}, ON);\n",
            "    WaitFixedTimeFrames(70);\n" + wake,
            "Paarl-to-Ebrietas post-entry sequence",
        )
    if arena is CLERIC_ARENA:
        original = _replace_once(original, "    WaitFor(\n", pre + "    WaitFor(\n",
                                 "Cleric-to-Ebrietas pre-entry protection")
        return _replace_once(
            original,
            f"    ForceAnimationPlayback({arena.actor}, 3028, false, false, false);\n"
            "    WaitFixedTimeFrames(110);\n"
            f"    SetCharacterGravity({arena.actor}, Enabled);\n"
            f"    SetCharacterMaphits({arena.actor}, false);\n"
            f"    SetEventFlag({arena.start_flag}, ON);\n",
            "    WaitFixedTimeFrames(110);\n"
            f"    SetCharacterGravity({arena.actor}, Enabled);\n"
            f"    SetCharacterMaphits({arena.actor}, false);\n" + wake,
            "Cleric-to-Ebrietas post-entry sequence",
        )
    if arena is AMELIA_ARENA:
        original = _replace_once(original, "    WaitFor(\n", pre + "    WaitFor(\n",
                                 "Amelia-to-Ebrietas pre-entry protection")
        return _replace_once(
            original,
            f"    ForceAnimationPlayback({arena.actor}, 7000, false, false, false);\n"
            f"    ForceAnimationPlayback({arena.actor}, 7001, false, false, false);\n"
            f"    SetEventFlag({arena.start_flag}, ON);\n",
            wake,
            "Amelia-to-Ebrietas post-cutscene sequence",
        )
    if arena is AMYGDALA_ARENA:
        original = _replace_once(
            original,
            f"    SetCharacterMaphits({arena.actor}, true);\n"
            f"    SetCharacterGravity({arena.actor}, Disabled);\n"
            f"    SetCharacterInvincibility({arena.actor}, Enabled);\n"
            f"    ForceAnimationPlayback({arena.actor}, 7003, true, false, false);\n",
            f"    SetCharacterMaphits({arena.actor}, true);\n"
            f"    SetCharacterGravity({arena.actor}, Disabled);\n" + pre,
            "Amygdala-only pre-entry sequence",
        )
        return _replace_once(
            original,
            f"    SetEventFlag({arena.start_flag}, ON);\n"
            f"    ForceAnimationPlayback({arena.actor}, 7006, false, false, false);\n"
            "    WaitFixedTimeFrames(30);\n"
            f"    ForceAnimationPlayback({arena.actor}, 7002, false, false, false);\n"
            "    WaitFixedTimeFrames(160);\n"
            f"    SetCharacterGravity({arena.actor}, Enabled);\n"
            f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
            f"    SetCharacterMaphits({arena.actor}, false);\n",
            f"    SetCharacterGravity({arena.actor}, Enabled);\n"
            f"    SetCharacterMaphits({arena.actor}, false);\n" + wake,
            "Amygdala-to-Ebrietas post-entry sequence",
        )
    raise ValueError(f"no Ebrietas activation contract for {arena.key}")


def _amygdala_at_ebrietas_activation(arena: ArenaContract, original: str) -> str:
    """Keep Ebrietas's damage trigger and transplant Amygdala's wake-up body."""
    for instruction in (
        f"    ForceAnimationPlayback({arena.actor}, 7001, true, false, false);\n",
        f"    SetCharacterImmortality({arena.actor}, Enabled);\n",
        f"    SetSpEffect({arena.actor}, 5647, false);\n",
    ):
        original = _replace_once(original, instruction, "", "Ebrietas-only pre-entry instruction")
    original = _replace_once(
        original, "    WaitFor(\n",
        f"    SetCharacterMaphits({arena.actor}, true);\n"
        f"    SetCharacterGravity({arena.actor}, Disabled);\n"
        f"    SetCharacterInvincibility({arena.actor}, Enabled);\n"
        f"    ForceAnimationPlayback({arena.actor}, 7003, true, false, false);\n"
        "    WaitFor(\n", "Amygdala pre-entry sequence")
    old = (f"    ForceAnimationPlayback({arena.actor}, 7000, false, true, false);\n"
           f"    SetCharacterImmortality({arena.actor}, Disabled);\n"
           f"    ClearSpEffect({arena.actor}, 5647);\n"
           f"    SetEventFlag({arena.start_flag}, ON);\n")
    new = (f"    SetEventFlag({arena.start_flag}, ON);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7006, false, false, false);\n"
           "    WaitFixedTimeFrames(30);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7002, false, false, false);\n"
           "    WaitFixedTimeFrames(160);\n"
           f"    SetCharacterGravity({arena.actor}, Enabled);\n"
           f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
           f"    SetCharacterMaphits({arena.actor}, false);\n")
    return _replace_once(original, old, new, "Amygdala post-entry sequence")


def _amygdala_at_amelia_activation(arena: ArenaContract, original: str) -> str:
    """Keep Amelia's cutscene and substitute Amygdala's witnessed wake-up."""
    original = _replace_once(
        original, "    SetObjectInvulnerability(2400801, Enabled);\n    WaitFor(\n",
        "    SetObjectInvulnerability(2400801, Enabled);\n"
        f"    SetCharacterMaphits({arena.actor}, true);\n"
        f"    SetCharacterGravity({arena.actor}, Disabled);\n"
        f"    SetCharacterInvincibility({arena.actor}, Enabled);\n"
        f"    ForceAnimationPlayback({arena.actor}, 7003, true, false, false);\n"
        "    WaitFor(\n", "Amygdala pre-cutscene wake-up sequence")
    old = (f"    ForceAnimationPlayback({arena.actor}, 7000, false, false, false);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7001, false, false, false);\n"
           f"    SetEventFlag({arena.start_flag}, ON);\n")
    new = (f"    SetEventFlag({arena.start_flag}, ON);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7006, false, false, false);\n"
           "    WaitFixedTimeFrames(30);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7002, false, false, false);\n"
           "    WaitFixedTimeFrames(160);\n"
           f"    SetCharacterGravity({arena.actor}, Enabled);\n"
           f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
           f"    SetCharacterMaphits({arena.actor}, false);\n")
    return _replace_once(original, old, new, "Amygdala post-cutscene wake-up sequence")


def _ebrietas_arena_activation(arena: ArenaContract, donor: CombatPackage,
                               original: str) -> str:
    """Keep only Ebrietas's portable immortal damage gate around donor entry."""
    for instruction in (
        f"    ForceAnimationPlayback({arena.actor}, 7001, true, false, false);\n",
        f"    SetSpEffect({arena.actor}, 5647, false);\n",
    ):
        original = _replace_once(original, instruction, "", "Ebrietas-only pre-wake state")
    old = (f"    ForceAnimationPlayback({arena.actor}, 7000, false, true, false);\n"
           f"    SetCharacterImmortality({arena.actor}, Disabled);\n"
           f"    ClearSpEffect({arena.actor}, 5647);\n"
           f"    SetEventFlag({arena.start_flag}, ON);\n")
    new = (f"    ForceAnimationPlayback({arena.actor}, {donor.entry_animation}, false, false, false);\n"
           f"    SetCharacterImmortality({arena.actor}, Disabled);\n"
           f"    SetEventFlag({arena.start_flag}, ON);\n")
    return _replace_once(original, old, new, "Ebrietas-only post-entry sequence")


def _amygdala_arena_activation(arena: ArenaContract, donor: CombatPackage,
                               original: str) -> str:
    """Keep Amygdala's pre-entry invincibility while dropping model motions."""
    for instruction in (
        f"    SetCharacterMaphits({arena.actor}, true);\n",
        f"    SetCharacterGravity({arena.actor}, Disabled);\n",
        f"    ForceAnimationPlayback({arena.actor}, 7003, true, false, false);\n",
    ):
        original = _replace_once(original, instruction, "", "Amygdala-only pre-entry instruction")
    old = (f"    SetEventFlag({arena.start_flag}, ON);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7006, false, false, false);\n"
           "    WaitFixedTimeFrames(30);\n"
           f"    ForceAnimationPlayback({arena.actor}, 7002, false, false, false);\n"
           "    WaitFixedTimeFrames(160);\n"
           f"    SetCharacterGravity({arena.actor}, Enabled);\n"
           f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
           f"    SetCharacterMaphits({arena.actor}, false);\n")
    new = (f"    ForceAnimationPlayback({arena.actor}, {donor.entry_animation}, false, false, false);\n"
           f"    SetEventFlag({arena.start_flag}, ON);\n"
           f"    SetCharacterInvincibility({arena.actor}, Disabled);\n")
    return _replace_once(original, old, new, "Amygdala-only post-entry sequence")


def _attached_single_actor_activation(arena: ArenaContract, donor: CombatPackage,
                                      original: str) -> str:
    """Retain reviewed arena entry geometry and use the donor's pinned wake-up."""
    if donor.key == "amygdala":
        if arena.key == CLERIC_ARENA.key:
            return _amygdala_at_cleric_activation(arena, original)
        if arena.key == BSB_ARENA.key:
            return _amygdala_at_bsb_activation(arena, original)
        if arena.key == PAARL_ARENA.key:
            return _amygdala_at_paarl_activation(arena, original)
        if arena.key == EBRIETAS_ARENA.key:
            return _amygdala_at_ebrietas_activation(arena, original)
        if arena.key == AMELIA_ARENA.key:
            return _amygdala_at_amelia_activation(arena, original)
        raise ValueError(f"no Amygdala entry adapter for {arena.key}")
    if donor.key == "ebrietas":
        return _ebrietas_activation(arena, original)
    if (not donor.generic_activation or donor.entry_animation is None
            or arena.activation_idle_animation is None):
        raise ValueError(f"{donor.key} package lacks a generic activation contract")
    if arena.key == AMYGDALA_ARENA.key:
        return _amygdala_arena_activation(arena, donor, original)
    if arena.key == EBRIETAS_ARENA.key:
        return _ebrietas_arena_activation(arena, donor, original)
    if arena.key == PAARL_ARENA.key:
        # The source donor does not own Paarl's animation, but the local
        # invincibility window keeps the disabled actor safe until its
        # destination radius trigger has completed.
        original = _replace_once(
            original,
            f"    ForceAnimationPlayback({arena.actor}, 7000, true, false, false);\n",
            "",
            "Paarl-only activation animation",
        )
    return _replace_once(
        original,
        f"ForceAnimationPlayback({arena.actor}, {arena.activation_idle_animation}, false, false, false);",
        f"ForceAnimationPlayback({arena.actor}, {donor.entry_animation}, false, false, false);",
        "donor entry animation")


def _attached_single_actor_patch(arena: ArenaContract, donor: CombatPackage,
                                 destination: str, donor_source: str, *,
                                 allow_materialized_actor_additions: bool) -> str:
    """Attach a pinned single-actor combat package into an m23 arena.

    The destination's fog, start flag, co-op entry and completion/reward body
    remain local.  Source routines receive declared project event IDs;
    the Event(0) calls are copied only after checking their original witness.
    """
    original, donor_blocks = event_blocks(destination), event_blocks(donor_source)
    _verify_pins("arena", original, arena.expected)
    _verify_pins("donor", donor_blocks, donor.expected)
    capability = contract_capability(arena, donor)
    if capability is None or capability.adapter not in {
            "generic-attachment", "amygdala-entry", "ebrietas-entry"}:
        raise ValueError(f"no attachment adapter for {arena.key} <- {donor.key}")
    if (any(binding.requires_actor_addition for binding in donor.virtual_entities)
            and not allow_materialized_actor_additions):
        raise ValueError(f"{donor.key} requires a materialized actor addition")
    targets = _attachment_targets(arena, donor, destination)
    virtual_targets = _virtual_entity_targets(arena, donor, destination)
    edits: dict[int, str] = {
        arena.activation_event: _attached_single_actor_activation(arena, donor, original[arena.activation_event]),
        arena.health_bar_event: _replace_once(
            original[arena.health_bar_event],
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label})",
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {donor.health_bar_label})",
            "donor health-bar label"),
        0: _attach_initializers(original[0], arena, donor, targets, virtual_targets, donor_blocks[0]),
    }
    if arena.phase_music_event_flag is not None:
        edits[arena.music_event] = _replace_once(
            original[arena.music_event],
            f"flagArea2 &= EventFlag({arena.phase_music_event_flag});",
            f"flagArea2 &= CharacterHasEventMessage({arena.actor}, {donor.phase_music_message});",
            "donor phase music trigger")
    elif arena.phase_music_message is not None:
        edits[arena.music_event] = _replace_once(
            original[arena.music_event],
            f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})",
            f"CharacterHasEventMessage({arena.actor}, {donor.phase_music_message})",
            "donor phase music trigger")
    else:
        raise ValueError(f"arena {arena.key} has no declared phase music trigger")
    lockcam = _remap_declared_literals(
        donor_blocks[donor.lockcam_event], actor=(donor.actor, arena.actor),
        completion=(donor.completion_event, arena.completion_event),
        event=(donor.lockcam_event, arena.lockcam_event))
    edits[arena.lockcam_event] = _remap_lockcam(lockcam, arena, donor)
    # Old BSB/Paarl phase and limb entries would otherwise run concurrently
    # against the new actor. Their Event(0) callers are intentionally left in
    # place except for the one declared attachment anchor.
    for event_id in {*arena.phase_slots, arena.part_routine_event, arena.cloth_routine_event}:
        if event_id is None:
            continue
        edits[event_id] = _end_event(original[event_id])

    result = _replace_event(destination, edits)
    result = _append_attachment_events(result, donor_blocks, donor, arena, targets, virtual_targets)
    output = event_blocks(result)
    if set(output) != set(original) | set(targets.values()):
        raise ValueError("single-actor contract changed an unexpected event identity")
    for event_id in original:
        if event_id not in edits and original[event_id] != output[event_id]:
            raise ValueError(f"single-actor contract touched unrelated arena event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("single-actor contract changed destination completion event")
    return result


def patch_contract_swap(arena: ArenaContract, donor: CombatPackage,
                        destination: str, donor_source: str, *,
                        allow_materialized_actor_additions: bool = False) -> str:
    """Build one checked arena overlay from one independently declared donor."""
    capability = contract_capability(arena, donor)
    if capability is None:
        raise ValueError(f"no complete contract capability for {arena.key} <- {donor.key}")
    if capability.adapter == "legacy-canary":
        _verify_pins("arena", event_blocks(destination), arena.expected)
        _verify_pins("donor", event_blocks(donor_source), donor.expected)
        return boss_canary.patch_event_source(destination, donor_source)
    if capability.adapter == "paarl-entry":
        return _paarl_patch(arena, donor, destination, donor_source)
    if capability.adapter == "bsb-entry":
        return _bsb_patch(arena, donor, destination, donor_source)
    if capability.adapter == "bsb-ebrietas-entry":
        return _bsb_at_ebrietas_patch(arena, donor, destination, donor_source)
    if capability.adapter == "bsb-phase-slots":
        return _bsb_phase_slot_patch(arena, donor, destination, donor_source)
    if capability.adapter == "paarl-appended-body":
        return _paarl_appended_body_patch(arena, donor, destination, donor_source)
    if capability.adapter in {"generic-attachment", "amygdala-entry", "ebrietas-entry"}:
        return _attached_single_actor_patch(
            arena, donor, destination, donor_source,
            allow_materialized_actor_additions=allow_materialized_actor_additions)
    raise ValueError(f"no typed adapter implementation for {arena.key} <- {donor.key}")


def _mapping(arena: ArenaContract, donor: CombatPackage) -> dict:
    attachments = (dict(zip((attachment.source_event for attachment in donor.attachments),
                            arena.attachment_event_ids)) if donor.attachments else {})
    capability = contract_capability(arena, donor)
    appended_body = ({donor.part_routine_event: arena.attachment_event_ids[-1]}
                     if capability is not None and capability.adapter == "paarl-appended-body"
                     else {})
    phase_map = ({event_id: attachments[event_id] for event_id in donor.phase_events
                  if event_id in attachments} if attachments
                 else dict(zip(donor.phase_events, arena.phase_slots)))
    virtual_entities = dict(zip((binding.source_entity for binding in donor.virtual_entities),
                                arena.virtual_entity_ids))
    return {
        "actor": {str(donor.actor): arena.actor},
        "completion_event": {str(donor.completion_event): arena.completion_event},
        "encounter_start_flag": {str(donor.start_flag): arena.start_flag},
        "phase_events": {str(source): target for source, target in phase_map.items()},
        "co_op_entry_event": None if donor.co_op_entry_event is None else {
            str(donor.co_op_entry_event): arena.co_op_entry_event,
        },
        "part_routine": None if donor.part_routine_event is None else {
            str(donor.part_routine_event): appended_body.get(
                donor.part_routine_event,
                attachments.get(donor.part_routine_event, arena.part_routine_event)),
        },
        "added_events": {str(source): target for source, target in
                         {**attachments, **appended_body}.items()},
        "virtual_entities": {str(source): target for source, target in virtual_entities.items()},
    }


def plan_contract_shuffle(seed: str, arena: ArenaContract = CLERIC_ARENA,
                          packages: Iterable[CombatPackage] = CLERIC_PACKAGES) -> dict:
    """Choose an arena-compatible donor deterministically, independent of legacy plans."""
    choices = sorted(tuple(packages), key=lambda package: package.key)
    if not choices:
        raise ValueError("no combat packages registered for this arena")
    donor = random.Random(f"bb-boss-contract-v1:{seed}:{arena.key}").choice(choices)
    return {
        "format": "bb-boss-contract-plan-v1",
        "dry_run": True,
        "status": "planned",
        "writer_status": "not_written",
        "seed": seed,
        "arena": arena.key,
        "donor": donor.key,
        "event_files": {"arena": arena.event_file, "donor": donor.event_file},
        "health_bar": {"event": arena.health_bar_event, "label": donor.health_bar_label,
                       "evidence": f"literal DisplayBossHealthBar operand in donor event {donor.health_bar_event}"},
        "remap": _mapping(arena, donor),
        "part_initializers": [asdict(binding) for binding in donor.part_bindings],
        "attachments": [
            {"source_event": attachment.source_event,
             "destination_event": arena.attachment_event_ids[index],
             "initializers": [asdict(binding) for binding in attachment.initializers]}
            for index, attachment in enumerate(donor.attachments)
        ],
        "virtual_entities": [
            {"source_entity": binding.source_entity,
             "destination_entity": arena.virtual_entity_ids[index],
             "initializer": binding.initializer,
             "requires_actor_addition": binding.requires_actor_addition}
            for index, binding in enumerate(donor.virtual_entities)
        ],
        "arena_hash_pins": dict(sorted(arena.expected.items())),
        "donor_hash_pins": dict(sorted(donor.expected.items())),
    }


def plan_contract_swap(arena: ArenaContract, donor: CombatPackage, slots, npcs, effects,
                       seed: str) -> dict:
    """Build the native map-swap and scaling plan for one typed contract pair.

    The event builder consumes the separate contract metadata.  This function
    intentionally emits the existing writer's ``bb-enemizer-plan-v2`` map and
    scaling shape so its map provenance checks continue to apply.
    """
    if contract_capability(arena, donor) is None:
        raise ValueError(f"no complete contract capability for {arena.key} <- {donor.key}")
    destinations = sorted(
        (slot for slot in slots if slot.entity_id == arena.actor and slot.map_name.startswith(arena.map_prefix)),
        key=lambda slot: slot.key,
    )
    donors = [slot for slot in slots if slot.entity_id == donor.actor and slot.map_name.startswith(donor.map_prefix)]
    if (len(destinations) != arena.destination_count or not donors
            or any(slot.archetype != arena.archetype for slot in destinations)
            or any(slot.archetype != donor.archetype for slot in donors)):
        raise ValueError(f"unsupported boss placement provenance for {arena.key} <- {donor.key}")
    if (len({slot.logical_key for slot in destinations}) != 1
            or any(slot.dummy or slot.talk_id or slot.archetype.chara_init_id for slot in destinations + donors)):
        raise ValueError(f"boss contract {arena.key} <- {donor.key} requires ordinary non-talk-bound placements")
    swap = Swap(
        destinations[0].logical_key, [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations}, arena.archetype, donor.archetype,
        warnings=["experimental boss contract; runtime entrance, phases and AP completion require validation"],
        destinations={slot.key: {"map_name": slot.map_name, "entity_id": slot.entity_id,
                                 "x": slot.x, "y": slot.y, "z": slot.z} for slot in destinations},
    )
    changes, skips = plan_scaling([swap], destinations, npcs, effects, boss_tiers=True)
    if len(changes) > 1 or (changes and skips):
        raise ValueError(f"boss contract {arena.key} <- {donor.key} has an ambiguous normalization plan")
    requirements = actor_addition_requirements(arena, donor, slots)
    primary_initializations = primary_initialization_requirements(arena, donor, slots)
    plan = {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"{arena.key}<-{donor.key}"},
        "boss_contract": plan_contract_shuffle(seed, arena, (donor,)),
        "scaling": {"enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes), "changes": [change.json() for change in changes],
                    "skip_count": len(skips), "skips": skips},
    }
    if requirements:
        plan["boss_actor_addition_requirements"] = requirements
    plan["primary_init_source_bindings"] = primary_initializations
    return plan
