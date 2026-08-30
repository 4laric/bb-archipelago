#!/usr/bin/env python3
"""Cross-check progression-relevant items against English FMG and mined game data.

The expected acquisition descriptions are curated from bloodborne-wiki.com's Key Items page.
They are validation hints, never evidence for numeric IDs or event flags.
"""
from __future__ import annotations

import argparse
import csv
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


EXPECTED = [
    # EquipParamGoods 4011's Japanese internal name is stale ("key to the old town").
    # English FMG, runtime descriptor, lot 2400450, flag 52400450, and the m24 MSB
    # treasure placement independently agree on Hunter Chief Emblem.
    ("Hunter Chief Emblem", "treasure", "Cathedral Ward"),
    ("Cainhurst Summons", "treasure", "Iosefka's Clinic"),
    ("Iron Door Key", "treasure", "Nightmare of Mensis"),
    ("Lecture Theatre Key", "treasure", "Lecture Building"),
    ("Lunarium Key", "treasure", "Byrgenwerth"),
    # Synthetic AP progression item: the client applies the vanilla memory
    # event flag rather than inserting nonexistent inventory goods.
    ("Forbidden Woods Password", "event_effect", "Grand Cathedral altar"),
    ("Oedon Tomb Key", "boss_reward", "Father Gascoigne"),
    ("Old Hunter Bell", "treasure", "Hunter's Dream"),
    ("Orphanage Key", "enemy_drop", "Upper Cathedral Ward Brainsucker"),
    ("Queenly Flesh", "npc_or_enemy", "Annalise"),
    ("Small Hair Ornament", "treasure", "Abandoned Old Workshop"),
    ("Tonsil Stone", "npc_reward", "Forbidden Woods resident"),
    ("Unopened Summons", "treasure", "Vileblood Queen's Chamber"),
    ("Upper Cathedral Key", "treasure", "Yahar'gul Chapel"),
    ("Astral Clocktower Key", "boss_reward", "Living Failures"),
    ("Balcony Key", "npc_reward", "Adeline"),
    ("Brain Fluid", "enemy_or_npc", "Research Hall / Adeline"),
    ("Celestial Dial", "boss_reward", "Lady Maria"),
    ("Eye of a Blood-drunk Hunter", "treasure", "Hunter's Dream"),
    ("Eye Pendant", "treasure", "Hunter's Nightmare"),
    ("Laurence's Skull", "treasure", "Research Hall"),
    ("Underground Cell Inner Chamber Key", "npc_reward", "Simon"),
    ("Underground Cell Key", "treasure", "Research Hall"),
    ("Blood Gem Workshop Tool", "treasure", "Central Yharnam"),
    ("Rune Workshop Tool", "treasure", "Hemwick Charnel Lane"),
    ("Third Umbilical Cord #1", "boss_reward", "Nightmare of Mensis"),
    ("Third Umbilical Cord #2", "boss_reward", "Nightmare of Mensis"),
    ("Third Umbilical Cord #3", "boss_reward", "Nightmare of Mensis"),
    ("Third Umbilical Cord #4", "quest_reward", "Iosefka/Arianna questlines"),
    ("Cainhurst Badge", "npc_reward", "Annalise"),
    ("Cosmic Eye Watcher Badge", "treasure", "Upper Cathedral Ward"),
    ("Crow Hunter Badge", "npc_or_enemy", "Eileen"),
    ("Old Hunter Badge", "boss_reward", "Gehrman"),
    ("Powder Keg Hunter Badge", "npc_or_enemy", "Djura"),
    ("Radiant Sword Hunter Badge", "treasure", "Healing Church Workshop"),
    ("Saw Hunter Badge", "treasure", "Central Yharnam"),
    ("Spark Hunter Badge", "boss_reward", "Darkbeast Paarl"),
    ("Sword Hunter Badge", "boss_reward", "Cleric Beast"),
    ("Wheel Hunter Badge", "npc_or_enemy", "Alfred"),
    ("Firing Hammer Badge", "enemy_drop", "Bestial Hunter"),
]


def tsv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh, delimiter="\t")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("english_item_names", type=Path)
    ap.add_argument("joined", type=Path)
    ap.add_argument("event_root", type=Path)
    ap.add_argument("output", type=Path)
    ns = ap.parse_args()

    names = {}
    for node in ET.parse(ns.english_item_names).getroot().findall("./entries/text"):
        if node.text and node.text != "%null%":
            names[node.text] = int(node.attrib["id"])

    lots_by_item = defaultdict(set)
    flags_by_item = defaultdict(set)
    for row in tsv(ns.joined / "lot_items.tsv"):
        if row["item_category"] != "4":
            continue
        item_id = int(row["item_id"])
        lots_by_item[item_id].add(row["item_lot_id"])
        if row["generic_acquisition_flag"] not in ("", "0", "-1"):
            flags_by_item[item_id].add(row["generic_acquisition_flag"])

    treasures_by_lot = defaultdict(list)
    for row in tsv(ns.joined / "fixed_treasure_lots.tsv"):
        treasures_by_lot[row["item_lot_id"]].append(row)
    enemies_by_lot = defaultdict(list)
    for row in tsv(ns.joined / "fixed_enemy_drop_sources.tsv"):
        enemies_by_lot[row["item_lot_id"]].append(row)
    scripts_by_lot = defaultdict(set)
    award = re.compile(r"\bAwardItemLot\((\d+)\)")
    event_decl = re.compile(r"^\s*\$Event\((\d+),\s*\w+,\s*function\(([^)]*)\)\s*\{")
    initializer = re.compile(r"\$InitializeEvent\(([^)]*)\)")
    for path in ns.event_root.rglob("*.emevd.dcx.js"):
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        definitions = {}
        dynamic_awards = []
        current = None
        depth = 0
        for line_number, line in enumerate(lines, 1):
            declaration = event_decl.match(line)
            if declaration:
                event_id, raw_params = declaration.groups()
                current = (event_id, [p.strip() for p in raw_params.split(",") if p.strip()])
                definitions[event_id] = current[1]
                depth = line.count("{") - line.count("}")
                continue
            if current:
                for match in re.finditer(r"\bAwardItemLot\(([A-Za-z_]\w*)\)", line):
                    if match.group(1) in current[1]:
                        dynamic_awards.append((current[0], current[1].index(match.group(1)), line_number))
                depth += line.count("{") - line.count("}")
                if depth <= 0:
                    current = None
        calls = defaultdict(list)
        for line_number, line in enumerate(lines, 1):
            for match in award.finditer(line):
                scripts_by_lot[match.group(1)].add(
                    f"{path.relative_to(ns.event_root).as_posix()}:{line_number}")
            for match in initializer.finditer(line):
                args = [a.strip() for a in match.group(1).split(",")]
                if len(args) >= 2 and args[1] in definitions:
                    calls[args[1]].append((line_number, args[2:]))
        for event_id, param_index, award_line in dynamic_awards:
            for call_line, args in calls[event_id]:
                if param_index < len(args) and args[param_index].isdigit():
                    scripts_by_lot[args[param_index]].add(
                        f"{path.relative_to(ns.event_root).as_posix()}:{award_line}"
                        f"<-init:{call_line}")

    rows = []
    for name, expected_kind, expected_source in EXPECTED:
        item_id = names.get(name)
        lots = sorted(lots_by_item.get(item_id, ()), key=int) if item_id is not None else []
        treasures = [r for lot in lots for r in treasures_by_lot.get(lot, ())]
        enemies = [r for lot in lots for r in enemies_by_lot.get(lot, ())]
        scripts = sorted({source for lot in lots for source in scripts_by_lot.get(lot, ())})
        observed = []
        if treasures:
            observed.append("treasure")
        if enemies:
            observed.append("enemy_drop")
        if scripts:
            observed.append("script_award")
        if lots and not observed:
            observed.append("lot_only")
        if item_id is None:
            status = "english_name_missing"
        elif expected_kind == "treasure" and treasures:
            status = "source_type_matches"
        elif expected_kind == "enemy_drop" and (enemies or scripts):
            status = "source_type_matches"
        elif expected_kind in ("npc_or_enemy", "enemy_or_npc") and enemies:
            status = "source_type_compatible"
        elif expected_kind == "treasure" and scripts:
            status = "scripted_treasure_compatible"
        elif expected_kind in ("boss_reward", "npc_reward", "npc_or_enemy", "enemy_or_npc") and scripts:
            status = "script_source_compatible"
        elif expected_kind in ("boss_reward", "npc_reward", "npc_or_enemy", "enemy_or_npc") and lots:
            status = "script_or_quest_review"
        elif not lots:
            status = "no_item_lot_found"
        else:
            status = "source_type_disagrees"
        rows.append({
            "item_name": name, "goods_param_id": "" if item_id is None else item_id,
            "expected_kind": expected_kind, "wiki_source_or_area": expected_source,
            "item_lot_ids": ";".join(lots),
            "acquisition_flags": ";".join(sorted(flags_by_item.get(item_id, ()), key=int)),
            "observed_sources": ";".join(observed),
            "msb_maps": ";".join(sorted({r["map_name"] for r in treasures})),
            "enemy_maps": ";".join(sorted({r["map_name"] for r in enemies})),
            "script_awards": ";".join(scripts),
            "status": status,
        })

    ns.output.parent.mkdir(parents=True, exist_ok=True)
    with ns.output.open("w", encoding="utf-8", newline="") as fh:
        out = csv.DictWriter(fh, rows[0].keys(), delimiter="\t", lineterminator="\n")
        out.writeheader()
        out.writerows(rows)
    for status in sorted({r["status"] for r in rows}):
        print(f"{status}: {sum(r['status'] == status for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
