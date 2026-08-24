#!/usr/bin/env python3
"""Build a policy-neutral census of enemizer entity-number uses in EMEVD.

This deliberately does not decide whether a slot is safe to randomize.  It
reproduces the current lexical match, records the syntactic operation families
around each match, and exposes namespace collisions for later human review.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import tempfile
import zlib
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .bb_enemizer.inventory import load_slots
except ImportError:  # Direct script execution adds tools/ rather than the repository root.
    from bb_enemizer.inventory import load_slots


INTEGER = re.compile(r"(?<!\d)-?\d+(?!\d)")
CALL = re.compile(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\(([^()]*)\)")
EVENT = re.compile(r"^\s*\$Event\((\d+),\s*\w+,\s*function\(([^)]*)\)\s*\{")
EVENT_REASON = "entity ID referenced by area EMEVD"


def read_tsv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle, delimiter="\t")


def operation_family(operation: str) -> str:
    operation = operation.removeprefix("resolved/")
    lowered = operation.lower()
    if operation.endswith(":event_id"):
        return "event_id_collision"
    if operation.endswith(":argument"):
        return "event_argument"
    if "flag" in lowered:
        return "flag_operand"
    if "itemlot" in lowered or "item_lot" in lowered:
        return "item_lot_operand"
    if any(word in lowered for word in (
        "character", "hpratio", "boss", "miniboss", "spEffect".lower(),
        "ai", "dead", "healthbar", "kill", "backread", "invincibility",
    )):
        return "character_operation"
    if any(word in lowered for word in ("region", "area", "radius", "distance")):
        return "spatial_operation"
    if any(word in lowered for word in ("object", "objact", "treasure")):
        return "object_operation"
    if any(word in lowered for word in ("animation", "sound", "sfx", "vfx", "camera", "cutscene")):
        return "presentation_operation"
    return "other_operation"


def has_character_operation(usage_classes: str) -> bool:
    """True when a slot's folded usage-class string records a character operation.

    This is the sharper protection predicate proposed in
    ``docs/ENEMIZER-COVERAGE.md``: an entity id is a genuine scripted actor only
    when it is the operand of a ``SetCharacter*`` / AI / boss / HP / SpEffect
    operation, not merely a number that appears somewhere in the area EMEVD.
    It reads the same ``usage_classes`` column this census already commits, so a
    consumer never has to re-parse EMEVD to reproduce the classification.
    """
    return any(entry.split(":", 1)[0] == "character_operation"
               for entry in usage_classes.split(";") if entry)


def event_definitions(lines: list[str]) -> dict[int, tuple[list[str], list[str]]]:
    definitions = {}
    current = None
    depth = 0
    body = []
    for line in lines:
        declaration = EVENT.match(line)
        if declaration:
            event_id, raw_params = declaration.groups()
            current = (int(event_id), [value.strip() for value in raw_params.split(",") if value.strip()])
            body = []
            depth = line.count("{") - line.count("}")
            continue
        if current:
            body.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                definitions[current[0]] = (current[1], body[:-1])
                current = None
    return definitions


def parameter_uses(lines: list[str], parameter: str) -> list[str]:
    uses = []
    for line in lines:
        code = line.partition("//")[0]
        for match in CALL.finditer(code):
            arguments = [value.strip() for value in match.group(2).split(",")]
            if parameter in arguments:
                uses.append("resolved/" + match.group(1))
    return uses


def line_uses(line: str, entity_id: int) -> tuple[list[str], bool, bool]:
    """Return matching operations, whether code matched, and whether a comment matched."""
    code, marker, comment = line.partition("//")
    token = str(entity_id)
    comment_match = bool(marker and re.search(rf"(?<!\d){token}(?!\d)", comment))
    code_match = bool(re.search(rf"(?<!\d){token}(?!\d)", code))
    operations = []
    if code_match:
        for match in CALL.finditer(code):
            operation = match.group(1)
            arguments = [value.strip() for value in match.group(2).split(",")]
            matching_indexes = [index for index, value in enumerate(arguments)
                                if value == str(entity_id)]
            for index in matching_indexes:
                if operation == "$InitializeEvent":
                    operations.append(f"{operation}:{'event_id' if index == 1 else 'argument'}")
                elif operation == "$Event":
                    operations.append(f"{operation}:{'event_id' if index == 0 else 'argument'}")
                else:
                    operations.append(operation)
    return operations, code_match, comment_match


def namespace_values(lot_items: Path) -> tuple[set[int], set[int]]:
    lots, flags = set(), set()
    for row in read_tsv(lot_items):
        lots.add(int(row["item_lot_id"]))
        flags.update(int(value) for value in row["all_acquisition_flags"].split(";") if value)
    return lots, flags


def build_rows(inventory: Path, policy_path: Path, event_root: Path, lot_items: Path) -> list[dict]:
    slots = load_slots(inventory)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    protected = [slot for slot in slots if policy.get(slot.logical_key, {}).get("reason") == EVENT_REASON]
    lots, flags = namespace_values(lot_items)

    scripts_by_area: dict[str, list[tuple[str, list[str], dict]]] = defaultdict(list)
    global_definitions: dict[int, list[tuple[str, list[str], list[str]]]] = defaultdict(list)
    for path in sorted(event_root.glob("m*.emevd.dcx.js")):
        area = path.name.split("_", 1)[0]
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        definitions = event_definitions(lines)
        scripts_by_area[area].append((path.name, lines, definitions))
        for event_id, (parameters, body) in definitions.items():
            global_definitions[event_id].append((path.name, parameters, body))

    result = []
    for slot in protected:
        area = slot.map_name.split("_", 1)[0]
        operations, sources = Counter(), []
        code_lines = comment_lines = lexical_without_operation = 0
        for file_name, lines, definitions in scripts_by_area.get(area, ()):
            for line_number, line in enumerate(lines, 1):
                found, code_match, comment_match = line_uses(line, slot.entity_id)
                if not code_match and not comment_match:
                    continue
                code_lines += int(code_match)
                comment_lines += int(comment_match)
                lexical_without_operation += int(code_match and not found)
                operations.update(found)
                if "$InitializeEvent:argument" in found:
                    for match in CALL.finditer(line.partition("//")[0]):
                        if match.group(1) != "$InitializeEvent":
                            continue
                        arguments = [value.strip() for value in match.group(2).split(",")]
                        if len(arguments) < 3 or not arguments[1].isdigit():
                            continue
                        event_id = int(arguments[1])
                        target = None
                        if event_id in definitions:
                            target = definitions[event_id]
                        elif len(global_definitions[event_id]) == 1:
                            _, parameters, body = global_definitions[event_id][0]
                            target = (parameters, body)
                        if target is None:
                            continue
                        parameters, body = target
                        for argument_index, value in enumerate(arguments[2:]):
                            if value == str(slot.entity_id) and argument_index < len(parameters):
                                operations.update(parameter_uses(body, parameters[argument_index]))
                sources.append(f"{file_name}:{line_number}")
        families = Counter()
        for operation, count in operations.items():
            families[operation_family(operation)] += count
        if lexical_without_operation:
            families["code_without_parsed_operation"] += lexical_without_operation
        if comment_lines:
            families["comment_text"] += comment_lines
        result.append({
            "map_name": slot.map_name,
            "part_name": slot.part_name,
            "logical_key": slot.logical_key,
            "entity_id": slot.entity_id,
            "code_lines": code_lines,
            "comment_lines": comment_lines,
            "parsed_operation_uses": sum(operations.values()),
            "operations": ";".join(f"{name}:{count}" for name, count in sorted(operations.items())),
            "usage_classes": ";".join(f"{name}:{count}" for name, count in sorted(families.items())),
            "collides_item_lot_id": slot.entity_id in lots,
            "collides_acquisition_flag": slot.entity_id in flags,
            "source_lines": ";".join(sources),
        })
    return result


def materialize_bundle(bundle: Path, target: Path) -> tuple[Path, Path]:
    """Extract only the census inputs, not the bundle's full 146 MB payload."""
    if not bundle.is_file():
        raise SystemExit(f"inputs bundle not found: {bundle}")
    database = sqlite3.connect(bundle)
    wanted = database.execute(
        "SELECT path, blob FROM files WHERE path = 'mined/msb_enemies.tsv' OR path LIKE 'event/%.emevd.dcx.js'"
    ).fetchall()
    database.close()
    inventory = target / "mined/msb_enemies.tsv"
    events = target / "event"
    for relative, blob in wanted:
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(zlib.decompress(blob))
    if not inventory.is_file() or not any(events.glob("m*.emevd.dcx.js")):
        raise SystemExit("inputs bundle lacks mined/msb_enemies.tsv or fixed-map EMEVD scripts")
    return inventory, events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path("research/bb_inputs.db"))
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--slot-policy", type=Path, default=Path("research/enemizer/slot_policy.json"))
    parser.add_argument("--events", type=Path)
    parser.add_argument("--lot-items", type=Path, default=Path("research/joined/lot_items.tsv"))
    parser.add_argument("--output", type=Path, default=Path("research/enemizer/emevd_entity_usage.tsv"))
    parser.add_argument("--summary", type=Path, default=Path("research/enemizer/emevd_entity_usage_summary.json"))
    args = parser.parse_args(argv)
    if bool(args.inventory) != bool(args.events):
        parser.error("--inventory and --events must be supplied together")
    temporary = tempfile.TemporaryDirectory() if not args.inventory else None
    try:
        inventory, events = ((args.inventory, args.events) if args.inventory else
                             materialize_bundle(args.bundle, Path(temporary.name)))
        result = build_rows(inventory, args.slot_policy, events, args.lot_items)
    finally:
        if temporary:
            temporary.cleanup()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(result)
    classes, operations, slots_by_class = Counter(), Counter(), Counter()
    for row in result:
        for value in row["usage_classes"].split(";"):
            if value:
                name, count = value.rsplit(":", 1); classes[name] += int(count); slots_by_class[name] += 1
        for value in row["operations"].split(";"):
            if value:
                name, count = value.rsplit(":", 1); operations[name] += int(count)
    summary = {
        "format": "bb-emevd-entity-usage-census-v1",
        "policy_changed": False,
        "physical_slots": len(result),
        "slots_with_parsed_operations": sum(bool(row["parsed_operation_uses"]) for row in result),
        "slots_with_only_unparsed_code_or_comments": sum(not row["parsed_operation_uses"] for row in result),
        "slots_colliding_with_item_lot_ids": sum(row["collides_item_lot_id"] for row in result),
        "slots_colliding_with_acquisition_flags": sum(row["collides_acquisition_flag"] for row in result),
        "usage_class_occurrences": dict(sorted(classes.items())),
        "slots_by_usage_class": dict(sorted(slots_by_class.items())),
        "slots_without_character_operations": sum(
            "character_operation:" not in row["usage_classes"] for row in result
        ),
        "item_lot_collisions_without_character_operations": sum(
            row["collides_item_lot_id"] and "character_operation:" not in row["usage_classes"]
            for row in result
        ),
        "slots_with_only_event_id_collisions": sum(
            row["usage_classes"].split(":", 1)[0] == "event_id_collision"
            and ";" not in row["usage_classes"] for row in result
        ),
        "operation_occurrences": dict(operations.most_common()),
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
