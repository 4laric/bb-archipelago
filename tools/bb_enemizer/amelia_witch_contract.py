"""Static, source-pinned Vicar Amelia combat in Witch of Hemwick's arena."""

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
AMELIA_SOURCE = "event/m24_00_00_00.emevd.dcx.js"
WITCH_SOURCE = "event/m22_00_00_00.emevd.dcx.js"
AMELIA, WITCH, SECOND = 2400800, 2200800, 2200801
AMELIA_ARCHETYPE = Archetype("c5020", 502000, 502000, 0)
WITCH_ARCHETYPE = Archetype("c2100", 210020, 210020, 0)
MINIONS = (2200810, 2200811, 2200812)
GENERATORS = (2205000, 2205001, 2205002)
SOURCE_HASHES = {
    12401802: "b869911c8ee05015b1b90d6fcac40ae0f492433ce83f0f2629e4973cdfbbcde0",
    0: "31936ed53ff8d095dcae5257c6d36e321a55bc8cd53ed564a1510363a9a04e27",
    12404802: "d9c5e8ef9feaa1758a8ee08e21a8da089b96f5bb7e17a740f8d34770b7c9ea31",
    12404804: "77adf8b72d36b425788c96b1bd697a193a8b81408ccc8e14c071687427f92621",
    12404807: "c1963c0461fe87ebd3a432bc41eaaeebcea3aa82ca86526d4e51da3619714279",
    12404808: "8a8be8efea5f76c0d44a669ddbafc86f1e59b7bdd5ebac85a556619ba3c236ed",
    12404810: "30b2c3b6e19b220396f325beaed9873285c58304d54a2ec2c939477dd1f84830",
    12404820: "dfe2dd42c30b7686b972b2a20eed997ee00660d7592bf1fe7a91ad0602d76b19",
    12404830: "b92005d1b304b616a48dc9f877601a8d024362e8745ffa34282f3c92257e7c9d",
}
# Completion, entry/co-op, music, camera, every old pair/revival/minion controller,
# and every replaced body are independently pinned before editing.
ARENA_HASHES = {
    0: "905725c3c1e58539e378d2bfb3f1a73dc90d1a702b49168c55d1590ce625a822",
    12201800: "5dffb875184250877c9dc9867bffb67329741d033ebf9fa9e77b170ea5145fe1",
    12201801: "d02c6a1eb1f47601a2512f9f221d910de19e92b4bd9a39b2358a8f2e2930ffd6",
    12201802: "02cd835b56665e1eb6f2ceb9252ef6d3c92fdf468180918348d8bbf54e13c3b3",
    12201803: "a8ba2f2e501778c8b543dabfcf26304d107b58958ee28b9516dcfb865ad066eb",
    12201804: "6d45f5c7920b54054955d9cfb46762a25430891329269c06421d70fdb459b1a2",
    12204802: "9b068a5c6a2f5cc57a9be0aa6d30f9f191ddb946f040c94b200c1422d6102af2",
    12204803: "d41f4a63d537c30c94cd4ff4208df30b98a989f25d45e9118525cd54d7963caf",
    12204804: "c212b5f5394951dcc5495470b65ebfd750db4ffd9cf842117c563cf5195bc4f3",
    12204805: "dba98109a757634bb32d5bd81de72400d20ed4cd988f48b5b3b1a5a6a5fe153d",
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
}
AMELIA_PIN = "99f32c1296938362bd6d5abbcc073f6179fd9173f18a3a5076391d37ff88c35e"
WITCH_PIN = "d82ece33f61d3ed3fbcd931f1089f7be4d0f82a2690f49c9ccdf5e021550cd20"
SECOND_PIN = "263b840cd3d8e07dc328eb870cd2047e3cbde5ed9e935e739fbf7fd29897beca"


@dataclass(frozen=True)
class AmeliaWitchIds:
    phase_one: int = 12992800
    cloth: int = 12992801
    limbs: int = 12992802
    masks: int = 12992803
    heal: int = 12992804
    bridge: int = 12992805
    retire: int = 12992806
    notification_flag: int = 12992820

    def events(self):
        return (
            self.phase_one,
            self.cloth,
            self.limbs,
            self.masks,
            self.heal,
            self.bridge,
            self.retire,
        )


DEFAULT_IDS = AmeliaWitchIds()


def _verify(text, pins, role):
    b = event_blocks(text)
    for i, h in pins.items():
        if i not in b or hashlib.sha256(b[i].encode()).hexdigest() != h:
            raise ValueError(f"unsupported original {role} event {i}")
    return b


def _remap(text, m):
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda x: str(
            m.get(int(x[0]), int(x[0])),
        ),
        text,
    )


def _one(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f"Amelia/Witch expected one {label}")
    return text.replace(old, new, 1)


def _end(block):
    return (
        re.sub(
            r"function\(([^)]*)\)",
            lambda x: "function("
            + ", ".join(
                (
                    "unused_" + n.strip()
                    if not n.strip().startswith("unused_")
                    else n.strip()
                )
                for n in x[1].split(",")
                if n.strip()
            )
            + ")",
            block.splitlines()[0],
        )
        + "\n    EndEvent();\n});"
    )


def _replace(src, edits):
    lines = src.splitlines()
    for e in reversed(parse_events(src)):
        if e.event_id in edits:
            lines[e.first_line - 1 : e.last_line] = edits[e.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _all():
    out = set()
    for b in read_prefix(BUNDLE, "event/").values():
        out.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", b.decode("utf-8-sig")))
        )
    return out


def _valid(ids, dest):
    vals = ids.events() + (ids.notification_flag,)
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", dest)))
    if (
        len(vals) != len(set(vals))
        or any(not 12992800 <= v <= 12992899 for v in vals)
        or set(vals) & (local | _all())
    ):
        raise ValueError(
            "Amelia/Witch IDs must be collision-free project-owned 129928xx values"
        )


def _map(ids):
    return {
        AMELIA: WITCH,
        12401800: 12201800,
        12404800: 12204800,
        12404802: 12204802,
        12404804: 12204804,
        12404807: ids.phase_one,
        12404808: ids.cloth,
        12404810: ids.limbs,
        12404820: ids.masks,
        12404830: ids.heal,
        12404223: ids.notification_flag,
        2410010: 2200010,
    }


def _init(z, src, dst, count):
    rows = [
        x
        for x in z.splitlines()
        if re.match(r"\s*\$InitializeEvent\([^,]+,\s*" + str(src) + r"(?:,|\))", x)
    ]
    if len(rows) != count:
        raise ValueError(
            f"Amelia Event(0) lacks {count} initializer witnesses for {src}"
        )
    return [_remap(x, {src: dst, AMELIA: WITCH}) for x in rows]


def patch_amelia_at_witch(destination, donor_source, ids=DEFAULT_IDS):
    arena = _verify(destination, ARENA_HASHES, "Witch arena")
    donor = _verify(donor_source, SOURCE_HASHES, "Amelia donor")
    _valid(ids, destination)
    if set(ids.events()) & set(arena):
        raise ValueError("Amelia/Witch added event ID collides with destination EMEVD")
    m = _map(ids)
    health = _remap(donor[12404802], m)
    health = _one(
        health, "CreatePlaylog(160);", "CreatePlaylog(88);", "destination playlog"
    )
    health = _one(
        health,
        "StartTimeMeasurement(2200010, 176, Enabled);",
        "StartTimeMeasurement(2200010, 104, Enabled);",
        "destination time measurement",
    )
    # Preserve Hemwick's fog/entry controller but replace its Witch-only idle with Amelia's source-witnessed entry sequence.
    activation = _one(
        arena[12201802],
        "    if (!(PlayerInsightAmount() == 0 && CharacterType(10000, TargetType.Alive))) {\n        ForceAnimationPlayback(2200800, 3011, false, false, false);\n    }",
        "    ForceAnimationPlayback(2200800, 7000, false, false, false);\n    ForceAnimationPlayback(2200800, 7001, false, false, false);",
        "Amelia entry animation",
    )
    music = _one(
        arena[12204803],
        "hpFlagArea &= CharacterHPValue(2200800) == 1 || CharacterHPValue(2200801) == 1;",
        "hpFlagArea &= CharacterHasEventMessage(2200800, 100);",
        "Amelia phase music trigger",
    )
    camera = _remap(donor[12404804], m)
    if camera.count("SetLockcamSlotNumber(24, 0,") != 2:
        raise ValueError("Amelia/Witch expected two source lockcam bindings")
    camera = camera.replace(
        "SetLockcamSlotNumber(24, 0,", "SetLockcamSlotNumber(22, 0,"
    )
    init = []
    for src, dst, count in (
        (12404807, ids.phase_one, 1),
        (12404808, ids.cloth, 1),
        (12404810, ids.limbs, 5),
        (12404820, ids.masks, 5),
        (12404830, ids.heal, 1),
    ):
        init.extend(_init(donor[0], src, dst, count))
    init += [
        f"    $InitializeEvent(0, {ids.bridge});",
        f"    $InitializeEvent(0, {ids.retire});",
    ]
    constructor = _one(
        arena[0],
        "    $InitializeEvent(0, 12204843);",
        "    $InitializeEvent(0, 12204843);\n" + "\n".join(init),
        "combat initializer anchor",
    )
    bridge = f"""$Event({ids.bridge}, Default, function() {{
    EndIf(EventFlag(12201800));
    WaitFor(CharacterDead(2200800));
    EndIf(EventFlag(12201800));
    ForceCharacterDeath(2200801, false);
}});"""
    retire = f"""$Event({ids.retire}, Default, function() {{
    ChangeCharacterEnableState(2200801, Disabled);
    SetCharacterAIState(2200801, Disabled);
    SetCharacterHPBarDisplay(2200801, Disabled);
    DeactivateGenerator(2205000, Disabled);
    DeactivateGenerator(2205001, Disabled);
    DeactivateGenerator(2205002, Disabled);
    ChangeCharacterEnableState(2200810, Disabled);
    ChangeCharacterEnableState(2200811, Disabled);
    ChangeCharacterEnableState(2200812, Disabled);
}});"""
    edits = {
        0: constructor,
        12201802: activation,
        12204802: health,
        12204803: music,
        12204804: camera,
    }
    for e in (
        12204807,
        12204808,
        12204810,
        12204811,
        12204812,
        12204814,
        12204820,
        12204830,
        12204832,
        12204835,
        12204838,
        12204839,
        12204840,
        12204841,
        12204842,
        12204843,
    ):
        edits[e] = _end(arena[e])
    imported = (
        _remap(donor[12404807], m),
        _remap(donor[12404808], m),
        _remap(donor[12404810], m),
        _remap(donor[12404820], m),
        _remap(donor[12404830], m),
        bridge,
        retire,
    )
    result = (
        _replace(destination, edits).rstrip() + "\n\n" + "\n\n".join(imported) + "\n"
    )
    out = event_blocks(result)
    if set(out) != set(arena) | set(ids.events()):
        raise ValueError("Amelia/Witch patch changed event identities")
    for e, b in arena.items():
        if e not in edits and out[e] != b:
            raise ValueError(f"Amelia/Witch changed unrelated destination event {e}")
    for e in (12201800, 12201801, 12201803, 12201804, 12204805):
        if out[e] != arena[e]:
            raise ValueError(
                "Amelia/Witch changed Witch terminal, progression, generator completion, or co-op flow"
            )
    copied = "\n".join((health, camera, *imported))
    if re.search(r"(?<!\d)(?:124|240)\d+(?!\d)", copied):
        raise ValueError("Amelia/Witch copied body retains donor-map literal")
    return result


def native_plan_amelia_at_witch(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids=DEFAULT_IDS,
):
    donor = read_blob(BUNDLE, AMELIA_SOURCE).decode("utf-8-sig")
    arena = read_blob(BUNDLE, WITCH_SOURCE).decode("utf-8-sig")
    _verify(donor, SOURCE_HASHES, "Amelia donor")
    _verify(arena, ARENA_HASHES, "Witch arena")
    _valid(ids, arena)
    src = [
        s
        for s in slots
        if s.entity_id == AMELIA
        and s.archetype == AMELIA_ARCHETYPE
        and s.map_name == "m24_00_00_00"
    ]
    dst = [
        s
        for s in slots
        if s.entity_id == WITCH
        and s.archetype == WITCH_ARCHETYPE
        and s.map_name == "m22_00_00_00"
    ]
    second = [
        s for s in slots if s.entity_id == SECOND and s.map_name == "m22_00_00_00"
    ]
    if (
        len(src) != 1
        or len(dst) != 1
        or len(second) != 1
        or any(s.dummy or s.talk_id for s in src + dst + second)
    ):
        raise ValueError(
            "Amelia/Witch requires exact original Amelia and Witch pair roster"
        )
    swap = Swap(
        dst[0].logical_key,
        [dst[0].key],
        {dst[0].key: dst[0].archetype},
        WITCH_ARCHETYPE,
        AMELIA_ARCHETYPE,
        warnings=[
            "experimental Amelia-at-Witch contract; retained second Witch bridge and arena fit are runtime-unobserved"
        ],
        destinations={
            dst[0].key: {
                "map_name": dst[0].map_name,
                "entity_id": dst[0].entity_id,
                "x": dst[0].x,
                "y": dst[0].y,
                "z": dst[0].z,
            }
        },
    )
    changes, skips = plan_scaling(
        [swap], dst, dict(npcs), dict(effects), boss_tiers=True
    )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "primary_init_source_bindings": [
            {
                "source_map": src[0].map_name,
                "source_part": src[0].part_name,
                "source_entity_id": AMELIA,
                "source_archetype": asdict(AMELIA_ARCHETYPE),
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": AMELIA_PIN,
                },
                "source_initialization": {
                    "talk_id": 0,
                    "unk_t18": -1,
                    "init_anim_id": -1,
                    "damage_anim_id": -1,
                },
                "destination_map": dst[0].map_name,
                "destination_part": dst[0].part_name,
                "destination_entity_id": WITCH,
            }
        ],
        "boss_contract": {
            "format": "bb-amelia-witch-contract-v1",
            "arena": "witch-of-hemwick",
            "donor": "vicar-amelia",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": SOURCE_HASHES,
            "arena_hash_pins": ARENA_HASHES,
            "preserved_destination_events": [
                12201800,
                12201801,
                12201803,
                12201804,
                12204805,
            ],
            "retained_destination_helpers": [
                {
                    "map": second[0].map_name,
                    "part": second[0].part_name,
                    "entity_id": SECOND,
                    "archetype": asdict(second[0].archetype),
                    "source_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": SECOND_PIN,
                    },
                    "source_initialization": {
                        "talk_id": 0,
                        "unk_t18": -1,
                        "init_anim_id": -1,
                        "damage_anim_id": -1,
                    },
                    "policy": "disabled until Amelia death bridge fulfills original two-Witch terminal",
                }
            ],
            "minion_policy": "all original 2200810-12 controllers and 2205000-2 generators are retired before Amelia combat",
            "event_patch": {
                "changed_events": [
                    {
                        "destination_event_id": 12204802,
                        "source_event_id": 12404802,
                        "source_sha256": SOURCE_HASHES[12404802],
                    }
                ],
                "added_events": [
                    {
                        "source_event_id": s,
                        "destination_event_id": d,
                        "source_sha256": SOURCE_HASHES[s],
                        "literal_remap": _map(ids),
                    }
                    for s, d in (
                        (12404807, ids.phase_one),
                        (12404808, ids.cloth),
                        (12404810, ids.limbs),
                        (12404820, ids.masks),
                        (12404830, ids.heal),
                    )
                ]
                + [
                    {
                        "source_event_id": None,
                        "destination_event_id": e,
                        "kind": "destination_bridge_or_retirement",
                    }
                    for e in (ids.bridge, ids.retire)
                ],
            },
        },
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [x.json() for x in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
