"""Rom's complete combat graph in the One Reborn's destination arena.

The original destination terminal still owns all rewards and progression.
Rom's death kills its retained offstage proxy; the displaced body/support
controllers are retired. Native placement retains the original relative Rom
spider and warp geometry, whose destination fit needs gameplay validation.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob
from . import rom_ebrietas_contract as rom
from .boss_canary import event_blocks
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = rom.BUNDLE
ARENA_SOURCE = "event/m28_00_00_00.emevd.dcx.js"
STATES = ("m28_00_00_00", "m28_00_00_01")
PRIMARY, PROXY = 2800800, 2800803
ARCHETYPE = Archetype("c5070", 507000, 0, 6553600)
RETAINED = (
    2800801,
    2800802,
    2800803,
    2800520,
    2800522,
    2800524,
    2800525,
    2800527,
    2800529,
)
RETIRED_EVENTS = (
    12804806,
    12804807,
    12804820,
    12804830,
    12804831,
    12804832,
    12804834,
    12804835,
    12804836,
    12804837,
    12804838,
    12804840,
    12804850,
    12804870,
    12804871,
)
COMBAT = (13204807, 13204808, 13204809, 13204810, 13204000, 13204050, 13204730)
EVENT_MAP = dict(zip(COMBAT, range(12993300, 12993307)))
BRIDGE = 12993307
WAVE_FLAGS = (12993308, 12993309)
SPIDERS = tuple(range(981100, 981130))
WARPS = (981130, 981131)
ARENA_HASHES = {
    0: "4de4c6a57d7aaffd0e6244099f666dc4ef3ca41eb3d9d5d4a7a3c1708ba8464a",
    12801800: "e9d1c62b8e026124033f59ef4837ad7a6acf0acd7370f6cef617390e3983f314",
    12801801: "862a767916fc6a576b3b75a46dcec8ad10d1fd65cf5d4bf7e8937d16707025db",
    12801802: "a91ed2bd9c33333b7d6549bca707ae31bd5516b473576363405c712d8ac16b13",
    12801803: "6aef4a36171592164ea1e1538764511f46b9d66ba5e67543cf85dacdb150d249",
    12804802: "7e17bc4225eaa32aa8405674a1d0b499fd0ba51ec3e47f13ebb8a5dca9d68140",
    12804803: "d9fe3eab4eeb93fcc5e13e719399de18dafe7583b527aaa9d648f355a9b39130",
    12804804: "fff8d31b08506d033ddcf87bd34518fc81ccf56d6b9af3956d973c7dcd80f7e8",
    12804805: "d0b1a556a8143ae8fa2cde98e704639ee4fdb0d842ba9ccf53af79db9ac56abd",
    12804880: "f45dfed0229e9e8b22ba47f1ec5be35513d91cb11597b139e8c9124567d0673b",
    12804881: "e2015ba9f925165d4a1e8607746071e9c2fba01a62b146f68be747ff21b2704e",
    12804882: "a736076639f022330032dcea205dad098631209e6a9fd3da92fd42bbec5361ea",
    12804883: "e2fc67522090ed5b522314832d492416ab76c7fd91bb7af42ebb6bc50a19ecfd",
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
ACTOR_WITNESSES = {
    "m28_00_00_00": {
        2800520: {
            "part": "c1050_0110",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105810,
                "chara_init_id": 6553600,
            },
            "sha256": "ebd81e2114d3394c8a6eb28051c85c9fdf52609576b2b46714803e5b619db131",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800522: {
            "part": "c1050_0112",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105811,
                "chara_init_id": 6553600,
            },
            "sha256": "f05463f2b014ad0d946a9cf6c31ee14aaea1af7e3e9803d46faa64ea84c662fb",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800524: {
            "part": "c1050_0114",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105810,
                "chara_init_id": 6553600,
            },
            "sha256": "866b9f6e72dec776f8b696ccc37c232aa2ce23d4cdec1e62b5fdee15b575f5d2",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800525: {
            "part": "c1050_0115",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105810,
                "chara_init_id": 6553600,
            },
            "sha256": "9f93949a1af828c9e6645f92cfc0caecfea3e07a035c7734679335e70262b2e0",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800527: {
            "part": "c1050_0117",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105811,
                "chara_init_id": 6553600,
            },
            "sha256": "5cbaf933d6ca13db44cc9c14d965291f7346eecd4ea19ddac91a92f9ee75e63b",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800529: {
            "part": "c1050_0119",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105810,
                "chara_init_id": 6553600,
            },
            "sha256": "6f6b139708f0c18bca6b56768fcf9c9bcce7b1cdbbd18d7e741e182772306627",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800803: {
            "part": "c1050_0120",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 507000,
                "think_param_id": 0,
                "chara_init_id": 0,
            },
            "sha256": "9f83ecd83b83ac250b4f22c6a59aad925febb6bb4e44d13e1f5aa9b9061e4a38",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800800: {
            "part": "c5070_0000",
            "archetype": {
                "model_name": "c5070",
                "npc_param_id": 507000,
                "think_param_id": 0,
                "chara_init_id": 6553600,
            },
            "sha256": "d63b5cc2179fe66b76a237d1286fec90c00b41068847dd2688253fe6868dff64",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800801: {
            "part": "c5071_0000",
            "archetype": {
                "model_name": "c5071",
                "npc_param_id": 507100,
                "think_param_id": 0,
                "chara_init_id": 6553600,
            },
            "sha256": "2e6cbceecd430e43c00cb16cbf464e4431a226fd260a1228d8f5d6fcd21b04e3",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800802: {
            "part": "c5072_0000",
            "archetype": {
                "model_name": "c5072",
                "npc_param_id": 507200,
                "think_param_id": 507200,
                "chara_init_id": 0,
            },
            "sha256": "1094204441e3591e5c98e68eb6fa41133788b3c1cd1282de85609e6e8c8a75e7",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
    },
    "m28_00_00_01": {
        2800520: {
            "part": "c1050_0110",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105810,
                "chara_init_id": 6553600,
            },
            "sha256": "2524a31e0ab89b13d049371be070d62514aa5cba02e28d4ffac370d65bfbf56f",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800522: {
            "part": "c1050_0112",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105811,
                "chara_init_id": 6553600,
            },
            "sha256": "ea8a36357e37ac8ef46e975a93ff7d36688c566af0a36e622a40086b393cf129",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800524: {
            "part": "c1050_0114",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105810,
                "chara_init_id": 6553600,
            },
            "sha256": "364b2a245b226feb77dc688814e7bec9acf334265bee49dfce863fd8a3046609",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800525: {
            "part": "c1050_0115",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105810,
                "chara_init_id": 6553600,
            },
            "sha256": "95b3115d07725e9dd27cd136cdf4061bf36b6ce5d4dc302be2b492eecbb2cd3a",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800527: {
            "part": "c1050_0117",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105811,
                "chara_init_id": 6553600,
            },
            "sha256": "0bcd2bec58a33eb22a16d870e93528b1213c0ccf8c02adeabb62621fc3331c19",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800529: {
            "part": "c1050_0119",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 105810,
                "think_param_id": 105810,
                "chara_init_id": 6553600,
            },
            "sha256": "53df7c070f759799a2beaeeab5d2380cf0c66dc1fb690edfe6e7694f7cc44c34",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800803: {
            "part": "c1050_0120",
            "archetype": {
                "model_name": "c1050",
                "npc_param_id": 507000,
                "think_param_id": 0,
                "chara_init_id": 0,
            },
            "sha256": "dd53094dd91f469d2d44af6dda3084b0620f7666258057e19550f5ed5ed0f69a",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800800: {
            "part": "c5070_0000",
            "archetype": {
                "model_name": "c5070",
                "npc_param_id": 507000,
                "think_param_id": 0,
                "chara_init_id": 6553600,
            },
            "sha256": "3d66cbbe3ec301c4e57705524ceb6a7fc2784cc23a991afe0762c45186a4fa5f",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800801: {
            "part": "c5071_0000",
            "archetype": {
                "model_name": "c5071",
                "npc_param_id": 507100,
                "think_param_id": 0,
                "chara_init_id": 6553600,
            },
            "sha256": "cd731459de6be54a6633ae36584894c75b0bf6ac351c16ec32a64091fa4e144a",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
        2800802: {
            "part": "c5072_0000",
            "archetype": {
                "model_name": "c5072",
                "npc_param_id": 507200,
                "think_param_id": 507200,
                "chara_init_id": 0,
            },
            "sha256": "911986915373bd1bd64e4f178039af5c985e50bd116c0d8cc52e910f34a6fa07",
            "initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
        },
    },
}


def _validate(destination: str = "") -> None:
    owned = set(EVENT_MAP.values()) | {BRIDGE, *WAVE_FLAGS, *SPIDERS, *WARPS}
    if len(owned) != 42 or owned & rom._original_ids():
        raise ValueError(
            "Rom/One Reborn project allocation collides with original inputs"
        )
    if owned & {
        int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)
    }:
        raise ValueError("Rom/One Reborn allocation collides with destination")


def _mapping() -> dict[int, int]:
    return {
        rom.ROM: PRIMARY,
        13201800: 12801800,
        13201802: 12801802,
        13204800: 12804800,
        13204801: 12804801,
        13204802: 12804802,
        13204803: 12804803,
        13204804: 12804804,
        13204811: WAVE_FLAGS[0],
        13204812: WAVE_FLAGS[1],
        3202806: WARPS[0],
        3202807: WARPS[1],
        3200010: 2800010,
        **EVENT_MAP,
        **{3200200 + i: entity for i, entity in enumerate(SPIDERS)},
    }


def patch_rom_at_one_reborn(destination: str, donor_source: str) -> str:
    original = rom._verify(destination, ARENA_HASHES, "One Reborn arena")
    donor = rom._verify(
        donor_source, rom.DONOR_HASHES, "Rom donor", rom.DONOR_ALTERNATES
    )
    _validate(destination)
    mapping = _mapping()
    health = rom._remap(donor[13204802], mapping)
    health = rom._replace_once(
        health, "CreatePlaylog(124);", "CreatePlaylog(238);", "destination playlog"
    )
    health = rom._replace_once(
        health,
        "StartTimeMeasurement(2800010, 62, Enabled);",
        "StartTimeMeasurement(2800010, 254, Enabled);",
        "destination time measurement",
    )
    music = rom._replace_once(
        original[12804803],
        "CharacterHasEventMessage(2800800, 300)",
        "CharacterHasEventMessage(2800800, 10)",
        "Rom phase message",
    )
    camera = rom._remap(donor[13204804], mapping).replace(
        "SetLockcamSlotNumber(32, 0,", "SetLockcamSlotNumber(28, 0,"
    )
    if camera.count("SetLockcamSlotNumber(28, 0,") != 2:
        raise ValueError("Rom/One Reborn camera remap lost source writes")
    additions = {}
    for source, target in EVENT_MAP.items():
        body = donor[source]
        if source in (13204808, 13204809):
            body = rom._replace_once(
                body,
                "    RequestCharacterAIReplan(2420800);\n",
                "",
                "foreign source replan",
            )
        body = rom._remap(body, mapping)
        if source == 13204050:
            body = rom._replace_once(
                body,
                "WaitFor(EventFlag(eventFlagId) && CharacterDead(2800800));",
                "WaitFor((EventFlag(eventFlagId) && CharacterDead(2800800)) || EventFlag(12801800));",
                "completed-load spider cleanup",
            )
        additions[target] = body
    cleanup = "\n".join(
        f"    ChangeCharacterEnableState({entity}, Disabled);\n"
        f"    SetCharacterAIState({entity}, Disabled);\n"
        f"    SetCharacterHPBarDisplay({entity}, Disabled);"
        for entity in RETAINED
    )
    additions[BRIDGE] = f"""$Event({BRIDGE}, Default, function() {{
{cleanup}
    EndIf(EventFlag(12801800));
    WaitFor(CharacterDead(2800800));
    ForceCharacterDeath(2800803, false);
}});"""
    calls = rom._source_initializers(donor[0], set(COMBAT), mapping)
    calls.append(f"    $InitializeEvent(0, {BRIDGE});")
    constructor = rom._replace_once(
        original[0],
        "    $InitializeEvent(0, 12804871);",
        "    $InitializeEvent(0, 12804871);\n" + "\n".join(calls),
        "constructor anchor",
    )
    edits = {
        0: constructor,
        12804802: health,
        12804803: music,
        12804804: camera,
        **{event: rom._end_event(original[event]) for event in RETIRED_EVENTS},
    }
    for event in (12801802, 12801803):
        edits[event] = rom._replace_once(
            original[event],
            "    ChangeCharacterEnableState(2800801, Enabled);\n",
            "",
            "displaced second-body activation",
        )
    result = (
        rom._replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions.values())
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(original) | set(additions):
        raise ValueError("Rom/One Reborn changed event identities")
    for event, body in original.items():
        if event not in edits and output[event] != body:
            raise ValueError(f"Rom/One Reborn changed unrelated event {event}")
    copied = "\n".join(output[event] for event in (12804802, 12804804, *additions))
    if re.search(
        r"(?<!\d)(?:132\d{5}|320(?:0[0-9]{3}|[1238][0-9]{3})|2420800)(?!\d)", copied
    ):
        raise ValueError("Rom/One Reborn retains foreign source-map dependency")
    return result


def native_plan_rom_at_one_reborn(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
) -> dict:
    arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
    rom._verify(arena, ARENA_HASHES, "One Reborn arena")
    rom._verify(
        read_blob(BUNDLE, rom.ROM_SOURCE).decode("utf-8-sig"),
        rom.DONOR_HASHES,
        "Rom donor",
        rom.DONOR_ALTERNATES,
    )
    _validate(arena)
    targets = rom._require(slots, PRIMARY, ARCHETYPE)
    cores = rom._require(slots, rom.ROM, rom.ROM_ARCHETYPE)
    if {row.map_name for row in targets} != set(STATES) or len(targets) != 2:
        raise ValueError("Rom/One Reborn needs both destination map states")
    if {row.map_name for row in cores} != set(rom.ROM_STATES) or len(cores) != 2:
        raise ValueError("Rom/One Reborn needs both original donor map states")
    swap = Swap(
        targets[0].logical_key,
        [row.key for row in targets],
        {row.key: row.archetype for row in targets},
        ARCHETYPE,
        rom.ROM_ARCHETYPE,
        warnings=[
            "experimental Rom/One Reborn; runtime arena fit and progression require validation"
        ],
        destinations={
            row.key: {
                "map_name": row.map_name,
                "entity_id": row.entity_id,
                "x": row.x,
                "y": row.y,
                "z": row.z,
            }
            for row in targets
        },
    )
    changes, skips = plan_scaling(
        [swap], list(targets), dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError("Rom/One Reborn primary normalization is ambiguous")
    additions, bindings, regions, retained = [], [], [], []
    by_identity = {(row.map_name, row.entity_id): row for row in slots}
    for state, source_state in zip(STATES, rom.ROM_STATES):
        target = by_identity[state, PRIMARY]
        core = by_identity[source_state, rom.ROM]
        for entity in (PRIMARY, *RETAINED):
            row = by_identity[state, entity]
            witness = ACTOR_WITNESSES[state][entity]
            if (
                row.part_name != witness["part"]
                or asdict(row.archetype) != witness["archetype"]
                or row.talk_id
            ):
                raise ValueError("Rom/One Reborn retained actor roster drift")
            if entity != PRIMARY:
                retained.append(
                    {
                        "map": state,
                        "part": row.part_name,
                        "entity_id": entity,
                        "archetype": asdict(row.archetype),
                        "source_provenance": rom._pin(witness["sha256"]),
                        "source_initialization": witness["initialization"],
                        "policy": "disabled; original proxy killed only after Rom death",
                    }
                )
        bindings.append(
            {
                "source_map": source_state,
                "source_part": core.part_name,
                "source_entity_id": rom.ROM,
                "source_archetype": asdict(rom.ROM_ARCHETYPE),
                "source_provenance": rom._pin(rom.ROM_CORE_PINS[source_state]),
                "source_initialization": rom._initialization(),
                "destination_map": state,
                "destination_part": target.part_name,
                "destination_entity_id": PRIMARY,
            }
        )
        for index, entity in enumerate(SPIDERS):
            spider = by_identity[source_state, 3200200 + index]
            if (
                spider.archetype != rom.SPIDER_ARCHETYPE
                or spider.dummy
                or spider.talk_id
            ):
                raise ValueError("Rom/One Reborn spider roster drift")
            additions.append(
                {
                    "source_map": source_state,
                    "source_part": spider.part_name,
                    "source_anchor_part": core.part_name,
                    "source_entity_id": spider.entity_id,
                    "source_archetype": asdict(spider.archetype),
                    "source_part_kind": "enemy",
                    "source_provenance": rom._pin(
                        rom.ROM_SPIDER_PINS[source_state][index],
                        anchor_sha256=rom.ROM_CORE_PINS[source_state],
                    ),
                    "source_initialization": rom._initialization(),
                    "destination_map": state,
                    "destination_anchor_part": target.part_name,
                    "destination_part": f"ap_rom_one_spider_{index:02d}",
                    "destination_entity_id": entity,
                    "allocation_evidence": "reserved 981100-981131; full original literal collision scan",
                }
            )
        for index, source_region in enumerate(
            ("Event_白痴の蜘蛛_ワープ先00", "Event_白痴の蜘蛛_ワープ先01")
        ):
            regions.append(
                {
                    "source_map": source_state,
                    "source_region": source_region,
                    "source_entity_id": 3202806 + index,
                    "source_provenance": {
                        "format": "bb-boss-region-pin-v1",
                        "region_sha256": rom.ROM_REGION_PINS[source_state][index],
                    },
                    "source_anchor_part": core.part_name,
                    "source_anchor_provenance": rom._pin(
                        rom.ROM_CORE_PINS[source_state]
                    ),
                    "destination_map": state,
                    "destination_region": f"ap_rom_one_warp_{index:02d}",
                    "destination_entity_id": WARPS[index],
                    "destination_anchor_part": target.part_name,
                    "destination_anchor_provenance": rom._pin(
                        ACTOR_WITNESSES[state][PRIMARY]["sha256"]
                    ),
                }
            )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "boss_actor_additions": additions,
        "boss_region_additions": regions,
        "primary_init_source_bindings": bindings,
        "boss_actor_scaling_requirements": [
            {
                "destination_map": row["destination_map"],
                "destination_part": row["destination_part"],
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": rom.SPIDER_ARCHETYPE.npc_param_id,
                "strategy": "allocate_distinct_verified_helper_clone",
            }
            for row in additions
        ],
        "boss_contract": {
            "format": "bb-rom-one-reborn-contract-v1",
            "arena": "the-one-reborn",
            "donor": "rom",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "retained_destination_helpers": retained,
            "source_hash_pins": rom.DONOR_HASHES,
            "arena_hash_pins": ARENA_HASHES,
            "preserved_destination_events": [
                12801800,
                12801801,
                12804805,
                12804880,
                12804881,
                12804882,
                12804883,
            ],
            "terminal_policy": "original proxy terminal; death bridge only after Rom dies",
            "added_event_ids": [*EVENT_MAP.values(), BRIDGE],
            "retired_events": list(RETIRED_EVENTS),
        },
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [row.json() for row in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
