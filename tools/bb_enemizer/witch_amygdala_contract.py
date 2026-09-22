"""Source-pinned Witch of Hemwick pair combat in Amygdala's arena.

Amygdala's terminal, fog objects, rewards, and progression remain local.  The
Witch pair needs more than a primary swap: the second Witch, three minions,
twenty authored regions, and three generators are source-pinned native inputs.
The construction is statically checked; its arena fit remains unobserved.
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
WITCH_SOURCE = "event/m22_00_00_00.emevd.dcx.js"
AMYGDALA_SOURCE = "event/m33_00_00_00.emevd.dcx.js"
WITCH, SECOND = 2200800, 2200801
MINIONS = (2200810, 2200811, 2200812)
AMYGDALA = 3300800
WITCH_ARCHETYPE = Archetype("c2100", 210020, 210020, 0)
SECOND_ARCHETYPE = Archetype("c2100", 210020, 210021, 0)
MINION_ARCHETYPE = Archetype("c2050", 205010, 205010, 2)
AMYGDALA_ARCHETYPE = Archetype("c5120", 512000, 512000, 0)
PROJECT_MIN, PROJECT_MAX = 12993000, 12993099

DONOR_HASHES = {
    0: "905725c3c1e58539e378d2bfb3f1a73dc90d1a702b49168c55d1590ce625a822",
    12201800: "5dffb875184250877c9dc9867bffb67329741d033ebf9fa9e77b170ea5145fe1",
    12201802: "02cd835b56665e1eb6f2ceb9252ef6d3c92fdf468180918348d8bbf54e13c3b3",
    12201804: "6d45f5c7920b54054955d9cfb46762a25430891329269c06421d70fdb459b1a2",
    12204802: "9b068a5c6a2f5cc57a9be0aa6d30f9f191ddb946f040c94b200c1422d6102af2",
    12204803: "d41f4a63d537c30c94cd4ff4208df30b98a989f25d45e9118525cd54d7963caf",
    12204804: "c212b5f5394951dcc5495470b65ebfd750db4ffd9cf842117c563cf5195bc4f3",
    12204807: "655699631c73031e6dd7df02bdafe29342cb95c0d17ecc7a7dcc65788bb0cfe9",
    12204808: "727a2f98f6cf687d9c884405d2ed339637f76dbce4f7453b26d4384bad36c52d",
    12204810: "4b46cc21a6893bdf69c5cb5d2a6b5c3864485c7397a869c65b552d3edaec7dbb",
    12204811: "9f9012a702a380023664ae4e306af0659bb5299f0a458e8e9a2657ec45cdfbed",
    12204812: "83319e5d8fbfead580332e407f4030f8b1809a0200c2a64a7e5b702989e42bba",
    12204814: "c34779e2ea895652b053bf59da26cee10c43a356dca99d7a056068a28b6d942a",
    12204820: "b52c73e7780c8b881bf620712635e11543a4d0a8b2441e432bbb875f24521a87",
    12204830: "92ff33f3a8c292029a0241a2b55d47b10d110ecc55b3c207413d432f0e1ad6e3",
    12204832: "e7d9553aaf54ee0b1244d7630315424c894c00c23ad92e84abc20de95b1f8189",
    12204835: "7609b9eccaba2ec2fae936b3af0c2a3e1d5f2cfc60e691203ae5bf7a60f88033",
    12204838: "c827f0e6f268137a32eaee69cbe663d6f1b11f5f0e07287248bcdd63819c3de1",
    12204839: "208f2ab1317ce5824016e2e066936c7ae4d3fb2ec1d9d6cf5ac27ca47e17f184",
    12204840: "501975bc72f190c1bfdc66b0334314c0ec543679ca0462f54fe28552d7666230",
    12204841: "55c22eaf16641de6ad8406e9ff3fb894de8688b6eae4511718323162baaba4ed",
    12204842: "7def5279370553e68f4013c60b8b0ef49dbd4ce187e68bc8200e7806a9a39639",
    12204843: "3d50d91dea8d65d9e1c703747e301f16cb2531a1077c7b718e988af1f42d9904",
    12204844: "811e8c99e9426a744bc0cc86e278f982081acbbd8295455a31467cf159c31a12",
}

ARENA_HASHES = {
    0: "b86f288c46fc74ddc81530e62437d9497c5a63ec09488c068211d85f4054f934",
    13301800: "d719f46bbaf08f19beebee00dc39b9ee16443c6614faa9689bb9abb6230f0871",
    13301801: "3c4491a114cc6871b37ffe3da87ec0c5616fe6dfa7bd0991a32b77ed0a492fd6",
    13301802: "dbf7c452ecf425a41d9c724ba0568db015224bb1a3b1516c9033779c59c1d3ae",
    13301803: "7613c67c60f7fd94fe8152c96887113aabaeee5cc728f79bd3c2fcfd2bfb0dd9",
    13304802: "448a7775ab941832e255cbb918acdb25b4ce8dc067f89376ff6404eee9b3ca69",
    13304803: "0f6aa448c5c4af20db4b5069bdce6516c2bc4d4f5b1ed5ccb1653bd47f18ccaf",
    13304804: "ebe1b13a76f981e01d250c845698e7e1625d43a0fb7d0a350beb647256e55155",
    13304805: "f50b7e8aa6fbd3e18e4f7477e7b611f677372da0acb262c446d7ae2f990f24cc",
    13304807: "32354612205279186043fb283a4c29962803822747e0ffb82fd05bcde48e41d6",
    13304808: "0b9f21dbf5d1f79aa0d6e393c976e3a24f102cfcc25930271ddd0e6d08fa5055",
    13304820: "e2d693a68d6560f3506e2070501ce2a919f1a70640a3145bab556237aac53592",
    13304830: "3ee36ea1ac6d459c45c95aad95bee1e0c3201bc8fdf460a2b3cebae3fa80a9f8",
    13304840: "d3c6246b1286e98ca0f27cb5123d6bdc043982618d533a9aa76a647d3ac5ff68",
    13304870: "3e8bdc2f4468414a909c1ba05060b3ffdfd521c05a41fd4cf01ed30ba44d9920",
    13304871: "d269583eaed1fc57f8a2a4c003ffadab36ea470a62252e52fa41224b1303a8cc",
}

WITCH_PINS = {
    WITCH: "d82ece33f61d3ed3fbcd931f1089f7be4d0f82a2690f49c9ccdf5e021550cd20",
    SECOND: "263b840cd3d8e07dc328eb870cd2047e3cbde5ed9e935e739fbf7fd29897beca",
    2200810: "cc0811ed346997c67bc24077a6498b5bfd1d671406bb53d3b09ed658241acdad",
    2200811: "6d6aca6776742a5a57b7c0d2cff745d91dc8fb2b8c585e0a4cfdd16b6956ced8",
    2200812: "887eb3820938237cee74908be2a96bad27da4ec4e0a907de15b1ef45ad6426a4",
}
AMYGDALA_PIN = "4d66ca60f567e2f0ba0ffcc43fb45c5666265fd9649952cc3828185f0ef1bc39"
WARP_REGION_PINS = {
    2202810: (
        "Event_領域_ボスワープ00",
        "152d66d12bfb29ef3f60e133fdc49bd4f3a4cb1b0ebaf6047892163ce6b04a32",
    ),
    2202811: (
        "Event_領域_ボスワープ01",
        "84c1d9fb82197116a18a8226cf6571efd9e3985a10aff8362d754e6ac7ed6416",
    ),
    2202812: (
        "Event_領域_ボスワープ02",
        "9d19cb8c3195c2e750b088b51be4403c3ddbf7922817aa6f93178537c6b17910",
    ),
    2202813: (
        "Event_領域_ボスワープ03",
        "a10fa24065cdad3a754899256eea801f12dc9fb8c03c4e0bf3a07af01d85786a",
    ),
    2202814: (
        "Event_領域_ボスワープ04",
        "21d102485bff70f14154c3855a1bc0fc179add003d78ccd741b6b7bd976c3ce2",
    ),
    2202815: (
        "Event_領域_ボスワープ05",
        "11f36875eb2c9dca95f8a0a92725928b6085792bd62beb8e6bdd54766370c1a8",
    ),
    2202816: (
        "Event_領域_ボスワープ06",
        "c37c6e51e32d716e00706de76a9b945aa690ef099315ad3843118db6f956478e",
    ),
    2202817: (
        "Event_領域_ボスワープ07",
        "b62b99e65247854ba11277809f3ad250e9070961a88160cc87afb7550417ded9",
    ),
}
SPAWN_REGION_PINS = {
    2205500: (
        "Generator_狂気の悪霊00",
        "40e5d1f9f16612e4fbe931e505b97b99fe8c9021882d6ecccbfd48990f4090f1",
    ),
    2205501: (
        "Generator_狂気の悪霊01",
        "b2f075e2a9fe87680027b66ae26af1bee0cc0d107fd685ba90e8535b818331b6",
    ),
    2205502: (
        "Generator_狂気の悪霊02",
        "87a8faa89c99d82ea3e1758dcc5f5c9eb9836ca57581c6b655489cdcf62422e0",
    ),
    2205503: (
        "Generator_狂気の悪霊03",
        "689d5daf1a1aba47714e9cd3819d5b4809b9dfd4fe198af9c9a5988af6b8a674",
    ),
    2205504: (
        "Generator_狂気の悪霊04",
        "b1093db061fcac70274d8d71c3e6a14194407e6d55885be2ca4abe33376a4c29",
    ),
    2205505: (
        "Generator_狂気の悪霊05",
        "2f36fae1550b112ad643d9ac9b6a4bce59812f1453c478f03c75c5b1ed68c851",
    ),
    2205506: (
        "Generator_狂気の悪霊06",
        "050d31f2069d620c148e9b82314d8a424ca044a9a90c06224faf88d237ece012",
    ),
    2205507: (
        "Generator_狂気の悪霊07",
        "2e776682b624927a4ef0a32c67476170afd40c4bbc032c4c653d264d9e92a643",
    ),
    2205508: (
        "Generator_狂気の悪霊08",
        "22f10957a1843b36d08145887a06930489bb4c7132a4a6d11013413e7bc4e411",
    ),
    2205509: (
        "Generator_狂気の悪霊09",
        "9c0c2e78940fb2b36dc09e42633d3bde03c8573770ae512b74120641d816c1f4",
    ),
    2205510: (
        "Generator_狂気の悪霊10",
        "ada557198a67837f57aa9c2c9419f19f85e1097b88e2e3e0f0710585403e5530",
    ),
    2205511: (
        "Generator_狂気の悪霊11",
        "a4c2398a11c564fb7a525295bb7bad4c6d6cd99e36f7d3f5a2f04fab4fcee9e8",
    ),
}
GENERATOR_PINS = (
    (
        "Generator_狂気の悪霊00",
        132,
        2205000,
        "6bbd6486f0848ee0e9adf6b311438c890ca3ebaef7e639c4f90e64083e239a6a",
    ),
    (
        "Generator_狂気の悪霊01",
        133,
        2205001,
        "0b34f60760312d3b0da79c73993d37381a175c16ecf794db1d89e97ea714a964",
    ),
    (
        "Generator_狂気の悪霊02",
        220,
        2205002,
        "43dfeb818f0fd0ec5573496262ead5865c2c70a715d8a5c81f95bdf209a1ed18",
    ),
)


@dataclass(frozen=True)
class WitchAmygdalaIds:
    phase: int = 12993000
    visibility: int = 12993001
    second_start: int = 12993002
    patrol: int = 12993003
    revival: int = 12993004
    warp_select: int = 12993005
    warp: int = 12993006
    post_warp: int = 12993007
    minion_count: int = 12993008
    minion_watch: int = 12993009
    summon: int = 12993010
    generator_manager: int = 12993011
    summon_one: int = 12993012
    summon_two: int = 12993013
    summon_three: int = 12993014
    minion_setup: int = 12993015
    insight: int = 12993016
    completion_cleanup: int = 12993017
    second_entity: int = 980800
    minion_first_entity: int = 980801
    warp_first_entity: int = 980810
    spawn_first_entity: int = 980820
    generator_event_first: int = 980840
    generator_entity_first: int = 980843
    visibility_flag_first: int = 12993040
    warp_flag_first: int = 12993042
    minion_count_flag: int = 12993080
    minion_status_first: int = 12993053
    generator_state_first: int = 12993056
    summon_permission_first: int = 12993058
    source_second_started_flag: int = 12993060
    insight_flag: int = 12993061

    def events(self) -> tuple[int, ...]:
        return (
            self.phase,
            self.visibility,
            self.second_start,
            self.patrol,
            self.revival,
            self.warp_select,
            self.warp,
            self.post_warp,
            self.minion_count,
            self.minion_watch,
            self.summon,
            self.generator_manager,
            self.summon_one,
            self.summon_two,
            self.summon_three,
            self.minion_setup,
            self.insight,
            self.completion_cleanup,
        )

    def project_ids(self) -> tuple[int, ...]:
        return self.events() + (
            self.visibility_flag_first,
            self.visibility_flag_first + 1,
            *(self.warp_flag_first + offset for offset in range(10)),
            *(self.minion_count_flag + offset for offset in range(10)),
            *(self.minion_status_first + offset for offset in range(3)),
            self.generator_state_first,
            self.generator_state_first + 1,
            *(self.summon_permission_first + offset for offset in range(2)),
            self.source_second_started_flag,
            self.insight_flag,
        )

    def helper_ids(self) -> tuple[int, ...]:
        return (
            self.second_entity,
            *(self.minion_first_entity + offset for offset in range(3)),
            *(self.warp_first_entity + offset for offset in range(8)),
            *(self.spawn_first_entity + offset for offset in range(12)),
            *(self.generator_event_first + offset for offset in range(3)),
            *(self.generator_entity_first + offset for offset in range(3)),
        )


DEFAULT_IDS = WitchAmygdalaIds()


def _verify(text: str, pins: Mapping[int, str], role: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event, digest in pins.items():
        if hashlib.sha256(blocks.get(event, "").encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {role} event {event}")
    return blocks


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda item: str(values.get(int(item[0]), int(item[0]))),
        text,
    )


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Witch/Amygdala expected one {label}")
    return text.replace(old, new, 1)


def _end(block: str) -> str:
    header = re.sub(
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
        block.splitlines()[0],
    )
    return header + "\n    EndEvent();\n});"


def _replace_events(text: str, edits: Mapping[int, str]) -> str:
    lines = text.splitlines()
    for event in reversed(parse_events(text)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


@cache
def _all_original_literals() -> set[int]:
    return {
        int(value)
        for body in read_prefix(BUNDLE, "event/").values()
        for value in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
    }


def _validate_ids(ids: WitchAmygdalaIds, destination: str) -> None:
    project, helpers = ids.project_ids(), ids.helper_ids()
    local = {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    if (
        len(project) != len(set(project))
        or any(value not in range(PROJECT_MIN, PROJECT_MAX + 1) for value in project)
        or set(project) & (local | _all_original_literals())
    ):
        raise ValueError(
            "Witch/Amygdala IDs must be collision-free project-owned 129930xx values"
        )
    if (
        len(helpers) != len(set(helpers))
        or any(value not in range(980800, 980900) for value in helpers)
        or set(helpers) & (local | _all_original_literals() | set(project))
    ):
        raise ValueError(
            "Witch/Amygdala helper IDs must be collision-free reserved 980800-range values"
        )


def _mapping(ids: WitchAmygdalaIds) -> dict[int, int]:
    values = {
        WITCH: AMYGDALA,
        SECOND: ids.second_entity,
        **{MINIONS[index]: ids.minion_first_entity + index for index in range(3)},
        12201800: 13301800,
        12201802: 13301802,
        12201804: 13301803,
        12204800: 13304800,
        12204801: 13304801,
        12204802: 13304802,
        12204803: 13304803,
        12204804: 13304804,
        12204807: ids.phase,
        12204808: ids.visibility,
        12204810: ids.second_start,
        12204811: ids.patrol,
        12204812: ids.revival,
        12204814: ids.warp_select,
        12204820: ids.warp,
        12204830: ids.post_warp,
        12204832: ids.minion_count,
        12204835: ids.minion_watch,
        12204838: ids.summon,
        12204839: ids.generator_manager,
        12204840: ids.summon_one,
        12204841: ids.summon_two,
        12204842: ids.summon_three,
        12204843: ids.minion_setup,
        12204844: ids.insight,
        12204848: ids.visibility_flag_first,
        12204849: ids.visibility_flag_first + 1,
        **{12204850 + index: ids.warp_flag_first + index for index in range(10)},
        12204860: ids.minion_count_flag,
        **{12204870 + index: ids.minion_status_first + index for index in range(3)},
        12204875: ids.generator_state_first,
        12204876: ids.generator_state_first + 1,
        12204880: ids.summon_permission_first,
        12204881: ids.summon_permission_first + 1,
        12201810: ids.source_second_started_flag,
        12204845: ids.insight_flag,
        2202800: 3302800,
        2202801: 3302801,
        2202805: 3302805,
        2203802: 3303802,
        2203803: 3303803,
        2200010: 3300010,
        **{2205000 + index: ids.generator_entity_first + index for index in range(3)},
    }
    values.update(
        {2202810 + index: ids.warp_first_entity + index for index in range(8)}
    )
    return values


def _initializers(
    event_zero: str, source_event: int, expected_count: int, mapping: Mapping[int, int]
) -> list[str]:
    rows = [
        line
        for line in event_zero.splitlines()
        if re.match(
            r"\s*\$InitializeEvent\([^,]+,\s*" + str(source_event) + r"(?:,|\))", line
        )
    ]
    if len(rows) != expected_count:
        raise ValueError(
            f"Witch Event(0) lacks {expected_count} initializer witnesses for {source_event}"
        )
    return [_remap(row, mapping) for row in rows]


def patch_witch_at_amygdala(
    destination: str, donor_source: str, ids: WitchAmygdalaIds = DEFAULT_IDS
) -> str:
    """Patch a single Amygdala map script after native helpers are staged."""
    arena, donor = _verify(destination, ARENA_HASHES, "Amygdala arena"), _verify(
        donor_source, DONOR_HASHES, "Witch donor"
    )
    _validate_ids(ids, destination)
    if set(ids.events()) & set(arena):
        raise ValueError(
            "Witch/Amygdala added event ID collides with destination EMEVD"
        )
    mapping = _mapping(ids)
    health = _remap(donor[12204802], mapping)
    health = _replace_once(
        health, "CreatePlaylog(88);", "CreatePlaylog(78);", "destination playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(3300010, 104, Enabled);",
        "StartTimeMeasurement(3300010, 94, Enabled);",
        "destination time measurement",
    )
    activation = _remap(donor[12201802], mapping)
    coop = _remap(donor[12201804], mapping)
    music = _remap(donor[12204803], mapping)
    camera = _remap(donor[12204804], mapping)
    if camera.count("SetLockcamSlotNumber(22, 0,") != 1:
        raise ValueError("Witch/Amygdala expected one source lockcam binding")
    camera = camera.replace(
        "SetLockcamSlotNumber(22, 0,", "SetLockcamSlotNumber(33, 0,"
    )
    copied_events = (
        (12204807, ids.phase, 1),
        (12204808, ids.visibility, 2),
        (12204810, ids.second_start, 1),
        (12204811, ids.patrol, 1),
        (12204812, ids.revival, 2),
        (12204814, ids.warp_select, 2),
        (12204820, ids.warp, 8),
        (12204830, ids.post_warp, 2),
        (12204832, ids.minion_count, 3),
        (12204835, ids.minion_watch, 3),
        (12204838, ids.summon, 1),
        (12204839, ids.generator_manager, 1),
        (12204840, ids.summon_one, 1),
        (12204841, ids.summon_two, 1),
        (12204842, ids.summon_three, 1),
        (12204843, ids.minion_setup, 1),
        (12204844, ids.insight, 1),
    )
    initializers = [
        row
        for source, _, count in copied_events
        for row in _initializers(donor[0], source, count, mapping)
    ]
    initializers.append(f"    $InitializeEvent(0, {ids.completion_cleanup});")
    cleanup = f"""$Event({ids.completion_cleanup}, Default, function() {{
    WaitFor(EventFlag(13301800));
    ChangeCharacterEnableState({ids.second_entity}, Disabled);
    ForceCharacterDeath({ids.second_entity}, false);
    ChangeCharacterEnableState({ids.minion_first_entity}, Disabled);
    ChangeCharacterEnableState({ids.minion_first_entity + 1}, Disabled);
    ChangeCharacterEnableState({ids.minion_first_entity + 2}, Disabled);
    DeactivateGenerator({ids.generator_entity_first}, Disabled);
    DeactivateGenerator({ids.generator_entity_first + 1}, Disabled);
    DeactivateGenerator({ids.generator_entity_first + 2}, Disabled);
}});"""
    edits = {
        0: _replace_once(
            arena[0],
            "    $InitializeEvent(0, 13304840);",
            "    $InitializeEvent(0, 13304840);\n" + "\n".join(initializers),
            "combat initializer anchor",
        ),
        13301802: activation,
        13301803: coop,
        13304802: health,
        13304803: music,
        13304804: camera,
        # Amygdala-only phase and part routines are still initialized by Event(0),
        # so make their retained signatures explicitly inert before importing Witch routines.
        13304807: _end(arena[13304807]),
        13304808: _end(arena[13304808]),
        13304820: _end(arena[13304820]),
        13304830: _end(arena[13304830]),
        13304840: _end(arena[13304840]),
    }
    imported = {
        destination_event: _remap(donor[source_event], mapping)
        for source_event, destination_event, _ in copied_events
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join((*imported.values(), cleanup))
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena) | set(ids.events()):
        raise ValueError("Witch/Amygdala patch changed event identities")
    for event, original in arena.items():
        if event not in edits and output[event] != original:
            raise ValueError(f"Witch/Amygdala changed unrelated Amygdala event {event}")
    for event in (13301800, 13301801, 13304805, 13304870, 13304871):
        if output[event] != arena[event]:
            raise ValueError(
                "Witch/Amygdala changed Amygdala terminal, rewards, or fog flow"
            )
    copied = "\n".join((*imported.values(), health, activation, coop, music, camera))
    if re.search(r"(?<!\d)(?:122|220)\d+(?!\d)", copied):
        raise ValueError(
            "Witch/Amygdala copied source map literals without an explicit remap"
        )
    return result


def _require(
    slots: Sequence[Slot], entity: int, archetype: Archetype, map_name: str
) -> Slot:
    rows = [
        slot
        for slot in slots
        if slot.entity_id == entity
        and slot.archetype == archetype
        and slot.map_name == map_name
    ]
    if len(rows) != 1 or rows[0].dummy or rows[0].talk_id:
        raise ValueError(
            f"Witch/Amygdala requires one pinned ordinary actor {entity} in {map_name}"
        )
    return rows[0]


def _initialization(source: Slot, target: Slot) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": WITCH_PINS[WITCH],
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
    }


def _region_additions(target: Slot, ids: WitchAmygdalaIds) -> list[dict]:
    rows = []
    for source_id, (source_name, fingerprint) in (
        *WARP_REGION_PINS.items(),
        *SPAWN_REGION_PINS.items(),
    ):
        is_warp = source_id in WARP_REGION_PINS
        index = source_id - (2202810 if is_warp else 2205500)
        destination_id = (
            ids.warp_first_entity if is_warp else ids.spawn_first_entity
        ) + index
        rows.append(
            {
                "source_map": "m22_00_00_00",
                "source_region": source_name,
                "source_entity_id": source_id,
                "source_provenance": {
                    "format": "bb-boss-region-pin-v1",
                    "region_sha256": fingerprint,
                },
                "source_anchor_part": "c2100_0000",
                "source_anchor_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": WITCH_PINS[WITCH],
                },
                "destination_map": target.map_name,
                "destination_region": f"ap_witch_{'warp' if is_warp else 'spawn'}_{index:02d}",
                "destination_entity_id": destination_id,
                "destination_anchor_part": target.part_name,
                "destination_anchor_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": AMYGDALA_PIN,
                },
            }
        )
    return rows


def _generator_additions(target: Slot, ids: WitchAmygdalaIds) -> list[dict]:
    minion_names = {
        f"c2050_000{index}": f"ap_witch_minion_{index}" for index in range(3)
    }
    spawn_map = {
        name: f"ap_witch_spawn_{index:02d}"
        for index, (name, _) in enumerate(SPAWN_REGION_PINS.values())
    }
    return [
        {
            "source_map": "m22_00_00_00",
            "source_event": source_name,
            "source_event_id": source_event_id,
            "source_entity_id": source_entity,
            "source_fingerprint": fingerprint,
            "destination_map": target.map_name,
            "destination_event": f"ap_witch_generator_{index}",
            "destination_event_id": ids.generator_event_first + index,
            "destination_entity_id": ids.generator_entity_first + index,
            "destination_part_name": "h002301",
            "destination_region_name": None,
            "spawn_part_map": {f"c2050_000{index}": minion_names[f"c2050_000{index}"]},
            "spawn_point_map": {
                name: spawn_map[name]
                for name in tuple(SPAWN_REGION_PINS)[index * 4 : (index + 1) * 4]
                for name in [SPAWN_REGION_PINS[name][0]]
            },
        }
        for index, (
            source_name,
            source_event_id,
            source_entity,
            fingerprint,
        ) in enumerate(GENERATOR_PINS)
    ]


def native_plan_witch_at_amygdala(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: WitchAmygdalaIds = DEFAULT_IDS,
) -> dict:
    """Return the native construction request; builder wiring remains separate."""
    donor, arena = read_blob(BUNDLE, WITCH_SOURCE).decode("utf-8-sig"), read_blob(
        BUNDLE, AMYGDALA_SOURCE
    ).decode("utf-8-sig")
    _verify(donor, DONOR_HASHES, "Witch donor")
    _verify(arena, ARENA_HASHES, "Amygdala arena")
    _validate_ids(ids, arena)
    primary = _require(slots, WITCH, WITCH_ARCHETYPE, "m22_00_00_00")
    target = _require(slots, AMYGDALA, AMYGDALA_ARCHETYPE, "m33_00_00_00")
    second = _require(slots, SECOND, SECOND_ARCHETYPE, "m22_00_00_00")
    minions = [
        _require(slots, entity, MINION_ARCHETYPE, "m22_00_00_00") for entity in MINIONS
    ]
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        primary.archetype,
        warnings=[
            "experimental Witch pair-at-Amygdala contract; runtime arena fit is unobserved"
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
        raise ValueError("Witch/Amygdala primary normalization is ambiguous")
    helpers = [
        (second, ids.second_entity, "ap_witch_second"),
        *[
            (minion, ids.minion_first_entity + index, f"ap_witch_minion_{index}")
            for index, minion in enumerate(minions)
        ],
    ]
    additions = [
        {
            "source_map": helper.map_name,
            "source_part": helper.part_name,
            "source_anchor_part": primary.part_name,
            "source_entity_id": helper.entity_id,
            "source_archetype": asdict(helper.archetype),
            "source_part_kind": "enemy",
            "source_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": WITCH_PINS[helper.entity_id],
                "anchor_sha256": WITCH_PINS[WITCH],
            },
            "source_initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
            "destination_map": target.map_name,
            "destination_anchor_part": target.part_name,
            "destination_part": destination_part,
            "destination_entity_id": destination_entity,
            "allocation_evidence": "project-reserved helper ID; native writer checks all Part/Region/Event collisions",
        }
        for helper, destination_entity, destination_part in helpers
    ]
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "amygdala<-witch-of-hemwick"},
        "boss_actor_additions": additions,
        "boss_region_additions": _region_additions(target, ids),
        "boss_generator_additions": _generator_additions(target, ids),
        "primary_init_source_bindings": [_initialization(primary, target)],
        "boss_actor_scaling_requirements": [
            {
                "destination_map": target.map_name,
                "destination_part": part,
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": source.archetype.npc_param_id,
                "strategy": "allocate_distinct_verified_helper_clone",
            }
            for source, _, part in helpers
        ],
        "boss_contract": {
            "format": "bb-witch-amygdala-contract-v1",
            "arena": "amygdala",
            "donor": "witch-of-hemwick",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(DONOR_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "preserved_destination_events": [
                13301800,
                13301801,
                13304805,
                13304870,
                13304871,
            ],
            "terminal_policy": "retain Amygdala terminal; Witch primary only dies after pinned pair revival controller reaches its two-body death path",
            "native_requirements": {
                "actor_additions": 4,
                "region_additions": 20,
                "generator_additions": 3,
                "generator_collision": "source h000013 maps to verified Amygdala anchor collision h002301",
                "destination_anchor": {
                    "map": target.map_name,
                    "part": target.part_name,
                    "part_sha256": AMYGDALA_PIN,
                    "collision_name": "h002301",
                },
            },
            "event_patch": {
                "changed_events": [
                    13301802,
                    13301803,
                    13304802,
                    13304803,
                    13304804,
                    13304807,
                    13304808,
                    13304820,
                    13304830,
                    13304840,
                ],
                "added_events": list(ids.events()),
                "source_event_remap": _mapping(ids),
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
