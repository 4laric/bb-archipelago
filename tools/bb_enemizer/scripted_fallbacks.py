"""JS-level scripted-AI initializer fallbacks for the reviewed boss pool.

Some placements are started by per-enemy ``$InitializeEvent`` calls whose
events apply model- or AI-specific operations (AI IDs, AI commands, NPC
parts, hit and display masks) that donor AI or models cannot carry. When such
a placement swaps, removing only that placement's pinned initializer lines
lets the donor behave normally at the placement.

The reviewed boss builder already decompiles, patches, and recompiles map
events with the pinned DarkScript, so these fallbacks are applied there as
one more constructor variant. Every removed line is pinned verbatim, and every
callee body is pinned by the SHA-256 of its decompiled block; a different game
version or event body refuses the build rather than patching blindly.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from .wakeup_fallback import AMBUSH_PINS, PINS as WAKEUP_PINS


FORMAT = "bb-enemizer-release-v1"
TRANCHE = "scripted"

# map -> decompiled callee event -> SHA-256 of its "$Event(...) ... });" block
CALLEE_BODIES: dict[str, dict[int, str]] = {
    "m24_01_00_00": {
        # c1120 sleep-to-wake: AI IDs 112499/112400 around animations 9000/9061
        12415130: "da8216c084ed51b6baf036f67cb9360599d62d51fb0146c65f8bbd55385969da",
        # c1100 sewer rat ambush: AI command 10 toward a pinned home region
        12410340: "dc5741a67f69a2e5d5710eba18c8da4bfc78b40d991cac669a5e108a3cdb80ff",
    },
    "m24_00_00_00": {
        # c2700 servant lantern display mask (bits 3/4)
        12405210: "df494a86aa40f98d2fe3857c53d2fb6974b63ea9b06a88f479ffdb1899cc0a87",
        # c2730 Church Giant sleep/sit AI IDs and poses, paired with their enders
        12405000: "9768941aa60a54a1ee3283797956c631f4b49c31695f26efbfa9a543231ab563",
        12405010: "9bfb35f1309349566f692402b823d2b3dceb17da6bdcb0707e05abd4d26bd151",
        12405020: "c147e74c4519f2634f6dfab052dfa283e820d97e13c67f735f2b89a9cfb9ef08",
        12405030: "c045399907d8df0d8e9dd5d7ad6ddfce33792b86bc796e0e8cfc59feb0417500",
        # Church Giant breakable parts: create, break/repair, hitmask
        12405430: "2f4f7b157af01890962e8f92cbb4b58b86db0763ce5f1329b876073b6130453c",
        12405400: "38b202c540783b3a54b82db928276917b41e58af64fdf1a8ab33eafc7272c581",
        12405460: "3de7683a4a67e2045a50fae46fb14738c4a33b140daa8a12853cbd599d97f2f3",
    },
}

_WAKEUP_LINES = {
    key: [f"$InitializeEvent({slot}, 12415130, {entity}, 9000, 9061, 52410270, 112499, 112400, {flag});"]
    for key, (entity, slot, flag) in WAKEUP_PINS.items()
}
_AMBUSH_LINES = {
    key: [f"$InitializeEvent({slot}, 12410340, {entity}, {home}, 10, 2412220);"]
    for key, (entity, slot, home) in AMBUSH_PINS.items()
}


def _giant(slot_a: int, slot_b: int, entity: int, part_flag: int, break_a: int, break_b: int) -> list[str]:
    return [
        f"$InitializeEvent({slot_a}, 12405430, 2490, 2490, NPCPartType.Part7, 40, {part_flag}, {entity});",
        f"$InitializeEvent({slot_b}, 12405430, 2491, 2491, NPCPartType.Part8, 40, {part_flag}, {entity});",
        f"$InitializeEvent({slot_a}, 12405400, 2490, 2490, NPCPartType.Part7, 7003, 5907, {part_flag}, {break_a}, {entity});",
        f"$InitializeEvent({slot_b}, 12405400, 2491, 2491, NPCPartType.Part8, 7000, 5907, {part_flag}, {break_b}, {entity});",
        f"$InitializeEvent({slot_a}, 12405460, 10, 40, {break_a}, {entity}, 0, 10);",
        f"$InitializeEvent({slot_b}, 12405460, 30, 40, {break_b}, {entity}, 1, 11);",
    ]


def _pose(slot: int, entity: int) -> list[str]:
    return [
        f"$InitializeEvent({slot}, 12405020, {entity}, 7010, 7013, 273120, 273110);",
        f"$InitializeEvent({slot}, 12405030, {entity}, 7012, {slot}, 273100);",
    ]


def _lantern(slot: int, entity: int) -> list[str]:
    return [f"$InitializeEvent({slot}, 12405210, {entity}, 5696);"]


_CATHEDRAL_LINES = {
    "m24_00_00_00:c2700_0000": _lantern(1, 2400116),
    "m24_00_00_00:c2700_0004": _lantern(4, 2400125),
    "m24_00_00_00:c2700_0009": _lantern(5, 2400127),
    "m24_00_00_00:c2700_0013": _lantern(2, 2400122),
    "m24_00_00_00:c2700_0029": _lantern(7, 2400161),
    "m24_00_00_00:c2700_0008": _giant(0, 1, 2400114, 12405500, 12405530, 12405560),
    "m24_00_00_00:c2730_0002": _pose(0, 2400207) + _giant(14, 15, 2400207, 12405507, 12405537, 12405567),
    "m24_00_00_00:c2730_0003": _pose(1, 2400126) + _giant(2, 3, 2400126, 12405501, 12405531, 12405561),
    "m24_00_00_00:c2730_0005": [
        "$InitializeEvent(0, 12405000, 2400205, 7010, 7013, 273150, 273140);",
        "$InitializeEvent(0, 12405010, 2400205, 7012, 0, 273130);",
    ] + _giant(10, 11, 2400205, 12405505, 12405535, 12405565),
    "m24_00_00_00:c2730_0009": _pose(2, 2400203) + _giant(8, 9, 2400203, 12405504, 12405534, 12405564),
    "m24_00_00_00:c2730_0010": _pose(4, 2400119),
    "m24_00_00_00:c2730_0011": _giant(6, 7, 2400133, 12405503, 12405533, 12405563),
}

# logical key -> pinned initializer lines removed when that placement swaps
LINES: dict[str, list[str]] = {**_WAKEUP_LINES, **_AMBUSH_LINES, **_CATHEDRAL_LINES}
# Released only by this boss-pool tranche; the wakeup keys already have their
# own tranche and native fallback, and ride along here when they swap.
RELEASED_KEYS = frozenset({**_AMBUSH_LINES, **_CATHEDRAL_LINES})
ENTITY_IDS: dict[str, int] = {
    **{key: entity for key, (entity, _slot, _flag) in WAKEUP_PINS.items()},
    **{key: entity for key, (entity, _slot, _home) in AMBUSH_PINS.items()},
    "m24_00_00_00:c2700_0000": 2400116, "m24_00_00_00:c2700_0004": 2400125,
    "m24_00_00_00:c2700_0008": 2400114, "m24_00_00_00:c2700_0009": 2400127,
    "m24_00_00_00:c2700_0013": 2400122, "m24_00_00_00:c2700_0029": 2400161,
    "m24_00_00_00:c2730_0002": 2400207, "m24_00_00_00:c2730_0003": 2400126,
    "m24_00_00_00:c2730_0005": 2400205, "m24_00_00_00:c2730_0009": 2400203,
    "m24_00_00_00:c2730_0010": 2400119, "m24_00_00_00:c2730_0011": 2400133,
}


def event_file(logical_key: str) -> str:
    return logical_key.split(":", 1)[0] + ".emevd.dcx.js"


def _event_id(line: str) -> int:
    return int(line[line.index("(") + 1:line.rindex(")")].split(",")[1])


def _callee_block(text: str, event_id: int) -> str:
    match = re.search(rf"^\$Event\({event_id},.*?^\}}\);", text, re.M | re.S)
    if match is None:
        raise ValueError(f"scripted fallback callee {event_id} is missing")
    return match.group(0)


def verify_source(map_name: str, text: str) -> None:
    """Refuse unless every pinned line and callee body matches this map."""
    text = text.replace("\r\n", "\n")
    for event_id, digest in CALLEE_BODIES[map_name].items():
        block = _callee_block(text, event_id)
        if hashlib.sha256(block.encode("utf-8")).hexdigest() != digest:
            raise ValueError(f"scripted fallback callee {event_id} changed in {map_name}")
    lines = [line.strip() for line in text.splitlines()]
    for key, pinned in LINES.items():
        if not key.startswith(map_name + ":"):
            continue
        for line in pinned:
            if lines.count(line) != 1:
                raise ValueError(f"scripted fallback initializer is not unique for {key}: {line}")
    # No initializer of a pinned callee may name a pinned entity outside its pins.
    pinned_lines = {line for key, values in LINES.items() if key.startswith(map_name + ":") for line in values}
    entities = {str(ENTITY_IDS[key]) for key in LINES if key.startswith(map_name + ":")}
    for line in lines:
        if not line.startswith("$InitializeEvent(") or line in pinned_lines:
            continue
        if _event_id(line) in CALLEE_BODIES[map_name]:
            arguments = {value.strip() for value in line[line.index("(") + 1:line.rindex(")")].split(",")}
            if arguments & entities:
                raise ValueError(f"unpinned initializer names a pinned scripted entity: {line}")


def patch_initializers(map_name: str, text: str, logical_keys: Iterable[str]) -> str:
    """Remove exactly the pinned initializer lines of the swapped placements."""
    verify_source(map_name, text)
    keys = sorted(set(logical_keys))
    unknown = [key for key in keys if key not in LINES or not key.startswith(map_name + ":")]
    if unknown:
        raise ValueError("no pinned scripted fallback for " + ", ".join(unknown))
    remove = {line for key in keys for line in LINES[key]}
    if not remove:
        raise ValueError("scripted fallback patch has no placements")
    kept, removed = [], 0
    for line in text.splitlines():
        if line.strip() in remove:
            removed += 1
            continue
        kept.append(line)
    if removed != len(remove):
        raise ValueError("scripted fallback removed an unexpected number of initializers")
    return "\n".join(kept) + ("\n" if text.endswith("\n") else "")


def fallback_rows(swaps: Iterable, slots: Iterable, release: Mapping[str, set[str]]) -> list[dict]:
    """Plan rows for swapped placements released by the scripted tranche."""
    swapped = {swap.logical_key for swap in swaps}
    rows = {}
    for slot in slots:
        key = slot.logical_key
        if key in swapped and TRANCHE in release.get(key, set()) and key in RELEASED_KEYS:
            rows[key] = {"logical_key": key, "entity_id": ENTITY_IDS[key],
                         "map": key.split(":", 1)[0]}
    return [rows[key] for key in sorted(rows)]


def scripted_fallback_keys(plan: Mapping) -> dict[str, list[str]]:
    """Event file -> swapped logical keys whose initializers the boss build removes.

    Reads both the native-path ``wakeup_fallbacks`` and the boss-only
    ``scripted_fallbacks`` rows; each must name a pinned placement with its
    pinned entity and an actual swap in the same plan.
    """
    swapped = {swap.get("logical_key") for swap in plan.get("swaps", [])}
    by_file: dict[str, set[str]] = {}
    for field in ("wakeup_fallbacks", "scripted_fallbacks"):
        rows = plan.get(field, [])
        if not isinstance(rows, list):
            raise ValueError(f"ordinary plan {field} must be a list")
        for row in rows:
            key = row.get("logical_key") if isinstance(row, Mapping) else None
            if key not in LINES:
                raise ValueError(f"unsupported scripted fallback placement: {key!r}")
            if row.get("entity_id") != ENTITY_IDS[key] or row.get("map") != key.split(":", 1)[0]:
                raise ValueError(f"scripted fallback witness differs for {key}")
            if key not in swapped:
                raise ValueError(f"scripted fallback has no swap witness: {key}")
            by_file.setdefault(event_file(key), set()).add(key)
    return {filename: sorted(keys) for filename, keys in sorted(by_file.items())}


def build_release(event_root: str | Path) -> dict:
    """The boss-pool scripted tranche, verified against the bundled sources."""
    root = Path(event_root)
    sources = {}
    for map_name in CALLEE_BODIES:
        raw = (root / f"{map_name}.emevd.dcx.js").read_bytes()
        verify_source(map_name, raw.decode("utf-8-sig"))
        sources[map_name] = hashlib.sha256(raw).hexdigest()
    releases = {}
    for key in sorted(RELEASED_KEYS):
        map_name = key.split(":", 1)[0]
        releases[key] = {
            "entity_ids": [ENTITY_IDS[key]],
            "physical_copies": 3 if map_name == "m24_01_00_00" else 1,
            "contract_class": "scripted_initializer_fallback",
            "reason": ("boss-pool only: the reviewed boss builder removes this placement's "
                       "pinned model-specific initializers when it swaps"),
            "initialization_event_ids": sorted({_event_id(line) for line in LINES[key]}),
            "removed_initializers": LINES[key],
        }
    return {
        "format": FORMAT,
        "tranche": TRANCHE,
        "releases": releases,
        "scripted_fallback": {
            "applies_in": "reviewed boss pool (build_boss_encounters) only",
            "source_sha256": sources,
            "callee_body_sha256": {map_name: {str(event): digest for event, digest in bodies.items()}
                                   for map_name, bodies in CALLEE_BODIES.items()},
        },
    }
