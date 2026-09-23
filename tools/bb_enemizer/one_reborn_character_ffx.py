"""Original typed character roots delivered through One Reborn's whole SFX bank.

This establishes direct root delivery, not recursive FXR or runtime closure.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Sequence

PROOF_FILE = Path(__file__).with_suffix(".json")
PROOF_SHA256 = "a7626146127e3e66345395c9841d86237c2bea221ba9a09828f318207bda6cbf"


def character_ffx_plan(actors: Sequence[dict], arena_key: str) -> dict:
    """Bind original TAE proofs to every core, body and caster destination."""
    raw = PROOF_FILE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROOF_SHA256:
        raise ValueError("One Reborn character effect proof resource changed")
    proof = json.loads(raw)
    destination = proof["destinations"][arena_key]
    source = proof["source_bank"]
    rosters: dict[str, Counter] = defaultdict(Counter)
    for actor in actors:
        rosters[actor["destination_map"]][actor["source_archetype"]["model_name"]] += 1
    expected = Counter({"c5070": 1, "c5071": 1, "c5072": 1, "c1050": 7})
    if not rosters or any(roster != expected for roster in rosters.values()):
        raise ValueError("One Reborn character delivery requires the complete multipart roster")

    requirements, deliveries = [], []
    seen_sources, seen_destinations = set(), set()
    all_roots: set[int] = set()
    for actor in actors:
        character = actor["source_archetype"]["model_name"]
        if character == "c5072":
            # Its original TAE has no events in the reviewed 96/100/118 profile.
            continue
        template = proof["characters"][character]
        identity = (actor["source_map"], actor["source_part"], actor["source_entity_id"])
        destination_identity = (actor["destination_map"], actor["destination_part"],
                                actor["destination_entity_id"])
        if destination_identity in seen_destinations:
            raise ValueError("duplicate One Reborn character delivery destination")
        seen_destinations.add(destination_identity)
        if identity not in seen_sources:
            requirement = copy.deepcopy(template["requirement_template"])
            requirement.update(zip(("source_map", "source_part", "source_entity_id"), identity))
            requirements.append(requirement)
            seen_sources.add(identity)
        roots = copy.deepcopy(template["bank_roots"])
        all_roots.update(root["witness"]["effect_id"] for root in roots)
        deliveries.append({
            "format": "bb-boss-character-ffx-bank-requirement-v1",
            **{key: actor[key] for key in (
                "source_map", "source_part", "source_entity_id",
                "destination_map", "destination_part", "destination_entity_id")},
            "source_character": character,
            "source_ffx_file": source["file"],
            "destination_ffx_file": destination["file"],
            "roots": roots,
        })
    return {
        "boss_character_ffx_requirements": requirements,
        "boss_character_ffx_bank_requirements": deliveries,
        "boss_ffx_merges": [{
            "source_file": source["file"], "source_sha256": source["sha256"],
            "destination_file": destination["file"],
            "destination_sha256": destination["sha256"],
            "required_effect_ids": sorted(all_roots),
            "policy": "preserve_destination_union_source_v1",
        }],
    }
