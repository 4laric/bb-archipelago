"""Source-pinned fallbacks for Central Yharnam's scripted-AI enemies.

Two events hand pinned placements AI that only their own model understands:
the sleep-to-wake event 12415130 (c1120 AI IDs) and the sewer rat ambush
12410340 (c1100 AI command 10). When such a placement swaps, the writer
suppresses only that placement's InitializeEvent call.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


EVENT_FILE = "m24_01_00_00.emevd.dcx.js"
EVENT_ID = 12415130
MAP = "m24_01_00_00"

# logical key -> (MSB entity ID, InitializeEvent slot, flag-condition argument)
PINS = {
    "m24_01_00_00:c1120_0009": (2410148, 8, 1),
    "m24_01_00_00:c1120_0010": (2410149, 9, 1),
    "m24_01_00_00:c1120_0011": (2410150, 10, 0),
    "m24_01_00_00:c1120_0015": (2410154, 14, 1),
    "m24_01_00_00:c1120_0016": (2410140, 0, 1),
    "m24_01_00_00:c1120_0017": (2410141, 1, 0),
    "m24_01_00_00:c1120_0019": (2410143, 3, 0),
    "m24_01_00_00:c1120_0020": (2410144, 4, 1),
    "m24_01_00_00:c1120_0022": (2410146, 6, 0),
    "m24_01_00_00:c1120_0023": (2410147, 7, 0),
}


# Sewer rat ambush: on entering region 2412220 each rat gets a new home
# region and c1100 AI command 10 (run there), cleared on arrival or on
# recognition. logical key -> (MSB entity ID, InitializeEvent slot, home region)
AMBUSH_EVENT_ID = 12410340
AMBUSH_COMMAND = 10
AMBUSH_TRIGGER_REGION = 2412220
AMBUSH_PINS = {
    "m24_01_00_00:c1100_0008": (2410220, 0, 2412230),
    "m24_01_00_00:c1100_0007": (2410221, 1, 2412231),
    "m24_01_00_00:c1100_0003": (2410222, 2, 2412232),
    "m24_01_00_00:c1100_0002": (2410223, 3, 2412233),
    "m24_01_00_00:c1100_0006": (2410224, 4, 2412234),
    "m24_01_00_00:c1100_0001": (2410225, 5, 2412235),
    "m24_01_00_00:c1100_0000": (2410226, 6, 2412236),
    "m24_01_00_00:c1100_0005": (2410227, 7, 2412237),
    "m24_01_00_00:c1100_0004": (2410228, 8, 2412238),
}
# Native body fingerprint of event 12410340 (BossCanary.Fingerprint over the
# real m24_01_00_00.emevd.dcx; print it with the writer's --event-fingerprint).
# The bundled inputs carry only decompiled JS, so this cannot be derived here.
# Until it is pinned the ambush placements are not released, and the writer
# refuses ambush rows. Must equal WakeupFallback.AmbushBodyFingerprint.
AMBUSH_BODY_FINGERPRINT: str | None = None


def event_for(logical_key: str) -> int:
    """Return the pinned initializer event a fallback placement belongs to."""
    if logical_key in PINS:
        return EVENT_ID
    if logical_key in AMBUSH_PINS:
        return AMBUSH_EVENT_ID
    raise ValueError(f"no pinned scripted-AI fallback for {logical_key}")


def verify_ambush(text: str) -> None:
    """Refuse unless the rat ambush initializers and body match their pins."""
    calls = re.findall(
        rf"\$InitializeEvent\((\d+),\s*{AMBUSH_EVENT_ID},\s*(\d+),\s*(\d+),"
        rf"\s*{AMBUSH_COMMAND},\s*{AMBUSH_TRIGGER_REGION}\);",
        text,
    )
    expected = {(str(slot), str(entity), str(region))
                for entity, slot, region in AMBUSH_PINS.values()}
    if set(calls) != expected or len(calls) != len(AMBUSH_PINS):
        raise ValueError("Central Yharnam rat ambush initializer pins changed")
    if text.count(f", {AMBUSH_EVENT_ID},") != len(AMBUSH_PINS):
        raise ValueError("Central Yharnam rat ambush event has unpinned initializers")
    body_match = re.search(rf"\$Event\({AMBUSH_EVENT_ID},[\s\S]*?\n\}}\);", text)
    if body_match is None:
        raise ValueError("Central Yharnam rat ambush event body is missing")
    body = body_match.group(0)
    required = (
        "WaitFor(InArea(10000, areaEntityId2));",
        "SetCharacterHome(chrEntityId, areaEntityId);",
        "RequestCharacterAICommand(chrEntityId, commandId, 0);",
        "RequestCharacterAICommand(chrEntityId, -1, 0);",
    )
    if any(witness not in body for witness in required):
        raise ValueError("Central Yharnam rat ambush event behavior changed")
    forbidden = (
        "SetEventFlag(", "ChangeCharacterEnableState(", "SetCharacterAIState(",
        "SetCharacterAIId(", "SetCharacterBackreadState(", "ForceCharacterDeath(",
        "InitializeEvent(",
    )
    if any(operation in body for operation in forbidden):
        raise ValueError("Central Yharnam rat ambush event now gates AI, backread, or flags")


def build_release(event_root: str | Path, *,
                  include_ambush: bool | None = None) -> dict:
    """Build the fallback record only when every pinned source witness matches.

    The rat ambush joins the record only once its native body fingerprint is
    pinned (``include_ambush`` overrides that for tests).
    """
    if include_ambush is None:
        include_ambush = AMBUSH_BODY_FINGERPRINT is not None
    source = Path(event_root) / EVENT_FILE
    raw = source.read_bytes()
    text = raw.decode("utf-8-sig")
    calls = re.findall(
        r"\$InitializeEvent\((\d+),\s*12415130,\s*(\d+),\s*9000,\s*9061,\s*52410270,\s*112499,\s*112400,\s*(\d+)\);",
        text,
    )
    expected_calls = {
        (str(slot), str(entity), str(flag))
        for entity, slot, flag in PINS.values()
    }
    if set(calls) != expected_calls or len(calls) != len(PINS):
        raise ValueError("Central Yharnam wakeup initializer pins changed")
    body_match = re.search(r"\$Event\(12415130,[\s\S]*?\n\}\);", text)
    if body_match is None:
        raise ValueError("Central Yharnam wakeup event body is missing")
    body = body_match.group(0)
    required = (
        "ForceAnimationPlayback(chrEntityId, animationId",
        "SetCharacterAIId(chrEntityId, aiId)",
        "CharacterAIState(chrEntityId, AIStateType.Alert)",
        "ForceAnimationPlayback(chrEntityId, animationId2",
        "SetCharacterAIId(chrEntityId, aiId2)",
    )
    if any(witness not in body for witness in required):
        raise ValueError("Central Yharnam wakeup event behavior changed")
    forbidden = (
        "SetCharacterAIState(chrEntityId, Disabled)",
        "ChangeCharacterEnableState(chrEntityId, Disabled)",
        "SetCharacterBackreadState(chrEntityId",
        "SetEventFlag(",
    )
    if any(operation in body for operation in forbidden):
        raise ValueError("Central Yharnam wakeup event now gates AI, backread, or flags")
    if text.count("52410270") != len(PINS):
        raise ValueError("Central Yharnam wakeup flag has uses outside pinned initializers")

    releases = {}
    initializers = []
    for logical_key, (entity_id, event_slot, flag_condition) in sorted(PINS.items()):
        releases[logical_key] = {
            "entity_ids": [entity_id],
            "physical_copies": 3,
            "reason": (
                "wakeup initializer uses c1120-specific AI IDs 112499 (sleep) "
                "and 112400 (wake); suppress only this initializer when this placement is randomized"
            ),
            "contract_class": "scripted_wakeup_fallback",
            "initialization_event_id": EVENT_ID,
        }
        initializers.append({
            "logical_key": logical_key,
            "entity_id": entity_id,
            "event_slot": event_slot,
            "arguments": [entity_id, 9000, 9061, 52410270, 112499, 112400, flag_condition],
        })
    record = {
        "format": "bb-enemizer-release-v1",
        "tranche": "wakeup",
        "releases": releases,
        "awake_fallback": {
            "map": MAP,
            "source_event_file": EVENT_FILE,
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "event_id": EVENT_ID,
            "operation": "suppress_initializer_for_swapped_entity",
            "preserve": (
                "All other EMEVD events and calls; the destination MSB entity, transforms, flags, "
                "quest events, and all non-wakeup script behavior."
            ),
            "initializers": initializers,
        },
    }
    if not include_ambush:
        return record
    verify_ambush(text)
    ambush_initializers = []
    for logical_key, (entity_id, event_slot, home_region) in sorted(AMBUSH_PINS.items()):
        releases[logical_key] = {
            "entity_ids": [entity_id],
            "physical_copies": 3,
            "reason": (
                "ambush initializer sends c1100-specific AI command 10 toward a pinned "
                "home region; suppress only this initializer when this placement is randomized"
            ),
            "contract_class": "scripted_ambush_fallback",
            "initialization_event_id": AMBUSH_EVENT_ID,
        }
        ambush_initializers.append({
            "logical_key": logical_key,
            "entity_id": entity_id,
            "event_slot": event_slot,
            "arguments": [entity_id, home_region, AMBUSH_COMMAND, AMBUSH_TRIGGER_REGION],
        })
    record["releases"] = dict(sorted(releases.items()))
    record["ambush_fallback"] = {
        "map": MAP,
        "source_event_file": EVENT_FILE,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "event_id": AMBUSH_EVENT_ID,
        "body_fingerprint": AMBUSH_BODY_FINGERPRINT,
        "operation": "suppress_initializer_for_swapped_entity",
        "preserve": (
            "All other EMEVD events and calls; the destination MSB entity, transforms, "
            "home regions, and all non-ambush script behavior."
        ),
        "initializers": ambush_initializers,
    }
    return record
