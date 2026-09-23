"""Pinned directed contracts for the two single-actor final encounters.

Both encounters occupy m21 but have distinct terminal/cutscene state.  Patches
therefore retain every destination-owned terminal, fog, co-op and transition
event and only replace combat-facing routines.
"""
from __future__ import annotations
import hashlib, re
from dataclasses import asdict, dataclass
from typing import Mapping
from .boss_contracts import CombatPackage, EventAttachment, PartBinding, event_blocks
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

EVENT_FILE='m21_00_00_00.emevd.dcx.js'
GEHRMAN=2100800
MOON=2100810

@dataclass(frozen=True)
class FinalArena:
    key:str; actor:int; terminal:int; entry:int; health:int; music:int; lockcam:int
    phase_events:tuple[int,...]; source_talk_id:int; source_cloth_events:tuple[int,...]=()

GEHRMAN_ARENA=FinalArena('gehrman',GEHRMAN,12101800,12101802,12104802,12104803,12104804,(12104807,12104808),210306)
MOON_ARENA=FinalArena('moon-presence',MOON,12101850,12101852,12104852,12104853,12104854,(12104860,12104870),0)

PINS={
 0:'fa40b334c1c2f7972b424b1332d9d23d4ed68c2c120f463c194431e46533df26',
 12101800:'f67934f4823c8c82c7675612ce4ae9f3c989b8c5426efc1c7e398f124938edb9',
 12101802:'9cb093d3e0aee513b4e2500b0b0a9a1e658c039b52e497eafa596a8752ccd26f',
 12101850:'ae1a5ecc4c0d2149f20d20a414cb8e374db9de618aa264ec226d48bedc738fdb',
 12101852:'0bde50f079f63078dd127d785f34e8ebdd8fce5cdaf44f5f5581fb69c01df3fb',
 12104802:'bb30fd6ca62dc57db799c576e84be78be221eb761ca6350da0197452f0bee570',
 12104803:'159ec5935e3770580344462a984ae2322ce8e367e996abe428d98856a66d1ce7',
 12104804:'13744977311646856c93a3cecc6b3067ae98d9fe804bd75236bda4ab1622a4c8',
 12104807:'982f550c29fffaed7203de03d2bc1740b45c92f9ccfede0f249f0696ad00adab',
 12104808:'357e7c711dc72e7316a1ecf4f3ea6d0a07453e31cbdf6a1cb6f99e3b1b2e596d',
 12104852:'a4022f49059e7bc5cb6a076481065f8418a885876121ec9a8f731120ccfe395e',
 12104853:'38b0df8eb0fb98bdf5e9e5f2c752f5220ffe23b35e5645e53eebad46e42adce4',
 12104854:'32ebde44a49a6b7a58b9ab4bc6b84e3187e8d3fb5721ef6ab19bab853ba65fe4',
 12104860:'5b91d32d18d586cd20510e5157b5ca35b7783efe137e6120dfd2c60d62cd6af9',
 12104870:'dc32a765534443ea5b41c0d1646f0d658417d29c359357cfb6daf1d00d483ad6',
}
GEHRMAN_PACKAGE=CombatPackage(
 key="gehrman", event_file=EVENT_FILE, map_prefix="m21_00_", actor=GEHRMAN,
 archetype=Archetype("c8050",805000,805000,0), completion_event=12101800,
 start_flag=12104800, activation_event=12101802, health_bar_event=12104802,
 health_bar_label=804000, phase_events=(12104807,12104808), co_op_entry_event=None,
 lockcam_event=12104804, phase_music_message=100, part_routine_event=None,
 part_bindings=(), attachments=(EventAttachment(12104807,(PartBinding(0,()),)),EventAttachment(12104808,(PartBinding(0,()),))), virtual_entities=(),
 entry_animation=None, lockcam_map=21, lockcam_subarea=0, expected=PINS)
MOON_PACKAGE=CombatPackage(
 key="moon-presence", event_file=EVENT_FILE, map_prefix="m21_00_", actor=MOON,
 archetype=Archetype("c5400",540000,540000,0), completion_event=12101850,
 start_flag=12104850, activation_event=12101852, health_bar_event=12104852,
 health_bar_label=540000, phase_events=(), co_op_entry_event=None, lockcam_event=12104854,
 phase_music_message=500, part_routine_event=12104860,
 part_bindings=(PartBinding(0,("5","5","NPCPartType.Part1","100","480","490","8000")),PartBinding(1,("6","6","NPCPartType.Part2","150","481","491","8010")),PartBinding(2,("7","7","NPCPartType.Part3","150","482","492","8030")),PartBinding(3,("8","8","NPCPartType.Part4","200","483","493","8020")),PartBinding(4,("9","9","NPCPartType.Part5","200","484","494","8040"))),
 attachments=(EventAttachment(12104860,(PartBinding(0,("5","5","NPCPartType.Part1","100","480","490","8000")),PartBinding(1,("6","6","NPCPartType.Part2","150","481","491","8010")),PartBinding(2,("7","7","NPCPartType.Part3","150","482","492","8030")),PartBinding(3,("8","8","NPCPartType.Part4","200","483","493","8020")),PartBinding(4,("9","9","NPCPartType.Part5","200","484","494","8040")))),EventAttachment(12104870,(PartBinding(0,()),))), virtual_entities=(),
 entry_animation=None, lockcam_map=21, lockcam_subarea=0, expected=PINS)


@dataclass(frozen=True)
class FinalAttachmentIds:
    first:int; second:int

def _verify(blocks: Mapping[int, str]) -> None:
    for event_id, digest in PINS.items():
        if event_id not in blocks or hashlib.sha256(blocks[event_id].encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original final-boss event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"{label} is not a unique pinned instruction")
    return text.replace(old, new, 1)


def _literal_remap(block: str, values: Mapping[int, int]) -> str:
    """Rewrite only exact numeric operands, never a prefix inside another ID."""
    return re.sub(r"(?<![\w])-?\d+(?![\w])",
                  lambda match: str(values.get(int(match[0]), int(match[0]))), block)


def _renamed_event(block: str, source_event: int, destination_event: int,
                   literals: Mapping[int, int]) -> str:
    block = _literal_remap(block, literals)
    return _replace_once(block, f"$Event({source_event},", f"$Event({destination_event},",
                         "attached event header")


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    from .boss_canary import parse_events
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _assert_available(source: str, ids: FinalAttachmentIds) -> None:
    literals = {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", source)}
    if {ids.first, ids.second} & literals:
        raise ValueError("final-boss attachment ID collides with original literal")


def _witness_initializer(event_zero: str, line: str, source_event: int) -> None:
    if event_zero.count(line) != 1:
        raise ValueError(f"Event(0) lacks unique initializer witness for {source_event}")


def _end_event(event_id: int, original: str | None = None) -> str:
    if original is None:
        return f"$Event({event_id}, Default, function() {{\n    EndEvent();\n}});"
    declaration = original.splitlines()[0]
    declaration = re.sub(r'function\(([^)]*)\)', lambda match: 'function(' + ', '.join(
        'unused_' + name.strip() for name in match[1].split(',') if name.strip()) + ')', declaration)
    return declaration + '\n    EndEvent();\n});'


def patch_gehrman_at_moon(source: str, ids: FinalAttachmentIds) -> str:
    """Place Gehrman combat in Moon's second-fight arena.

    Moon's terminal and the 21000050 transition cutscene are byte-for-byte
    preserved.  The Moon limb and player-immortality helpers are disabled;
    Gehrman's self-buff and message-20 cleanup are attached from their
    witnessed Event(0) calls.
    """
    original = event_blocks(source)
    _verify(original)
    _assert_available(source, ids)
    _witness_initializer(original[0], "    $InitializeEvent(0, 12104807);", 12104807)
    _witness_initializer(original[0], "    $InitializeEvent(0, 12104808);", 12104808)
    health = _replace_once(original[12104852],
        "DisplayBossHealthBar(Enabled, 2100810, 0, 540000)",
        "DisplayBossHealthBar(Enabled, 2100810, 0, 804000)", "Gehrman health label")
    health = _replace_once(health, "    SetCharacterAIState(2100810, Enabled);\n",
        "    SetCharacterAIState(2100810, Enabled);\n    SetCharacterEventTarget(2100810, 2100801);\n",
        "Gehrman witnessed event target")
    music = _replace_once(original[12104853], "CharacterHasEventMessage(2100810, 500)",
                          "CharacterHasEventMessage(2100810, 100)", "Gehrman phase music")
    lockcam = _renamed_event(original[12104804], 12104804, 12104854,
        {GEHRMAN: MOON, 12101800: 12101850})
    init = _replace_once(original[0], "    $InitializeEvent(0, 12104870);",
        "    $InitializeEvent(0, 12104870);\n"
        f"    $InitializeEvent(0, {ids.first});\n    $InitializeEvent(0, {ids.second});",
        "Moon append initializer anchor")
    edits = {0: init, 12104852: health, 12104853: music, 12104854: lockcam,
             12104860: _end_event(12104860, original[12104860]), 12104870: _end_event(12104870)}
    additions = (
        _renamed_event(original[12104807], 12104807, ids.first, {GEHRMAN: MOON, 12101800: 12101850}),
        _renamed_event(original[12104808], 12104808, ids.second, {GEHRMAN: MOON, 12101800: 12101850}),
    )
    output = _replace_events(source, edits).rstrip() + "\n\n" + "\n\n".join(additions) + "\n"
    blocks = event_blocks(output)
    if blocks[12101850] != original[12101850] or blocks[12101852] != original[12101852]:
        raise ValueError("Gehrman-at-Moon changed Moon terminal/cutscene")
    return output


def patch_moon_at_gehrman(source: str, ids: FinalAttachmentIds) -> str:
    """Place Moon combat in Gehrman's first-fight arena.

    Gehrman's terminal and 21000040 endgame entry remain untouched.  This does
    not suppress the destination's later Moon transition: that sequencing is
    destination progression, not donor combat.
    """
    original = event_blocks(source)
    _verify(original)
    _assert_available(source, ids)
    for line in (
        "    $InitializeEvent(0, 12104860, 5, 5, NPCPartType.Part1, 100, 480, 490, 8000);",
        "    $InitializeEvent(0, 12104870);",
    ):
        _witness_initializer(original[0], line, 12104860 if "60" in line else 12104870)
    health = _replace_once(original[12104802], "DisplayBossHealthBar(Enabled, 2100800, 0, 804000)",
                           "DisplayBossHealthBar(Enabled, 2100800, 0, 540000)", "Moon health label")
    # Moon's source health event has no SetCharacterEventTarget call.
    health = _replace_once(health, "    SetCharacterEventTarget(2100800, 2100801);\n", "",
                           "Gehrman-only event target removal")
    music = _replace_once(original[12104803], "CharacterHasEventMessage(2100800, 100)",
                          "CharacterHasEventMessage(2100800, 500)", "Moon phase music")
    lockcam = _renamed_event(original[12104854], 12104854, 12104804,
        {MOON: GEHRMAN, 12101850: 12101800})
    # Copy every source-authored limb initializer through the shared package.
    # A mismatched package operand must refuse rather than silently substitute
    # another limb's break animation.
    limb_lines = []
    for binding in MOON_PACKAGE.part_bindings:
        arguments = ", ".join(binding.arguments)
        source_line = f"    $InitializeEvent({binding.slot}, 12104860, {arguments});"
        _witness_initializer(original[0], source_line, 12104860)
        limb_lines.append(source_line.replace("12104860", str(ids.first), 1))
    limb_calls = "\n".join(limb_lines)
    init = _replace_once(original[0], "    $InitializeEvent(0, 12104870);",
        "    $InitializeEvent(0, 12104870);\n" + limb_calls + f"\n    $InitializeEvent(0, {ids.second});",
        "Gehrman append initializer anchor")
    edits = {0: init, 12104802: health, 12104803: music, 12104804: lockcam,
             12104807: _end_event(12104807), 12104808: _end_event(12104808)}
    additions = (
        _renamed_event(original[12104860], 12104860, ids.first, {MOON: GEHRMAN, 12101850: 12101800}),
        _renamed_event(original[12104870], 12104870, ids.second, {MOON: GEHRMAN, 12101850: 12101800}),
    )
    output = _replace_events(source, edits).rstrip() + "\n\n" + "\n\n".join(additions) + "\n"
    blocks = event_blocks(output)
    if blocks[12101800] != original[12101800] or blocks[12101802] != original[12101802]:
        raise ValueError("Moon-at-Gehrman changed Gehrman terminal/cutscene")
    return output



def _exact_slot(slots: list[Slot], arena: FinalArena, archetype: Archetype) -> Slot:
    matches = [slot for slot in slots if slot.entity_id == arena.actor]
    if len(matches) != 1:
        raise ValueError(f"{arena.key} requires exactly one inventory entity {arena.actor}")
    slot = matches[0]
    if slot.archetype != archetype:
        raise ValueError(f"{arena.key} entity {arena.actor} has unexpected inventory archetype")
    if slot.talk_id != arena.source_talk_id:
        raise ValueError(f"{arena.key} entity {arena.actor} has unexpected TalkID")
    return slot


def _directed(arena: FinalArena, donor: FinalArena) -> tuple[CombatPackage, CombatPackage, str]:
    if arena is MOON_ARENA and donor is GEHRMAN_ARENA:
        return MOON_PACKAGE, GEHRMAN_PACKAGE, "gehrman-at-moon"
    if arena is GEHRMAN_ARENA and donor is MOON_ARENA:
        return GEHRMAN_PACKAGE, MOON_PACKAGE, "moon-at-gehrman"
    raise ValueError("final-boss contracts require reciprocal Gehrman/Moon arenas")


def plan_final_boss_swap(slots: list[Slot], npcs: Mapping[int, dict], effects: Mapping[int, dict],
                         *, arena: FinalArena, donor: FinalArena,
                         attachment_ids: FinalAttachmentIds, seed: str) -> dict:
    """Emit the standard v2 native/scaling plan plus a reviewed event contract.

    Source initialization fingerprints are intentionally a binding request, not
    a guessed MSB transform.  The native builder fills and validates their
    exact fields using its original-MSB pin helper.
    """
    target_package, donor_package, patch_key = _directed(arena, donor)
    target = _exact_slot(slots, arena, target_package.archetype)
    source = _exact_slot(slots, donor, donor_package.archetype)
    swap = Swap(target.logical_key, [target.key], {target.key: target.archetype},
                target.archetype, source.archetype,
                warnings=["experimental final-boss contract; runtime endgame transition requires validation"],
                destinations={target.key: {"map_name": target.map_name, "entity_id": target.entity_id,
                                            "x": target.x, "y": target.y, "z": target.z}})
    changes, skips = plan_scaling([swap], [target], dict(npcs), dict(effects), boss_tiers=True)
    if len(changes) > 1 or (changes and skips):
        raise ValueError("final-boss primary swap has ambiguous scaling")
    added = (attachment_ids.first, attachment_ids.second)
    contract = {
        "format": "bb-final-boss-contract-v1", "arena": arena.key, "donor": donor.key,
        "patch": patch_key, "event_file": EVENT_FILE,
        "attachment_event_ids": list(added),
        "preserved_destination_events": [arena.terminal, arena.entry],
        "primary_init_source_bindings": [{
            "source_map": source.map_name, "source_part": source.part_name,
            "source_entity_id": source.entity_id, "source_archetype": asdict(source.archetype),
            "source_talk_id": source.talk_id,
            "destination_map": target.map_name, "destination_part": target.part_name,
            "destination_entity_id": target.entity_id,
            "required_native_fields": ["talk_id", "unk_t18", "init_anim_id", "damage_anim_id", "provenance"],
        }],
        "source_initialization": "native writer must populate exact original-MSB pin; no CharaInit-to-TalkID inference",
    }
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed, "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"{arena.key}<-{donor.key}"},
        "boss_contract": contract,
        "scaling": {"enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes), "changes": [change.json() for change in changes],
                    "skip_count": len(skips), "skips": skips},
    }
