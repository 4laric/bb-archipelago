#!/usr/bin/env python3
"""
dump_options_metadata.py -- extract the Bloodborne apworld's option surface to JSON.

`site/wizard.html` renders ENTIRELY from `site/options-metadata.json`, so this tool is the
single source of truth for "what options exist and what they do". Port of er-archipelago's
`tools/dump_options_metadata.py`, with one deliberate difference:

WHY THIS AST-PARSES INSTEAD OF IMPORTING THE WORLD
--------------------------------------------------
er-archipelago builds its option dataclass at import time (`make_dataclass` over a registry),
so nothing short of importing a real Archipelago can tell you what the surface is. Bloodborne's
surface is STATIC: `BloodborneOptions` in `worlds/bloodborne/__init__.py` is a literal dataclass
whose fields name literal `Toggle` / `Choice` / `Range` subclasses declared in the same file.
Parsing it needs no Archipelago checkout, which is what lets `--check` run as an ordinary unit
test and in a CI job that installs nothing. The gate against drift is that this file and the
dataclass are the same file: a renamed option moves both at once, and `--check` byte-compares.

The classes live inside an `else:` branch guarded by `try: from Options import ...`, because the
world is importable without Archipelago for the research tools. The walk below is therefore
recursive over the module body rather than a scan of top-level statements.

Emitted per option: yaml key (canonical dataclass order), class name, kind
(toggle/choice/range), display_name, docstring verbatim, default, choice values, range bounds.

Usage:
    python tools/dump_options_metadata.py            # write site/options-metadata.json
    python tools/dump_options_metadata.py --check    # exit 1 if it is stale (CI drift gate)
"""
import argparse
import ast
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORLD = os.path.join(ROOT, "worlds", "bloodborne", "__init__.py")
ARCHIPELAGO_JSON = os.path.join(ROOT, "worlds", "bloodborne", "archipelago.json")
EXAMPLES = os.path.join(ROOT, "examples")
OUT_JSON = os.path.join(ROOT, "site", "options-metadata.json")

GAME = "Bloodborne"

# ---------------------------------------------------------------------------
# THE WIZARD'S TABS. Presentation only: `field_order` is what buildYaml writes, so regrouping
# can never reorder or change an emitted yaml. Every visible key must appear in exactly one
# group -- enforced below, so a new option cannot land in the dataclass and vanish from the page.
# ---------------------------------------------------------------------------
GROUPS = [
    ("Goal", ["goal"]),
    ("Seed size", [
        "include_dlc", "include_dlc_gear", "one_time_enemy_checks",
        "randomize_enemy_drops", "randomize_shops",
    ]),
    ("Items", [
        "full_item_pool", "uncanny_weapons", "randomize_armor",
        "randomize_starting_weapons", "remove_weapon_requirements",
        "consumable_quantity_bonus",
    ]),
    ("Routing", [
        "alternate_hypogean_gaol_routes", "hemwick_access_gate",
        "questlines_hold_progression",
    ]),
    ("Client", [
        "auto_upgrade", "auto_equip", "death_link", "death_link_send",
        "death_link_first_death_grace", "death_link_amnesty",
    ]),
]

# ---------------------------------------------------------------------------
# PRESETS -- the wizard's starting points. Every preset carries ONLY deviations from the option
# defaults (validated below), and the two non-default ones are READ FROM examples/*.yaml rather
# than restated here, so the shipped example yamls and the wizard's presets cannot disagree.
# ---------------------------------------------------------------------------
PRESETS = [
    {
        "id": "defaults",
        "title": "Defaults",
        "tagline": "The base game, exactly as the apworld ships it.",
        "description": "Every option at its default: base game only, the full item pool, "
                       "randomized starting weapons, and the Moon Presence goal. The seed the "
                       "world is tested against.",
        "example": None,
    },
    {
        "id": "central_yharnam_variety",
        "title": "Central Yharnam variety",
        "tagline": "A varied-grant playtest seed, DLC on.",
        "description": "The varied-grant playtest configuration: The Old Hunters in play, "
                       "the full item pool, and no optional check categories -- a broad "
                       "delivery test rather than a maximal one.",
        "example": "central-yharnam-variety.yaml",
    },
    {
        "id": "playtest_35",
        "title": "Playtest 35",
        "tagline": "Full-world, high-coverage solo seed.",
        "description": "The long-form coverage seed: DLC, Uncanny variants, randomized armor "
                       "and shops, and auto-upgrade on. Everything the world can place, placed.",
        "example": "playtest-35.yaml",
    },
]


# ---------------------------------------------------------------------------
# AST extraction
# ---------------------------------------------------------------------------
OPTION_BASES = {
    "Toggle": "toggle",
    "DefaultOnToggle": "toggle",
    "Choice": "choice",
    "Range": "range",
}


def _classes(module):
    """Every ClassDef in the module, at any nesting depth (the option classes live in an else:)."""
    found = {}

    def walk(nodes):
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                found[node.name] = node
                walk(node.body)
            elif isinstance(node, (ast.If, ast.Try)):
                walk(node.body)
                walk(getattr(node, "orelse", []))
                walk(getattr(node, "finalbody", []))
                for handler in getattr(node, "handlers", []):
                    walk(handler.body)

    walk(module.body)
    return found


def _assignments(node):
    """`name -> literal value` for the simple class-body assignments we care about."""
    out = {}
    for stmt in node.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            out[target.id] = ast.literal_eval(stmt.value)
        except ValueError:
            continue
    return out


def describe(key, node):
    base = None
    for b in node.bases:
        name = b.id if isinstance(b, ast.Name) else getattr(b, "attr", None)
        if name in OPTION_BASES:
            base = name
            break
    if base is None:
        sys.exit("[FAIL] option class %s has no recognised Option base" % node.name)

    kind = OPTION_BASES[base]
    values = _assignments(node)
    doc = ast.get_docstring(node) or ""

    d = {
        "key": key,
        "class": node.name,
        "kind": kind,
        "display_name": values.get("display_name", node.name),
        "description": doc,
        "default": None,
        "choices": None,
        "range": None,
    }

    if kind == "toggle":
        # DefaultOnToggle IS the default; a subclass may still override it.
        default = values.get("default", 1 if base == "DefaultOnToggle" else 0)
        d["default"] = bool(default)
    elif kind == "choice":
        labels = values.get("_display_labels", {})
        choices = []
        for name, value in sorted(
            ((k[len("option_"):], v) for k, v in values.items() if k.startswith("option_")),
            key=lambda pair: pair[1],
        ):
            choices.append({
                "name": name,
                "value": value,
                # `get_option_name` is what Archipelago shows; when a class overrides it via
                # `_display_labels` the wizard must show the same words, not the yaml key.
                "label": labels.get(value, name.replace("_", " ")),
            })
        if not choices:
            sys.exit("[FAIL] choice option %r declares no option_* values" % key)
        d["choices"] = choices
        d["default"] = next(
            c["name"] for c in choices if c["value"] == values.get("default", choices[0]["value"])
        )
    else:
        start, end = values.get("range_start", 0), values.get("range_end", 0)
        d["range"] = {"start": start, "end": end}
        d["default"] = values.get("default", start)

    if not d["description"].strip():
        sys.exit("[FAIL] option %r has no docstring -- the wizard has nothing to say about it" % key)
    return d


def field_order(classes):
    node = classes.get("BloodborneOptions")
    if node is None:
        sys.exit("[FAIL] BloodborneOptions dataclass not found in %s" % WORLD)
    fields = []
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            annotation = stmt.annotation
            name = annotation.id if isinstance(annotation, ast.Name) else None
            if name is None:
                sys.exit("[FAIL] BloodborneOptions field %r has a non-name annotation"
                         % stmt.target.id)
            fields.append((stmt.target.id, name))
    if not fields:
        sys.exit("[FAIL] BloodborneOptions declares no fields")
    return fields


# ---------------------------------------------------------------------------
# presets, read from examples/*.yaml
# ---------------------------------------------------------------------------
def read_example(filename):
    """The flat `Bloodborne:` mapping of an example yaml, as `{key: raw string}`.

    Deliberately not pyyaml: this tool has to run in a CI job that installs nothing, and the one
    shape it must read is a flat two-space block of scalars. Nested blocks (`start_inventory`)
    are skipped rather than half-parsed, and comment lines are dropped.
    """
    path = os.path.join(EXAMPLES, filename)
    out, inside = {}, False
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if not line.startswith(" "):
                inside = line.strip() == "%s:" % GAME
                continue
            if not inside:
                continue
            stripped = line.strip()
            if len(line) - len(line.lstrip()) != 2 or ":" not in stripped:
                continue  # a nested block's body, or its key -- neither is a flat option
            key, _, value = stripped.partition(":")
            value = value.split("#", 1)[0].strip()
            if value:
                out[key.strip()] = value
    return out


def coerce(option, raw):
    if option["kind"] == "toggle":
        if raw in ("true", "false"):
            return raw == "true"
        sys.exit("[FAIL] %s: %r is not a yaml bool" % (option["key"], raw))
    if option["kind"] == "range":
        return int(raw)
    return raw.strip('"\'')


def build_presets(options):
    by_key = {o["key"]: o for o in options}
    out = []
    for preset in PRESETS:
        values = {}
        if preset["example"]:
            for key, raw in read_example(preset["example"]).items():
                option = by_key.get(key)
                if option is None:
                    continue  # progression_balancing / accessibility are AP core, not our surface
                value = coerce(option, raw)
                if option["kind"] == "choice":
                    names = {c["name"] for c in option["choices"]}
                    if value not in names:
                        sys.exit("[FAIL] preset %s: %s=%r not in %s"
                                 % (preset["id"], key, value, sorted(names)))
                elif option["kind"] == "range":
                    lo, hi = option["range"]["start"], option["range"]["end"]
                    if not lo <= value <= hi:
                        sys.exit("[FAIL] preset %s: %s=%r outside %d..%d"
                                 % (preset["id"], key, value, lo, hi))
                # Presets carry DEVIATIONS ONLY: a restated default is noise that silently
                # becomes a lie the day the default moves.
                if value != option["default"]:
                    values[key] = value
        out.append({k: v for k, v in preset.items() if k != "example"} | {"values": values})
    return out


# ---------------------------------------------------------------------------
def extract():
    source = open(WORLD, encoding="utf-8").read()
    classes = _classes(ast.parse(source))
    fields = field_order(classes)

    options = []
    for key, class_name in fields:
        node = classes.get(class_name)
        if node is None:
            sys.exit("[FAIL] BloodborneOptions field %r names unknown class %s" % (key, class_name))
        options.append(describe(key, node))

    keys = [k for k, _ in fields]
    grouped, groups = {}, []
    for name, members in GROUPS:
        for key in members:
            if key not in keys:
                sys.exit("[FAIL] group %r names %r, which is not on the option surface -- "
                         "fix GROUPS in this file" % (name, key))
            if key in grouped:
                sys.exit("[FAIL] option %r is in two groups (%s, %s)" % (key, grouped[key], name))
            grouped[key] = name
        groups.append({"name": name, "options": list(members)})
    ungrouped = [k for k in keys if k not in grouped]
    if ungrouped:
        # FATAL, unlike er-archipelago's soft warning: there is no "Advanced" fold on this page,
        # so an ungrouped option would simply not be drawn -- a knob that exists in the yaml and
        # nowhere on the wizard is exactly the silent gap this tool is here to prevent.
        sys.exit("[FAIL] option(s) in no group: %s -- add them to GROUPS" % ", ".join(ungrouped))

    apworld_version = json.load(open(ARCHIPELAGO_JSON, encoding="utf-8"))["world_version"]
    # Deterministic (no timestamps) so --check can byte-compare.
    surface = json.dumps(
        [[o["key"], o["kind"], o["default"], o["choices"], o["range"]] for o in options],
        sort_keys=True, default=str)

    return {
        "schema": 1,
        "game": GAME,
        # WHICH APWORLD THIS SURFACE BELONGS TO. The wizard is a static page deployed on its own
        # schedule, so it is routinely ahead of the apworld a player installed -- and Archipelago
        # does not stop that: an unknown option key prints one buried line and generates without
        # it. So the version is shown in the wizard header and rides into the emitted yaml's
        # `description`, which AP prints in the generation log and stores in the multidata.
        "apworld_version": apworld_version,
        "source": "worlds/bloodborne/__init__.py -> BloodborneOptions (parsed)",
        "source_sha256": hashlib.sha256(surface.encode("utf-8")).hexdigest(),
        "field_order": keys,
        "groups": groups,
        "options": options,
        "presets": build_presets(options),
    }


def dumps(meta):
    # "</" escaped so the blob is safe to inline inside a <script> tag.
    return json.dumps(meta, indent=1, ensure_ascii=False).replace("</", "<\\/") + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Dump the Bloodborne option surface to JSON.")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if site/options-metadata.json is stale")
    args = parser.parse_args(argv)

    fresh = dumps(extract())
    count = len(json.loads(fresh)["options"])

    if args.check:
        if not os.path.isfile(OUT_JSON):
            print("[STALE] site/options-metadata.json is missing")
            return 1
        current = open(OUT_JSON, encoding="utf-8", newline="").read().replace("\r\n", "\n")
        if current != fresh:
            print("[STALE] site/options-metadata.json differs from a fresh dump")
            print("        fix: python tools/dump_options_metadata.py")
            return 1
        print("[ok] option metadata is current (%d options)" % count)
        return 0

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fresh)
    print("[ok] wrote site/options-metadata.json (%d options)" % count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
