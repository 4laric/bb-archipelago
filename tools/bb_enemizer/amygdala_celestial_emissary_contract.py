"""Pinned Amygdala combat in the Celestial Emissary arena.

The visible c2500 body is Amygdala.  The native Celestial terminal retains its c2570
subject and an added bridge kills that giant only after Amygdala dies.  Runtime
behavior is unobserved.
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
AMYGDALA_SOURCE = "event/m33_00_00_00.emevd.dcx.js"
CELESTIAL_SOURCE = "event/m24_02_00_00.emevd.dcx.js"
AMYGDALA = 3300800
PRIMARY, GIANT = 2420810, 2420811
AMYGDALA_ARCHETYPE = Archetype("c5120", 512000, 512000, 0)
PRIMARY_ARCHETYPE = Archetype("c2500", 250080, 250060, 0)
GIANT_ARCHETYPE = Archetype("c2570", 257010, 257010, 0)
WAVES = (2420711, 2420712, 2420713, 2420716, 2420717, 2420719, 2420720)
SUPPORT = (2420750, 2420751)
GENERATORS = (2423711, 2423712, 2423713, 2423716, 2423717, 2423719, 2423720)
TERMINAL = 12421700
PROJECT_MIN, PROJECT_MAX = 12992500, 12992599

DONOR_HASHES = {
    0: "b86f288c46fc74ddc81530e62437d9497c5a63ec09488c068211d85f4054f934",
    13301802: "dbf7c452ecf425a41d9c724ba0568db015224bb1a3b1516c9033779c59c1d3ae",
    13301803: "7613c67c60f7fd94fe8152c96887113aabaeee5cc728f79bd3c2fcfd2bfb0dd9",
    13304802: "448a7775ab941832e255cbb918acdb25b4ce8dc067f89376ff6404eee9b3ca69",
    13304803: "0f6aa448c5c4af20db4b5069bdce6516c2bc4d4f5b1ed5ccb1653bd47f18ccaf",
    13304804: "ebe1b13a76f981e01d250c845698e7e1625d43a0fb7d0a350beb647256e55155",
    13304807: "32354612205279186043fb283a4c29962803822747e0ffb82fd05bcde48e41d6",
    13304808: "0b9f21dbf5d1f79aa0d6e393c976e3a24f102cfcc25930271ddd0e6d08fa5055",
    13304820: "e2d693a68d6560f3506e2070501ce2a919f1a70640a3145bab556237aac53592",
    13304830: "3ee36ea1ac6d459c45c95aad95bee1e0c3201bc8fdf460a2b3cebae3fa80a9f8",
    13304840: "d3c6246b1286e98ca0f27cb5123d6bdc043982618d533a9aa76a647d3ac5ff68",
}
ARENA_HASHES = {
    0: "cda0f114ad3f96b4b93fda3b81ac6d6ed5808bdb0be3f6d16e8225733e729dde",
    12421700: "483357a45d27cb2f9df9212f1daf7f10119c4d35ad849e4d179f0dd9e34d2794",
    12421701: "74cf39dcaa359da0c26e3e97a3ea8f890f6eab39a6c0f42b9cc61bb128c3929d",
    12421702: "e5832b29e358dfe905ab5d47a0c23a84283f9b645dddecaf9a0e7e7ff56ed726",
    12421703: "bb9efdf0969275401f21b29c03ec6cb310a753c98c439f56c12738ebc16b44b0",
    12424702: "b95fb234bbd7f7f9696b5352703a0efb8f965fdafde6860489b2e017fe7ccb4b",
    12424703: "a73cb1fa43c1017779bc8c9c97fd6cfd51726dccdc4bf865dd8096b86b81a3c4",
    12424704: "3d91994d955c589fc9591706094ee3495f2cfadbe0c42081d19055f936b33301",
    12424705: "421cfaba876dca84f5ffeeb1e0c6c90cb8a4b70d07c62fde3452718e6c704da7",
    12424770: "0c3ad0e5b83f271b42caf897500cdd3327d2a7a383e729502d4085af9de191df",
    12424780: "58292f49f2c2bd4f192fee328efde8df50cf316bbe8a1c276ae3dbee85d32352",
    12424784: "e4ddde103a86fdfa89d4c7b741de7fb3289572f09141930f3deaf1329771ad60",
    12424785: "0dde9aa805e67a42f8105d18523be600fcc71aeca5de67455391ce6a034a21ea",
    12424787: "b08453f27d5cab1fa0b9caa19f92c6a50a55c1f7659fe0541118990e0355406c",
    12424790: "0c2c830c5dda5c32fbc108aa9ece339d2c65fe08156c229de8bc998bdfe3dd9a",
    12424791: "1f4a365ca7d7f959da65d08223b0f3562023ac20a704943f020d3c8e4bf76f43",
    12424792: "074453574579340828f22913794084de74be8b5fbaafa60d5c4483c34d0c05d8",
    12424795: "a69637947e83355022e5b883e1ce25bd6744e471beb8d2da54de8acbea6af417",
}
EBRIETAS_HASHES = {
    12421800: "7cb7c78833c5ef60a5599d35c22964e87b75f980c3165e139d7c28fc8a1bd34b",
    12421801: "2b01b305ae68b5d9e67407c316ed1a902f182124022987b9e258b527fb67f97f",
    12421802: "9bc79c8e55c2a2c9793a90070de1f76c35a46ebd98c2c79176b2fcc02ae8adc4",
    12421803: "dcbbafd95ebeebce5ddd63d637fc07b93bff8f52c33b77665e0ca21e6d649152",
    12424802: "effdc8bf4ca63c0371f209afbd388d0c682793bc2efaf258675e871bcae21ad2",
    12424803: "a487e349f0a416298a26fb93c87c0c57fd7211e7da3da8938d37b6e909130966",
    12424804: "9324596b40c1d5a8ec57a11c71eab66105a1550a81cdcacd4432a86ec366ea74",
    12424805: "e5cd1832606baf9b45afa6e5acb1f12c3e34cb52c26a86a687a0d65022f152eb",
    12424810: "593b24830019a78d0d17d10df4808d26d50b2ab3c2a0b07bff678974b28d5729",
    12424811: "2c98ff8ebff5a7fc0c83dcd11e62cd255e587b9de534d2868d3ef08047987618",
    12424812: "b6e8cf0d6ca0a2afe743f9251730d15833be4f8a1c143e83ee9ce13dbb55256f",
    12424813: "640ca6bac740fe18404ee8f78f3e71bd6608f8914f3044bae018d9781f5e5e8d",
    12424870: "4fac0ea46041effd27d59b41752ef9758ba1c6021647ef9831f87de11e5564ba",
    12424871: "50091165e085e178edd4641859d7af08032e2dc4c1be99e7d3631ecbaa07abbc",
    12424980: "cebf5265578c05b598b8c2f9d2c524c852a32e48facb4856db1426185f098cb1",
    12424990: "0b8bf3929d610e3938673ca58072126cbde658e3aa75911c958a1b7e7f43a700",
}
EBRIETAS_EVENTS = tuple(EBRIETAS_HASHES)
AMYGDALA_SOURCE_PINS = {
    "m33_00_00_00": "4d66ca60f567e2f0ba0ffcc43fb45c5666265fd9649952cc3828185f0ef1bc39",
}
RETAINED_PINS = {
    PRIMARY: "b59699c3a1530fdd4f2af2aebaf8ecf51de6bfa7665a7858e4dc2ce6eeebb910",
    GIANT: "db231b04a55ae8481e3a490baa0e3d0b3a869b7720982dc668ac2bc59b43d82d",
    2420711: "95c82d4515a4d9ac2da55b9e2ec8283d984a1b06854df23bd4ab8cb3a94bd713",
    2420712: "8bdaaf92db8179e0c6caa26d1bbbe797683f53073152431883e57dce98419778",
    2420713: "b2ba985e21287c62d5fe64349f1349963a24546264b7c94108ff1802b436d152",
    2420716: "b56d7f36acb208d5c9b049955c3fa07761aa85a0fa4781dd53e0c1ab37775ae2",
    2420717: "6a39b4b07ee88fc2f5a4b9c1955132c4155c461152509e34779953627fa54de7",
    2420719: "13a559895dd7beac0745a1b31a71e338cf86781374fa59c275484e71f12e8cfd",
    2420720: "36959229af687ddc347e79c43dca84a16a1a70973f1c7542166fdc4ddb4f83f1",
    2420750: "3880c91215a6946d33fd4be046c7dae5e42011532462ead60a62516119cd87b6",
    2420751: "b48f991e496629e90c779a25c11b57d1a8ee5f4a6635bd5e1f17ab19d41b0e12",
}


@dataclass(frozen=True)
class AmygdalaCelestialIds:
    phase_one: int = 12992500
    phase_two: int = 12992501
    hitmask: int = 12992502
    limbs: int = 12992503
    body_part: int = 12992504
    death_to_giant: int = 12992505
    retire_celestial: int = 12992506

    def values(self):
        return (
            self.phase_one,
            self.phase_two,
            self.hitmask,
            self.limbs,
            self.body_part,
            self.death_to_giant,
            self.retire_celestial,
        )

DEFAULT_IDS = AmygdalaCelestialIds()
SUPPRESSED_EVENTS = (
    12424770,
    12424780,
    12424784,
    12424785,
    12424787,
    12424790,
    12424791,
    12424792,
    12424795,
)


def _verify(blocks, hashes, role):
    for event, digest in hashes.items():
        if hashlib.sha256(blocks.get(event, "").encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {role} event {event}")


def _replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f"Amygdala/Celestial expected one {label}")
    return text.replace(old, new, 1)


def _remap(text, values):
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])", lambda m: str(values.get(int(m[0]), int(m[0]))), text
    )


def _end_event(block):
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda m: "function("
        + ", ".join(
            x.strip() if x.strip().startswith("unused_") else "unused_" + x.strip()
            for x in m[1].split(",")
            if x.strip()
        )
        + ")",
        block.splitlines()[0],
    )
    return header + "\n    EndEvent();\n});"


def _replace_events(source, edits):
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


@cache
def _original_literals():
    return {
        int(v)
        for body in read_prefix(BUNDLE, "event/").values()
        for v in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
    }


def _validate_ids(ids, destination):
    values = ids.values()
    local = {int(v) for v in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    if (
        len(set(values)) != len(values)
        or any(v < PROJECT_MIN or v > PROJECT_MAX for v in values)
        or set(values).intersection(local | _original_literals())
    ):
        raise ValueError(
            "Amygdala/Celestial IDs must be collision-free project-owned 129925xx values"
        )


def _initializers(event_zero, source_event, dest_event, expected_count):
    calls = [
        x
        for x in event_zero.splitlines()
        if re.match(
            r"\s*\$InitializeEvent\([^,]+,\s*" + str(source_event) + r"(?:,|\))", x
        )
    ]
    if len(calls) != expected_count:
        raise ValueError(
            f"Amygdala Event(0) lacks {expected_count} initializer witnesses for {source_event}"
        )
    return [
        re.sub(
            r"(\$InitializeEvent\([^,]+,\s*)" + str(source_event) + r"(?=,|\))",
            r"\g<1>" + str(dest_event),
            call,
            count=1,
        )
        for call in calls
    ]


def _mapping(ids):
    return {
        AMYGDALA: PRIMARY,
        13301800: TERMINAL,
        13301802: 12421702,
        13301803: 12421703,
        13304800: 12424700,
        13304801: 12424701,
        13304802: 12424702,
        13304803: 12424703,
        13304804: 12424704,
        13304807: ids.phase_one,
        13304808: ids.phase_two,
        13304820: ids.hitmask,
        13304830: ids.limbs,
        13304840: ids.body_part,
        3302802: 2422812,
        3302805: 2422815,
        3303802: 2423812,
        3303803: 2423813,
        3300010: 2420010,
    }


def _health(donor, ids):
    result = _remap(donor, _mapping(ids))
    retained = (
        f"    SetCharacterAIState({GIANT}, Disabled);\n    SetCharacterHPBarDisplay({GIANT}, Disabled);\n    SetCharacterGravity({GIANT}, Disabled);\n"
        + "".join(
            f"    SetCharacterAIState({x}, Disabled);\n    SetCharacterHPBarDisplay({x}, Disabled);\n"
            for x in (*WAVES, *SUPPORT)
        )
    )
    result = _replace_once(
        result,
        f"    SetCharacterHPBarDisplay({PRIMARY}, Disabled);\n",
        f"    SetCharacterHPBarDisplay({PRIMARY}, Disabled);\n" + retained,
        "Celestial helper initialization",
    )
    result = _replace_once(
        result,
        f"        IssueBossRoomEntryNotification(0);\n        SetNetworkUpdateAuthority({PRIMARY}, AuthorityLevel.Forced);",
        f"        if (!EventFlag({TERMINAL})) {{\n            IssueBossRoomEntryNotification(0);\n        }}\n        SetNetworkUpdateAuthority({PRIMARY}, AuthorityLevel.Forced);\n        SetNetworkUpdateAuthority({GIANT}, AuthorityLevel.Forced);",
        "Celestial entry authority",
    )
    return _replace_once(
        result, "CreatePlaylog(78);", "CreatePlaylog(104);", "Celestial playlog"
    )


def _camera(donor):
    result = _remap(donor, _mapping(DEFAULT_IDS))
    result = _replace_once(
        result,
        "    SetNetworkSyncState(Disabled);",
        f"    SetNetworkSyncState(Disabled);\n    EndIf(EventFlag({TERMINAL}));",
        "completed-arena camera guard",
    )
    result = result.replace(
        "SetLockcamSlotNumber(33, 0,", "SetLockcamSlotNumber(24, 2,"
    )
    if "SetLockcamSlotNumber(33," in result:
        raise ValueError("Amygdala/Celestial copied Amygdala camera map")
    return result


def _retire(ids):
    gens = "".join(f"    DeactivateGenerator({x}, Disabled);\n" for x in GENERATORS)
    actors = "".join(
        f"    SetCharacterAIState({x}, Disabled);\n    SetCharacterHPBarDisplay({x}, Disabled);\n    ChangeCharacterEnableState({x}, Disabled);\n"
        for x in (*WAVES, *SUPPORT)
    )
    deaths = "".join(
        f"    ForceCharacterDeath({x}, false);\n" for x in (*WAVES, *SUPPORT)
    )
    return f"""$Event({ids.retire_celestial}, Default, function() {{
{gens}    SetCharacterAIState({GIANT}, Disabled);
    SetCharacterHPBarDisplay({GIANT}, Disabled);
    SetCharacterGravity({GIANT}, Disabled);
{actors}    if (EventFlag({TERMINAL})) {{
{deaths}        EndEvent();
    }}
    WaitFor(EventFlag({TERMINAL}));
{deaths}}});"""


def _bridge(ids):
    return f"""$Event({ids.death_to_giant}, Default, function() {{
    EndIf(EventFlag({TERMINAL}));
    WaitFor(CharacterDead({PRIMARY}));
    EndIf(EventFlag({TERMINAL}));
    ForceCharacterDeath({GIANT}, false);
}});"""


def patch_amygdala_at_celestial_emissary(destination, donor_source, ids=DEFAULT_IDS):
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, ARENA_HASHES, "Celestial arena")
    _verify(arena, EBRIETAS_HASHES, "shared Ebrietas")
    _verify(donor, DONOR_HASHES, "Amygdala donor")
    _validate_ids(ids, destination)
    constructor = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 12424795);",
        "    $InitializeEvent(0, 12424795);\n"
        + "\n".join(
            call
            for source_event, destination_event, count in (
                (13304807, ids.phase_one, 1),
                (13304808, ids.phase_two, 1),
                (13304820, ids.hitmask, 2),
                (13304830, ids.limbs, 10),
                (13304840, ids.body_part, 1),
            )
            for call in _initializers(donor[0], source_event, destination_event, count)
        )
        + f"\n    $InitializeEvent(0, {ids.death_to_giant});\n    $InitializeEvent(0, {ids.retire_celestial});",
        "Celestial constructor anchor",
    )
    mapping = _mapping(ids)
    edits = {
        0: constructor,
        12421702: _remap(donor[13301802], mapping),
        12421703: _remap(donor[13301803], mapping),
        12424702: _health(donor[13304802], ids),
        12424703: _remap(donor[13304803], mapping),
        12424704: _camera(donor[13304804]),
        **{x: _end_event(arena[x]) for x in SUPPRESSED_EVENTS},
        ids.phase_one: _remap(donor[13304807], mapping),
        ids.phase_two: _remap(donor[13304808], mapping),
        ids.hitmask: _remap(donor[13304820], mapping),
        ids.limbs: _remap(donor[13304830], mapping),
        ids.body_part: _remap(donor[13304840], mapping),
        ids.death_to_giant: _bridge(ids),
        ids.retire_celestial: _retire(ids),
    }
    result = _replace_events(
        destination, {x: b for x, b in edits.items() if x in arena}
    )
    result = (
        result.rstrip() + "\n\n" + "\n\n".join(edits[x] for x in ids.values()) + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.values()):
        raise ValueError("Amygdala/Celestial changed event identities")
    for x, b in arena.items():
        if x not in edits and output[x] != b:
            raise ValueError(f"Amygdala/Celestial changed unrelated arena event {x}")
    if output[TERMINAL] != arena[TERMINAL]:
        raise ValueError("Amygdala/Celestial changed destination giant terminal")
    for x in EBRIETAS_EVENTS:
        if output[x] != arena[x]:
            raise ValueError(f"Amygdala/Celestial changed shared Ebrietas event {x}")
    copied = "\n".join(
        output[x]
        for x in (12421702, 12421703, 12424702, 12424703, 12424704, *ids.values())
    )
    if re.search(r"(?<!\d)(?:133|330)\\d{4,}(?!\d)", copied):
        raise ValueError("Amygdala/Celestial copied combat retains donor-map literals")
    return result


def _require(slots, entity, archetype, map_name=None):
    found = sorted(
        (
            x
            for x in slots
            if x.entity_id == entity and (map_name is None or x.map_name == map_name)
        ),
        key=lambda x: x.key,
    )
    if not found or any(x.dummy or x.archetype != archetype for x in found):
        raise ValueError(f"unsupported Amygdala/Celestial placement provenance for {entity}")
    return found


def _binding(source, target):
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": AMYGDALA_SOURCE_PINS[source.map_name],
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


def native_plan_amygdala_at_celestial_emissary(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: AmygdalaCelestialIds = DEFAULT_IDS,
):
    arena_source = read_blob(BUNDLE, CELESTIAL_SOURCE).decode("utf-8-sig")
    donor_source = read_blob(BUNDLE, AMYGDALA_SOURCE).decode("utf-8-sig")
    arena, donor = event_blocks(arena_source), event_blocks(donor_source)
    _verify(arena, ARENA_HASHES, "Celestial arena")
    _verify(arena, EBRIETAS_HASHES, "shared Ebrietas")
    _verify(donor, DONOR_HASHES, "Amygdala donor")
    _validate_ids(ids, arena_source)
    amygdala = _require(slots, AMYGDALA, AMYGDALA_ARCHETYPE, "m33_00_00_00")
    primary = _require(slots, PRIMARY, PRIMARY_ARCHETYPE, "m24_02_00_00")
    giant = _require(slots, GIANT, GIANT_ARCHETYPE, "m24_02_00_00")
    helpers = []
    for x in WAVES:
        helpers.extend(
            _require(slots, x, Archetype("c2500", 250081, 250061, 0), "m24_02_00_00")
        )
    helpers.extend(
        _require(slots, 2420750, Archetype("c2571", 257100, 1, 0), "m24_02_00_00")
    )
    helpers.extend(
        _require(slots, 2420751, Archetype("c2571", 257101, 1, 0), "m24_02_00_00")
    )
    if (
        len(amygdala) != 1
        or len(primary) != 1
        or len(giant) != 1
        or len(helpers) != 9
    ):
        raise ValueError(
            "Amygdala/Celestial requires one Amygdala source, a primary, giant, and nine retained helpers"
        )
    source = amygdala[0]
    target = primary[0]
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        AMYGDALA_ARCHETYPE,
        warnings=[
            "experimental Amygdala-at-Celestial contract; runtime behavior unobserved"
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
        raise ValueError(
            "Amygdala/Celestial primary swap has an ambiguous normalization plan"
        )
    retained = []
    for x in [giant[0], *helpers]:
        retained.append(
            {
                "map": x.map_name,
                "part": x.part_name,
                "entity_id": x.entity_id,
                "archetype": asdict(x.archetype),
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": RETAINED_PINS[x.entity_id],
                },
                "source_initialization": {
                    "talk_id": 0,
                    "unk_t18": -1,
                    "init_anim_id": -1,
                    "damage_anim_id": -1,
                },
                "policy": (
                    "retain_giant_disabled_alive_until_amygdala_death_bridge"
                    if x.entity_id == GIANT
                    else "retain_celestial_wave_or_support_disabled_until_destination_completion"
                ),
            }
        )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "boss_contract": {
            "format": "bb-amygdala-celestial-emissary-contract-v1",
            "arena": "celestial-emissary",
            "donor": "amygdala",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "attachment_event_ids": asdict(ids),
            "physical_swap_count": 1,
            "terminal_policy": "retain byte-identical giant terminal; bridge Amygdala death to giant only afterward",
            "retained_destination_helpers": retained,
            "preserved_destination_events": [
                TERMINAL,
                12421701,
                12424705,
                12424710,
                12424711,
            ],
            "preserved_ebrietas_events": list(EBRIETAS_EVENTS),
            "arena_hash_pins": dict(ARENA_HASHES),
            "donor_hash_pins": dict(DONOR_HASHES),
        },
        "primary_init_source_bindings": [_binding(source, target)],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [x.json() for x in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
