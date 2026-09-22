"""Pinned Ebrietas combat package in Rom's Byrgenwerth arena.

The contract keeps Rom's terminal, post-defeat blood-moon sequence, fog,
player-fall safety and co-op progression.  Runtime behavior is unobserved.
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
from .rom_ebrietas_contract import (
    BUNDLE,
    EBRIETAS_CORE_PINS,
    EBRIETAS_OWNER_PINS,
    EBRIETAS_STATES,
    ROM_CORE_PINS,
    DONOR_ALTERNATES as ROM_ARENA_ALTERNATES,
    ROM_SOURCE,
    ROM_SPIDER_PINS,
    ROM_STATES,
    SPIDER_ARCHETYPE,
)
from .scaling import plan_scaling

EBRIETAS_SOURCE = "event/m24_02_00_00.emevd.dcx.js"
EBRIETAS, ROM, OWNER = 2420800, 3200800, 2420801
EBRIETAS_ARCHETYPE = Archetype("c2510", 251000, 251000, 0)
ROM_ARCHETYPE = Archetype("c5100", 510000, 510000, 334233600)
OWNER_ARCHETYPE = Archetype("c9010", 251001, 1, 0)
POSTBOSS_ARCHETYPES = {
    "c8070_0000": Archetype("c8070", 807000, 1, 0),
    "c3060_0000": Archetype("c3060", 807000, 1, 0),
}

PROJECT_MIN, PROJECT_MAX = 12992200, 12992299
OWNER_ENTITY, OWNER_PART = 980300, "ap_ebrietas_bullet_owner"

SOURCE_HASHES = {
    0: "cda0f114ad3f96b4b93fda3b81ac6d6ed5808bdb0be3f6d16e8225733e729dde",
    12421802: "9bc79c8e55c2a2c9793a90070de1f76c35a46ebd98c2c79176b2fcc02ae8adc4",
    12424802: "effdc8bf4ca63c0371f209afbd388d0c682793bc2efaf258675e871bcae21ad2",
    12424803: "a487e349f0a416298a26fb93c87c0c57fd7211e7da3da8938d37b6e909130966",
    12424804: "9324596b40c1d5a8ec57a11c71eab66105a1550a81cdcacd4432a86ec366ea74",
    12424870: "4fac0ea46041effd27d59b41752ef9758ba1c6021647ef9831f87de11e5564ba",
    12424871: "50091165e085e178edd4641859d7af08032e2dc4c1be99e7d3631ecbaa07abbc",
    12424980: "cebf5265578c05b598b8c2f9d2c524c852a32e48facb4856db1426185f098cb1",
    12424990: "0b8bf3929d610e3938673ca58072126cbde658e3aa75911c958a1b7e7f43a700",
}

ARENA_HASHES = {
    0: "06d52948a0106e003bcf803c001e678e5eb87fc4be1c04a7ed2721522f2e54c7",
    13201800: "9cd2500de447eb5c5a4b5c7487e0f073653fb8f5e7f72ed3de3f00f148dd1fbf",
    13201801: "771aaffb640aa55836e63e081a03cd88147c33ca4500fdfbb2b57cdee622a310",
    13201802: "9ac690a52a2c21af5b5469de792caab012a501463ae8728261636b49e34fc444",
    13201803: "539f4a5d00bf48576529b6153f19b5277f2f9480fe673199d6762224bc9f204e",
    13201804: "d3a13352368ec01825c2803b7dacf01f6016b9728f66e88075f21428c47b4df3",
    13204000: "b656b38c1a7222ecff6418a0b44657163c08c99f3cbc0cd32ab533fc67729b89",
    13204050: "bf2e3255853fc04a81010a965c23afa2843084a47da2baebc46ef8f797d19bc4",
    13204730: "629b97cb1ad7b9f3f34d347c149aae14af0f0262aa779eee5172a16eec96f4eb",
    13204802: "5ad2891179d1d835dcce0749eb93e20077cea36fd218e2bc126265912499c61e",
    13204803: "5ef611fa7eea1582d3d5395d2f8507075aecc92fde3c1c23edcc77c092d9901d",
    13204804: "d4de375d4f13ffe206a977798943064e6b6069f5bf9f44743d87780ecb9bad9c",
    13204805: "571957f0e1cd7714c8860db6c4f7c9a0a5fc314f9279cddaff3a22c9765752c3",
    13204807: "a92a7d98eea9d8351bc1886c7d57d1f42b289965d4feaa907a78180bf6de5205",
    13204808: "002b06f501a776d5c0e4a15d0bb577f241c5a767eac73e44caf6ee990be850a6",
    13204809: "2a4be9a13d8f76efbeab63430ed9533767d15e47b33a05444d1c542c24ecd819",
    13204810: "da8c045a4a0e2c24443b6230d1175733c430174b85e9166c08860e0722b5e2c7",
    13204820: "4a17fb43863b595190ba9795cbd9755078fa3f3b68a07e6e3b0a4825d93ec457",
    13204821: "ef34a4b2f49acd0cec97a8e8bf7d862f302be6da181b419d7f240c0a957f8c8e",
    13204830: "f00cedfee8df357686c4508b74c0970c1bf1ee06c202d0221f0758dec42f9cda",
    13204831: "8e528ec028e933a91ed7cf79a20a00818c0cb54722a328c404feec17b170ed50",
    13204832: "d2870a913d562021718220dcb8deaec067b680f0012d44976d7bf7561c04565e",
    13204833: "1c46262105bb76d4b5101305f68c32203ee0a3aa32705156a786f19cc29577e0",
    13204834: "6b8a310571c07e306ef108da2287eaddad9723fd335a5397e34ba7200b714acc",
}

POSTBOSS_PINS = {
    "m32_00_00_00": {
        "c8070_0000": "1570ba9e1ba1ba62e14ddcd0854710625f2d39ed979b1fb538d4d4c11baf19fb",
        "c3060_0000": "1e2654adb2056f04f96ba5c1f98652524745a942ec3e627f09a9eccf545212a6",
    },
    "m32_00_00_01": {
        "c8070_0000": "608e0c1f4968753ef445dd0369cc99a225f09783736927bba16836db67284b05",
        "c3060_0000": "e01dfe877989f59aaabc85ed58ac6c865baad0a76e924756daf816d13acdaff6",
    },
}


@dataclass(frozen=True)
class EbrietasRomIds:
    phase: int = 12992200
    bullet: int = 12992201
    limb_part5: int = 12992202
    limb_parts1_4: int = 12992203
    owner_cleanup: int = 12992204
    spider_cleanup: int = 12992205
    owner_entity: int = OWNER_ENTITY
    owner_part: str = OWNER_PART
    evidence: str = (
        "Ebrietas/Rom allocation v1; full original EMEVD and MSB entity scan"
    )

    def events(self) -> tuple[int, ...]:
        return (
            self.phase,
            self.bullet,
            self.limb_part5,
            self.limb_parts1_4,
            self.owner_cleanup,
            self.spider_cleanup,
        )


DEFAULT_IDS = EbrietasRomIds()


def _verify(
    text: str,
    pins: Mapping[int, str],
    role: str,
    alternates: Mapping[int, str] | None = None,
) -> dict[int, str]:
    blocks = event_blocks(text)
    for event_id, digest in pins.items():
        body = blocks.get(event_id)
        actual = "" if body is None else hashlib.sha256(body.encode()).hexdigest()
        allowed = {digest}
        alternate = (alternates or {}).get(event_id)
        if alternate is not None:
            allowed.add(alternate)
        if actual not in allowed:
            raise ValueError(f"unsupported original {role} event {event_id}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Ebrietas/Rom expected one {label}")
    return text.replace(old, new, 1)


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _remap(text: str, mapping: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda m: str(mapping.get(int(m[0]), int(m[0]))),
        text,
    )


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
        values.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
        )
    for row in (
        read_prefix(BUNDLE, "mined/")
        .get("mined/msb_enemies.tsv", b"")
        .decode("utf-8-sig")
        .splitlines()[1:]
    ):
        columns = row.split("\t")
        if len(columns) > 3 and columns[3].lstrip("-").isdigit():
            values.add(int(columns[3]))
    return values


def _validate(ids: EbrietasRomIds, destination: str = "") -> None:
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    events = ids.events()
    if (
        len(set(events)) != len(events)
        or any(not PROJECT_MIN <= event <= PROJECT_MAX for event in events)
        or set(events).intersection(local | _original_ids())
        or ids.owner_entity != OWNER_ENTITY
        or ids.owner_entity in local | _original_ids()
        or ids.owner_part != OWNER_PART
        or not ids.evidence.strip()
    ):
        raise ValueError(
            "Ebrietas/Rom IDs must be collision-free project-owned 129922xx/980300 values"
        )


def _mapping(ids: EbrietasRomIds) -> dict[int, int]:
    return {
        EBRIETAS: ROM,
        OWNER: ids.owner_entity,
        12421800: 13201800,
        12421802: 13201802,
        12424800: 13204800,
        12424801: 13204801,
        12424802: 13204802,
        12424803: 13204803,
        12424804: 13204804,
        12424980: ids.phase,
        12424990: ids.bullet,
        12424870: ids.limb_part5,
        12424871: ids.limb_parts1_4,
        2423802: 3203802,
        2423803: 3203803,
        2422802: 3202801,
        2420010: 3200010,
    }


def _source_calls(event_zero: str, mapping: Mapping[int, int]) -> list[str]:
    event_ids = (12424980, 12424990, 12424870, 12424871)
    rows = [
        row
        for row in event_zero.splitlines()
        if any(
            re.search(r"\$InitializeEvent\([^,]+,\s*" + str(event) + r"(?:,|\))", row)
            for event in event_ids
        )
    ]
    expected = {12424980: 1, 12424990: 1, 12424870: 1, 12424871: 4}
    for event, count in expected.items():
        actual = sum(str(event) in row for row in rows)
        if actual != count:
            raise ValueError(
                f"Ebrietas Event(0) lacks exact initializer closure for {event}"
            )
    return [_remap(row, mapping) for row in rows]


def patch_ebrietas_at_rom(
    destination: str, donor_source: str, ids: EbrietasRomIds = DEFAULT_IDS
) -> str:
    donor = _verify(donor_source, SOURCE_HASHES, "Ebrietas donor")
    original = _verify(destination, ARENA_HASHES, "Rom arena", ROM_ARENA_ALTERNATES)
    _validate(ids, destination)
    mapping = _mapping(ids)

    activation = original[13201802]
    activation = _replace_once(
        activation,
        "    WaitFor(\n",
        "    ForceAnimationPlayback(3200800, 7001, true, false, false);\n"
        "    SetCharacterImmortality(3200800, Enabled);\n"
        "    SetSpEffect(3200800, 5647, false);\n"
        "    WaitFor(\n",
        "Ebrietas wake-up preparation",
    )
    activation = _replace_once(
        activation,
        "    SetEventFlag(13204800, ON);",
        "    ForceAnimationPlayback(3200800, 7000, false, true, false);\n"
        "    SetCharacterImmortality(3200800, Disabled);\n"
        "    ClearSpEffect(3200800, 5647);\n"
        "    SetEventFlag(13204800, ON);",
        "Ebrietas wake-up completion",
    )

    health = _remap(donor[12424802], mapping)
    health = health.replace("CreatePlaylog(104);", "CreatePlaylog(124);")
    health = health.replace(
        "StartTimeMeasurement(3200010, 40, Enabled);",
        "StartTimeMeasurement(3200010, 62, Enabled);",
    )
    music = donor[12424803]
    if music.count("SetEventFlag(12425246, ON);") != 2:
        raise ValueError("Ebrietas/Rom expected two source arena music flags")
    music = _remap(
        re.sub(r"^\s*SetEventFlag\(12425246, ON\);\n", "", music, flags=re.MULTILINE),
        mapping,
    )
    camera = _remap(donor[12424804], mapping).replace(
        "SetLockcamSlotNumber(24, 2,", "SetLockcamSlotNumber(32, 0,"
    )
    attachments = [
        _remap(donor[event], mapping)
        for event in (12424980, 12424990, 12424870, 12424871)
    ]

    calls = _source_calls(donor[0], mapping)
    calls.extend(
        (
            f"    $InitializeEvent(0, {ids.owner_cleanup});",
            f"    $InitializeEvent(0, {ids.spider_cleanup});",
        )
    )
    constructor = _replace_once(
        original[0],
        "    $InitializeEvent(0, 13204821);",
        "    $InitializeEvent(0, 13204821);\n"
        f"    CreateBulletOwner({ids.owner_entity});\n" + "\n".join(calls),
        "Rom constructor combat anchor",
    )

    owner_cleanup = f"""$Event({ids.owner_cleanup}, Default, function() {{
    WaitFor(EventFlag(13201800));
    ChangeCharacterEnableState({ids.owner_entity}, Disabled);
    ForceCharacterDeath({ids.owner_entity}, false);
}});"""
    spider_lines = "\n".join(
        f"    ChangeCharacterEnableState({3200200 + i}, Disabled);\n"
        f"    SetCharacterAIState({3200200 + i}, Disabled);"
        for i in range(30)
    )
    death_lines = "\n".join(
        f"    ForceCharacterDeath({3200200 + i}, false);" for i in range(30)
    )
    spider_cleanup = f"""$Event({ids.spider_cleanup}, Default, function() {{
{spider_lines}
    WaitFor(EventFlag(13201800));
{death_lines}
}});"""
    edits = {
        0: constructor,
        13201802: activation,
        13204802: health,
        13204803: music,
        13204804: camera,
    }
    for event in (13204000, 13204050, 13204730, 13204807, 13204808, 13204809, 13204810):
        edits[event] = _end_event(original[event])
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join([*attachments, owner_cleanup, spider_cleanup])
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(original).union(ids.events()):
        raise ValueError("Ebrietas/Rom patch changed event identities")
    for event_id, body in original.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Ebrietas/Rom patch changed unrelated event {event_id}")
    protected = (
        13201800,
        13201801,
        13201803,
        13201804,
        13204805,
        13204820,
        13204821,
        13204830,
        13204831,
        13204832,
        13204833,
        13204834,
    )
    for event_id in protected:
        if output[event_id] != original[event_id]:
            raise ValueError(f"Ebrietas/Rom changed protected arena event {event_id}")
    copied = "\n".join(
        output[event]
        for event in (
            13204802,
            13204803,
            13204804,
            ids.phase,
            ids.bullet,
            ids.limb_part5,
            ids.limb_parts1_4,
        )
    )
    if re.search(r"(?<!\d)(?:124\d{5}|242\d{4})(?!\d)", copied):
        raise ValueError("Ebrietas/Rom copied combat body retains a donor-map literal")
    return result


def _pin(part_sha256: str, anchor_sha256: str | None = None) -> dict:
    values = (part_sha256,) if anchor_sha256 is None else (part_sha256, anchor_sha256)
    if any(len(value) != 64 or re.search(r"[^0-9a-f]", value) for value in values):
        raise ValueError("Ebrietas/Rom native pins require lowercase SHA256 values")
    result = {"format": "bb-boss-actor-pin-v1", "part_sha256": part_sha256}
    if anchor_sha256 is not None:
        result["anchor_sha256"] = anchor_sha256
    return result


def _initialization() -> dict:
    return {"talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1}


def _require(slots: Sequence[Slot], entity: int, archetype: Archetype) -> list[Slot]:
    rows = sorted(
        (
            slot
            for slot in slots
            if slot.entity_id == entity
            and slot.archetype == archetype
            and not slot.dummy
            and not slot.talk_id
        ),
        key=lambda slot: slot.key,
    )
    if not rows:
        raise ValueError(f"unsupported Ebrietas/Rom placement provenance for {entity}")
    return rows


def native_plan_ebrietas_at_rom(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: EbrietasRomIds = DEFAULT_IDS,
) -> dict:
    """Return the two-state primary swap and pinned bullet-owner addition."""
    _verify(
        read_blob(BUNDLE, EBRIETAS_SOURCE).decode("utf-8-sig"),
        SOURCE_HASHES,
        "Ebrietas donor",
    )
    arena = read_blob(BUNDLE, ROM_SOURCE).decode("utf-8-sig")
    _verify(arena, ARENA_HASHES, "Rom arena", ROM_ARENA_ALTERNATES)
    _validate(ids, arena)
    sources = _require(slots, EBRIETAS, EBRIETAS_ARCHETYPE)
    owners = _require(slots, OWNER, OWNER_ARCHETYPE)
    destinations = _require(slots, ROM, ROM_ARCHETYPE)
    spiders = {
        3200200 + index: _require(slots, 3200200 + index, SPIDER_ARCHETYPE)
        for index in range(30)
    }
    if (
        len(sources) != 2
        or {row.map_name for row in sources} != set(EBRIETAS_STATES)
        or len(owners) != 2
        or {row.map_name for row in owners} != set(EBRIETAS_STATES)
        or len(destinations) != 2
        or {row.map_name for row in destinations} != set(ROM_STATES)
        or any(
            len(rows) != 2 or {row.map_name for row in rows} != set(ROM_STATES)
            for rows in spiders.values()
        )
    ):
        raise ValueError(
            "Ebrietas/Rom requires exact two-state source, owner and 31-actor destination roster"
        )

    source_by_state = {row.map_name: row for row in sources}
    owner_by_state = {row.map_name: row for row in owners}
    destination_by_state = {row.map_name: row for row in destinations}
    swap = Swap(
        destinations[0].logical_key,
        [row.key for row in destinations],
        {row.key: row.archetype for row in destinations},
        ROM_ARCHETYPE,
        EBRIETAS_ARCHETYPE,
        warnings=[
            "experimental Ebrietas-at-Rom contract; runtime arena, bullet owner and AP behavior require validation"
        ],
        destinations={
            row.key: {
                "map_name": row.map_name,
                "entity_id": row.entity_id,
                "x": row.x,
                "y": row.y,
                "z": row.z,
            }
            for row in destinations
        },
    )
    changes, skips = plan_scaling(
        [swap], list(destinations), dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError(
            "Ebrietas/Rom primary swap has an ambiguous normalization plan"
        )

    additions, bindings = [], []
    for destination_state in ROM_STATES:
        source_state = EBRIETAS_STATES[ROM_STATES.index(destination_state)]
        source, owner = source_by_state[source_state], owner_by_state[source_state]
        destination = destination_by_state[destination_state]
        bindings.append(
            {
                "source_map": source_state,
                "source_part": source.part_name,
                "source_entity_id": EBRIETAS,
                "source_archetype": asdict(EBRIETAS_ARCHETYPE),
                "source_provenance": _pin(EBRIETAS_CORE_PINS[source_state]),
                "source_initialization": _initialization(),
                "destination_map": destination_state,
                "destination_part": destination.part_name,
                "destination_entity_id": ROM,
            }
        )
        additions.append(
            {
                "source_map": source_state,
                "source_part": owner.part_name,
                "source_anchor_part": source.part_name,
                "source_entity_id": OWNER,
                "source_archetype": asdict(OWNER_ARCHETYPE),
                "source_part_kind": "enemy",
                "source_provenance": _pin(
                    EBRIETAS_OWNER_PINS[source_state], EBRIETAS_CORE_PINS[source_state]
                ),
                "source_initialization": _initialization(),
                "destination_map": destination_state,
                "destination_anchor_part": destination.part_name,
                "destination_part": ids.owner_part,
                "destination_entity_id": ids.owner_entity,
                "allocation_evidence": ids.evidence,
            }
        )

    retained = []
    for state in ROM_STATES:
        for index in range(30):
            slot = next(
                row for row in spiders[3200200 + index] if row.map_name == state
            )
            retained.append(
                {
                    "map": state,
                    "part": slot.part_name,
                    "entity_id": slot.entity_id,
                    "archetype": asdict(slot.archetype),
                    "source_provenance": _pin(ROM_SPIDER_PINS[state][index]),
                    "source_initialization": _initialization(),
                    "policy": "retain_native_part_disabled_alive_until_destination_completion",
                }
            )
        for part, archetype in POSTBOSS_ARCHETYPES.items():
            matches = [
                row
                for row in slots
                if row.map_name == state
                and row.part_name == part
                and row.entity_id == 3200801
                and row.archetype == archetype
            ]
            if len(matches) != 1:
                raise ValueError(
                    "Ebrietas/Rom post-defeat actor placement provenance is incomplete"
                )
            retained.append(
                {
                    "map": state,
                    "part": part,
                    "entity_id": 3200801,
                    "archetype": asdict(archetype),
                    "source_provenance": _pin(POSTBOSS_PINS[state][part]),
                    "source_initialization": _initialization(),
                    "policy": "retain_native_post_defeat_actor_unchanged",
                }
            )

    requirements = [
        {
            "destination_map": row["destination_map"],
            "destination_part": row["destination_part"],
            "parent_logical_key": swap.logical_key,
            "source_npc_param_id": OWNER_ARCHETYPE.npc_param_id,
            "strategy": "allocate_distinct_verified_helper_clone",
        }
        for row in additions
    ]
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "rom<-ebrietas"},
        "boss_contract": {
            "format": "bb-ebrietas-rom-contract-v1",
            "arena": "rom",
            "donor": "ebrietas",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(SOURCE_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "arena_hash_alternates": dict(ROM_ARENA_ALTERNATES),
            "preserved_destination_events": [
                13201800,
                13201801,
                13201803,
                13201804,
                13204805,
                13204820,
                13204821,
                13204830,
                13204831,
                13204832,
                13204833,
                13204834,
            ],
            "retained_destination_helpers": retained,
            "retired_spider_policy": "disable all thirty alive before combat; kill only after destination completion",
            "source_actor_event_closure": {
                "12421802": "Ebrietas wake timing woven into Rom damage trigger",
                "12424802": "health and co-op scaling copied",
                "12424803": "music copied onto Rom sounds and arena region",
                "12424804": "message camera copied onto Rom lockcam",
                "12424980": "phase AI command copied",
                "12424990": "bullet-owner attack copied",
                "12424870": "Part5 controller copied",
                "12424871": "four remaining limb bindings copied",
            },
        },
        "boss_actor_additions": additions,
        "primary_init_source_bindings": bindings,
        "boss_actor_scaling_requirements": requirements,
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }


def ebrietas_rom_helper_scaling_parents(plan: Mapping) -> dict[tuple[str, str], str]:
    rows = plan.get("boss_actor_scaling_requirements", ())
    result = {
        (row["destination_map"], row["destination_part"]): row["parent_logical_key"]
        for row in rows
    }
    if len(result) != len(rows):
        raise ValueError("duplicate Ebrietas helper scaling destination")
    return result
