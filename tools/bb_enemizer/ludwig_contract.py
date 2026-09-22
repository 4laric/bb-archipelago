"""Static Ludwig two-actor contract (runtime behavior remains unobserved)."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,re
from typing import Mapping,Sequence
from .model import Archetype,Slot,Swap
from .scaling import plan_scaling
from .boss_canary import event_blocks,parse_events

LUDWIG_ONE=3400800; LUDWIG_TWO=3400801; CLERIC=2410800
P1=Archetype('c4510',451000,451000,0); P2=Archetype('c4510',451001,451000,0)
SOURCE='event/m34_00_00_00.emevd.dcx.js'
EVENTS=(13404820,13404821,13404822,13404823,13404824,13404825,13404830,13404835,13404840,13404841)

SOURCE_HASHES = {
    0: "3772e9c2957d38bcdbc984631dab0033deaef57c1d092a8c77005cdd4d7c1d55",
    13401800: "15c6ba33b2df44b9fdc67ea470d1f32281bac11a588ba6c876de7ac85df5d8dd",
    13401801: "512227ef549cf14ead83ae803efb7f73294b7f406abea9c940b8b49a6d5f26bd",
    13404802: "09b991a95b087e141b27c3e69f2d55e330bf6a8764df7eb475ebdfd9df9e5ac7",
    13404803: "ee69949f3bf2119d6cb051e41abfed11c5de83b306f9a9e36a6b42df182745ba",
    13404804: "8bb1209c5f08d944570b67e634223c7375b3596fe56f2c44a5712b2d04359d78",
    13404820: "2a1075a99453bacb20f94e697137fe830eb2507ffcf74699ad7707ad62671c14",
    13404821: "a650abcf1dca7030d8d39eb944ef5e3c1ba0a9665dfb4fc8f9fbf3c82280e8bf",
    13404822: "ae620a8fe09a2614d36cc0714743fac5f2e9f7bd7fb888c78fdb738910250968",
    13404823: "3fd2cc74e5e8cf9ed1da11cea82f3244c1228bc4224b1a280431a4a64b519292",
    13404824: "19b82e96f8a880da845bf09c977b9d116da91584069edb0a3f630271ae119c70",
    13404825: "b64ae6b68f0a7dc4d922328fa23659be54219fd7010465f03493a141858e16f2",
    13404830: "e29423935a2cea0e2078da6f93030c835ac884337cfd9a832c055c13b778414f",
    13404835: "e9cafe3d4edfa21eb0c325a480ac17457d6b98d7d485cf2b542998320b07ba32",
    13404840: "3ab3d74eb2c16456051f503cb1e082f4ed769bbbf94e7570ddd4f99393bbe56b",
    13404841: "404a71c4d413e4aef35b1b9eaf683feb881acf4250724e4e5a265123d9a8a14d",
}

@dataclass(frozen=True)
class LudwigIds:
 phase_two_entity:int; bridge_event:int; event_ids:Mapping[int,int]; destination_part:str; evidence:str

def _blocks(text): return event_blocks(text)
def _pin(block): return hashlib.sha256(block.encode()).hexdigest()
def _replace(src,edits):
 lines=src.splitlines()
 for e in reversed(parse_events(src)):
  if e.event_id in edits: lines[e.first_line-1:e.last_line]=edits[e.event_id].splitlines()
 return '\n'.join(lines)+'\n'
def _remap(block,mapping):
 return re.sub(r'(?<![\w])-?\d+(?![\w])',lambda x:str(mapping.get(int(x[0]),int(x[0]))),block)

def patch_ludwig_at_cleric(destination: str, donor: str, ids: LudwigIds) -> str:
    """Adapt the normal two-phase fight without its source cutscene/warp.

    The three normal limb initializers are selected from the pinned constructor.
    Its alternate 13400999 branch belongs to the source encounter and is not
    transplanted. The transition copies the first actor's current floor/position;
    this is experimental arena behavior, not a claim of runtime equivalence.
    """
    from .boss_contracts import CLERIC_ARENA
    from .maria_contract import _verify, _replace_once, _noop
    d, s = _blocks(destination), _blocks(donor)
    _verify(d, CLERIC_ARENA.expected, 'Cleric arena')
    expected = dict(SOURCE_HASHES)
    # Installed 01.09 patch keeps the hidden second form updated every two
    # frames. Preserve that witnessed fix instead of replacing it with the
    # earlier research-bundle NoUpdate instruction.
    patched_health = '02a77d3081f5fa336ec6db647099ef975dd7bca6f38da26b9d6176564ff814ab'
    if _pin(s.get(13404802, '')) == patched_health:
        expected[13404802] = patched_health
    _verify(s, expected, 'Ludwig donor')
    if set(ids.event_ids) != set(EVENTS):
        raise ValueError('Ludwig requires every declared phase graph event')
    allocated = [*ids.event_ids.values(), ids.bridge_event, ids.phase_two_entity]
    if len(set(allocated)) != len(allocated) or any(x <= 0 for x in allocated):
        raise ValueError('Ludwig IDs must be positive and unique')
    used = {int(x) for x in re.findall(r'(?<![\w])-?\d+(?![\w])', destination)}
    if used.intersection(allocated):
        raise ValueError('Ludwig allocation collides with destination')
    mapping = {LUDWIG_ONE: CLERIC, LUDWIG_TWO: ids.phase_two_entity,
               9471: 12411700, 13401800: 12411700,
               13404802: 12414702, 13404803: 12414703, 13404804: 12414704,
               13404808: 12414700, 13404809: 12414701, 13404810: 12415400,
               3403802: 2413802, 3403803: 2413803, 3402802: 2412802,
               3400010: 2410010, **ids.event_ids}
    # Keep only the explicitly witnessed normal limb configuration. Copying
    # both branches would start two different routines in each identical slot.
    normal = s[0].split('    if (!EventFlag(13400999)) {\n        $InitializeEvent(0, 13404824);', 1)[1].split('    } else {', 1)[0]
    calls = []
    additions = []
    for old in EVENTS:
        constructor = normal if old == 13404830 else s[0]
        witnessed = [line.strip() for line in constructor.splitlines()
                     if re.search(rf'\$InitializeEvent\([^,]+,\s*{old}(?:,|\))', line)]
        if len(witnessed) != (3 if old == 13404830 else 1):
            raise ValueError('Ludwig exact normal initializer witness drift')
        calls.extend('    ' + _remap(line, mapping) for line in witnessed)
        body = s[old]
        if old in (13404820, 13404821, 13404822, 13404823):
            # Select the original normal threshold, rather than consulting
            # another arena's alternate encounter flag at runtime.
            body, count = re.subn(
                r'\(\(EventFlag\(13400999\) && HPRatio\(3400800\) < [0-9.]+\)\s*'
                r'\|\| \(!EventFlag\(13400999\) && HPRatio\(3400800\) < ([0-9.]+)\)\)',
                r'(HPRatio(3400800) < \1)', body)
            if count != 1:
                raise ValueError('Ludwig phase threshold witness drift')
        elif old == 13404824:
            body = _replace_once(body, '    SetEventFlag(9180, ON);\n', '', 'source cutscene flag')
        elif old == 13404825:
            first = body.index('    if (!HasMultiplayerState(MultiplayerState.Multiplayer)) {')
            last = body.index('    DisplayBossHealthBar(Disabled, 3400800, 0, 451000);', first)
            body = body[:first] + body[last:]
            body = _replace_once(body, '    SetEventFlag(9180, OFF);\n', '', 'source cutscene flag')
            body = _replace_once(body,
                '    ChangeCharacterEnableState(3400800, Disabled);\n    SetNetworkUpdateRate(3400801,',
                '    WarpCharacterAndCopyFloor(3400801, TargetEntityType.Character, 3400800, -1, 3400800);\n'
                '    ChangeCharacterEnableState(3400801, Enabled);\n'
                '    ChangeCharacterEnableState(3400800, Disabled);\n    SetNetworkUpdateRate(3400801,',
                'destination phase placement')
            for instruction in (
                '    CharacterWarpRequest(3400800, TargetEntityType.Area, 3402900, -1);\n',
                '    WarpCharacterAndCopyFloor(3400801, TargetEntityType.Area, 3402806, -1, 3400800);\n',
            ):
                body = _replace_once(body, instruction, '', 'source arena warp')
        additions.append(_remap(body, mapping))
    health = s[13404802]
    health = _replace_once(health,
        '    if (EventFlag(13400999)) {\n        SetSpEffect(3400800, 8040, false);\n'
        '        SetSpEffect(3400801, 8040, false);\n    }\n', '', 'alternate source health')
    health = _replace_once(health, 'WaitFor(EventFlag(13404808));',
        'WaitFor(EventFlag(13404808) || EventFlag(13404810));', 'Cleric entry lifecycle')
    health = _replace_once(health, '    SetCharacterAIState(3400801, Disabled);',
        '    SetCharacterAIState(3400801, Disabled);\n'
        '    if (!EventFlag(13404825)) {\n'
        '        ChangeCharacterEnableState(3400801, Disabled);\n    }', 'phase-two initial state')
    health = _remap(health, mapping)
    activation = _replace_once(d[12411702],
        '    ForceAnimationPlayback(2410800, 3028, false, false, false);\n', '', 'Cleric-only entry animation')
    music = _remap(s[13404803], mapping)
    camera = _remap(s[13404804], mapping).replace('SetLockcamSlotNumber(34, 0,', 'SetLockcamSlotNumber(24, 1,')
    helper = ids.phase_two_entity
    bridge = (f'$Event({ids.bridge_event}, Default, function() {{\n'
              f'    if (EventFlag(12411700)) {{\n'
              f'        ChangeCharacterEnableState({helper}, Disabled);\n'
              f'        ForceCharacterDeath({helper}, false);\n        EndEvent();\n    }}\n'
              f'    WaitFor(EventFlag(12414702));\n'
              f'    WaitFor(CharacterDead({CLERIC}) || CharacterDead({helper}));\n'
              f'    ForceCharacterDeath({CLERIC}, false);\n'
              f'    SetEventFlag({ids.bridge_event}, ON);\n'
              f'    WaitFor(EventFlag(12411700));\n'
              f'    ChangeCharacterEnableState({helper}, Disabled);\n'
              f'    ForceCharacterDeath({helper}, false);\n}});')
    calls.append(f'    $InitializeEvent(0, {ids.bridge_event});')
    zero = _replace_once(d[0], '    $InitializeEvent(0, 12414708);',
        '    $InitializeEvent(0, 12414708);\n' + '\n'.join(calls), 'Cleric constructor anchor')
    terminal = _replace_once(d[12411700], 'WaitFor(CharacterDead(2410800));',
        f'WaitFor(EventFlag({ids.bridge_event}));', 'Cleric terminal death predicate')
    edits = {0: zero, 12411700: terminal, 12411702: activation,
             12414702: health, 12414703: music, 12414704: camera,
             **{e: _noop(d[e]) for e in (12414707, 12414708, 12414710, 12414720)}}
    return _replace(destination, edits).rstrip() + '\n\n' + '\n\n'.join(additions + [bridge]) + '\n'


def native_plan_ludwig_at_cleric(slots: Sequence[Slot], npcs: Mapping[int, dict],
                                 effects: Mapping[int, dict], ids: LudwigIds, seed: str) -> dict:
    cleric = [slot for slot in slots if slot.entity_id == CLERIC
              and slot.archetype == Archetype('c5000', 500241, 500241, 0)]
    one = [slot for slot in slots if slot.entity_id == LUDWIG_ONE and slot.archetype == P1]
    two = [slot for slot in slots if slot.entity_id == LUDWIG_TWO and slot.archetype == P2]
    if (len(cleric) != 3 or len(one) != 1 or len(two) != 1
            or {slot.map_name for slot in cleric} != {'m24_01_00_00', 'm24_01_00_01', 'm24_01_00_11'}
            or one[0].map_name != 'm34_00_00_00' or two[0].map_name != one[0].map_name):
        raise ValueError('Ludwig requires exact primary, phase-two and all Cleric states')
    source, helper = one[0], two[0]
    swap = Swap(cleric[0].logical_key, [slot.key for slot in cleric],
                {slot.key: slot.archetype for slot in cleric}, cleric[0].archetype, P1,
                destinations={slot.key: {'map_name': slot.map_name, 'entity_id': slot.entity_id,
                              'x': slot.x, 'y': slot.y, 'z': slot.z} for slot in cleric})
    changes, skips = plan_scaling([swap], cleric, dict(npcs), dict(effects), boss_tiers=True)
    additions = [{
        'source_map': helper.map_name, 'source_part': helper.part_name,
        'source_anchor_part': source.part_name, 'source_entity_id': LUDWIG_TWO,
        'source_archetype': asdict(P2), 'source_talk_id': helper.talk_id,
        'destination_map': slot.map_name, 'destination_anchor_part': slot.part_name,
        'destination_part': ids.destination_part, 'destination_entity_id': ids.phase_two_entity,
        'allocation_evidence': ids.evidence,
    } for slot in cleric]
    initializations = [{
        'source_map': source.map_name, 'source_part': source.part_name,
        'source_entity_id': LUDWIG_ONE, 'source_archetype': asdict(P1),
        'destination_map': slot.map_name, 'destination_part': slot.part_name,
        'destination_entity_id': slot.entity_id,
    } for slot in cleric]
    return {
        'format': 'bb-enemizer-plan-v2', 'dry_run': True, 'seed': seed,
        'swap_count': 1, 'swaps': [swap.json()], 'boss_actor_additions': additions,
        'primary_init_source_bindings': initializations,
        'boss_contract': {
            'format': 'bb-ludwig-contract-v1', 'arena': 'cleric-beast', 'donor': 'ludwig',
            'runtime_status': 'unobserved', 'source_variant': 'normal-two-phase',
            'helper_scaling_status': 'requires boss_actor_scaling allocation in combined build',
            'phase_transition': 'destination actor floor; original source cutscene and warp omitted',
            'terminal_predicates': [{'event_id': 12411700, 'original_actor': CLERIC,
                                    'bridge_event_id': ids.bridge_event}],
            'event_ids': dict(ids.event_ids),
        },
        'scaling': {'enabled': bool(changes), 'mechanism': 'inferred_static_npc_clone_sp_effect',
                    'change_count': len(changes), 'changes': [change.json() for change in changes],
                    'skip_count': len(skips), 'skips': skips},
    }
