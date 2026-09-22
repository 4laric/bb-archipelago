"""Static One Reborn multipart donor contract for Ebrietas' arena."""

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
from .rom_ebrietas_contract import (
    EBRIETAS_CORE_PINS,
    EBRIETAS_OWNER_PINS,
    OWNER_ARCHETYPE,
    _end_event,
    _replace_once,
    _initialization,
    _pin,
)

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
ONE_REBORN_SOURCE = "event/m28_00_00_00.emevd.dcx.js"
EBRIETAS_SOURCE = "event/m24_02_00_00.emevd.dcx.js"
SOURCE_STATES = ("m28_00_00_00", "m28_00_00_01")
TARGET_STATES = ("m24_02_00_00", "m24_02_00_01")
CORE, BODY, CONTROLLER, PROXY = 2800800, 2800801, 2800802, 2800803
CASTERS = (2800520, 2800522, 2800524, 2800525, 2800527, 2800529)
TARGET = 2420800
ARCH = {
    CORE: Archetype("c5070", 507000, 0, 6553600),
    BODY: Archetype("c5071", 507100, 0, 6553600),
    CONTROLLER: Archetype("c5072", 507200, 507200, 0),
    PROXY: Archetype("c1050", 507000, 0, 0),
    2800520: Archetype("c1050", 105810, 105810, 6553600),
    2800522: Archetype("c1050", 105810, 105811, 6553600),
    2800524: Archetype("c1050", 105810, 105810, 6553600),
    2800525: Archetype("c1050", 105810, 105810, 6553600),
    2800527: Archetype("c1050", 105810, 105811, 6553600),
    2800529: Archetype("c1050", 105810, 105810, 6553600),
}
TARGET_ARCH = Archetype("c2510", 251000, 251000, 0)
DONOR_HASHES = {
    12804803: "d9fe3eab4eeb93fcc5e13e719399de18dafe7583b527aaa9d648f355a9b39130",
    0: "4de4c6a57d7aaffd0e6244099f666dc4ef3ca41eb3d9d5d4a7a3c1708ba8464a",
    12801800: "e9d1c62b8e026124033f59ef4837ad7a6acf0acd7370f6cef617390e3983f314",
    12804802: "7e17bc4225eaa32aa8405674a1d0b499fd0ba51ec3e47f13ebb8a5dca9d68140",
    12804804: "fff8d31b08506d033ddcf87bd34518fc81ccf56d6b9af3956d973c7dcd80f7e8",
    12804806: "afcb289a3014689054e5a30e72e2555053c9d8b185cb822dec13ea106a96e5e0",
    12804807: "fa8009ac3b77bc771a3eb35e8bf3fc163bbcfe308d4c7c769f46e0d3a5e56801",
    12804820: "c6256101f5156e5e1988ae70e39f0a00b04240ca51bfea86233bef8e89df2e6e",
    12804830: "7affa6abc8aa8ab9df377bc6387238ac66f4e07ebe25a7ec052ce356615c1ccf",
    12804831: "bab524091adf0cf5202a152f82ef13efca1ebe948ff6f7fe300454e13e1525e3",
    12804832: "fb47473a7b42e2260f282476d6a757e38ccfaa680bc42ffadcd74bf1cf602156",
    12804834: "478b6080b4d42a69d19cfaf115f323552e1f0266765719104a28919cee7ef819",
    12804835: "4cfb763bcacef97534ebe317cbb09784bc8a27c49dd9a62ad9986a99382d1e97",
    12804836: "9028e42c5794dc44331409a2761b1378ce8a3b4a4c323abe661cf8beb5174ee1",
    12804837: "ba451c3890f61f45efb042175fab7fac8c0dc918dd448164281e6a150227c070",
    12804838: "545058a0e45e0fc2b78f793d9b6e228b3a56da73a2a640741dafa7875f48214e",
    12804840: "0935e02a26ac1d253ff11ca3b87d6a2f35a6460c2ae18672ca3ae9d77d89a320",
    12804850: "f0c9694be90d0f04928f7fde6b570942a0cdcb87af51404f3eee30b033757025",
    12804870: "2392ad27ac01ab99592e37c386fb5fb7d47947e22e016428698373c0902afb25",
    12804871: "647831fb3b4f5b2f9058faa1981f04b62a77b7a744bd4c207b64660d44c9cc67",
}
ARENA_HASHES = {
    0: "cda0f114ad3f96b4b93fda3b81ac6d6ed5808bdb0be3f6d16e8225733e729dde",
    12421800: "7cb7c78833c5ef60a5599d35c22964e87b75f980c3165e139d7c28fc8a1bd34b",
    12421801: "2b01b305ae68b5d9e67407c316ed1a902f182124022987b9e258b527fb67f97f",
    12421802: "9bc79c8e55c2a2c9793a90070de1f76c35a46ebd98c2c79176b2fcc02ae8adc4",
    12421803: "dcbbafd95ebeebce5ddd63d637fc07b93bff8f52c33b77665e0ca21e6d649152",
    12424802: "effdc8bf4ca63c0371f209afbd388d0c682793bc2efaf258675e871bcae21ad2",
    12424803: "a487e349f0a416298a26fb93c87c0c57fd7211e7da3da8938d37b6e909130966",
    12424804: "9324596b40c1d5a8ec57a11c71eab66105a1550a81cdcacd4432a86ec366ea74",
    12424870: "4fac0ea46041effd27d59b41752ef9758ba1c6021647ef9831f87de11e5564ba",
    12424871: "50091165e085e178edd4641859d7af08032e2dc4c1be99e7d3631ecbaa07abbc",
    12424980: "cebf5265578c05b598b8c2f9d2c524c852a32e48facb4856db1426185f098cb1",
    12424990: "0b8bf3929d610e3938673ca58072126cbde658e3aa75911c958a1b7e7f43a700",
}
PINS = {
    "m28_00_00_00": dict(
        zip(
            (CORE, BODY, CONTROLLER, PROXY, *CASTERS),
            (
                "d63b5cc2179fe66b76a237d1286fec90c00b41068847dd2688253fe6868dff64",
                "2e6cbceecd430e43c00cb16cbf464e4431a226fd260a1228d8f5d6fcd21b04e3",
                "1094204441e3591e5c98e68eb6fa41133788b3c1cd1282de85609e6e8c8a75e7",
                "9f83ecd83b83ac250b4f22c6a59aad925febb6bb4e44d13e1f5aa9b9061e4a38",
                "ebd81e2114d3394c8a6eb28051c85c9fdf52609576b2b46714803e5b619db131",
                "f05463f2b014ad0d946a9cf6c31ee14aaea1af7e3e9803d46faa64ea84c662fb",
                "866b9f6e72dec776f8b696ccc37c232aa2ce23d4cdec1e62b5fdee15b575f5d2",
                "9f93949a1af828c9e6645f92cfc0caecfea3e07a035c7734679335e70262b2e0",
                "5cbaf933d6ca13db44cc9c14d965291f7346eecd4ea19ddac91a92f9ee75e63b",
                "6f6b139708f0c18bca6b56768fcf9c9bcce7b1cdbbd18d7e741e182772306627",
            ),
        )
    ),
    "m28_00_00_01": dict(
        zip(
            (CORE, BODY, CONTROLLER, PROXY, *CASTERS),
            (
                "3d66cbbe3ec301c4e57705524ceb6a7fc2784cc23a991afe0762c45186a4fa5f",
                "cd731459de6be54a6633ae36584894c75b0bf6ac351c16ec32a64091fa4e144a",
                "911986915373bd1bd64e4f178039af5c985e50bd116c0d8cc52e910f34a6fa07",
                "dd53094dd91f469d2d44af6dda3084b0620f7666258057e19550f5ed5ed0f69a",
                "2524a31e0ab89b13d049371be070d62514aa5cba02e28d4ffac370d65bfbf56f",
                "ea8a36357e37ac8ef46e975a93ff7d36688c566af0a36e622a40086b393cf129",
                "364b2a245b226feb77dc688814e7bec9acf334265bee49dfce863fd8a3046609",
                "95b3115d07725e9dd27cd136cdf4061bf36b6ce5d4dc302be2b492eecbb2cd3a",
                "0bcd2bec58a33eb22a16d870e93528b1213c0ccf8c02adeabb62621fc3331c19",
                "53df7c070f759799a2beaeeab5d2380cf0c66dc1fb690edfe6e7694f7cc44c34",
            ),
        )
    ),
}


@dataclass(frozen=True)
class OneRebornEbrietasIds:
    camera: int = 12993200
    tether: int = 12993201
    limb_guard: int = 12993202
    limb_flag: int = 12993203
    limb_first: int = 12993204
    controller_first: int = 12993211
    caster_react: int = 12993219
    caster_count: int = 12993221
    phase_one: int = 12993227
    phase_two: int = 12993228
    bridge: int = 12993229
    cleanup: int = 12993230
    caster_count_flag: int = 12993240
    notification_flag: int = 12993244
    helper_first: int = 981000

    def events(self):
        return (
            self.camera,
            self.tether,
            self.limb_guard,
            *range(self.limb_first, self.cleanup + 1),
        )

    def values(self):
        return self.events() + (
            self.limb_flag,
            *range(self.caster_count_flag, self.caster_count_flag + 4),
            self.notification_flag,
        )


DEFAULT_IDS = OneRebornEbrietasIds()


def _verify(text, pins, label):
    b = event_blocks(text)
    for e, h in pins.items():
        if e not in b or hashlib.sha256(b[e].encode()).hexdigest() != h:
            raise ValueError(f"unsupported original {label} event {e}")
    return b


def _replace(text, edits):
    lines = text.splitlines()
    for e in reversed(parse_events(text)):
        if e.event_id in edits:
            lines[e.first_line - 1 : e.last_line] = edits[e.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _remap(text, m):
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])", lambda x: str(m.get(int(x[0]), int(x[0]))), text
    )


def _end(b):
    return _end_event(b)


def _original_ids():
    return {
        int(x)
        for v in read_prefix(BUNDLE, "event/").values()
        for x in re.findall(rb"(?<![\w])-?\d+(?![\w])", v)
    }


def _check(ids, dest):
    vals = set(ids.values())
    helpers = set(range(ids.helper_first, ids.helper_first + 9))
    used = _original_ids() | set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", dest)))
    if (
        len(vals) != len(ids.values())
        or any(x < 12993200 or x > 12993299 for x in vals)
        or vals & used
    ):
        raise ValueError(
            "One Reborn/Ebrietas IDs must be collision-free 129932xx values"
        )
    if helpers & used:
        raise ValueError(
            "One Reborn/Ebrietas helper IDs must be collision-free 981000+ values"
        )


def patch_one_reborn_at_ebrietas(destination, donor, ids=DEFAULT_IDS):
    arena = _verify(destination, ARENA_HASHES, "Ebrietas arena")
    source = _verify(donor, DONOR_HASHES, "One Reborn donor")
    _check(ids, destination)
    m = {
        CORE: TARGET,
        BODY: ids.helper_first,
        CONTROLLER: ids.helper_first + 1,
        PROXY: ids.helper_first + 2,
        **{x: ids.helper_first + 3 + i for i, x in enumerate(CASTERS)},
        12801800: 12421800,
        12804800: 12424800,
        12804223: ids.notification_flag,
        12804802: 12424802,
        12804808: ids.limb_flag,
        12804860: ids.caster_count_flag,
        12804871: ids.phase_two,
        2800010: 2420010,
    }
    copies = [
        (12804804, ids.camera),
        (12804806, ids.tether),
        (12804807, ids.limb_guard),
        *((12804820, ids.limb_first + i) for i in range(7)),
        *(
            (e, ids.controller_first + i)
            for i, e in enumerate(
                (
                    12804830,
                    12804831,
                    12804832,
                    12804834,
                    12804835,
                    12804836,
                    12804837,
                    12804838,
                )
            )
        ),
        *((12804840, ids.caster_react + i) for i in range(2)),
        *((12804850, ids.caster_count + i) for i in range(6)),
        (12804870, ids.phase_one),
        (12804871, ids.phase_two),
    ]
    # Keep authored Event(0) arguments and slots; bare synthetic initializers would lose limbs and caster bindings.
    pending = {}
    for source_event, destination_event in copies:
        pending.setdefault(source_event, []).append(destination_event)
    init_rows = []
    for line in source[0].splitlines():
        match = re.search(
            r", (128048(?:04|06|07|20|30|31|32|34|35|36|37|38|40|50|70|71))", line
        )
        if match:
            source_event = int(match.group(1))
            targets = pending[source_event]
            if not targets:
                raise ValueError(
                    f"One Reborn/Ebrietas unexpected source initializer {source_event}"
                )
            init_rows.append(_remap(line, {**m, source_event: targets.pop(0)}))
    if any(rows for rows in pending.values()):
        raise ValueError("One Reborn/Ebrietas missing source constructor witness")
    imported = {d: _remap(source[src], {**m, src: d}) for src, d in copies}
    imported[ids.camera] = imported[ids.camera].replace(
        "SetLockcamSlotNumber(28, 0,", "SetLockcamSlotNumber(24, 2,"
    )
    if imported[ids.camera].count("SetLockcamSlotNumber(24, 2,") != 2:
        raise ValueError("One Reborn/Ebrietas camera mapping lost source writes")
    health = _remap(source[12804802], m)
    health = _replace_once(
        health, "CreatePlaylog(238);", "CreatePlaylog(104);", "destination playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2420010, 254, Enabled);",
        "StartTimeMeasurement(2420010, 40, Enabled);",
        "destination measurement",
    )
    activation = arena[12421802]
    for line in (
        "    ForceAnimationPlayback(2420800, 7001, true, false, false);\n",
        "    SetCharacterImmortality(2420800, Enabled);\n",
        "    SetSpEffect(2420800, 5647, false);\n",
        "    ForceAnimationPlayback(2420800, 7000, false, true, false);\n",
        "    SetCharacterImmortality(2420800, Disabled);\n",
        "    ClearSpEffect(2420800, 5647);\n",
    ):
        activation = _replace_once(
            activation, line, "", "Ebrietas-specific wake control"
        )
    music = _replace_once(
        arena[12424803],
        "CharacterHasEventMessage(2420800, 100)",
        "CharacterHasEventMessage(2420800, 300)",
        "One Reborn phase music",
    )
    constructor = _replace_once(
        arena[0],
        "    CreateBulletOwner(2420801);\n",
        "",
        "unused Ebrietas bullet owner",
    )
    init = "\n".join(
        (
            *init_rows,
            f"    $InitializeEvent(0, {ids.bridge});",
            f"    $InitializeEvent(0, {ids.cleanup});",
        )
    )
    edits = {
        0: constructor.replace("});", "\n" + init + "\n});", 1),
        12421802: activation,
        12424802: health,
        12424803: music,
        12424804: _end(arena[12424804]),
        12424870: _end(arena[12424870]),
        12424871: _end(arena[12424871]),
        12424980: _end(arena[12424980]),
        12424990: _end(arena[12424990]),
    }
    bridge = f"""$Event({ids.bridge}, Default, function() {{
    EndIf(EventFlag(12421800));
    WaitFor(HPRatio({m[PROXY]}) <= 0);
    RequestCharacterAnimationReset(2420800, Interpolation.Uninterpolated);
    RequestCharacterAnimationReset({m[BODY]}, Interpolation.Uninterpolated);
    ForceCharacterDeath({m[BODY]}, false);
    ForceCharacterDeath({m[CONTROLLER]}, false);
    ForceCharacterDeath({m[PROXY]}, false);
    ForceCharacterDeath({m[CASTERS[0]]}, false);
    ForceCharacterDeath({m[CASTERS[1]]}, false);
    ForceCharacterDeath({m[CASTERS[2]]}, false);
    ForceCharacterDeath({m[CASTERS[3]]}, false);
    ForceCharacterDeath({m[CASTERS[4]]}, false);
    ForceCharacterDeath({m[CASTERS[5]]}, false);
    ForceCharacterDeath(2420800, false);
}});"""
    cleanup = f"""$Event({ids.cleanup}, Default, function() {{
    ChangeCharacterEnableState(2420801, Disabled);
    SetCharacterAIState(2420801, Disabled);
    SetCharacterHPBarDisplay(2420801, Disabled);
    WaitFor(EventFlag(12421800));
    ForceCharacterDeath(2420801, false);
    ChangeCharacterEnableState({m[BODY]}, Disabled);
    ChangeCharacterEnableState({m[CONTROLLER]}, Disabled);
    ChangeCharacterEnableState({m[PROXY]}, Disabled);
    ChangeCharacterEnableState({m[CASTERS[0]]}, Disabled);
    ChangeCharacterEnableState({m[CASTERS[1]]}, Disabled);
    ChangeCharacterEnableState({m[CASTERS[2]]}, Disabled);
    ChangeCharacterEnableState({m[CASTERS[3]]}, Disabled);
    ChangeCharacterEnableState({m[CASTERS[4]]}, Disabled);
    ChangeCharacterEnableState({m[CASTERS[5]]}, Disabled);
}});"""
    result = (
        _replace(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join((*imported.values(), bridge, cleanup))
        + "\n"
    )
    out = event_blocks(result)
    if set(out) != set(arena) | set(ids.events()):
        raise ValueError("One Reborn/Ebrietas patch changed event identities")
    if out[12421800] != arena[12421800] or out[12421801] != arena[12421801]:
        raise ValueError("One Reborn/Ebrietas changed Ebrietas terminal or rewards")
    if any(out[e] != b for e, b in arena.items() if e not in edits):
        raise ValueError("One Reborn/Ebrietas changed unrelated Ebrietas event")
    return result


def _rows(slots, e, a, states):
    x = {s.map_name: s for s in slots if s.entity_id == e and s.map_name in states}
    if set(x) != set(states) or any(
        s.dummy or s.talk_id or s.archetype != a for s in x.values()
    ):
        raise ValueError(f"One Reborn/Ebrietas requires pinned actor {e}")
    return x


def native_plan_one_reborn_at_ebrietas(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids=DEFAULT_IDS,
):
    donor = read_blob(BUNDLE, ONE_REBORN_SOURCE).decode("utf-8-sig")
    arena = read_blob(BUNDLE, EBRIETAS_SOURCE).decode("utf-8-sig")
    patch_one_reborn_at_ebrietas(arena, donor, ids)
    cores = _rows(slots, CORE, ARCH[CORE], SOURCE_STATES)
    targets = _rows(slots, TARGET, TARGET_ARCH, TARGET_STATES)
    owners = _rows(slots, 2420801, OWNER_ARCHETYPE, TARGET_STATES)
    helpers = [BODY, CONTROLLER, PROXY, *CASTERS]
    donors = {e: _rows(slots, e, ARCH[e], SOURCE_STATES) for e in helpers}
    swap = Swap(
        targets[TARGET_STATES[0]].logical_key,
        [s.key for s in targets.values()],
        {s.key: s.archetype for s in targets.values()},
        TARGET_ARCH,
        ARCH[CORE],
        warnings=[
            "experimental One Reborn-at-Ebrietas contract; runtime arena behavior is unobserved"
        ],
        destinations={
            s.key: {
                "map_name": s.map_name,
                "entity_id": s.entity_id,
                "x": s.x,
                "y": s.y,
                "z": s.z,
            }
            for s in targets.values()
        },
    )
    changes, skips = plan_scaling(
        [swap], list(targets.values()), dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError("One Reborn/Ebrietas primary normalization is ambiguous")
    additions = []
    req = []
    init = []
    for ss, ts in zip(SOURCE_STATES, TARGET_STATES):
        core, target = cores[ss], targets[ts]
        init.append(
            {
                "source_map": ss,
                "source_part": core.part_name,
                "source_entity_id": CORE,
                "source_archetype": asdict(ARCH[CORE]),
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": PINS[ss][CORE],
                },
                "source_initialization": {
                    "talk_id": 0,
                    "unk_t18": -1,
                    "init_anim_id": -1,
                    "damage_anim_id": -1,
                },
                "destination_map": ts,
                "destination_part": target.part_name,
                "destination_entity_id": TARGET,
            }
        )
        for i, e in enumerate(helpers):
            src = donors[e][ss]
            part = f"ap_one_reborn_{('body','controller','proxy','caster_0','caster_1','caster_2','caster_3','caster_4','caster_5')[i]}"
            additions.append(
                {
                    "source_map": ss,
                    "source_part": src.part_name,
                    "source_anchor_part": core.part_name,
                    "source_entity_id": e,
                    "source_archetype": asdict(ARCH[e]),
                    "source_part_kind": "enemy",
                    "source_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": PINS[ss][e],
                        "anchor_sha256": PINS[ss][CORE],
                    },
                    "source_initialization": {
                        "talk_id": 0,
                        "unk_t18": -1,
                        "init_anim_id": -1,
                        "damage_anim_id": -1,
                    },
                    "destination_map": ts,
                    "destination_anchor_part": target.part_name,
                    "destination_part": part,
                    "destination_entity_id": ids.helper_first + i,
                    "allocation_evidence": "project-reserved helper ID; native writer checks Part/Region/Event collisions",
                }
            )
            req.append(
                {
                    "destination_map": ts,
                    "destination_part": part,
                    "parent_logical_key": swap.logical_key,
                    "source_npc_param_id": ARCH[e].npc_param_id,
                    "strategy": (
                        "reviewed_same_source_npc_helper_clone_required"
                        if e == PROXY
                        else "allocate_distinct_verified_helper_clone"
                    ),
                }
            )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "ebrietas<-the-one-reborn"},
        "boss_actor_additions": additions,
        "primary_init_source_bindings": init,
        "boss_actor_scaling_requirements": req,
        "boss_contract": {
            "format": "bb-one-reborn-ebrietas-contract-v1",
            "arena": "ebrietas",
            "donor": "the-one-reborn",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(DONOR_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "preserved_destination_events": [12421800, 12421801, 12421803],
            "retained_destination_helpers": [
                {
                    "map": row.map_name,
                    "part": row.part_name,
                    "entity_id": row.entity_id,
                    "archetype": asdict(row.archetype),
                    "source_provenance": _pin(EBRIETAS_OWNER_PINS[row.map_name]),
                    "source_initialization": _initialization(),
                    "policy": "unused destination bullet owner disabled until completion",
                }
                for row in owners.values()
            ],
            "terminal_policy": "retain Ebrietas terminal; donor proxy death bridges to primary death only after proxy HP reaches zero",
            "celestial_progression_policy": "unrelated m24 Celestial events remain byte-identical",
            "native_requirements": {
                "actor_additions": 18,
                "region_additions": 0,
                "generator_additions": 0,
                "sfx_additions": 0,
                "evidence": "original One Reborn closure uses only fixed actor parts; destination BGM remains local",
            },
            "event_patch": {
                "changed_events": [
                    *[
                        {
                            "destination_event_id": event,
                            "source_event_id": None,
                            "kind": "adapt_destination_entry_music_and_initialization",
                        }
                        for event in (0, 12421802, 12424803)
                    ],
                    {
                        "destination_event_id": 12424802,
                        "source_event_id": 12804802,
                        "source_sha256": DONOR_HASHES[12804802],
                    },
                    *[
                        {
                            "destination_event_id": event,
                            "source_event_id": None,
                            "kind": "suppress_ebrietas_model_specific_controller",
                        }
                        for event in (12424804, 12424870, 12424871, 12424980, 12424990)
                    ],
                ],
                "added_events": [
                    {
                        "source_event_id": source,
                        "destination_event_id": destination,
                        "source_sha256": DONOR_HASHES[source],
                    }
                    for source, destination in (
                        (12804804, ids.camera),
                        (12804806, ids.tether),
                        (12804807, ids.limb_guard),
                        *((12804820, ids.limb_first + i) for i in range(7)),
                        *(
                            (source, ids.controller_first + i)
                            for i, source in enumerate(
                                (
                                    12804830,
                                    12804831,
                                    12804832,
                                    12804834,
                                    12804835,
                                    12804836,
                                    12804837,
                                    12804838,
                                )
                            )
                        ),
                        *((12804840, ids.caster_react + i) for i in range(2)),
                        *((12804850, ids.caster_count + i) for i in range(6)),
                        (12804870, ids.phase_one),
                        (12804871, ids.phase_two),
                    )
                ]
                + [
                    {
                        "source_event_id": None,
                        "destination_event_id": event,
                        "kind": "destination_terminal_bridge_or_cleanup",
                    }
                    for event in (ids.bridge, ids.cleanup)
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
