"""Evidence-pinned Shadows of Yharnam combat in Orphan's arena.

The contract keeps Orphan's entry, rewards, beach shadow and post-boss flow.
All three Shadows, their three snake generators and four attachment actors are
transplanted as one combat package.  Runtime arena behavior is unobserved.
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
SHADOWS_SOURCE = "event/m27_00_00_00.emevd.dcx.js"
ORPHAN_SOURCE = "event/m36_00_00_00.emevd.dcx.js"

SHADOWS = (2700800, 2700801, 2700802)
SNAKES = (2700803, 2700804, 2700805)
ATTACHMENTS = (2700810, 2700811, 2700813, 2700814)
SOURCE_ACTORS = SHADOWS + SNAKES + ATTACHMENTS
ORPHAN_CORE, ORPHAN_PHASE, ORPHAN_SUPPORT = 3600800, 3600801, 3600803

ARCHETYPES = {
    2700800: Archetype("c2120", 212700, 212700, 0),
    2700801: Archetype("c2120", 212710, 212710, 0),
    2700802: Archetype("c2120", 212720, 212720, 0),
    2700803: Archetype("c5033", 503300, 503300, 0),
    2700804: Archetype("c5033", 503300, 503300, 0),
    2700805: Archetype("c5033", 503300, 503300, 0),
    2700810: Archetype("c2121", 212750, 1, 0),
    2700811: Archetype("c2121", 212751, 1, 0),
    2700813: Archetype("c2121", 212751, 1, 0),
    2700814: Archetype("c2121", 212750, 1, 0),
}
ORPHAN_ARCHETYPES = {
    ORPHAN_CORE: Archetype("c4540", 454000, 454000, 0),
    ORPHAN_PHASE: Archetype("c4541", 454100, 454100, 0),
    ORPHAN_SUPPORT: Archetype("c4543", 454300, 454300, 0),
}

DONOR_HASHES = {
    0: "5eb47b935baa6e9e53251c01e15322d10a36025601e67617a3624ab975e5071a",
    12701800: "cd44f8e4d12d4b7851212b338cf92b0507aa9a7ef7a9584e61961bb3d7ebfa07",
    12704802: "d25c72b2ce42007c119cafcbafbe84c16b5d71dcfb19f938ae0020a08e9ad1e8",
    12704803: "7ad45bce51000cc00388884064813e4c082ec40c1b66d137450910d8c1adac42",
    12704804: "e327421106416287d3ddba66344720877da0ac544f7796fb6a3bb14b458ec60c",
    12704805: "4b5d0e7a8f9bf349d1b2f69277857fef5517a016cf635b1d4f57a3ce59765eac",
    12704806: "3fe1f420f7e6f700a83d4c525abd8ff4612497693f931a817fd3e819469c0d34",
    12704807: "808daf264c202bda492e3ecf3d53a8949842be943306b69394f53d2d35715263",
    12704810: "7f9cc850816d93614c0c7e74376595595397ebed03752c186a71e4a269e67319",
    12704811: "533c1800e81c196c21b004f8689593ad0d681e217e211a028451388799826037",
    12704812: "f163cafc6cb33e9b151016cf914ee23cc26b8daf74567988c32f5bfa5abb9aaf",
    12704815: "a2a4722c6b05e8c46b161de5b190b2b94e2e8165797a6a17a21f25aced454539",
    12704825: "c2cf31fbd2f5312e363fc7cb4e7dab038b062b2d28c019ce054bb7b4c6d84ca7",
    12704830: "d4cad144bb2531d7824f6abcd69804c523e7d1e64f5bf3bafb05aeb1e17f9532",
}
# Installed CUSA03173 01.09 changes one unrelated quest constructor call in
# Event(0), 12700907 -> 12700910.  The boss initializer rows are byte-identical.
DONOR_ALTERNATES = {
    0: "5b0e8366a437736280662cf2a12428b122b69b510cead07c45a9fc67f7492b42",
}

ARENA_HASHES = {
    0: "a6c55dfa6a26dbb4d086f2eb73a12d3956a1dec570699dfbc6c63d0f51fb54b3",
    13601800: "5423c79a2613f564aecbc24658b5b30152c08acb21ede1e817a15abeb5c66c38",
    13601801: "a1e52549f15c53a6e55e4aeafb2f21cf863e1a267d58b9121695241118f2de78",
    13601802: "e2396aaa1c6e9082e71baa1689195eb8c4afbb79870aec7ba85532fd8c053476",
    13601803: "43c5a2c33491090c42c2efa1913c15aadd1208c9ad1440502b7c36876a273593",
    13604802: "8d7b309380f51d2933c573d286cee4ecdb4dc2797376c16dead9078df7f28fb9",
    13604803: "f6754136d8003799fd8c001053980bb67f25b033108b690852d0b0aedd128e72",
    13604804: "1360cbaab6065617a103ca2668dc2e601b10ea73bb97099a59055ad48f074d4e",
    13604805: "0c4495a2403778481467bef908cb72ff5c7cea94f50d25a1ee6e66ea8aa50cdc",
    13604820: "81c25057e062e5cf3d4728af2ba34359bc8b7c75ee28ded6ea7eb8519decd443",
    13604830: "fcec0fd932510a899f0e1a31433ee06438f56f0e0ec27b0ae5e24dc539de57ec",
    13604840: "027beee553830c6635d9452f708c0bcb95ca95fb53239bd6e12d5e764c32f75c",
    13604850: "de7acf9de30e70460a229e9f489b52eb00ab51289317a6b81d80382a67e6ddf1",
}
ARENA_ALTERNATES = {
    0: "d9c76c6c7fcd7efe7eb641d470519cd217d70561ec8a81962f5248a76e316cb7",
    13601802: "db7835c85dcca96716065d5b2106299bcb821db64c506fb931dc3dae0e0de757",
    13604802: "54cb28efcdc5dbf46afd69ebfa6155d8635a61770e8f2375c6be127a8fb44004",
}

ACTOR_PINS = {
    2700800: "f91f3492e77e0bfe20d4fa74b00229042b67404c4e8549b9ce49060579424388",
    2700801: "8ccbe181a9a9fac58f32b5c433e61303b7616d12c6bb072cfa7c3ab4f7ba6c14",
    2700802: "1c6709b46409807298c98e359b537fd8ff0cf73c88a071ad608441fefe90e004",
    2700803: "bffcc44cd445e14090eff8ef29a1b9d8cdf717efac0e64857bbc7797d4f8c414",
    2700804: "fe48cb5b9c15c3e2c06dce5741c44885479173f5f87d6e25ceb13b22fa4e4c75",
    2700805: "a7e982caff8e1c7e06b6c37904b799f74309a675e87c5f51503df80e6b1faaa5",
    2700810: "3594fbdfd43d55c4ce6c55492bb2d617b4bb7c344365cc5e47dcd991723a5319",
    2700811: "caefa28112ca49b443225f712689082d96756b8ee9adc49c116341af1220dbac",
    2700813: "0e65038d5541f99afca785c76c2a724d9d81be4c787d44c5d3659acb4b7b9743",
    2700814: "a6472d31f6ac74a5e2ba1a22d2d164f8d721224db1cc7729dc220e91ba4b700b",
}
ORPHAN_PINS = {
    ORPHAN_CORE: "35eb4a762d39a03f2b99e8407adc8e0fd73d55f01cb84462a15cbb53cd58e2e1",
    ORPHAN_PHASE: "770be2af7c4bc6ca097b2bdb3644b13796a16cf271653e504632efb5befc6f36",
    ORPHAN_SUPPORT: "4561475addb4ed1a4f1e085153b03c8c3ba58907e89bf979bc64b2e0804c1dce",
}

GENERATOR_PINS = (
    (
        "Generator_蛇玉首単体01",
        136,
        2705001,
        "c0844294bff7c057e64d5f88d240a0298edb1ddb51d0253c47eccb9d041aa5f6",
        "c5033_0003",
    ),
    (
        "Generator_蛇玉首単体02",
        137,
        2705002,
        "4fd9c9ccdff8ba62f555a88b793296871b9683ca14e370ece090f7a3367c562d",
        "c5033_0000",
    ),
    (
        "Generator_蛇玉首単体03",
        138,
        2705003,
        "fa72677ccf137e0de97e27e025a49bf414dcf2a1c2ace5dc3aa8677d5213a939",
        "c5033_0001",
    ),
)
REGION_PINS = (
    (
        "Generator_蛇玉首単体04",
        2705014,
        "1f9f8e248958c828987cce69ccf351320bdc770ece066160e246ef9682e003cc",
    ),
    (
        "Generator_蛇玉首単体05",
        2705015,
        "b4c66240f3a7cede3f482b67eab0038e5679f8459997112867b2cd55171050b5",
    ),
    (
        "Generator_蛇玉首単体06",
        2705016,
        "0da431e4e33027d08635857e1763abbc86f4589c422a4e661851180b676558b1",
    ),
    (
        "Generator_蛇玉首単体07",
        2705017,
        "6cfd85b19732a7ad13d4e09bb5fdaec71fbb927669da3596f648371d0983648f",
    ),
    (
        "Generator_蛇玉首単体08",
        2705018,
        "58533a700c3c2896a5849bf6880389960764593625521cedee91ee32159395f2",
    ),
    (
        "Generator_蛇玉首単体09",
        2705019,
        "cc319e8388f1c09b5443ae12ea73aa51dfb5bbc33b6929cca054f7c7c6c751f0",
    ),
    (
        "Generator_蛇玉首単体10",
        2705020,
        "2e6fa606d82c3201c35608c9a632d5d161f9942eeacab069f4d264fcefb9ecbe",
    ),
    (
        "Generator_蛇玉首単体11",
        2705021,
        "f9655a4a55879df73b0162339fd920c622abba447e67f936fe1fe9c5a4f299ae",
    ),
    (
        "Generator_蛇玉首単体12",
        2705022,
        "56216355b082e46b2347073e0d010aa84e86074393b079d301cf5079dd0916bb",
    ),
    (
        "Generator_蛇玉首単体13",
        2705023,
        "399a064c18586065c80938c0df7d25f571329b9b2c21d7f551c1502d4d6f5f87",
    ),
    (
        "Generator_蛇玉首単体14",
        2705024,
        "98147955f35c41384215bf1fbb3b1152921d1cab4319a6e7f6fad86565fc514a",
    ),
    (
        "Generator_蛇玉首単体15",
        2705025,
        "d668c2951fc5b1c74cef76d9e9552de59365bfe58e23dbd150824f75349caf6f",
    ),
)

ACTIVE_PRIMARY = 981310
SECONDARY_ENTITIES = tuple(range(981300, 981309))
HELPER_ENTITIES = (ACTIVE_PRIMARY, *SECONDARY_ENTITIES)
SECONDARY_PARTS = (
    "ap_shadows_body_1",
    "ap_shadows_body_2",
    "ap_shadows_snake_0",
    "ap_shadows_snake_1",
    "ap_shadows_snake_2",
    "ap_shadows_attachment_0",
    "ap_shadows_attachment_1",
    "ap_shadows_attachment_3",
    "ap_shadows_attachment_4",
)
HELPER_MAP = {
    2700800: ACTIVE_PRIMARY,
    **dict(zip(SOURCE_ACTORS[1:], SECONDARY_ENTITIES)),
}
PART_MAP = {
    2700800: "ap_shadows_body_0",
    **dict(zip(SOURCE_ACTORS[1:], SECONDARY_PARTS)),
}


@dataclass(frozen=True)
class ShadowsOrphanIds:
    group_phase: int = 12993500
    summon: int = 12993501
    distance_pair: int = 12993502
    distance_all: int = 12993503
    body_phase: int = 12993504
    attachment: int = 12993505
    effect: int = 12993506
    summon_cleanup: int = 12993507
    bridge: int = 12993508
    destination_cleanup: int = 12993509
    helper_entry: int = 12993510
    generator_event_first: int = 12993560
    generator_entity_first: int = 981330
    region_entity_first: int = 981340

    def event_map(self) -> dict[int, int]:
        return {
            12704806: self.group_phase,
            12704807: self.summon,
            12704810: self.distance_pair,
            12704811: self.distance_all,
            12704812: self.body_phase,
            12704815: self.attachment,
            12704825: self.effect,
            12704830: self.summon_cleanup,
        }

    def project_events(self) -> tuple[int, ...]:
        return (
            *self.event_map().values(),
            self.bridge,
            self.destination_cleanup,
            self.helper_entry,
        )


DEFAULT_IDS = ShadowsOrphanIds()


def _verify(
    text: str,
    pins: Mapping[int, str],
    role: str,
    alternates: Mapping[int, str] | None = None,
) -> dict[int, str]:
    blocks = event_blocks(text)
    for event, digest in pins.items():
        body = blocks.get(event, "")
        allowed = {digest}
        if event in (alternates or {}):
            allowed.add((alternates or {})[event])
        if hashlib.sha256(body.encode()).hexdigest() not in allowed:
            raise ValueError(f"unsupported original {role} event {event}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Shadows/Orphan expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])", lambda m: str(values.get(int(m[0]), int(m[0]))), text
    )


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _end_event(block: str) -> str:
    header = block.splitlines()[0]
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda m: "function("
        + ", ".join("unused_" + x.strip() for x in m[1].split(",") if x.strip())
        + ")",
        header,
    )
    return header + "\n    EndEvent();\n});"


@cache
def _original_ids() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(map(int, re.findall(rb"(?<![\w])-?\d+(?![\w])", body)))
    rows = (
        read_prefix(BUNDLE, "mined/")
        .get("mined/msb_enemies.tsv", b"")
        .decode("utf-8-sig")
        .splitlines()[1:]
    )
    for row in rows:
        columns = row.split("\t")
        if len(columns) > 3 and columns[3].lstrip("-").isdigit():
            values.add(int(columns[3]))
    return values


def _validate_ids(ids: ShadowsOrphanIds, destination: str = "") -> None:
    events = ids.project_events() + tuple(
        ids.generator_event_first + i for i in range(3)
    )
    entities = (
        HELPER_ENTITIES
        + tuple(ids.generator_entity_first + i for i in range(3))
        + tuple(ids.region_entity_first + i for i in range(12))
    )
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    original = _original_ids()
    if (
        len(set(events)) != len(events)
        or any(not 12993500 <= value <= 12993599 for value in events)
        or set(events) & (local | original)
    ):
        raise ValueError(
            "Shadows/Orphan event IDs must be collision-free 129935xx values"
        )
    if (
        len(set(entities)) != len(entities)
        or any(not 981300 <= value <= 981399 for value in entities)
        or set(entities) & (local | original)
    ):
        raise ValueError(
            "Shadows/Orphan helper IDs must be collision-free 981300-981399 values"
        )


def _mapping(ids: ShadowsOrphanIds) -> dict[int, int]:
    return {
        **HELPER_MAP,
        2705001: ids.generator_entity_first,
        2705002: ids.generator_entity_first + 1,
        2705003: ids.generator_entity_first + 2,
        12701800: 13601800,
        12704800: 13604808,
        12704801: 13604809,
        12704802: 13604802,
        12704803: 13604803,
        12704804: 13604804,
        2703802: 3603802,
        2703803: 3603803,
        2702802: 3602802,
        2700010: 3600010,
        27: 36,
        **ids.event_map(),
    }


def _initializer_rows(
    constructor: str, source_event: int, expected: int, values: Mapping[int, int]
) -> list[str]:
    rows = [
        line
        for line in constructor.splitlines()
        if re.search(
            r"\$InitializeEvent\([^,]+,\s*" + str(source_event) + r"(?:,|\))", line
        )
    ]
    if len(rows) != expected:
        raise ValueError(
            f"Shadows Event(0) initializer witness drift for {source_event}"
        )
    return [_remap(row, values) for row in rows]


def patch_shadows_at_orphan(
    destination: str, donor_source: str, ids: ShadowsOrphanIds = DEFAULT_IDS
) -> str:
    """Install the pinned ten-actor Shadows package while keeping Orphan progression."""
    arena = _verify(destination, ARENA_HASHES, "Orphan arena", ARENA_ALTERNATES)
    donor = _verify(donor_source, DONOR_HASHES, "Shadows donor", DONOR_ALTERNATES)
    _validate_ids(ids, destination)
    values = _mapping(ids)

    health = _remap(donor[12704802], values)
    health = _replace_once(
        health,
        "    SetEventFlag(13604808, ON);",
        "    SetEventFlag(13604810, ON);\n    SetEventFlag(13604808, ON);",
        "destination battle state",
    )
    health = _replace_once(
        health,
        "    CreatePlaylog(82);",
        "    CreatePlaylog(42);",
        "destination playlog",
    )
    health = _replace_once(
        health,
        "    StartTimeMeasurement(3600010, 98, Enabled);",
        "    StartTimeMeasurement(3600010, 58, Enabled);",
        "destination time measurement",
    )
    music = _remap(donor[12704803], values)
    camera = _remap(donor[12704804], values)

    initializer_counts = {
        12704806: 1,
        12704807: 3,
        12704812: 3,
        12704815: 4,
        12704825: 2,
        12704830: 3,
    }
    constructors = [
        row
        for event, count in initializer_counts.items()
        for row in _initializer_rows(donor[0], event, count, values)
    ]
    # Events 12704810/11 exist in the source EMEVD but Event(0) never starts
    # them.  Copy their definitions for closure without inventing activation.
    if _initializer_rows(donor[0], 12704810, 0, values) or _initializer_rows(
        donor[0], 12704811, 0, values
    ):
        raise ValueError("unexpected Shadows distance-controller initializer")
    constructors.extend(
        [
            "    $InitializeEvent(0, 13604804);",
            f"    $InitializeEvent(0, {ids.bridge});",
            f"    $InitializeEvent(0, {ids.destination_cleanup});",
            f"    $InitializeEvent(0, {ids.helper_entry});",
        ]
    )
    constructor = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 13601804);",
        "    $InitializeEvent(0, 13601804);\n" + "\n".join(constructors),
        "constructor anchor",
    )

    bridge = f"""$Event({ids.bridge}, Default, function() {{
    EndIf(EventFlag(13601800));
    WaitFor(CharacterDead({ACTIVE_PRIMARY}) && CharacterDead(981300) && CharacterDead(981301));
    SetCharacterInvincibility(3600800, Disabled);
    ForceCharacterDeath(3600800, false);
}});"""
    cleanup_lines = [
        f"    ChangeCharacterEnableState({entity}, Disabled);\n    ForceCharacterDeath({entity}, false);"
        for entity in (*HELPER_ENTITIES, ORPHAN_PHASE, ORPHAN_SUPPORT)
    ]
    cleanup = f"""$Event({ids.destination_cleanup}, Default, function() {{
    SetCharacterAIState(3600800, Disabled);
    SetCharacterAIState(3600801, Disabled);
    SetCharacterAIState(3600803, Disabled);
    SetCharacterInvincibility(3600800, Enabled);
    SetCharacterInvincibility(3600801, Enabled);
    SetCharacterInvincibility(3600803, Enabled);
    ChangeCharacterEnableState(3600800, Disabled);
    ChangeCharacterEnableState(3600801, Disabled);
    ChangeCharacterEnableState(3600803, Disabled);
    WaitFor(EventFlag(13601800));
{chr(10).join(cleanup_lines)}
    DeactivateGenerator({ids.generator_entity_first}, Disabled);
    DeactivateGenerator({ids.generator_entity_first + 1}, Disabled);
    DeactivateGenerator({ids.generator_entity_first + 2}, Disabled);
    SetEventFlag(12704808, OFF);
}});"""
    entry = f"""$Event({ids.helper_entry}, Default, function() {{
    EndIf(EventFlag(13601800));
    SetCharacterAIState(3600800, Disabled);
    SetCharacterInvincibility(3600800, Enabled);
    ChangeCharacterEnableState(3600800, Disabled);
    ChangeCharacterEnableState({ACTIVE_PRIMARY}, Disabled);
    ChangeCharacterEnableState(981300, Disabled);
    ChangeCharacterEnableState(981301, Disabled);
    WaitFor(EventFlag(13604808));
    SetCharacterAIState(3600800, Disabled);
    SetCharacterInvincibility(3600800, Enabled);
    ChangeCharacterEnableState(3600800, Disabled);
    ChangeCharacterEnableState({ACTIVE_PRIMARY}, Enabled);
    ChangeCharacterEnableState(981300, Enabled);
    ChangeCharacterEnableState(981301, Enabled);
}});"""
    copied = {new: _remap(donor[old], values) for old, new in ids.event_map().items()}
    edits = {
        0: constructor,
        13604802: health,
        13604803: music,
        13604804: camera,
        13604820: _end_event(arena[13604820]),
        13604830: _end_event(arena[13604830]),
        13604840: _end_event(arena[13604840]),
        13604850: _end_event(arena[13604850]),
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join((*copied.values(), bridge, cleanup, entry))
        + "\n"
    )
    after = event_blocks(result)
    expected = set(arena) | set(ids.project_events())
    if set(after) != expected:
        raise ValueError("Shadows/Orphan changed unexpected event identities")
    for event in (13601801, 13601802, 13601803, 13601804, 13604800, 13604801, 13604805):
        if after[event] != arena[event]:
            raise ValueError(
                f"Shadows/Orphan changed protected destination event {event}"
            )
    if after[13601800] != arena[13601800]:
        raise ValueError("Shadows/Orphan changed protected destination terminal")
    return result


def _pin(part_sha256: str, anchor_sha256: str | None = None) -> dict:
    result = {"format": "bb-boss-actor-pin-v1", "part_sha256": part_sha256}
    if anchor_sha256 is not None:
        result["anchor_sha256"] = anchor_sha256
    return result


def _initialization() -> dict:
    return {"talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1}


def _require(
    slots: Sequence[Slot], entity: int, archetype: Archetype, map_name: str
) -> Slot:
    rows = [
        slot for slot in slots if slot.entity_id == entity and slot.map_name == map_name
    ]
    if (
        len(rows) != 1
        or rows[0].dummy
        or rows[0].talk_id
        or rows[0].archetype != archetype
    ):
        raise ValueError(f"Shadows/Orphan requires pinned actor {map_name}:{entity}")
    return rows[0]


def native_plan_shadows_at_orphan(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: ShadowsOrphanIds = DEFAULT_IDS,
) -> dict:
    donor_text = read_blob(BUNDLE, SHADOWS_SOURCE).decode("utf-8-sig")
    arena_text = read_blob(BUNDLE, ORPHAN_SOURCE).decode("utf-8-sig")
    patch_shadows_at_orphan(arena_text, donor_text, ids)
    source_rows = {
        entity: _require(slots, entity, ARCHETYPES[entity], "m27_00_00_00")
        for entity in SOURCE_ACTORS
    }
    target = _require(
        slots, ORPHAN_CORE, ORPHAN_ARCHETYPES[ORPHAN_CORE], "m36_00_00_00"
    )
    retained = [
        _require(slots, entity, ORPHAN_ARCHETYPES[entity], "m36_00_00_00")
        for entity in (ORPHAN_PHASE, ORPHAN_SUPPORT)
    ]
    primary = source_rows[SHADOWS[0]]
    source_anchor = source_rows[SHADOWS[1]]
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        primary.archetype,
        warnings=[
            "experimental Shadows-at-Orphan contract; runtime arena and summon behavior are unobserved"
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
        raise ValueError("Shadows/Orphan primary normalization is ambiguous")

    additions = []
    for entity in SOURCE_ACTORS:
        row = source_rows[entity]
        additions.append(
            {
                "source_map": row.map_name,
                "source_part": row.part_name,
                "source_anchor_part": source_anchor.part_name,
                "source_entity_id": entity,
                "source_archetype": asdict(row.archetype),
                "source_part_kind": "enemy",
                "source_provenance": _pin(ACTOR_PINS[entity], ACTOR_PINS[SHADOWS[1]]),
                "source_initialization": _initialization(),
                "destination_map": target.map_name,
                "destination_anchor_part": target.part_name,
                "destination_part": PART_MAP[entity],
                "destination_entity_id": HELPER_MAP[entity],
                "allocation_evidence": "project-reserved 981300-981399 helper range; native collision validation required",
            }
        )
    regions = []
    for index, (name, source_entity, fingerprint) in enumerate(REGION_PINS):
        regions.append(
            {
                "source_map": primary.map_name,
                "source_region": name,
                "source_entity_id": source_entity,
                "source_provenance": {
                    "format": "bb-boss-region-pin-v1",
                    "region_sha256": fingerprint,
                },
                "source_anchor_part": source_anchor.part_name,
                "source_anchor_provenance": _pin(ACTOR_PINS[SHADOWS[1]]),
                "destination_map": target.map_name,
                "destination_region": f"ap_shadows_snake_spawn_{index:02d}",
                "destination_entity_id": ids.region_entity_first + index,
                "destination_anchor_part": target.part_name,
                "destination_anchor_provenance": _pin(ORPHAN_PINS[ORPHAN_CORE]),
            }
        )
    snake_parts = {
        "c5033_0003": PART_MAP[2700803],
        "c5033_0000": PART_MAP[2700804],
        "c5033_0001": PART_MAP[2700805],
    }
    generators = []
    for index, (
        name,
        source_event_id,
        source_entity,
        fingerprint,
        snake_part,
    ) in enumerate(GENERATOR_PINS):
        generators.append(
            {
                "source_map": primary.map_name,
                "source_event": name,
                "source_event_id": source_event_id,
                "source_entity_id": source_entity,
                "source_fingerprint": fingerprint,
                "destination_map": target.map_name,
                "destination_event": f"ap_shadows_snake_generator_{index}",
                "destination_event_id": ids.generator_event_first + index,
                "destination_entity_id": ids.generator_entity_first + index,
                "destination_part_name": target.collision_name,
                "destination_region_name": None,
                "spawn_part_map": {snake_part: snake_parts[snake_part]},
                "spawn_point_map": {
                    REGION_PINS[index * 4 + offset][
                        0
                    ]: f"ap_shadows_snake_spawn_{index * 4 + offset:02d}"
                    for offset in range(4)
                },
            }
        )
    retained_rows = [
        {
            "map": row.map_name,
            "part": row.part_name,
            "entity_id": row.entity_id,
            "archetype": asdict(row.archetype),
            "source_provenance": _pin(ORPHAN_PINS[row.entity_id]),
            "source_initialization": _initialization(),
            "policy": "disabled and alive until destination terminal; force-killed and hidden after completion",
        }
        for row in retained
    ]
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "orphan-of-kos<-shadows-of-yharnam"},
        "boss_actor_additions": additions,
        "boss_region_additions": regions,
        "boss_generator_additions": generators,
        "primary_init_source_bindings": [
            {
                "source_map": primary.map_name,
                "source_part": primary.part_name,
                "source_entity_id": primary.entity_id,
                "source_archetype": asdict(primary.archetype),
                "source_provenance": _pin(ACTOR_PINS[SHADOWS[0]]),
                "source_initialization": _initialization(),
                "destination_map": target.map_name,
                "destination_part": target.part_name,
                "destination_entity_id": target.entity_id,
            }
        ],
        "boss_actor_scaling_requirements": [
            {
                "destination_map": target.map_name,
                "destination_part": PART_MAP[entity],
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": ARCHETYPES[entity].npc_param_id,
                "strategy": "allocate_distinct_verified_helper_clone",
            }
            for entity in SOURCE_ACTORS
        ],
        "boss_contract": {
            "format": "bb-shadows-orphan-contract-v1",
            "arena": "orphan-of-kos",
            "donor": "shadows-of-yharnam",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(DONOR_HASHES),
            "source_hash_alternates": dict(DONOR_ALTERNATES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "preserved_destination_events": [
                13601801,
                13601802,
                13601803,
                13601804,
                13604800,
                13604801,
                13604805,
            ],
            "retained_destination_helpers": retained_rows,
            "inert_terminal_proxy": {
                "entity_id": ORPHAN_CORE,
                "part": target.part_name,
                "policy": "transplanted source primary remains hidden, AI-disabled and alive until the three active Shadow bodies die; bridge force-death then releases the byte-identical destination terminal",
            },
            "placement_anchor_policy": {
                "source_anchor_entity": SHADOWS[1],
                "source_anchor_part": source_anchor.part_name,
                "destination_anchor_entity": ORPHAN_CORE,
                "destination_anchor_part": target.part_name,
                "policy": "one common anchor for every actor and region addition preserves all donor-relative offsets while keeping the active-primary source distinct from the primary-slot source actor",
            },
            "source_roster": {
                "combat_bodies": list(SHADOWS),
                "snake_bodies": list(SNAKES),
                "attachments": list(ATTACHMENTS),
                "generators": [2705001, 2705002, 2705003],
                "spawn_regions": [row[1] for row in REGION_PINS],
            },
            "source_actor_event_closure": {
                "12704802": "three health bars, co-op scaling, generator and snake initialization",
                "12704803": "phase music copied onto destination map sounds; source phase signal 12704808 retained transiently",
                "12704804": "group camera copied onto map 36 lockcam",
                "12704806": "group phase command loop",
                "12704807": "three snake summon/generator slots",
                "12704810/11": "source definitions copied but deliberately unstarted because source Event(0) has no initializer",
                "12704812": "three per-body phase slots",
                "12704815": "four c2121 attachment slots",
                "12704825": "two per-body effect slots",
                "12704830": "three terminal snake cleanup slots",
            },
            "phase_flag_policy": {
                "flag": 12704808,
                "evidence": "read by source music controller; no EMEVD setter in pinned source",
                "policy": "retain as donor combat signal and clear after destination completion",
            },
            "native_requirements": {
                "actor_additions": 10,
                "region_additions": 12,
                "generator_additions": 3,
                "destination_collision": target.collision_name,
            },
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


def shadows_helper_scaling_parents(plan: Mapping) -> dict[tuple[str, str], str]:
    rows = plan.get("boss_actor_scaling_requirements", ())
    result = {
        (row["destination_map"], row["destination_part"]): row["parent_logical_key"]
        for row in rows
    }
    if len(result) != len(rows):
        raise ValueError("duplicate Shadows helper scaling destination")
    return result


helper_scaling_parents = shadows_helper_scaling_parents
