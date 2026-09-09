"""Original fixed-map boss encounter contracts, derived from the input bundle.

This is a static census, not an assertion that a boss is safe to transplant.
Only literal operands are resolved; initializer indirection stays explicit.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping

from .model import Slot, canonical_map

DECLARATION = re.compile(r"\$Event\(\s*(\d+),\s*(\w+),\s*function\(([^)]*)\)\s*\{")
CALL_NAME = re.compile(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")
FIXED_SCRIPT = re.compile(r"^(m\d{2}_\d{2}_\d{2}_\d{2})\.emevd\.dcx\.js$")
# These literal entity operands are witnessed in the bundled boss scripts.
# Other operations are retained as references, not assigned an entity meaning.
FIRST_ENTITY = {
    "HandleBossDefeat", "CharacterDead", "HPRatio", "CharacterHPValue",
    "ChangeCharacterEnableState", "ForceCharacterDeath", "SetCharacterAIState",
    "SetCharacterInvincibility", "RequestCharacterAnimationReset",
}
COMPLETION = {"CharacterDead", "HPRatio", "CharacterHPValue"}


def mask_comments_and_strings(text: str) -> str:
    """Keep positions/newlines while removing comments and quoted text."""
    pattern = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
    return pattern.sub(lambda m: "".join("\n" if c == "\n" else " " for c in m[0]), text)


def _closing(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    raise ValueError(f"unclosed {opening} at offset {start}")


def _arguments(text: str) -> tuple[str, ...]:
    values, start, depth = [], 0, 0
    for index, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            values.append(text[start:index].strip())
            start = index + 1
    if text.strip():
        values.append(text[start:].strip())
    return tuple(values)


@dataclass(frozen=True)
class Call:
    operation: str
    arguments: tuple[str, ...]
    line: int

    def integer(self, index: int) -> int | None:
        if index >= len(self.arguments) or not re.fullmatch(r"-?\d+", self.arguments[index]):
            return None
        return int(self.arguments[index])


@dataclass(frozen=True)
class Event:
    event_id: int
    restart: str
    parameters: tuple[str, ...]
    first_line: int
    last_line: int
    calls: tuple[Call, ...]


def parse_events(text: str) -> list[Event]:
    code = mask_comments_and_strings(text)
    events = []
    for match in DECLARATION.finditer(code):
        brace = match.end() - 1
        end = _closing(code, brace, "{", "}")
        calls = []
        body = code[brace + 1:end]
        for call in CALL_NAME.finditer(body):
            opening = call.end() - 1
            closing = _closing(body, opening, "(", ")")
            calls.append(Call(call[1], _arguments(body[opening + 1:closing]),
                              code.count("\n", 0, brace + 1 + call.start()) + 1))
        events.append(Event(int(match[1]), match[2], _arguments(match[3]),
                            code.count("\n", 0, match.start()) + 1,
                            code.count("\n", 0, end) + 1, tuple(calls)))
    if code.count("$Event(") != len(events):
        raise ValueError("unsupported event declaration in boss corpus")
    return events


def _entity(call: Call) -> int | None:
    if call.operation in FIRST_ENTITY:
        return call.integer(0)
    if call.operation == "DisplayBossHealthBar":
        return call.integer(1)
    return None


def _ref(source: str, event: Event, call: Call) -> dict:
    return {"source": source, "event_id": event.event_id, "line": call.line,
            "operation": call.operation, "arguments": list(call.arguments)}


def build_boss_catalog(scripts: Mapping[str, str], slots: Iterable[Slot],
                       bindings: Mapping[str, int]) -> dict:
    slots_by_map = defaultdict(list)
    for slot in slots:
        map_name = slot.map_name.split(".")[0]
        slots_by_map[canonical_map(map_name)].append(slot)
    encounters, unresolved, excluded = [], [], []
    sources = {}
    for source, text in sorted(scripts.items()):
        filename = source.replace("\\", "/").split("/")[-1]
        match = FIXED_SCRIPT.fullmatch(filename)
        if not match or match[1].startswith("m29_"):
            excluded.append(source)
            continue
        sources[source] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        map_name = canonical_map(match[1])
        events = parse_events(text)
        definitions = Counter(event.event_id for event in events)
        placements = defaultdict(list)
        for slot in slots_by_map[map_name]:
            if slot.entity_id > 0:
                placements[slot.entity_id].append(slot)
        for terminal in events:
            defeats = [c for c in terminal.calls if c.operation == "HandleBossDefeat"]
            if not defeats:
                continue
            for call in defeats:
                if call.integer(0) is None:
                    unresolved.append(_ref(source, terminal, call))
            anchors = {c.integer(0) for c in defeats if c.integer(0) is not None}
            if not anchors:
                continue
            roles = defaultdict(set)
            for entity in anchors:
                roles[entity].add("defeat_operand")
            for call in terminal.calls:
                entity = _entity(call)
                if entity is not None and (entity in placements or entity in anchors):
                    roles[entity].add("completion_test" if call.operation in COMPLETION else "terminal_character_operand")
            # Match direct actor operands or exact references to the owning
            # event flag. Constructors are listed separately, never treated
            # as one giant encounter that links every actor in a map.
            def related(event: Event) -> bool:
                if event.event_id in (0, 50):
                    return False
                return event is terminal or any(
                    _entity(c) in roles or any(str(entity) in c.arguments for entity in roles) or
                    ("Flag" in c.operation and str(terminal.event_id) in c.arguments)
                    for c in event.calls
                )
            selected = [event for event in events if related(event)]
            for event in selected:
                for call in event.calls:
                    if call.operation == "DisplayBossHealthBar" and call.integer(1) is not None:
                        roles[call.integer(1)].add("health_bar")
            # One additional pass exposes the actor operations for newly
            # identified health-bar proxies. Do not recursively pull in all
            # actors mentioned by a related script.
            selected = [event for event in events if related(event)]
            uses, bars, expressions, initializers = [], [], [], []
            selected_ids = {event.event_id for event in selected}
            for event in events:
                for call in event.calls:
                    if call.operation not in ("$InitializeEvent", "$InitializeCommonEvent"):
                        continue
                    callee_id = call.integer(1)
                    if callee_id not in selected_ids and not any(str(e) in call.arguments[2:] for e in roles):
                        continue
                    targets = [candidate for candidate in events if candidate.event_id == callee_id]
                    target = targets[0] if len(targets) == 1 and call.operation == "$InitializeEvent" else None
                    enough = target is not None and len(call.arguments) - 2 >= len(target.parameters)
                    initializers.append({**_ref(source, event, call), "callee_event": callee_id,
                        "resolution": "local_parameter_binding" if enough else "unresolved",
                        "bindings": dict(zip(target.parameters, call.arguments[2:])) if enough else {},
                    })
            for event in selected:
                for call in event.calls:
                    if _entity(call) in roles or any(str(e) in call.arguments for e in roles):
                        uses.append({**_ref(source, event, call), "known_entity_operand": _entity(call) in roles})
                    if call.operation == "DisplayBossHealthBar":
                        bars.append(_ref(source, event, call))
                    if event is terminal and call.operation == "WaitFor" and any(op + "(" in " ".join(call.arguments) for op in COMPLETION):
                        expressions.append(_ref(source, event, call))
            actors = []
            for entity, actor_roles in sorted(roles.items()):
                physical = sorted(placements.get(entity, []), key=lambda slot: slot.key)
                actors.append({"entity_id": entity, "roles": sorted(actor_roles), "placements": [
                    {"key": slot.key, "logical_key": slot.logical_key, "dummy": slot.dummy,
                     "talk_id": slot.talk_id, "collision": slot.collision_name,
                     "position": [slot.x, slot.y, slot.z], "archetype": asdict(slot.archetype)}
                    for slot in physical
                ]})
            operation_counts = Counter(c.operation for event in selected for c in event.calls)
            ap = sorted(key for key, flag in bindings.items() if flag == terminal.event_id)
            gaps = ["runtime encounter behavior unvalidated", "callee and flag dependency traversal incomplete"]
            if definitions[terminal.event_id] != 1:
                gaps.append("ambiguous terminal event definition")
            if any(not actor["placements"] for actor in actors):
                gaps.append("actor has no fixed-map placement")
            if not ap:
                gaps.append("no matching AP boss binding")
            if any(item["resolution"] == "unresolved" for item in initializers):
                gaps.append("parameterized actor initializer requires resolution")
            if any(call.integer(0) is None for call in defeats):
                gaps.append("unresolved defeat operand")
            encounters.append({
                "key": f"{map_name}:{terminal.event_id}", "map": map_name,
                "completion_event": terminal.event_id, "ap_locations": ap,
                "completion_flag_evidence": "owning event ID matches AP binding; implicit event-end write remains inferred",
                "source": source, "source_sha256": sources[source],
                "terminal_lines": [terminal.first_line, terminal.last_line],
                "terminal_uses_this_event": any(c.operation == "ThisEvent" for c in terminal.calls),
                "defeat_entities": sorted(anchors), "actors": actors,
                "actor_shape": "single_actor" if len(actors) == 1 else "multiple_actors",
                "completion_expressions": expressions, "health_bars": bars,
                "related_events": [{"event_id": e.event_id, "lines": [e.first_line, e.last_line],
                                    "parameters": list(e.parameters)} for e in selected],
                "operations": dict(sorted(operation_counts.items())), "actor_references": uses,
                "actor_initializers": initializers,
                "cutscene_calls": [_ref(source, e, c) for e in selected for c in e.calls if "Cutscene" in c.operation],
                "animation_calls": [_ref(source, e, c) for e in selected for c in e.calls if "Animation" in c.operation],
                "event_writes": [_ref(source, terminal, c) for c in terminal.calls if c.operation in ("SetEventFlag", "BatchSetEventFlags")],
                "gaps": gaps, "runtime_validated": False, "approved_for_randomization": False,
            })
    encounters.sort(key=lambda record: record["key"])
    covered = {key for record in encounters for key in record["ap_locations"]}
    return {"format": "bb-boss-catalog-v1", "policy_changed": False, "evidence": "static_original_corpus",
            "source_hash_encoding": "UTF-8 text without BOM",
            "sources": sources, "encounters": encounters, "unresolved_defeats": unresolved,
            "excluded_scripts": excluded, "unmatched_ap_bindings": sorted(set(bindings) - covered),
            "summary": {"encounters": len(encounters), "ap_bindings_matched": len(covered),
                        "single_actor": sum(e["actor_shape"] == "single_actor" for e in encounters),
                        "multiple_actors": sum(e["actor_shape"] == "multiple_actors" for e in encounters)}}
