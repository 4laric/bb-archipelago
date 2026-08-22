#!/usr/bin/env python3
"""Narrow the DeathLink send-signal search against the committed corpus.

Issue #78 prep: before anyone spends live gameplay minutes hunting the death
signal, establish from the committed inputs bundle what the event scripts and
params already tell us. The headline result is a *negative* one, and it is the
useful kind:

    No EMEVD event flag is written on every player death.

`CharacterDead(10000)` (entity 10000 is the player) appears exactly three times
in the whole decompiled corpus, and none of those sites is a general-purpose
"the player died" flag write. So the send signal has to come from a live state
read (HP at zero, a death-state SpEffect, or a memory bit found by the session
kit in `tools/death_signal_session.ps1`), not from the flag manager that
already serves location checks.

    python tools/death_signal_candidates.py            # report
    python tools/death_signal_candidates.py --bundle <path>

Everything printed here is `inferred` in the RESEARCH-BASELINE vocabulary: it
traces to a committed corpus row, and nothing here claims any candidate *is*
the death signal. That claim needs the live session.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sqlite3
import zlib
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLE = REPO / "research" / "bb_inputs.db"

PLAYER_ENTITY = 10000
EVENT = re.compile(r"^\s*\$Event\((\d+),")
SET_FLAG = re.compile(r"\bSetEventFlag\((\d+),\s*(ON|OFF)\)")
SET_RESPAWN = re.compile(r"\bSetPlayerRespawnPoint\((\d+)\)")
CALL = re.compile(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")

# SpEffect names that mark the PLAYER's death transition/state: 死亡遷移
# ("death transition") and 死亡状態維持 ("death-state maintenance") rows,
# including the cage-only and dungeon variants, plus 死んだとき復活 ("revive
# on death"). The broad 死亡 ("death") pattern also matches arena, NPC-puppet,
# and weapon-mode death *judgments*, which are not the player dying; those are
# reported separately as reviewed-and-set-aside so the narrowing stays honest.
# The many 瀕死 ("near death", low-HP passive) rows match neither pattern:
# they never fire *because* you died.
PLAYER_DEATH_NAME = re.compile(r"死亡遷移|死亡状態維持|死んだとき復活")
ANY_DEATH_NAME = re.compile(r"死亡|死んだとき復活")

# Engine-side concepts with no EMEVD instruction at all. A zero count here is
# the evidence that the bloodstain/respawn bookkeeping is not script-visible.
ABSENT_INSTRUCTIONS = ("Bloodstain", "SpawnBloodstain", "DropBloodstain")
RESPAWN_WARP = "WarpPlayerToRespawnPoint"


@dataclass(frozen=True)
class DeathSite:
    """One `CharacterDead(10000)` in code, with its event-local context."""

    path: str
    line: int
    event_id: int
    conditions: tuple[str, ...]            # call names in the enclosing WaitFor
    flags_before: tuple[tuple[int, str], ...]  # SetEventFlag writes ahead of the wait
    flags_after: tuple[tuple[int, str], ...]   # writes after the wait
    respawn_points: tuple[int, ...]        # SetPlayerRespawnPoint after the wait


@dataclass
class _Event:
    event_id: int
    start: int
    lines: list[tuple[int, str]] = field(default_factory=list)  # (lineno, code)


def load_scripts(bundle: Path) -> dict[str, str]:
    if not bundle.is_file():
        raise SystemExit(f"inputs bundle not found: {bundle}")
    database = sqlite3.connect(bundle)
    rows = database.execute(
        "SELECT path, blob FROM files WHERE path LIKE 'event/%.emevd.dcx.js'"
    ).fetchall()
    database.close()
    if not rows:
        raise SystemExit(f"{bundle} carries no event scripts")
    return {path: zlib.decompress(blob).decode("utf-8") for path, blob in rows}


def _events(path: str, text: str) -> list[_Event]:
    events: list[_Event] = []
    current: _Event | None = None
    depth = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        declaration = EVENT.match(raw)
        if declaration and current is None:
            current = _Event(int(declaration.group(1)), lineno)
            depth = raw.count("{") - raw.count("}")
            continue
        if current is not None:
            current.lines.append((lineno, raw.partition("//")[0]))
            depth += raw.count("{") - raw.count("}")
            if depth <= 0:
                events.append(current)
                current = None
    return events


def _waitfor_statement(lines: list[tuple[int, str]], hit: int) -> str:
    """Reassemble the WaitFor(...) statement containing line index `hit`."""
    start = hit
    while start > 0 and "WaitFor(" not in lines[start][1]:
        start -= 1
    parts = []
    depth = 0
    for _, code in lines[start:]:
        parts.append(code)
        depth += code.count("(") - code.count(")")
        if depth <= 0 and parts:
            break
    return " ".join(parts)


def player_death_sites(scripts: dict[str, str]) -> list[DeathSite]:
    needle = f"CharacterDead({PLAYER_ENTITY})"
    sites: list[DeathSite] = []
    for path in sorted(scripts):
        for event in _events(path, scripts[path]):
            for index, (lineno, code) in enumerate(event.lines):
                if needle not in code:
                    continue
                statement = _waitfor_statement(event.lines, index)
                conditions = tuple(sorted(set(CALL.findall(statement)) - {"WaitFor"}))
                before, after, respawns = [], [], []
                for write_lineno, write_code in event.lines:
                    for flag, state in SET_FLAG.findall(write_code):
                        target = before if write_lineno < lineno else after
                        target.append((int(flag), state))
                    if write_lineno > lineno:
                        respawns.extend(int(point) for point in SET_RESPAWN.findall(write_code))
                sites.append(DeathSite(
                    path=path, line=lineno, event_id=event.event_id,
                    conditions=conditions,
                    flags_before=tuple(sorted(set(before))),
                    flags_after=tuple(sorted(set(after))),
                    respawn_points=tuple(sorted(set(respawns))),
                ))
    return sites


def death_speffects(bundle: Path) -> tuple[dict[int, str], dict[int, str]]:
    """Death-related SpEffect rows as (player-state, set-aside), keyed by id.

    Player-state rows are the `inferred` candidates a live session can watch;
    set-aside rows matched the broad death pattern but judge something else's
    death (arena, NPC puppet, weapon mode).
    """
    database = sqlite3.connect(bundle)
    row = database.execute(
        "SELECT blob FROM files WHERE path = 'params/SpEffectParam.csv'"
    ).fetchone()
    database.close()
    if row is None:
        raise SystemExit(f"{bundle} carries no params/SpEffectParam.csv")
    text = zlib.decompress(row[0]).decode("utf-8-sig")
    player, aside = {}, {}
    for record in csv.DictReader(io.StringIO(text)):
        if not ANY_DEATH_NAME.search(record["Name"]):
            continue
        target = player if PLAYER_DEATH_NAME.search(record["Name"]) else aside
        target[int(record["ID"])] = record["Name"]
    return player, aside


def code_occurrences(scripts: dict[str, str], token: str) -> int:
    """Occurrences of `token(` in code, comments excluded."""
    count = 0
    for text in scripts.values():
        for raw in text.splitlines():
            code = raw.partition("//")[0]
            count += len(re.findall(re.escape(token) + r"\s*\(", code))
    return count


def report(bundle: Path) -> int:
    scripts = load_scripts(bundle)
    sites = player_death_sites(scripts)
    speffects, set_aside = death_speffects(bundle)

    print(f"# Death-signal candidate narrowing ({bundle})")
    print()
    print(f"## CharacterDead({PLAYER_ENTITY}) sites: {len(sites)}")
    for site in sites:
        print(f"- {site.path}:{site.line} event {site.event_id}")
        print(f"    wait conditions : {', '.join(site.conditions)}")
        print(f"    flags set BEFORE the death wait: "
              + (", ".join(f"{flag} {state}" for flag, state in site.flags_before) or "none"))
        print(f"    flags set AFTER  the death wait: "
              + (", ".join(f"{flag} {state}" for flag, state in site.flags_after) or "none"))
        print(f"    respawn point set after        : "
              + (", ".join(str(point) for point in site.respawn_points) or "none"))
    unconditional = [site for site in sites
                     if site.flags_after and "PlayerHasItem" not in site.conditions
                     and "EventFlag" not in site.conditions]
    print()
    if unconditional:
        print(f"!! {len(unconditional)} site(s) write a flag unconditionally on death:")
        for site in unconditional:
            print(f"   event {site.event_id} -> {site.flags_after}")
    else:
        print("No event writes a flag unconditionally on player death.")
        print("The send signal must be a live state read, not an event flag.")

    print()
    print(f"## Player death-state SpEffect candidates: {len(speffects)}")
    for speffect_id, name in sorted(speffects.items()):
        print(f"- {speffect_id}: {name}")
    print()
    print(f"## Death-pattern rows reviewed and set aside (not the player dying): "
          f"{len(set_aside)}")
    for speffect_id, name in sorted(set_aside.items()):
        print(f"- {speffect_id}: {name}")

    print()
    print("## Engine-side concepts with no script-visible instruction")
    for token in ABSENT_INSTRUCTIONS:
        print(f"- {token}: {code_occurrences(scripts, token)} occurrence(s)")
    print(f"- {RESPAWN_WARP}: {code_occurrences(scripts, RESPAWN_WARP)} occurrence(s) "
          "(the respawn side IS script-visible)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    args = parser.parse_args(argv)
    return report(args.bundle)


if __name__ == "__main__":
    raise SystemExit(main())
