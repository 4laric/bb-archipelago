"""Turn the retained enemizer plan into a paste-ready bad-enemy report.

A playtester who meets a broken, stuck, or repeatedly dying enemy should not
have to know what an entity id is. The seed cache keeps the exact plan the
writer consumed (bb-archipelago#321), so this module reads the active
overlay's plan back, names the area in plain words, and writes one Markdown
file the player pastes into an issue. Everything a maintainer needs to
reproduce the swap (seed, slot, cache key, plan hash, destination tuple,
target tuple, coordinates) rides along automatically.

Nothing here touches the game or the overlay; it only reads.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .client_config import default_state_root
from .core import (
    ENEMIZER_PLAN_NAME,
    GameInstall,
    SeedCache,
    ValidationError,
    _load_owner,
    _read_json,
)
from .workflow import LauncherSettings, _request_identity

ISSUE_URL = "https://github.com/4laric/bb-archipelago/issues/new"
REPORT_DIR = "enemy-reports"

# Bloodborne's fixed-map ids, in the words a player uses. Chalice dungeons
# (m29) never enter the inventory the planner reads, so they are absent on
# purpose. Sources: docs/SLICE-ROADMAP.md and docs/LOCATION-NAMING.md.
MAP_AREAS: dict[str, str] = {
    "m21_00": "Hunter's Dream",
    "m21_01": "Abandoned Old Workshop",
    "m22_00": "Hemwick Charnel Lane",
    "m23_00": "Old Yharnam",
    "m24_00": "Cathedral Ward",
    "m24_01": "Central Yharnam",
    "m24_02": "Upper Cathedral Ward",
    "m25_00": "Forsaken Cainhurst Castle",
    "m26_00": "Nightmare of Mensis",
    "m27_00": "Forbidden Woods",
    "m28_00": "Yahar'gul, Unseen Village",
    "m32_00": "Byrgenwerth / Lecture Building",
    "m33_00": "Nightmare Frontier",
    "m34_00": "Hunter's Nightmare",
    "m35_00": "Research Hall",
    "m36_00": "Fishing Hamlet",
}


def area_key(map_name: str) -> str:
    """``m24_01_00_11`` -> ``m24_01``."""
    fields = map_name.split("_")
    return "_".join(fields[:2]) if len(fields) >= 2 else map_name


def area_name(map_name: str) -> str:
    key = area_key(map_name)
    return MAP_AREAS.get(key, f"unknown area {key}")


def launcher_version() -> str:
    """The packaged launcher's file version, or a marker for a source checkout."""
    if getattr(sys, "frozen", False):
        from .doctor import _read_windows_file_version

        version = _read_windows_file_version(Path(sys.executable))
        return version or "packaged (no version resource)"
    return "source checkout"


@dataclass(frozen=True)
class SwapRow:
    logical_key: str
    map_name: str
    map_states: tuple[str, ...]
    area: str
    entity_id: int
    part_name: str
    x: float
    y: float
    z: float
    source_model: str
    source_npc: int
    source_name: str
    source_size: str
    source_tier: str
    source_locomotion: str
    source_echoes: int
    target_model: str
    target_npc: int
    target_name: str
    target_size: str
    target_tier: str
    target_locomotion: str
    target_echoes: int
    warnings: tuple[str, ...]

    @property
    def was(self) -> str:
        return _describe(self.source_model, self.source_npc, self.source_name)

    @property
    def now(self) -> str:
        return _describe(self.target_model, self.target_npc, self.target_name)


def _describe(model: str, npc: int, name: str) -> str:
    label = f"{model} / NpcParam {npc}"
    return f"{label} ({name})" if name else label


@dataclass(frozen=True)
class ReportContext:
    cache_key: str
    build_path: Path
    manifest: Mapping[str, Any]
    plan: Mapping[str, Any]
    seed: str
    slot: str
    request_path: str


def swap_rows(plan: Mapping[str, Any]) -> list[SwapRow]:
    """One row per logical placement, in map order.

    Alternate map states (``m24_01_00_00`` / ``_01`` / ``_11``) hold the same
    enemy at the same spot and always receive one shared target, so they fold
    into one row that lists the states it covers.
    """
    rows: list[SwapRow] = []
    for swap in plan.get("swaps", []):
        if not isinstance(swap, dict):
            continue
        source = swap.get("source") or {}
        target = swap.get("target") or {}
        source_tag = swap.get("source_tag") or {}
        target_tag = swap.get("target_tag") or {}
        source_facts = swap.get("source_facts") or {}
        target_facts = swap.get("target_facts") or {}
        destinations = swap.get("destinations") or {}
        keys = swap.get("destination_keys") or list(destinations) or [swap.get("logical_key", "")]
        if not keys:
            continue
        keys = sorted(str(key) for key in keys)
        first = keys[0]
        placement = destinations.get(first) or {}
        map_name, _, part = first.partition(":")
        map_name = str(placement.get("map_name") or map_name)
        states = tuple(
            str((destinations.get(key) or {}).get("map_name") or key.partition(":")[0])
            for key in keys
        )
        rows.append(
                SwapRow(
                    logical_key=str(swap.get("logical_key", first)),
                    map_name=map_name,
                    map_states=states,
                    area=area_name(map_name),
                    entity_id=int(placement.get("entity_id", -1)),
                    part_name=part,
                    x=float(placement.get("x", 0.0)),
                    y=float(placement.get("y", 0.0)),
                    z=float(placement.get("z", 0.0)),
                    source_model=str(source.get("model_name", "?")),
                    source_npc=int(source.get("npc_param_id", -1)),
                    source_name=str(source_facts.get("name", "")),
                    source_size=str(source_tag.get("size_class", "?")),
                    source_tier=str(source_tag.get("tier", "?")),
                    source_locomotion=str(source_tag.get("locomotion", "?")),
                    source_echoes=int(source_facts.get("echoes", 0)),
                    target_model=str(target.get("model_name", "?")),
                    target_npc=int(target.get("npc_param_id", -1)),
                    target_name=str(target_facts.get("name", "")),
                    target_size=str(target_tag.get("size_class", "?")),
                    target_tier=str(target_tag.get("tier", "?")),
                    target_locomotion=str(target_tag.get("locomotion", "?")),
                    target_echoes=int(target_facts.get("echoes", 0)),
                    warnings=tuple(str(w) for w in swap.get("warnings", [])),
                )
            )
    rows.sort(key=lambda row: (row.map_name, row.entity_id, row.part_name))
    return rows


def areas_in_plan(plan: Mapping[str, Any]) -> list[tuple[str, str, int]]:
    """``(area key, area name, swapped placements)`` for every area the plan touches."""
    counts: dict[str, int] = {}
    for row in swap_rows(plan):
        counts[area_key(row.map_name)] = counts.get(area_key(row.map_name), 0) + 1
    return [(key, MAP_AREAS.get(key, f"unknown area {key}"), counts[key]) for key in sorted(counts)]


def rank_by_echoes(rows: Iterable[SwapRow], echoes: int) -> list[SwapRow]:
    """Closest target echo rewards first: the #321 'something keeps dying' signal."""
    return sorted(rows, key=lambda row: (abs(row.target_echoes - echoes), row.map_name, row.entity_id))


def load_context(settings: LauncherSettings, *, player_name: str = "") -> ReportContext:
    """Read the active overlay's retained plan. Raises ValidationError with a remedy."""
    install = GameInstall.from_root(settings.game_root)
    if not install.mods.exists():
        raise ValidationError(
            "no Bloodborne AP overlay is active; run Randomize & Launch first, then report"
        )
    owner = _load_owner(install.mods)
    enemizer = owner.get("enemizer") if isinstance(owner.get("enemizer"), dict) else {}
    if not enemizer.get("enabled"):
        raise ValidationError(
            "the active overlay has enemy randomization off, so there is no enemy swap to report"
        )
    cache = SeedCache(settings.cache_root)
    build = cache.verify(cache.path_for(str(owner["cache_key"])))
    plan_record = build.manifest.get("enemizer", {}).get("plan")
    if not plan_record:
        raise ValidationError(
            "this build was made before the launcher kept enemy plans; press Rebuild once "
            "(same seed, same swaps) and the report will work from then on"
        )
    plan = _read_json(build.path / ENEMIZER_PLAN_NAME, "retained enemizer plan")
    seed = slot = "?"
    request_path = str(settings.ap_request)
    try:
        request = _request_identity(
            settings.ap_request,
            player_name=player_name,
            state_root=settings.state_root or default_state_root(),
        )
        seed, slot, request_path = str(request["seed"]), str(request["slot"]), str(request["path"])
    except Exception:  # noqa: BLE001 - the report is still useful without the request
        identity = owner.get("identity") if isinstance(owner.get("identity"), dict) else {}
        seed = str(identity.get("seed", "?"))
        slot = str(identity.get("slot", "?"))
    return ReportContext(
        cache_key=str(owner["cache_key"]),
        build_path=build.path,
        manifest=build.manifest,
        plan=plan,
        seed=seed,
        slot=slot,
        request_path=request_path,
    )


def _md_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(cell) for cell in row) + " |")
    return lines


def _states(row: SwapRow) -> str:
    """``m24_01_00_00 +2 states`` when alternate map states share the placement."""
    extra = len(row.map_states) - 1
    return row.map_name + (f" +{extra} state{'s' if extra > 1 else ''}" if extra > 0 else "")


def _row_cells(row: SwapRow) -> list[object]:
    return [
        row.entity_id if row.entity_id > 0 else "(none)",
        row.part_name,
        _states(row),
        row.was,
        row.now,
        f"{row.source_size}/{row.source_tier} -> {row.target_size}/{row.target_tier}",
        f"{row.source_locomotion} -> {row.target_locomotion}",
        row.target_echoes,
        f"{row.x:.1f}, {row.y:.1f}, {row.z:.1f}",
        "; ".join(row.warnings) or "-",
    ]


ROW_HEADERS = [
    "Entity", "Part", "Map", "Was", "Now", "Size/tier", "Locomotion", "Echoes",
    "Position x, y, z", "Planner notes",
]


def format_report(
    context: ReportContext,
    *,
    area: str | None = None,
    echoes: int | None = None,
    note: str = "",
    version: str | None = None,
    now: datetime | None = None,
) -> str:
    """The Markdown a player pastes. ``area`` is a map prefix such as ``m24_01``."""
    plan = context.plan
    enemizer = context.manifest.get("enemizer", {})
    plan_record = enemizer.get("plan") or {}
    options = plan_record.get("options") or plan.get("options") or {}
    stress = plan.get("stress")
    rows = swap_rows(plan)
    focus = area_key(area) if area else None
    focused = [row for row in rows if focus is None or area_key(row.map_name) == focus]
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Bloodborne AP enemy report",
        "",
        f"Paste this whole file into a new issue at {ISSUE_URL} (or the playtest channel).",
        "Add what you saw in the note line if you have not already: where you were standing,",
        "what the enemy looked like, and what it did (stuck, invisible, kept dying, crashed the map).",
        "Names in parentheses are the game's own internal designer names; the model and",
        "NpcParam ids beside them are what a maintainer needs.",
        "",
        f"- Generated: {stamp}",
        f"- Launcher: {version or launcher_version()}",
        f"- AP seed / slot: {context.seed} / {context.slot}",
        f"- Seed file: {context.request_path}",
        f"- Enemy seed: {plan.get('seed', enemizer.get('seed', '?'))}",
        f"- Enemy options: tier mixing {'on' if options.get('allow_tier_mixing') else 'off'}, "
        f"locomotion preserved {'on' if options.get('preserve_locomotion') else 'off'}",
    ]
    if stress:
        lines.append(
            f"- Stress profile: {stress.get('kind')}"
            + (f"={stress.get('argument')}" if stress.get("argument") else "")
            + (f" in {stress.get('focus')}" if stress.get("focus") else "")
            + f" ({stress.get('matched', '?')} of {len(plan.get('swaps', []))} swaps embody it)"
        )
    lines.extend([
        f"- Cache key: {context.cache_key}",
        f"- Plan sha256: {plan_record.get('sha256', '?')}",
        f"- Swaps in this build: {len(rows)} placements "
        f"({sum(len(row.map_states) for row in rows)} map-state copies)",
        f"- Reported area: {MAP_AREAS.get(focus, focus) if focus else 'all areas'}",
        f"- Echoes observed: {echoes if echoes is not None else 'not given'}",
        f"- Player note: {note.strip() or '(none)'}",
        "",
    ])

    if echoes is not None:
        ranked = rank_by_echoes(focused or rows, echoes)[:8]
        lines.append(f"## Closest matches to {echoes} echoes")
        lines.append("")
        lines.append("Enemies whose reward is nearest the figure you saw, nearest first. "
                     "A repeated off-screen reward usually means one of these is dying on spawn.")
        lines.append("")
        lines.extend(_table(
            ["Rank", "Area", "Entity", "Now", "Echoes", "Was", "Position x, y, z"],
            [[index + 1, row.area, row.entity_id if row.entity_id > 0 else "(none)", row.now,
              row.target_echoes, row.was, f"{row.x:.1f}, {row.y:.1f}, {row.z:.1f}"]
             for index, row in enumerate(ranked)],
        ))
        lines.append("")

    if focus is not None:
        lines.append(f"## Swaps in {MAP_AREAS.get(focus, focus)} ({len(focused)} placements)")
        lines.append("")
        if focused:
            lines.extend(_table(ROW_HEADERS, [_row_cells(row) for row in focused]))
        else:
            lines.append("No enemy in this area was randomized in this build; every enemy "
                         "there is vanilla. If one still misbehaves, it is not the enemizer.")
        lines.append("")
    else:
        for key, name, count in areas_in_plan(plan):
            lines.append(f"## {name} ({key}, {count} placements)")
            lines.append("")
            lines.extend(_table(
                ROW_HEADERS,
                [_row_cells(row) for row in rows if area_key(row.map_name) == key],
            ))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(state_root: Path | str, text: str, *, now: datetime | None = None) -> Path:
    """Write the report under the launcher state root and return its path."""
    root = Path(state_root).expanduser() / REPORT_DIR
    root.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    path = root / f"enemy-report-{stamp}.md"
    counter = 1
    while path.exists():
        counter += 1
        path = root / f"enemy-report-{stamp}-{counter}.md"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
