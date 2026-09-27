"""Destination-owned bounds for shuffled boss activation.

Location witnesses are pinned original music events. Apply after a donor
adapter, before merging map variants: only that encounter's changed events
and primary health event are eligible, so neighboring vanilla encounters and
completion/reward events remain untouched.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from .boss_canary import event_blocks, parse_events


@dataclass(frozen=True)
class ArenaActivationPolicy:
    event_file: str
    music_event: int
    health_event: int
    actor: int
    start_flag: int
    entry_event: int
    source_sha256: str
    predicate: str
    witnesses: tuple[str, ...]


ACTIVATION_POLICIES: dict[str, ArenaActivationPolicy] = {
    'amygdala': ArenaActivationPolicy(
        'm33_00_00_00.emevd.dcx.js', 13304803, 13304802, 3300800, 13304800, 13304980,
        '0f6aa448c5c4af20db4b5069bdce6516c2bc4d4f5b1ed5ccb1653bd47f18ccaf',
        'PlayerInMap(33, 0) && InArea(10000, 3302802)', ('InArea(10000, 3302802)',)),
    'blood-starved-beast': ArenaActivationPolicy(
        'm23_00_00_00.emevd.dcx.js', 12304803, 12304802, 2300800, 12304800, 12304980,
        'f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1',
        'PlayerInMap(23, 0) && InArea(10000, 2302801)', ('InArea(10000, 2302801)',)),
    'celestial-emissary': ArenaActivationPolicy(
        'm24_02_00_00.emevd.dcx.js', 12424703, 12424702, 2420810, 12424700, 12424982,
        'a73cb1fa43c1017779bc8c9c97fd6cfd51726dccdc4bf865dd8096b86b81a3c4',
        'PlayerInMap(24, 2) && InArea(10000, 2422812)', ('InArea(10000, 2422812)',)),
    'cleric-beast': ArenaActivationPolicy(
        'm24_01_00_00.emevd.dcx.js', 12414703, 12414702, 2410800, 12414700, 12414980,
        '115ae8dc85c184a4dfe729eaef337b01ea0bcffc7a34ec0dde3f343dcbeb5c14',
        'PlayerInMap(24, 1) && InArea(10000, 2412801)', ('InArea(10000, 2412801)',)),
    'darkbeast-paarl': ArenaActivationPolicy(
        'm23_00_00_00.emevd.dcx.js', 12304703, 12304702, 2300810, 12304700, 12304981,
        'e425e391e28c7dae502e70533be953a18976657b4ab3f5ba328bf4304840e825',
        'PlayerInMap(23, 0) && InArea(10000, 2302812)', ('InArea(10000, 2302812)',)),
    'ebrietas': ArenaActivationPolicy(
        'm24_02_00_00.emevd.dcx.js', 12424803, 12424802, 2420800, 12424800, 12424981,
        'a487e349f0a416298a26fb93c87c0c57fd7211e7da3da8938d37b6e909130966',
        'PlayerInMap(24, 2) && InArea(10000, 2422802)', ('InArea(10000, 2422802)',)),
    'father-gascoigne': ArenaActivationPolicy(
        'm24_01_00_00.emevd.dcx.js', 12414803, 12414802, 2410810, 12414800, 12414981,
        'a6b50e5c86a3b2471166de37c25da11361053e96065b263c7220913f79399150',
        'PlayerInMap(24, 1) && InArea(10000, 2412812)', ('InArea(10000, 2412812)',)),
    'gehrman': ArenaActivationPolicy(
        'm21_00_00_00.emevd.dcx.js', 12104803, 12104802, 2100800, 12104800, 12104980,
        '159ec5935e3770580344462a984ae2322ce8e367e996abe428d98856a66d1ce7',
        'PlayerInMap(21, 0) && InArea(10000, 2102802)', ('InArea(10000, 2102802)',)),
    'lady-maria': ArenaActivationPolicy(
        'm35_00_00_00.emevd.dcx.js', 13504803, 13504802, 3500800, 13504808, 13504980,
        '4b68b33578063025a63792c05c886b4c9afc63404b65acfb3a80efbc83d83239',
        'PlayerInMap(35, 0) && InArea(10000, 3502802)', ('InArea(10000, 3502802)',)),
    'laurence': ArenaActivationPolicy(
        'm34_00_00_00.emevd.dcx.js', 13404853, 13404852, 3400850, 13404858, 13404980,
        '6d373eb2995d299bd4008cbc5c7fa72a0d77823ed62129af6916a4ad0235ce7a',
        'PlayerInMap(34, 0) && InArea(10000, 3402852)', ('InArea(10000, 3402852)',)),
    'living-failures': ArenaActivationPolicy(
        'm35_00_00_00.emevd.dcx.js', 13504853, 13504852, 3500851, 13504858, 13504981,
        '5385ba65580ca716f6a460aa1388f94828fe21e37337c6a8ba343636bd23bd64',
        'PlayerInMap(35, 0) && InArea(10000, 3502812)', ('InArea(10000, 3502812)',)),
    'ludwig': ArenaActivationPolicy(
        'm34_00_00_00.emevd.dcx.js', 13404803, 13404802, 3400800, 13404808, 13404981,
        'ee69949f3bf2119d6cb051e41abfed11c5de83b306f9a9e36a6b42df182745ba',
        'PlayerInMap(34, 0) && InArea(10000, 3402802)', ('InArea(10000, 3402802)',)),
    'martyr-logarius': ArenaActivationPolicy(
        'm25_00_00_00.emevd.dcx.js', 12504803, 12504802, 2500800, 12504800, 12504980,
        'edee08431133d70220856551eb1b4518e7e8898c80fcbde9448a81537e9a7e0a',
        'PlayerInMap(25, 0) && InArea(10000, 2502802)', ('InArea(10000, 2502802)',)),
    'mergos-wet-nurse': ArenaActivationPolicy(
        'm26_00_00_00.emevd.dcx.js', 12604803, 12604802, 2600800, 12604800, 12604982,
        '398aca1f47084e02f0d84294bd86de6c1ea857628d2e20a538974468b5660396',
        'PlayerInMap(26, 0) && InArea(10000, 2602801)', ('InArea(10000, 2602801)',)),
    'micolash': ArenaActivationPolicy(
        'm26_00_00_00.emevd.dcx.js', 12604853, 12604852, 2600850, 12604850, 12604981,
        'd1f257fd7d39dfee586737b765bc62d760471d2f4cc79b2448ccfe920e513548',
        'PlayerInMap(26, 0) && InArea(10000, 2602852)', ('InArea(10000, 2602852)',)),
    'moon-presence': ArenaActivationPolicy(
        'm21_00_00_00.emevd.dcx.js', 12104853, 12104852, 2100810, 12104850, 12104981,
        '38b0df8eb0fb98bdf5e9e5f2c752f5220ffe23b35e5645e53eebad46e42adce4',
        'PlayerInMap(21, 0) && InArea(10000, 2102801)', ('InArea(10000, 2102801)',)),
    'orphan-of-kos': ArenaActivationPolicy(
        'm36_00_00_00.emevd.dcx.js', 13604803, 13604802, 3600800, 13604808, 13604980,
        'f6754136d8003799fd8c001053980bb67f25b033108b690852d0b0aedd128e72',
        'PlayerInMap(36, 0) && InArea(10000, 3602802)', ('InArea(10000, 3602802)',)),
    'rom': ArenaActivationPolicy(
        'm32_00_00_00.emevd.dcx.js', 13204803, 13204802, 3200800, 13204800, 13204980,
        '5ef611fa7eea1582d3d5395d2f8507075aecc92fde3c1c23edcc77c092d9901d',
        'PlayerInMap(32, 0) && InArea(10000, 3202801)', ('InArea(10000, 3202801)',)),
    'shadows-of-yharnam': ArenaActivationPolicy(
        'm27_00_00_00.emevd.dcx.js', 12704803, 12704802, 2700800, 12704800, 12704980,
        '7ad45bce51000cc00388884064813e4c082ec40c1b66d137450910d8c1adac42',
        'PlayerInMap(27, 0) && InArea(10000, 2702802)', ('InArea(10000, 2702802)',)),
    'the-one-reborn': ArenaActivationPolicy(
        'm28_00_00_00.emevd.dcx.js', 12804803, 12804802, 2800800, 12804800, 12804980,
        'd9fe3eab4eeb93fcc5e13e719399de18dafe7583b527aaa9d648f355a9b39130',
        'PlayerInMap(28, 0) && InArea(10000, 2802802)', ('InArea(10000, 2802802)',)),
    'vicar-amelia': ArenaActivationPolicy(
        'm24_00_00_00.emevd.dcx.js', 12404803, 12404802, 2400800, 12404800, 12404980,
        '13b0d9be89ea9bd0e8d385c24275a42bb9b6e97891b4caa9e1ee639bd3d09700',
        'PlayerInMap(24, 0) && InArea(10000, 2402802)', ('InArea(10000, 2402802)',)),
    'witch-of-hemwick': ArenaActivationPolicy(
        'm22_00_00_00.emevd.dcx.js', 12204803, 12204802, 2200800, 12204800, 12204980,
        'd41f4a63d537c30c94cd4ff4208df30b98a989f25d45e9118525cd54d7963caf',
        'PlayerInMap(22, 0) && InArea(10000, 2202801)', ('InArea(10000, 2202801)',)),
}


def arena_entry_predicate(arena_key: str) -> str:
    try:
        return ACTIVATION_POLICIES[arena_key].predicate
    except KeyError as exc:
        raise ValueError(f"No reviewed activation bounds for {arena_key}") from exc


def guard_shuffled_activation(arena, original: str, patched: str) -> str:
    policy = ACTIVATION_POLICIES[arena.key]
    before, after = event_blocks(original), event_blocks(patched)
    witness = before[policy.music_event]
    if hashlib.sha256(witness.encode()).hexdigest() != policy.source_sha256:
        raise ValueError(f"{arena.key} activation location source drift")
    if any(value not in witness for value in policy.witnesses):
        raise ValueError(f"{arena.key} activation location witness missing")
    owned = {eid for eid, body in after.items() if before.get(eid) != body}
    owned.add(policy.health_event)
    display = re.compile(r"DisplayBossHealthBar\(Enabled, (\d+),")
    actors = {int(m[1]) for eid in owned for m in display.finditer(after[eid])}
    actors.update(int(value) for value in re.findall(
        r"SetCharacterAIState\((\d+), Enabled\)", after[policy.health_event]))
    if not actors:
        raise ValueError(f"{arena.key} shuffled encounter has no health-bar owner")
    # These explicit IDs stay in the original arena's live-backed flag bank.
    # Reserve against all donor/source literals, including helper allocations.
    flag = policy.entry_event
    marker = f"    $InitializeEvent(0, {flag});"
    existing = after.get(flag)
    latch = (f"$Event({flag}, Default, function() {{\n"
             f"    WaitFor(EventFlag({policy.start_flag}) && ({policy.predicate}));\n"
             "});")
    if existing is not None:
        if existing != latch or marker not in after[0]:
            raise ValueError(f"{arena.key} activation latch collision")
    elif re.search(rf"(?<![\w]){flag}(?![\w])", original + patched):
        raise ValueError(f"{arena.key} activation latch collision")
    edits = {}
    for eid in owned:
        body = after[eid]
        # A streamed-out actor can report zero HP. Positive phase thresholds
        # must be evaluated while the encounter is entered and the actor live;
        # death predicates (<= 0) deliberately keep their separate semantics.
        threshold = re.compile(r"HPRatio\((\d+)\)\s*(<=?)\s*(\d+(?:\.\d+)?)\b")
        def live_threshold(match):
            actor = int(match[1])
            if actor not in actors or not 0 < float(match[3]) <= 1:
                return match[0]
            return (f"(EventFlag({flag}) && CharacterBackreadStatus({actor}) "
                    f"&& HPRatio({actor}) > 0 && {match[0]})")
        if existing is None:
            body = threshold.sub(live_threshold, body)
        lines = body.splitlines()
        output = []
        for line in lines:
            match = re.search(r"(?:DisplayBossHealthBar\(Enabled, |SetCharacterAIState\()(\d+),", line)
            enables_ai = "SetCharacterAIState(" in line and ", Enabled);" in line
            notification = eid == policy.health_event and "IssueBossRoomEntryNotification(" in line
            if notification or (match and int(match[1]) in actors and (display.search(line) or enables_ai)):
                indent = line[:len(line)-len(line.lstrip())]
                condition = (policy.predicate if eid == policy.health_event else
                             f"EventFlag({flag}) && {policy.predicate.split(' && ')[0]}")
                gate = f"{indent}WaitFor({condition});"
                if not output or output[-1] != gate:
                    output.append(gate)
            output.append(line)
        body = "\n".join(output)
        if body != after[eid]:
            edits[eid] = body
    if existing is None:
        constructor = edits.get(0, after[0])
        header = constructor.splitlines()[0] + "\n"
        constructor = constructor.replace(header, header +
            f"    SetEventFlag({flag}, OFF);\n", 1)
        end = constructor.rfind("\n});")
        if end < 0:
            raise ValueError("malformed activation constructor")
        edits[0] = constructor[:end] + "\n" + marker + constructor[end:]
    lines = patched.splitlines()
    for event in reversed(parse_events(patched)):
        if event.event_id in edits:
            lines[event.first_line-1:event.last_line] = edits[event.event_id].splitlines()
    result = "\n".join(lines) + "\n"
    if existing is None:
        result += "\n" + latch + "\n"
    return result
