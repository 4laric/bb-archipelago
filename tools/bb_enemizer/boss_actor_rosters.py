"""Evidence-pinned multi-actor boss combat rosters.

These are static source contracts for CUSA03173 AppVer 01.09. They identify
combat actors only; destination fog, rewards, cutscenes and completion ownership
are deliberately excluded.
"""
from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_enemizer.bosses import Event, parse_events
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.model import Slot
from tools.bb_inputs import read_blob, read_prefix

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"


@dataclass(frozen=True)
class Actor:
    entity_id: int
    role: str  # core, phase_proxy, support, effect_owner


@dataclass(frozen=True)
class EventWitness:
    event_id: int
    actor_ids: tuple[int, ...]

    @property
    def fingerprint(self) -> tuple[int, tuple[int, ...]]:
        """Stable, reviewable relation rather than a heuristic event search."""
        return self.event_id, self.actor_ids


@dataclass(frozen=True)
class EncounterRoster:
    key: str
    source: str
    source_sha256: str
    actors: tuple[Actor, ...]
    generators: tuple[int, ...]
    witnesses: tuple[EventWitness, ...]
    unresolved_entities: tuple[int, ...] = ()
    excluded_destination_entities: tuple[int, ...] = ()


@dataclass(frozen=True)
class ActorPlacement:
    entity_id: int
    key: str
    logical_key: str
    position: tuple[float, float, float]
    model_name: str
    npc_param_id: int
    think_param_id: int
    chara_init_id: int


@dataclass(frozen=True)
class VerifiedRoster:
    roster: EncounterRoster
    placements: tuple[ActorPlacement, ...]


def _actors(role: str, *ids: int) -> tuple[Actor, ...]:
    return tuple(Actor(entity, role) for entity in ids)


ROSTERS: tuple[EncounterRoster, ...] = (
    EncounterRoster(
        "witch_of_hemwick", "event/m22_00_00_00.emevd.dcx.js",
        "ebba03cdcbb9783ae2f6bb72f5681ab97c4a3dd0082c8f9af82e2ea12bb83cdb",
        _actors("core", 2200800) + _actors("phase_proxy", 2200801)
        + _actors("support", 2200810, 2200811, 2200812),
        (2205000, 2205001, 2205002),
        (EventWitness(12201800, (2200800, 2200801)),
         EventWitness(12201803, (2200810, 2200811, 2200812)),
         EventWitness(12204810, (2200800, 2200801)),
         EventWitness(12204811, (2200800, 2200810))),
    ),
    EncounterRoster(
        "father_gascoigne", "event/m24_01_00_00.emevd.dcx.js",
        "6d58b164e95233201e1490db0a443ac2fae99000de045840c6be0344a8c8d888",
        _actors("core", 2410810) + _actors("phase_proxy", 2410811), (),
        (EventWitness(12411800, (2410810, 2410811)),
         EventWitness(12414802, (2410810, 2410811))),
    ),
    EncounterRoster(
        "celestial_emissary", "event/m24_02_00_00.emevd.dcx.js",
        "688538e606f1df42abfcad7bf17c234f468392f2a164075ecc2659ce623c88d3",
        _actors("core", 2420810) + _actors("phase_proxy", 2420811)
        + _actors("support", 2420711, 2420712, 2420713, 2420716, 2420717,
                  2420719, 2420720, 2420750, 2420751),
        (2423711, 2423712, 2423713, 2423716, 2423717, 2423719, 2423720),
        (EventWitness(12421700, (2420811,)),
         EventWitness(12421702, (2420810, 2420711, 2420712, 2420713, 2420716,
                                  2420717, 2420719, 2420720)),
         EventWitness(12424790, (2420810, 2420811)),
         EventWitness(12424791, (2420811, 2420750, 2420751))),
    ),
    EncounterRoster(
        "martyr_logarius", "event/m25_00_00_00.emevd.dcx.js",
        "77448d9329ba0b0eb24143d23194bb3c664b9b62a6bc2622c241212d67024d90",
        _actors("core", 2500800) + _actors("support", 2500801)
        + _actors("effect_owner", 2500802), (),
        (EventWitness(12501800, (2500800, 2500801, 2500802)),
         EventWitness(12504802, (2500800, 2500801, 2500802)),
         EventWitness(12504806, (2500800, 2500801)),
         EventWitness(12504807, (2500800, 2500802))),
    ),
    EncounterRoster(
        "mergos_wet_nurse", "event/m26_00_00_00.emevd.dcx.js",
        "7cb356580055ca641f096122f2cd2e5d902aeb036c6e56f51bc9e58918058e1f",
        _actors("core", 2600800) + _actors("support", 2600801)
        + _actors("phase_proxy", 2600802), (),
        (EventWitness(12601800, (2600800, 2600801, 2600802, 2600803)),
         EventWitness(12604802, (2600800, 2600801, 2600802)),
         EventWitness(12604804, (2600803,)),
         EventWitness(12604840, (2600800, 2600801))),
        unresolved_entities=(2600803,),
    ),
    EncounterRoster(
        "shadows_of_yharnam", "event/m27_00_00_00.emevd.dcx.js",
        "db3b4e14f7af8b6edcec52660670129c0487cd1367469abd8b1633bccbc7e0bd",
        _actors("core", 2700800, 2700801, 2700802)
        + _actors("support", 2700803, 2700804, 2700805, 2700810, 2700811,
                  2700813, 2700814),
        (2705001, 2705002, 2705003),
        (EventWitness(12701800, (2700800, 2700801, 2700802)),
         EventWitness(12704802, (2700800, 2700801, 2700802, 2700803, 2700804,
                                  2700805)),
         # The assistant IDs bind into parameterized 12704815 from the map
         # constructor; the callee itself contains parameter names, not IDs.
         EventWitness(0, (2700810, 2700811, 2700813, 2700814))),
    ),
    EncounterRoster(
        "the_one_reborn", "event/m28_00_00_00.emevd.dcx.js",
        "7b70859801f0d45be3380ab970b72e7ea8e89bb41571ad7629b2cb47f68e7f28",
        _actors("core", 2800800, 2800801, 2800802)
        + _actors("phase_proxy", 2800803)
        + _actors("support", 2800520, 2800522, 2800524, 2800525, 2800527,
                  2800529), (),
        (EventWitness(12801800, (2800800, 2800801, 2800802, 2800803, 2800520,
                                  2800522, 2800524, 2800525, 2800527, 2800529)),
         EventWitness(12804802, (2800800, 2800801, 2800802, 2800803, 2800520,
                                  2800522, 2800524, 2800525, 2800527, 2800529)),
         EventWitness(12804830, (2800801, 2800802))),
    ),
    EncounterRoster(
        "ludwig", "event/m34_00_00_00.emevd.dcx.js",
        "d50b17ff84e5d9f8d93a74030948fad84426b13080cc96a8ceec69c5bfdfb7f2",
        _actors("core", 3400800) + _actors("phase_proxy", 3400801), (),
        (EventWitness(13401800, (3400800, 3400801)),
         EventWitness(13404802, (3400800, 3400801))),
        excluded_destination_entities=(3400810,),
    ),
    EncounterRoster(
        "living_failures", "event/m35_00_00_00.emevd.dcx.js",
        "63f648e14db260beea39b36b2a91b00599f69d321529c20972dbcb41ef30147d",
        _actors("phase_proxy", 3500850)
        + _actors("core", 3500851, 3500852, 3500853, 3500854)
        + _actors("support", 3500860), (),
        (EventWitness(13501850, (3500850, 3500851, 3500852, 3500853, 3500854)),
         EventWitness(13504852, (3500850, 3500851, 3500852, 3500853, 3500854,
                                  3500860)),
         EventWitness(13505680, (3500851, 3500852, 3500853, 3500854, 3500860))),
    ),
    EncounterRoster(
        "orphan_of_kos", "event/m36_00_00_00.emevd.dcx.js",
        "f958e9ea522ddd49f49f87fbe7f6f9dc27b4a2d843fe85aa824f2e01597702ae",
        _actors("core", 3600800) + _actors("phase_proxy", 3600801)
        + _actors("support", 3600803), (),
        (EventWitness(13601800, (3600800, 3600801)),
         EventWitness(13604802, (3600800, 3600801)),
         EventWitness(13604820, (3600800, 3600801)),
         EventWitness(13604830, (3600801, 3600803))),
        excluded_destination_entities=(3600802,),
    ),
)

BY_KEY: Mapping[str, EncounterRoster] = {roster.key: roster for roster in ROSTERS}


def _event_fingerprint(event: Event) -> tuple[int, tuple[tuple[str, tuple[str, ...]], ...]]:
    return event.event_id, tuple((call.operation, call.arguments) for call in event.calls)


def _event_mentions(event: Event, entity_id: int) -> bool:
    needle = str(entity_id)
    return any(needle in call.arguments for call in event.calls)


def _load_slots(bundle: Path) -> list[Slot]:
    with tempfile.TemporaryDirectory(prefix="bb-boss-actors-") as temp:
        inventory = Path(temp) / "msb_enemies.tsv"
        inventory.write_bytes(read_blob(bundle, "mined/msb_enemies.tsv"))
        return load_slots(inventory)


def verify_rosters(
    bundle: Path = BUNDLE,
    *,
    rosters: Sequence[EncounterRoster] = ROSTERS,
) -> tuple[VerifiedRoster, ...]:
    """Verify the declared contract against the original bundled sources.

    This intentionally validates declarations only. It does not discover or
    approve new actors heuristically.
    """
    scripts = {name: data.decode("utf-8-sig") for name, data in read_prefix(bundle, "event/").items()}
    slots = _load_slots(bundle)
    verified: list[VerifiedRoster] = []
    for roster in rosters:
        text = scripts.get(roster.source)
        if text is None:
            raise ValueError(f"{roster.key}: missing source {roster.source}")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != roster.source_sha256:
            raise ValueError(f"{roster.key}: source hash changed for {roster.source}")
        events = {event.event_id: event for event in parse_events(text)}
        declared_ids = {actor.entity_id for actor in roster.actors} | set(roster.unresolved_entities)
        for witness in roster.witnesses:
            event = events.get(witness.event_id)
            if event is None:
                raise ValueError(f"{roster.key}: missing witness event {witness.event_id}")
            if witness.fingerprint != (witness.event_id, witness.actor_ids):
                raise ValueError(f"{roster.key}: malformed witness tuple")
            for entity_id in witness.actor_ids:
                if entity_id not in declared_ids:
                    raise ValueError(f"{roster.key}: witness names undeclared actor {entity_id}")
                if not _event_mentions(event, entity_id):
                    raise ValueError(f"{roster.key}: event {witness.event_id} does not witness {entity_id}")
        for actor in roster.actors:
            if not any(actor.entity_id in witness.actor_ids for witness in roster.witnesses):
                raise ValueError(f"{roster.key}: actor {actor.entity_id} has no source witness")
        placements: list[ActorPlacement] = []
        for actor in roster.actors:
            matched = [slot for slot in slots if slot.entity_id == actor.entity_id]
            if not matched:
                raise ValueError(f"{roster.key}: placeable actor {actor.entity_id} has no MSB placement")
            for slot in matched:
                placements.append(ActorPlacement(
                    actor.entity_id, slot.key, slot.logical_key, (slot.x, slot.y, slot.z),
                    slot.archetype.model_name, slot.archetype.npc_param_id,
                    slot.archetype.think_param_id, slot.archetype.chara_init_id,
                ))
        if set(roster.unresolved_entities) & {placement.entity_id for placement in placements}:
            raise ValueError(f"{roster.key}: unresolved entity was treated as placeable")
        if set(roster.excluded_destination_entities) & {actor.entity_id for actor in roster.actors}:
            raise ValueError(f"{roster.key}: destination infrastructure entered combat roster")
        verified.append(VerifiedRoster(roster, tuple(placements)))
    return tuple(verified)
