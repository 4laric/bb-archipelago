#!/usr/bin/env python3
"""Extract literal Bloodborne EMEVD flag references and join them to fixed treasures."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


CALL = re.compile(r"\b(SetEventFlag|EventFlag|ObjActEventFlag|EventFlagState)\s*\(([^)]*)\)")
EVENT = re.compile(r"^\s*\$Event\((\d+),\s*\w+,\s*function\(([^)]*)\)\s*\{")
INITIALIZE = re.compile(r"\$InitializeEvent\(([^)]*)\)")
INTEGER = re.compile(r"^-?\d+$")


def read_tsv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh, delimiter="\t")


def write_tsv(path: Path, fields: list[str], rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        out = csv.DictWriter(fh, fields, delimiter="\t", lineterminator="\n")
        out.writeheader()
        out.writerows(rows)


def literal_flag(operation: str, arguments: str) -> str | None:
    args = [arg.strip() for arg in arguments.split(",")]
    index = 2 if operation == "EventFlagState" else 0
    if len(args) <= index or not INTEGER.fullmatch(args[index]):
        return None
    value = int(args[index])
    return str(value) if value >= 0 else None


def flag_expression(operation: str, arguments: str) -> str | None:
    args = [arg.strip() for arg in arguments.split(",")]
    index = 2 if operation == "EventFlagState" else 0
    return args[index] if len(args) > index else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_root", type=Path)
    parser.add_argument("fixed_treasure_lots", type=Path)
    parser.add_argument("output", type=Path)
    ns = parser.parse_args()

    scripts = {path: path.read_text(encoding="utf-8-sig").splitlines()
               for path in sorted(ns.event_root.rglob("*.emevd.dcx.js"))}
    definitions = {}
    global_definitions = defaultdict(list)
    dynamic_uses = []
    for path, lines in scripts.items():
        current = None
        depth = 0
        for line_number, line in enumerate(lines, 1):
            declaration = EVENT.match(line)
            if declaration:
                event_id, raw_params = declaration.groups()
                params = [p.strip() for p in raw_params.split(",") if p.strip()]
                current = (event_id, params)
                definitions[(path, event_id)] = params
                global_definitions[event_id].append((path, params))
                depth = line.count("{") - line.count("}")
                continue
            if current:
                event_id, params = current
                for call in CALL.finditer(line):
                    operation, arguments = call.groups()
                    expression = flag_expression(operation, arguments)
                    if expression in params:
                        dynamic_uses.append((path, event_id, params.index(expression), expression,
                                             operation, line_number, line.strip()))
                depth += line.count("{") - line.count("}")
                if depth <= 0:
                    current = None

    invocations = defaultdict(list)
    unresolved_initializers = 0
    for caller_path, lines in scripts.items():
        # Fixed campaign/DLC scripts are top-level. Nested m29 callers are generated Chalice
        # variants and multiply identical parameter flows hundreds of thousands of times.
        if caller_path.parent != ns.event_root:
            continue
        for line_number, line in enumerate(lines, 1):
            for match in INITIALIZE.finditer(line):
                args = [arg.strip() for arg in match.group(1).split(",")]
                if len(args) < 2 or not INTEGER.fullmatch(args[1]):
                    unresolved_initializers += 1
                    continue
                event_id = args[1]
                target = None
                if (caller_path, event_id) in definitions:
                    target = caller_path
                elif len(global_definitions[event_id]) == 1:
                    target = global_definitions[event_id][0][0]
                if target is None:
                    unresolved_initializers += 1
                    continue
                invocations[(target, event_id)].append((caller_path, line_number, args[2:]))

    references = []
    dynamic_calls = Counter()
    for path, lines in scripts.items():
        rel = path.relative_to(ns.event_root).as_posix()
        event_id = ""
        for line_number, line in enumerate(lines, 1):
            declaration = EVENT.match(line)
            if declaration:
                event_id = declaration.group(1)
            for call in CALL.finditer(line):
                operation, arguments = call.groups()
                flag = literal_flag(operation, arguments)
                if flag is None:
                    dynamic_calls[operation] += 1
                    continue
                references.append({
                    "flag": flag,
                    "operation": operation,
                    "event_file": rel,
                    "event_id": event_id,
                    "line": line_number,
                    "source": line.strip(),
                    "resolution": "literal",
                    "initializer_file": "",
                    "initializer_line": "",
                })
    resolved_dynamic = 0
    unresolved_dynamic = 0
    for path, event_id, param_index, expression, operation, line_number, source in dynamic_uses:
        calls = invocations.get((path, event_id), [])
        any_resolved = False
        for caller_path, caller_line, args in calls:
            if param_index >= len(args) or not INTEGER.fullmatch(args[param_index]):
                continue
            value = int(args[param_index])
            if value < 0:
                continue
            any_resolved = True
            resolved_dynamic += 1
            references.append({
                "flag": str(value), "operation": operation,
                "event_file": path.relative_to(ns.event_root).as_posix(),
                "event_id": event_id, "line": line_number, "source": source,
                "resolution": f"parameter:{expression}",
                "initializer_file": caller_path.relative_to(ns.event_root).as_posix(),
                "initializer_line": caller_line,
            })
        if not any_resolved:
            unresolved_dynamic += 1
    references.sort(key=lambda r: (int(r["flag"]), r["event_file"], r["line"], r["operation"]))
    write_tsv(ns.output / "event_flag_references.tsv",
              ["flag", "operation", "event_file", "event_id", "line", "source", "resolution",
               "initializer_file", "initializer_line"], references)

    refs_by_flag = defaultdict(list)
    for ref in references:
        refs_by_flag[ref["flag"]].append(ref)

    locations = []
    matched_flags = set()
    acquisition_flags = set()
    for treasure in read_tsv(ns.fixed_treasure_lots):
        flags = [f for f in re.split(r"[;|, ]+", treasure["acquisition_flags"]) if f]
        for flag in flags:
            acquisition_flags.add(flag)
            matches = refs_by_flag.get(flag, [])
            if matches:
                matched_flags.add(flag)
            base = dict(treasure)
            base["acquisition_flag"] = flag
            if not matches:
                locations.append({**base, "operation": "", "event_file": "", "script_event_id": "",
                                  "line": "", "source": "", "resolution": "",
                                  "initializer_file": "", "initializer_line": ""})
            else:
                for ref in matches:
                    locations.append({**base, "operation": ref["operation"],
                                      "event_file": ref["event_file"],
                                      "script_event_id": ref["event_id"], "line": ref["line"],
                                      "source": ref["source"], "resolution": ref["resolution"],
                                      "initializer_file": ref["initializer_file"],
                                      "initializer_line": ref["initializer_line"]})
    location_fields = list(locations[0])
    write_tsv(ns.output / "fixed_location_event_refs.tsv", location_fields, locations)

    summary = {
        "event_script_files": len(list(ns.event_root.rglob("*.emevd.dcx.js"))),
        "total_resolved_flag_references": len(references),
        "literal_flag_references": sum(r["resolution"] == "literal" for r in references),
        "parameter_resolved_flag_references": sum(r["resolution"] != "literal" for r in references),
        "distinct_resolved_flags": len(refs_by_flag),
        "dynamic_flag_calls_seen_by_operation": dict(sorted(dynamic_calls.items())),
        "parameterized_flag_uses": len(dynamic_uses),
        "resolved_parameterized_references": resolved_dynamic,
        "unresolved_parameterized_uses": unresolved_dynamic,
        "unresolved_or_ambiguous_initializers": unresolved_initializers,
        "fixed_acquisition_flags": len(acquisition_flags),
        "fixed_acquisition_flags_referenced_by_scripts": len(matched_flags),
        "fixed_acquisition_flags_not_referenced_by_scripts": len(acquisition_flags - matched_flags),
    }
    (ns.output / "event_join_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
