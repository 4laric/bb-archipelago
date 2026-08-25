#!/usr/bin/env python3
"""Audit what the committed corpus actually says about each slice-3 flag.

Issue #158: slice 3 shipped with no live witness in Cathedral Ward or Old
Yharnam, so every detection flag there is a static claim. Before asking the
owner for a game session, this settles which half of the claim the repository
can already answer and which half only a session can.

For each slice-3 detection flag it records, from named sources only:

* ``writer`` -- the instruction that sets the flag. An acquisition flag is
  written by the engine when its ``ItemLotParam`` row is awarded, and the
  citation is that row's ``getItemFlagId``. A boss/interaction flag whose ID is
  an event ID has *no* ``SetEventFlag`` anywhere in the corpus: the write is the
  engine's own "an event that reaches ``End`` turns on the flag with its ID"
  rule. That rule is not an instruction, so it cannot be cited, and every such
  flag is reported ``corpus_gap: implicit_write`` -- including the two slice-1
  boss flags this repository has shipped since the first slice. The gap is
  uniform, not new to slice 3, which is the point of carrying the controls.
* ``self_read`` -- whether the owning event tests its own ID as a flag
  (``ThisEvent()``). This is the strongest in-corpus corroboration that the ID
  is a persistent flag rather than only an event number.
* ``readers`` -- every other file that reads the flag.
* ``off_writers`` -- any instruction that can turn it back off. Monotonicity is
  a requirement of ``docs/EVENT-FLAG-RESEARCH.md``, and a flag cleared by a
  ``BatchSetEventFlags(..., OFF)`` range would be a detection defect, so the
  ranges are resolved through their initializer arguments rather than skipped
  when the operands are event parameters.
* ``placed_lots`` -- for a pickup, how many ItemLotParam rows carrying the flag
  are actually placed by an MSB treasure. More than one placed lot means two
  physical checks share one flag.

Nothing here is a runtime observation. Per ``CONTRIBUTING.md`` every row's
evidence label stays ``inferred``; ``corpus_status`` says only whether the
static claim is complete or has a hole in it.

    python tools/audit_slice3_witnesses.py            # rewrite the committed audit
    python tools/audit_slice3_witnesses.py --check    # fail if it would change
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.bb_inputs import read_blob, read_prefix  # noqa: E402
from worlds.bloodborne.fixed_locations import FIXED_LOCATIONS  # noqa: E402
from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS  # noqa: E402

BUNDLE = REPO / "research" / "bb_inputs.db"
AUDIT_TSV = REPO / "research" / "validation" / "slice3_witness_audit.tsv"
AUDIT_JSON = REPO / "research" / "validation" / "slice3_witness_summary.json"

SLICE3_REGIONS = ("Cathedral Ward", "Old Yharnam")

# The six scripted checks of slice 3, plus the two slice-1 boss flags as
# controls. A control row is not decoration: if the slice-1 flags come back
# with a different corpus status than the slice-3 ones, slice 3 is worse than
# what already shipped, and if they come back the same it is not.
SCRIPTED = (
    # key, flag, owning map, role. The boss entity is *not* listed: it is read
    # out of the event's own HandleBossDefeat operand, and its NpcParam row out
    # of the MSB placement of that entity, so no ID here is typed by hand.
    ("boss_cleric_beast", 12411700, "m24_01_00_00", "control_slice1"),
    ("boss_father_gascoigne", 12411800, "m24_01_00_00", "control_slice1"),
    ("boss_blood_starved_beast", 12301800, "m23_00_00_00", "slice3_goal"),
    ("boss_vicar_amelia", 12401800, "m24_00_00_00", "slice3"),
    ("interaction_laurences_skull", 12401803, "m24_00_00_00", "slice3"),
    ("treasure_radiant_sword_hunter_badge", 52400480, "m24_00_00_00", "slice3"),
)

HANDLE_BOSS = re.compile(r"HandleBossDefeat\(\s*(\d+)\s*\)")

EVENT_START = re.compile(r"\$Event\((\d+),\s*\w+,\s*function\(([^)]*)\)")
INIT = re.compile(r"\$InitializeEvent\(\s*\d+,\s*(\d+)((?:,\s*[^),]+)*)\)")
BATCH = re.compile(r"BatchSetEventFlags\(\s*([^,]+?),\s*([^,]+?),\s*(ON|OFF)\s*\)")
SET_FLAG = re.compile(r"SetEventFlag\(\s*(\d+),\s*(ON|OFF)\s*\)")


def load_events() -> dict[str, list[str]]:
    return {
        path.split("/")[-1]: blob.decode("utf-8", "replace").splitlines()
        for path, blob in read_prefix(BUNDLE, "event/").items()
    }


def event_bodies(lines: list[str]) -> list[tuple[int, list[str], int, int]]:
    """(event_id, parameter names, first line, last line) for each $Event."""
    found = []
    for index, line in enumerate(lines):
        match = EVENT_START.search(line)
        if match:
            if found:
                found[-1][3] = index
            found.append([int(match.group(1)),
                          [p.strip() for p in match.group(2).split(",") if p.strip()],
                          index + 1, len(lines)])
    return [(a, b, c, d) for a, b, c, d in found]


def initializer_arguments(events: dict[str, list[str]]) -> dict[int, set[tuple[str, ...]]]:
    args: dict[int, set[tuple[str, ...]]] = defaultdict(set)
    for lines in events.values():
        for line in lines:
            for match in INIT.finditer(line):
                payload = [a.strip() for a in match.group(2).split(",") if a.strip()]
                args[int(match.group(1))].add(tuple(payload))
    return args


def off_ranges(events: dict[str, list[str]]) -> list[tuple[str, int, str]]:
    """Every OFF range in the corpus, with parameter operands resolved.

    An unresolved operand is emitted with bounds ``None`` so that it is counted
    as a hole rather than silently dropped -- "the tool could not read it" and
    "the range does not reach the flag" are different answers.
    """
    args = initializer_arguments(events)
    resolved: list[tuple[str, int, str]] = []
    for name, lines in events.items():
        bodies = event_bodies(lines)
        for index, line in enumerate(lines):
            for match in BATCH.finditer(line):
                low, high, state = (match.group(1).strip(), match.group(2).strip(),
                                    match.group(3))
                if state != "OFF":
                    continue
                if low.isdigit() and high.isdigit():
                    resolved.append((name, index + 1, f"{low}:{high}"))
                    continue
                owner = next((b for b in bodies if b[2] <= index + 1 <= b[3]), None)
                if owner is None:
                    resolved.append((name, index + 1, "unresolved"))
                    continue
                event_id, params = owner[0], owner[1]
                calls = args.get(event_id) or set()
                if not calls or low not in params or high not in params:
                    resolved.append((name, index + 1, "unresolved"))
                    continue
                for call in sorted(calls):
                    try:
                        resolved.append((name, index + 1,
                                         f"{call[params.index(low)]}:{call[params.index(high)]}"))
                    except IndexError:
                        resolved.append((name, index + 1, "unresolved"))
    return resolved


def flag_reaches(flag: int, ranges: list[tuple[str, int, str]]) -> list[str]:
    hits = []
    for name, line, bounds in ranges:
        if bounds == "unresolved":
            hits.append(f"{name}:{line}:unresolved")
            continue
        low, high = (int(x) for x in bounds.split(":"))
        if low <= flag <= high:
            hits.append(f"{name}:{line}:{bounds}")
    return hits


def read_csv(name: str) -> list[dict[str, str]]:
    text = read_blob(BUNDLE, name).decode("utf-8", "replace")
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def placed_lots() -> dict[str, set[str]]:
    """item_lot_id -> the MSB treasure maps that place it."""
    placed: dict[str, set[str]] = defaultdict(set)
    for row in read_csv("mined/msb_treasures.tsv"):
        for field in ("item_lot_1", "item_lot_2", "item_lot_3"):
            lot = row.get(field)
            if lot and lot not in ("-1", "0"):
                placed[lot].add(row["map_name"])
    return placed


def lots_by_flag() -> dict[str, set[str]]:
    by_flag: dict[str, set[str]] = defaultdict(set)
    with (REPO / "research" / "joined" / "lot_items.tsv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            for flag in (row["all_acquisition_flags"] or "").split(";"):
                if flag.strip():
                    by_flag[flag.strip()].add(row["item_lot_id"])
    return by_flag


def npc_names() -> dict[str, str]:
    text = read_blob(BUNDLE, "params/NpcParam.csv").decode("utf-8", "replace")
    reader = csv.reader(io.StringIO(text))
    next(reader)
    return {row[0]: row[1] for row in reader if row}


def enemy_placements() -> dict[str, set[tuple[str, str]]]:
    placements: dict[str, set[tuple[str, str]]] = defaultdict(set)
    text = read_blob(BUNDLE, "mined/msb_enemies.tsv").decode("utf-8", "replace")
    for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
        entity = row.get("part_entity_id")
        if entity and entity != "-1":
            placements[entity].add((row["map_name"], row.get("npc_param_id", "")))
    return placements


def audit() -> tuple[list[dict[str, str]], dict[str, object]]:
    events = load_events()
    ranges = off_ranges(events)
    by_flag = lots_by_flag()
    placed = placed_lots()
    names = npc_names()

    explicit: dict[int, list[str]] = defaultdict(list)
    readers: dict[int, set[str]] = defaultdict(set)
    for name, lines in events.items():
        for index, line in enumerate(lines):
            for match in SET_FLAG.finditer(line):
                explicit[int(match.group(1))].append(f"{name}:{index + 1}:{match.group(2)}")
    scanned_lines = sum(len(v) for v in events.values())

    interesting = {flag for _, flag, _, _ in SCRIPTED}
    interesting |= {int(loc.event_flag) for loc in FIXED_LOCATIONS
                    if loc.region in SLICE3_REGIONS and loc.event_flag}
    pattern = {flag: re.compile(rf"\b{flag}\b") for flag in interesting}
    for name, lines in events.items():
        for line in lines:
            code = line.split("//", 1)[0]
            for flag, rx in pattern.items():
                if rx.search(code):
                    readers[flag].add(name)

    rows: list[dict[str, str]] = []

    placements_by_entity = enemy_placements()

    for key, flag, owner_map, role in SCRIPTED:
        owner_file = f"{owner_map}.emevd.dcx.js"
        lines = events[owner_file]
        body = next((b for b in event_bodies(lines) if b[0] == flag), None)
        self_read = ""
        writer = ""
        if body is not None:
            block = lines[body[2] - 1:body[3]]
            self_read = "yes" if any("ThisEvent()" in line for line in block) else "no"
            writer = f"{owner_file}:{body[2]} $Event({flag}) end"
            writer_kind = "event_end_implicit"
        else:
            # Not an event ID: an acquisition flag written by its ItemLotParam row.
            lot_rows = sorted(by_flag.get(str(flag), ()))
            writer = f"ItemLotParam getItemFlagId on lot {','.join(lot_rows)}"
            writer_kind = "item_lot_acquisition"
        offs = flag_reaches(flag, ranges)
        gaps = []
        if writer_kind == "event_end_implicit":
            gaps.append("implicit_write")
        if offs:
            gaps.append("off_reachable")
        # A boss can have more than one HandleBossDefeat operand -- Gascoigne's
        # two phases are two entities -- so every operand is resolved rather
        # than the row being abandoned as ambiguous.
        entity_note = ""
        entities: list[str] = []
        if body is not None:
            block = lines[body[2] - 1:body[3]]
            entities = sorted({m.group(1) for line in block for m in HANDLE_BOSS.finditer(line)})
        notes = []
        for entity in entities:
            placements = placements_by_entity.get(entity, set())
            maps = sorted({m for m, _ in placements})
            npcs = sorted({n for _, n in placements if n})
            note = f"HandleBossDefeat({entity}) placed in {';'.join(maps) or 'NOT PLACED'}"
            if owner_map not in maps:
                gaps.append("entity_not_placed_in_owning_map")
            for npc in npcs:
                note += f"; NpcParam {npc} = {names.get(npc, 'ABSENT')}"
                if npc not in names:
                    gaps.append("npc_param_absent")
            notes.append(note)
        entity_note = " | ".join(notes)
        rows.append({
            "key": key,
            "flag": str(flag),
            "kind": "scripted",
            "role": role,
            "writer": writer,
            "writer_kind": writer_kind,
            "self_read": self_read,
            "readers": ";".join(sorted(readers.get(flag, ()))),
            "explicit_set_sites": ";".join(explicit.get(flag, ())),
            "off_writers": ";".join(offs),
            "placed_lots": "",
            "corroboration": entity_note,
            "corpus_status": "corpus_gap:" + ",".join(gaps) if gaps else "corpus_complete",
            "evidence_label": "inferred",
        })

    for loc in FIXED_LOCATIONS:
        if loc.region not in SLICE3_REGIONS or not loc.event_flag:
            continue
        flag = int(loc.event_flag)
        lots = sorted(by_flag.get(str(flag), ()))
        placed_here = sorted(lot for lot in lots if lot in placed)
        offs = flag_reaches(flag, ranges)
        gaps = []
        if str(loc.item_lot_id) not in lots:
            gaps.append("declared_lot_lacks_flag")
        if len(placed_here) != 1:
            gaps.append(f"placed_lots={len(placed_here)}")
        if offs:
            gaps.append("off_reachable")
        if explicit.get(flag):
            gaps.append("emevd_writes_flag")
        rows.append({
            "key": loc.key,
            "flag": str(flag),
            "kind": "pickup",
            "role": loc.region.lower().replace(" ", "_"),
            "writer": f"ItemLotParam getItemFlagId on lot {loc.item_lot_id}",
            "writer_kind": "item_lot_acquisition",
            "self_read": "",
            "readers": ";".join(sorted(readers.get(flag, ()))),
            "explicit_set_sites": ";".join(explicit.get(flag, ())),
            "off_writers": ";".join(offs),
            "placed_lots": ";".join(placed_here),
            "corroboration": f"same-flag lots {','.join(lots)}" if len(lots) > 1 else "",
            "corpus_status": "corpus_gap:" + ",".join(gaps) if gaps else "corpus_complete",
            "evidence_label": "inferred",
        })

    summary = {
        "scanned_event_files": len(events),
        "scanned_event_lines": scanned_lines,
        "resolved_off_ranges": len(ranges),
        "unresolved_off_ranges": sum(1 for _, _, b in ranges if b == "unresolved"),
        "audited_rows": len(rows),
        "scripted_rows": sum(1 for r in rows if r["kind"] == "scripted"),
        "pickup_rows": sum(1 for r in rows if r["kind"] == "pickup"),
        "corpus_complete": sum(1 for r in rows if r["corpus_status"] == "corpus_complete"),
        "corpus_gap": sum(1 for r in rows if r["corpus_status"] != "corpus_complete"),
        "gap_reasons": sorted({r["corpus_status"] for r in rows
                               if r["corpus_status"] != "corpus_complete"}),
        "observed_live": 0,
    }
    return rows, summary


FIELDS = ("key", "flag", "kind", "role", "writer", "writer_kind", "self_read", "readers",
          "explicit_set_sites", "off_writers", "placed_lots", "corroboration",
          "corpus_status", "evidence_label")


def render(rows: list[dict[str, str]]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="fail if the committed audit is not what the corpus says now")
    options = parser.parse_args(argv)
    rows, summary = audit()
    tsv = render(rows)
    js = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    if options.check:
        stale = []
        if not AUDIT_TSV.exists() or AUDIT_TSV.read_text(encoding="utf-8") != tsv:
            stale.append(str(AUDIT_TSV))
        if not AUDIT_JSON.exists() or AUDIT_JSON.read_text(encoding="utf-8") != js:
            stale.append(str(AUDIT_JSON))
        if stale:
            print("stale, rerun tools/audit_slice3_witnesses.py: " + ", ".join(stale))
            return 1
        print(f"audit is current: {summary['audited_rows']} rows, "
              f"{summary['corpus_gap']} with a corpus gap")
        return 0
    AUDIT_TSV.write_text(tsv, encoding="utf-8")
    AUDIT_JSON.write_text(js, encoding="utf-8")
    print(f"wrote {AUDIT_TSV} ({summary['audited_rows']} rows) and {AUDIT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
