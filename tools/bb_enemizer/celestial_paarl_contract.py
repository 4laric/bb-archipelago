"""Pinned full Celestial Emissary combat at Darkbeast Paarl.

Paarl keeps its completion, rewards, fog, and progression.  The donor brings
its primary, phase giant, seven generated waves, two supports, eleven regions,
seven generators, and their complete controller initializer closure.
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
from .boss_contracts import PAARL_ARENA
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
CE_SOURCE = "event/m24_02_00_00.emevd.dcx.js"
PAARL_SOURCE = "event/m23_00_00_00.emevd.dcx.js"
SOURCE_STATES = ("m24_02_00_00", "m24_02_00_01")
DESTINATION_STATES = ("m23_00_00_00", "m23_00_00_01")
SOURCE_PRIMARY, PRIMARY, GIANT = 2420810, 2300810, 980600
WAVES = tuple(range(980601, 980608))
SUPPORT = (980608, 980609)
HELPERS = (GIANT, *WAVES, *SUPPORT)
REGION_ENTITIES = tuple(range(980610, 980621))
GENERATOR_ENTITIES = tuple(range(980621, 980628))
GENERATOR_EVENT_IDS = tuple(range(980628, 980635))

PRIMARY_ARCHETYPE = Archetype("c2500", 250080, 250060, 0)
PAARL_ARCHETYPE = Archetype("c5080", 508000, 508000, 0)
GIANT_ARCHETYPE = Archetype("c2570", 257010, 257010, 0)
WAVE_ARCHETYPE = Archetype("c2500", 250081, 250061, 0)
SUPPORT_ARCHETYPES = (
    Archetype("c2571", 257100, 1, 0),
    Archetype("c2571", 257101, 1, 0),
)

SOURCE_HASHES = {
    0: "cda0f114ad3f96b4b93fda3b81ac6d6ed5808bdb0be3f6d16e8225733e729dde",
    12421702: "e5832b29e358dfe905ab5d47a0c23a84283f9b645dddecaf9a0e7e7ff56ed726",
    12421703: "bb9efdf0969275401f21b29c03ec6cb310a753c98c439f56c12738ebc16b44b0",
    12424702: "b95fb234bbd7f7f9696b5352703a0efb8f965fdafde6860489b2e017fe7ccb4b",
    12424703: "a73cb1fa43c1017779bc8c9c97fd6cfd51726dccdc4bf865dd8096b86b81a3c4",
    12424704: "3d91994d955c589fc9591706094ee3495f2cfadbe0c42081d19055f936b33301",
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


@dataclass(frozen=True)
class CelestialPaarlIds:
    generator_cleanup: int = 12992700
    giant_command: int = 12992701
    giant_ai: int = 12992702
    giant_home: int = 12992703
    giant_phase: int = 12992704
    support_warp: int = 12992705
    support_phase: int = 12992706
    giant_choreography: int = 12992707
    giant_death_bridge: int = 12992708
    wave_home: int = 12992709
    lifecycle_cleanup: int = 12992710
    music_flag: int = 12992790
    evidence: str = "Celestial/Paarl allocation v1; original EMEVD/MSBB corpus scan"

    def events(self) -> tuple[int, ...]:
        values = asdict(self)
        return tuple(
            values[name]
            for name in (
                "generator_cleanup",
                "giant_command",
                "giant_ai",
                "giant_home",
                "giant_phase",
                "support_warp",
                "support_phase",
                "giant_choreography",
                "giant_death_bridge",
                "wave_home",
                "lifecycle_cleanup",
            )
        )


DEFAULT_IDS = CelestialPaarlIds()

SOURCE_ACTORS = (
    (2420811, "c2570_0001", GIANT, "ap_ce_giant", GIANT_ARCHETYPE),
    (2420711, "c2500_0001", WAVES[0], "ap_ce_wave_1", WAVE_ARCHETYPE),
    (2420712, "c2500_0002", WAVES[1], "ap_ce_wave_2", WAVE_ARCHETYPE),
    (2420713, "c2500_0003", WAVES[2], "ap_ce_wave_3", WAVE_ARCHETYPE),
    (2420716, "c2500_0006", WAVES[3], "ap_ce_wave_6", WAVE_ARCHETYPE),
    (2420717, "c2500_0007", WAVES[4], "ap_ce_wave_7", WAVE_ARCHETYPE),
    (2420719, "c2500_0009", WAVES[5], "ap_ce_wave_9", WAVE_ARCHETYPE),
    (2420720, "c2500_0010", WAVES[6], "ap_ce_wave_10", WAVE_ARCHETYPE),
    (2420750, "c2571_0000", SUPPORT[0], "ap_ce_support_1", SUPPORT_ARCHETYPES[0]),
    (2420751, "c2571_0001", SUPPORT[1], "ap_ce_support_2", SUPPORT_ARCHETYPES[1]),
)

ACTOR_PINS = {
    "m24_02_00_00": (
        "b59699c3a1530fdd4f2af2aebaf8ecf51de6bfa7665a7858e4dc2ce6eeebb910",
        "db231b04a55ae8481e3a490baa0e3d0b3a869b7720982dc668ac2bc59b43d82d",
        "95c82d4515a4d9ac2da55b9e2ec8283d984a1b06854df23bd4ab8cb3a94bd713",
        "8bdaaf92db8179e0c6caa26d1bbbe797683f53073152431883e57dce98419778",
        "b2ba985e21287c62d5fe64349f1349963a24546264b7c94108ff1802b436d152",
        "b56d7f36acb208d5c9b049955c3fa07761aa85a0fa4781dd53e0c1ab37775ae2",
        "6a39b4b07ee88fc2f5a4b9c1955132c4155c461152509e34779953627fa54de7",
        "13a559895dd7beac0745a1b31a71e338cf86781374fa59c275484e71f12e8cfd",
        "36959229af687ddc347e79c43dca84a16a1a70973f1c7542166fdc4ddb4f83f1",
        "3880c91215a6946d33fd4be046c7dae5e42011532462ead60a62516119cd87b6",
        "b48f991e496629e90c779a25c11b57d1a8ee5f4a6635bd5e1f17ab19d41b0e12",
    ),
    "m24_02_00_01": (
        "53166a85478171b61dc5a7a88a1600f21880ee1572367628b4868ad6f5c99018",
        "e2031b00add6fdac2dde628013aa0e6d2d56d381f2921717f2bb7433378b7c09",
        "fca2a067920237eb0c6676211917cde06bf9b36841d972f6cbc1fd9b9c113bef",
        "75da29f4df18a4e05e0b2427f4e14fbe03f40d44e237d1d9cdfa97166de56e59",
        "8b62dc44ba8ace58580da34099e25f86f63b7db41d6c14676d9db2c378d56636",
        "a80806083fa58e85dabfc906c90820f71c0eaf80ea872569660c05624c769648",
        "42a90de02db3c23d5a9795ea3074296933b7c84064c95708a45834ec43377e57",
        "601f1f4cc27f2a7b90a9a9f94135089fddf70561a76b5be10fa2e5cd60eb1f2a",
        "6a1c3dce35b977d2569f907b3ad631cec0dbec96e7fcb0fb35b6b148fc1b1e4a",
        "6f0594a37fa4b66989da79935fbb9fd0b4f7c6545b1542fdbea4ca73e86738f2",
        "ad90ea30af3112fd8311ccb6d1b979b1c8ce91466c61b24ed13983c597f5cc1d",
    ),
}
DESTINATION_PINS = {
    "m23_00_00_00": "cac704506e58dfd3f2c57113d919fafe0a70d01b7a40b869deffa3c6e22cc0a2",
    "m23_00_00_01": "6c8a693b9c846922a1113726ec69a11b47973c5e367a94757ad82d3fbf3081ee",
}

REGION_SPECS = (
    ("Gene_月からの使者01", 2422711, "ap_ce_spawn_1"),
    ("Gene_月からの使者02", 2422712, "ap_ce_spawn_2"),
    ("Gene_月からの使者03", 2422713, "ap_ce_spawn_3"),
    ("Gene_月からの使者06", 2422716, "ap_ce_spawn_6"),
    ("Gene_月からの使者07", 2422717, "ap_ce_spawn_7"),
    ("Gene_月からの使者09", 2422719, "ap_ce_spawn_9"),
    ("Gene_月からの使者10", 2422720, "ap_ce_spawn_10"),
    ("Event_巣_月からの使者本体", 2422721, "ap_ce_giant_home"),
    ("Event_月からの使者本体_魔法攻撃エリア", 2422722, "ap_ce_giant_magic"),
    ("Event_月からの使者_ひまわり畑から出ない", 2422816, "ap_ce_bounds"),
    (
        "Event_領域_月からの使者_再戦動き始め_月からの使者（大）が引き返す",
        2422817,
        "ap_ce_wake",
    ),
)
REGION_PINS = {
    "m24_02_00_00": (
        "ad3631d2bc4453ce1aa602b2808c1c0eeec03f296a2becf9f4d290ebef97dc57",
        "bef4ead1fccd41becb83a82bbae122d7fca95c98fbf8e0e239a537fe0b41282d",
        "4fc7ab9e82b69043a617e76ebee2fa4428e5742283ab79885302901b87ffb42d",
        "52fafdbe0e1c4a96a207f624b4d5516573d7ff80ed798d8262989bbc9e525aa1",
        "42b22731e53ca8e1701f06ba1a8efe3885828d338e34b54c51ad0ea8769e2fc9",
        "5465ebfe5913796afde369b6ac6762c4a9d5ae3ce15072fe25300557a0db7de5",
        "7a5316d26c6c3001ed3621cdd5891f760c3c6065b55e524efd4714bb132ba7ad",
        "10f5c35359b91a1adc297df8a9ee72cf37392f691ebb77a4024c16423082c036",
        "d20fa5cf05db21b63fe5096eb647a2083519b81ab49282388b0e5e97a9d0aac5",
        "4cfd288716416d831257319559565dc5193ddf03f3a6d6772e969f6985a48fcd",
        "ce0564fab01411d50fabf73caf840e20b555b8c86ce5164494b678afef2b1dcc",
    ),
    "m24_02_00_01": (
        "6a1d6a24aa5cdf496848af888113c7e9c3876ff6a93f6c39667e3a6c4b5acb62",
        "ef8a574819670456ca2005fd952fe0695a203e69aa8be14a21c011ff34ce6691",
        "1724469f0cd21b14ea9f8461b6b68a5a6ea205fdebfe460fa975244cda4b4c36",
        "254f8b056048b767bf50cbcaf530b8fc6776fbd151e63f84abb3c358acbb655b",
        "93b5918c5a13c1b0491e2426a7cc4d14ccba65bbab1898a8fb2544e06cea0fba",
        "c02d69ef81ca534484fb5be5b619a7eba39bc5446f8a88b1e17534c8130248e8",
        "2ec106bb56fadec529371e6060b01fa61d9f4caca6565cf179398d8c866c159d",
        "1e99fe4259cdb893ca3f910cfecc989780c8d2ec48f447cb58dce91f2aaa2acb",
        "98c3b9cdc75003eb697fc53663dc611c54f8e440eab1a823e69a0f0d888a1305",
        "15bc972fd913ac2f03cced561dc9bd20f990d0935ac000efc485eb2eaeaf22ee",
        "31f734059d98a37d8bc9e8ba877ba449ce5d15c2d25d32ef02fa7d57ff502165",
    ),
}

GENERATOR_SPECS = (
    ("Gene_月からの使者01", 146, 2423711, "c2500_0001"),
    ("Gene_月からの使者02", 147, 2423712, "c2500_0002"),
    ("Gene_月からの使者03", 148, 2423713, "c2500_0003"),
    ("Gene_月からの使者06", 160, 2423716, "c2500_0006"),
    ("Gene_月からの使者07", 161, 2423717, "c2500_0007"),
    ("Gene_月からの使者09", 164, 2423719, "c2500_0009"),
    ("Gene_月からの使者10", 179, 2423720, "c2500_0010"),
)
GENERATOR_PINS = {
    "m24_02_00_00": (
        "15e8f8352e1afcf7d9f3d3bc9ef62b3d3100c6293d54b85c330fe2b71a6da9f8",
        "bad4e2abef3dc672f3085f16142c562d1af118beccf4f1d33de20e0973decd50",
        "44b97b731bcc3b8ea8f5c668b62b1845c6da14c0c86943f0eba8521645b33bd5",
        "11e4e692a284ab2b5b646741b91032cd8832fc93b742bacdbd44a12eeb775e41",
        "aedecb85fa197861079a5ab6df2a59afdfa28187df1463ceef78f609c340ea49",
        "0b439489af1f1081c1137c405783190bf4009b8d641987813fd0cf11694e5405",
        "4a634a5977889ec562cc87bd2bf60b1c1bda739dd7e8f1f00b5361a09053f432",
    ),
    "m24_02_00_01": (
        "856bee0dfd4ff1d67e475acdc1a6457fd8241c03562c66e410bb80a9761a069e",
        "54e70627f797dae062f45d294b1d09c63b2682aa11022b5abc5fe5cea63722d1",
        "021e5d8c7c5662bb70a4c6e3d63797b7083fe07ee7df32dc51db631cce9038e4",
        "a5b8f70356209a1a5e30cb2120064c3de4d77c48e5ea6931240a1226f898f37e",
        "32f2165c0f04a0af9cbd2faed3a928b309bae02068bd0bd6dfd26825907ccd84",
        "1c508bc3cd43fb72b36f83db9541d81f8b67ca9f819655b563ae78984337b9f7",
        "6c8c26416c5dedb3566c471dc17656efe5cd579fa82e803b763cc24acce322db",
    ),
}


def _verify(text: str, expected: Mapping[int, str], role: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event_id, digest in expected.items():
        if hashlib.sha256(blocks.get(event_id, "").encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {role} event {event_id}")
    return blocks


@cache
def _original_literals() -> set[int]:
    return {
        int(value)
        for body in read_prefix(BUNDLE, "event/").values()
        for value in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
    }


def _validate_ids(ids: CelestialPaarlIds, destination: str) -> None:
    events = ids.events()
    if len(set(events)) != len(events) or any(
        not 12992700 <= value <= 12992789 for value in events
    ):
        raise ValueError(
            "Celestial/Paarl events must be unique project-owned 129927xx values"
        )
    allocated = (
        set(events)
        | {ids.music_flag}
        | set(HELPERS)
        | set(REGION_ENTITIES)
        | set(GENERATOR_ENTITIES)
        | set(GENERATOR_EVENT_IDS)
    )
    if allocated.intersection(_original_literals()) or set(events).intersection(
        event_blocks(destination)
    ):
        raise ValueError(
            "Celestial/Paarl project allocation collides with original corpus"
        )


def _require(
    slots: Sequence[Slot], entity: int, archetype: Archetype, map_name: str
) -> Slot:
    found = [
        row
        for row in slots
        if row.entity_id == entity
        and row.archetype == archetype
        and row.map_name == map_name
    ]
    if len(found) != 1 or found[0].dummy or found[0].talk_id:
        raise ValueError(
            f"unsupported Celestial/Paarl placement provenance for {entity} in {map_name}"
        )
    return found[0]


def _pin(part: str, anchor: str | None = None) -> dict:
    result = {"format": "bb-boss-actor-pin-v1", "part_sha256": part}
    if anchor is not None:
        result["anchor_sha256"] = anchor
    return result


def _init() -> dict:
    return {"talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1}


def native_plan_celestial_at_paarl(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: CelestialPaarlIds = DEFAULT_IDS,
) -> dict:
    donor_text = read_blob(BUNDLE, CE_SOURCE).decode("utf-8-sig")
    arena_text = read_blob(BUNDLE, PAARL_SOURCE).decode("utf-8-sig")
    _verify(donor_text, SOURCE_HASHES, "Celestial donor")
    _verify(arena_text, PAARL_ARENA.expected, "Paarl arena")
    _validate_ids(ids, arena_text)
    sources = {
        state: _require(slots, SOURCE_PRIMARY, PRIMARY_ARCHETYPE, state)
        for state in SOURCE_STATES
    }
    targets = {
        state: _require(slots, PRIMARY, PAARL_ARCHETYPE, state)
        for state in DESTINATION_STATES
    }
    helpers = {
        state: {
            entity: _require(slots, entity, archetype, state)
            for entity, _, _, _, archetype in SOURCE_ACTORS
        }
        for state in SOURCE_STATES
    }
    destinations = [targets[state] for state in DESTINATION_STATES]
    swap = Swap(
        destinations[0].logical_key,
        [row.key for row in destinations],
        {row.key: row.archetype for row in destinations},
        PAARL_ARCHETYPE,
        PRIMARY_ARCHETYPE,
        warnings=[
            "experimental Celestial-Emissary-at-Paarl contract; runtime behavior unobserved"
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
        [swap], destinations, dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError(
            "Celestial/Paarl primary swap has an ambiguous normalization plan"
        )
    additions, regions, generators, bindings = [], [], [], []
    for state_index, destination_state in enumerate(DESTINATION_STATES):
        source_state = SOURCE_STATES[state_index]
        source, target = sources[source_state], targets[destination_state]
        bindings.append(
            {
                "source_map": source_state,
                "source_part": source.part_name,
                "source_entity_id": SOURCE_PRIMARY,
                "source_archetype": asdict(PRIMARY_ARCHETYPE),
                "source_provenance": _pin(ACTOR_PINS[source_state][0]),
                "source_initialization": _init(),
                "destination_map": destination_state,
                "destination_part": target.part_name,
                "destination_entity_id": PRIMARY,
            }
        )
        for actor_index, (
            source_entity,
            source_part,
            destination_entity,
            destination_part,
            archetype,
        ) in enumerate(SOURCE_ACTORS, 1):
            if helpers[source_state][source_entity].part_name != source_part:
                raise ValueError("Celestial/Paarl source actor name drift")
            additions.append(
                {
                    "source_map": source_state,
                    "source_part": source_part,
                    "source_anchor_part": source.part_name,
                    "source_entity_id": source_entity,
                    "source_archetype": asdict(archetype),
                    "source_part_kind": "enemy",
                    "source_provenance": _pin(
                        ACTOR_PINS[source_state][actor_index],
                        ACTOR_PINS[source_state][0],
                    ),
                    "source_initialization": _init(),
                    "destination_map": destination_state,
                    "destination_anchor_part": target.part_name,
                    "destination_part": destination_part,
                    "destination_entity_id": destination_entity,
                    "allocation_evidence": ids.evidence,
                }
            )
        for index, (source_region, source_entity, destination_region) in enumerate(
            REGION_SPECS
        ):
            regions.append(
                {
                    "source_map": source_state,
                    "source_region": source_region,
                    "source_entity_id": source_entity,
                    "source_provenance": {
                        "format": "bb-boss-region-pin-v1",
                        "region_sha256": REGION_PINS[source_state][index],
                    },
                    "source_anchor_part": source.part_name,
                    "source_anchor_provenance": _pin(ACTOR_PINS[source_state][0]),
                    "destination_map": destination_state,
                    "destination_region": destination_region,
                    "destination_entity_id": REGION_ENTITIES[index],
                    "destination_anchor_part": target.part_name,
                    "destination_anchor_provenance": _pin(
                        DESTINATION_PINS[destination_state]
                    ),
                }
            )
        for index, (source_name, source_event, source_entity, source_part) in enumerate(
            GENERATOR_SPECS
        ):
            generators.append(
                {
                    "source_map": source_state,
                    "source_event": source_name,
                    "source_event_id": source_event,
                    "source_entity_id": source_entity,
                    "source_fingerprint": GENERATOR_PINS[source_state][index],
                    "destination_map": destination_state,
                    "destination_event": f"ap_ce_generator_{index + 1}",
                    "destination_event_id": GENERATOR_EVENT_IDS[index],
                    "destination_entity_id": GENERATOR_ENTITIES[index],
                    "destination_part_name": None,
                    "destination_region_name": None,
                    "spawn_part_map": {source_part: SOURCE_ACTORS[index + 1][3]},
                    "spawn_point_map": {source_name: REGION_SPECS[index][2]},
                }
            )
    requirements = [
        {
            "destination_map": row["destination_map"],
            "destination_part": row["destination_part"],
            "parent_logical_key": swap.logical_key,
            "source_npc_param_id": row["source_archetype"]["npc_param_id"],
            "strategy": "allocate_distinct_verified_helper_clone",
        }
        for row in additions
    ]
    literal_map = _mapping(ids)
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {
            "experimental_boss_contract": "darkbeast-paarl<-celestial-emissary"
        },
        "boss_actor_additions": additions,
        "boss_region_additions": regions,
        "boss_generator_additions": generators,
        "primary_init_source_bindings": bindings,
        "boss_actor_scaling_requirements": requirements,
        "boss_contract": {
            "format": "bb-celestial-paarl-contract-v1",
            "arena": "darkbeast-paarl",
            "donor": "celestial-emissary",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(SOURCE_HASHES),
            "arena_hash_pins": dict(PAARL_ARENA.expected),
            "preserved_destination_events": [12301700, 12301701, 12304705],
            "terminal_policy": "retain byte-identical Paarl terminal; bridge giant death to primary only afterward",
            "source_roster": {
                "primary": SOURCE_PRIMARY,
                "giant": 2420811,
                "waves": [row[0] for row in SOURCE_ACTORS[1:8]],
                "support": [2420750, 2420751],
                "regions": [row[1] for row in REGION_SPECS],
                "generators": [row[2] for row in GENERATOR_SPECS],
            },
            "event_literal_map": {
                str(key): value
                for key, value in literal_map.items()
                if key
                in {row[1] for row in REGION_SPECS}
                | {row[2] for row in GENERATOR_SPECS}
            },
            "foreign_literal_policy": {
                "literals": [2800800, 2800801, 2800802, 2800803],
                "evidence": "One Reborn actors absent from both pinned Celestial maps",
                "action": "replace no-op co-op block with source-backed primary scaling; materialize no foreign actors",
            },
            "region_transform_policy": "native anchor-relative transform; MSBB yaw is degrees",
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


def celestial_helper_scaling_parents(plan: Mapping) -> dict[tuple[str, str], str]:
    rows = plan.get("boss_actor_scaling_requirements", ())
    result = {
        (row["destination_map"], row["destination_part"]): row["parent_logical_key"]
        for row in rows
    }
    if len(result) != len(rows):
        raise ValueError("duplicate Celestial helper scaling destination")
    return result


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Celestial/Paarl expected one {label}")
    return text.replace(old, new)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(values.get(int(match.group()), int(match.group()))),
        text,
    )


def _mapping(ids: CelestialPaarlIds) -> dict[int, int]:
    result = {
        SOURCE_PRIMARY: PRIMARY,
        2420811: GIANT,
        12421700: 12301700,
        12421702: 12301702,
        12421703: 12301703,
        12424700: 12304700,
        12424701: 12304701,
        12424702: 12304702,
        12424703: 12304703,
        12424704: 12304704,
        2422812: 2302812,
        2422815: 2302811,
        2423812: 2303812,
        2423813: 2303813,
        2800010: 2300010,
        12425246: ids.music_flag,
        12424770: ids.generator_cleanup,
        12424780: ids.giant_command,
        12424784: ids.giant_ai,
        12424785: ids.giant_home,
        12424787: ids.wave_home,
        12424790: ids.giant_phase,
        12424791: ids.support_warp,
        12424792: ids.support_phase,
        12424795: ids.giant_choreography,
    }
    result.update({source: target for source, _, target, _, _ in SOURCE_ACTORS})
    result.update(
        {
            source: REGION_ENTITIES[index]
            for index, (_, source, _) in enumerate(REGION_SPECS)
        }
    )
    result.update(
        {
            source: GENERATOR_ENTITIES[index]
            for index, (_, _, source, _) in enumerate(GENERATOR_SPECS)
        }
    )
    return result


def _end_event(block: str) -> str:
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            "unused_" + value.strip()
            for value in match.group(1).split(",")
            if value.strip()
        )
        + ")",
        block.splitlines()[0],
    )
    return header + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for parsed in reversed(parse_events(source)):
        if parsed.event_id in edits:
            lines[parsed.first_line - 1 : parsed.last_line] = edits[
                parsed.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _calls(
    event_zero: str, source_event: int, destination_event: int, expected: int
) -> list[str]:
    rows = [
        re.sub(
            r"(\$InitializeEvent\([^,]+,\s*)" + str(source_event),
            r"\g<1>" + str(destination_event),
            line,
        )
        for line in event_zero.splitlines()
        if re.match(
            r"\s*\$InitializeEvent\([^,]+,\s*" + str(source_event) + r"(?:,|\))", line
        )
    ]
    if len(rows) != expected:
        raise ValueError(
            f"Celestial Event(0) must initialize {source_event} {expected} time(s)"
        )
    return rows


def _activation(source: str, ids: CelestialPaarlIds) -> str:
    result = _remap(source, _mapping(ids))
    result = _replace_once(
        result,
        "InArea(10000, 2302811)",
        "EntityInRadiusOfEntity(2300810, 10000, 16)",
        "Paarl entry trigger",
    )
    tail = "    ChangeCharacterEnableState(980606, Enabled);\n    SetCharacterAIState(980606, Enabled);\n    ForceAnimationPlayback(980606, 6200, false, false, false);\n});"
    return _replace_once(
        result,
        tail,
        tail[:-4]
        + "    EndIf(EventFlag(9340));\n    $InitializeEvent(0, 9350, 1);\n    SetEventFlag(9340, ON);\n});",
        "Paarl discovery progression",
    )


def _health(source: str, ids: CelestialPaarlIds) -> str:
    for effect in (7500, 7501):
        old = "\n".join(
            [
                *(
                    f"    SetSpEffect({actor}, {effect}, true);"
                    for actor in range(2800800, 2800804)
                ),
                "    WaitFixedTimeFrames(1);",
                *(
                    f"    AdaptHpchangingSpEffectToNPCPartOfTarget({actor});"
                    for actor in range(2800800, 2800804)
                ),
            ]
        )
        new = f"    SetSpEffect({SOURCE_PRIMARY}, {effect}, true);\n    WaitFixedTimeFrames(1);\n    AdaptHpchangingSpEffectToNPCPartOfTarget({SOURCE_PRIMARY});"
        source = _replace_once(
            source, old, new, f"foreign {effect} co-op scaling block"
        )
    source = _replace_once(
        source,
        "            SetNetworkUpdateAuthority(2800810, AuthorityLevel.Forced);\n            SetNetworkUpdateAuthority(2800811, AuthorityLevel.Forced);",
        "            SetNetworkUpdateAuthority(2420810, AuthorityLevel.Forced);\n            SetNetworkUpdateAuthority(2420811, AuthorityLevel.Forced);",
        "foreign authority pair",
    )
    source = _replace_once(
        source, "CreatePlaylog(104);", "CreatePlaylog(86);", "Paarl playlog"
    )
    source = _replace_once(
        source,
        "StartTimeMeasurement(2800010, 40, Enabled);",
        "StartTimeMeasurement(2800010, 102, Enabled);",
        "Paarl measurement",
    )
    return _remap(source, _mapping(ids))


def _music(source: str, ids: CelestialPaarlIds) -> str:
    source = _replace_once(
        source,
        "SetMapSoundState(2703802, Disabled);",
        "SetMapSoundState(2423812, Disabled);",
        "foreign phase-one sound",
    )
    source = _replace_once(
        source,
        "SetMapSoundState(2703803, Disabled);",
        "SetMapSoundState(2423813, Disabled);",
        "foreign phase-two sound",
    )
    return _remap(source, _mapping(ids))


def _camera(source: str, ids: CelestialPaarlIds) -> str:
    result = _remap(source, _mapping(ids)).replace(
        "SetLockcamSlotNumber(24, 2,", "SetLockcamSlotNumber(23, 0,"
    )
    return _replace_once(
        result,
        "    SetNetworkSyncState(Disabled);",
        "    SetNetworkSyncState(Disabled);\n    EndIf(EventFlag(12301700));",
        "completed camera guard",
    )


def _bridge(ids: CelestialPaarlIds) -> str:
    return f"""$Event({ids.giant_death_bridge}, Default, function() {{
    EndIf(EventFlag(12301700));
    WaitFor(CharacterDead({GIANT}));
    EndIf(EventFlag(12301700));
    ForceCharacterDeath({PRIMARY}, false);
}});"""


def _cleanup(ids: CelestialPaarlIds) -> str:
    generators = "".join(
        f"    DeactivateGenerator({entity}, Disabled);\n"
        for entity in GENERATOR_ENTITIES
    )
    actors = "".join(
        f"    SetCharacterImmortality({entity}, Disabled);\n    SetCharacterAIState({entity}, Disabled);\n    SetCharacterHPBarDisplay({entity}, Disabled);\n    ChangeCharacterEnableState({entity}, Disabled);\n    ForceCharacterDeath({entity}, false);\n"
        for entity in HELPERS
    )
    return f"""$Event({ids.lifecycle_cleanup}, Default, function() {{
    WaitFor(EventFlag(12301700));
{generators}{actors}}});"""


def patch_celestial_emissary_at_paarl(
    destination: str, donor_source: str, ids: CelestialPaarlIds = DEFAULT_IDS
) -> str:
    arena = _verify(destination, PAARL_ARENA.expected, "Paarl arena")
    donor = _verify(donor_source, SOURCE_HASHES, "Celestial donor")
    _validate_ids(ids, destination)
    mapping = _mapping(ids)
    transplant = (
        (ids.generator_cleanup, 12424770, 8),
        (ids.giant_command, 12424780, 1),
        (ids.giant_ai, 12424784, 1),
        (ids.giant_home, 12424785, 2),
        (ids.wave_home, 12424787, 2),
        (ids.giant_phase, 12424790, 1),
        (ids.support_warp, 12424791, 1),
        (ids.support_phase, 12424792, 2),
        (ids.giant_choreography, 12424795, 1),
    )
    initializers = [
        _remap(line, mapping)
        for destination_event, source_event, count in transplant
        for line in _calls(donor[0], source_event, destination_event, count)
    ]
    initializers.extend(
        (
            f"    $InitializeEvent(0, {ids.giant_death_bridge});",
            f"    $InitializeEvent(0, {ids.lifecycle_cleanup});",
        )
    )
    anchor = "    $InitializeEvent(0, 12304715, 2300, 2300, NPCPartType.Part1, 480, 490, 8000, 130);"
    constructor = _replace_once(
        arena[0],
        anchor,
        anchor + "\n" + "\n".join(initializers),
        "Paarl constructor anchor",
    )
    edits = {
        0: constructor,
        12301702: _activation(donor[12421702], ids),
        12301703: _remap(donor[12421703], mapping),
        12304702: _health(donor[12424702], ids),
        12304703: _music(donor[12424703], ids),
        12304704: _camera(donor[12424704], ids),
        12304707: _end_event(arena[12304707]),
        12304715: _end_event(arena[12304715]),
        **{
            destination_event: _remap(donor[source_event], mapping)
            for destination_event, source_event, _ in transplant
        },
        ids.giant_death_bridge: _bridge(ids),
        ids.lifecycle_cleanup: _cleanup(ids),
    }
    result = _replace_events(
        destination,
        {event_id: body for event_id, body in edits.items() if event_id in arena},
    )
    result = (
        result.rstrip()
        + "\n\n"
        + "\n\n".join(edits[event_id] for event_id in ids.events())
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.events()):
        raise ValueError("Celestial/Paarl changed event identities")
    for event_id, body in arena.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Celestial/Paarl changed unrelated event {event_id}")
    if output[12301700] != arena[12301700]:
        raise ValueError("Celestial/Paarl changed Paarl terminal progression")
    copied = "\n".join(
        output[event_id]
        for event_id in (
            12301702,
            12301703,
            12304702,
            12304703,
            12304704,
            *ids.events(),
        )
    )
    if re.search(r"(?<!\d)(?:124\d{5}|242\d{4}|270\d{4}|280\d{4})(?!\d)", copied):
        raise ValueError("Celestial/Paarl copied combat retains a donor-map literal")
    return result
