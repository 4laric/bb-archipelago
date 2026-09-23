"""Source-pinned removal of destination boss entrance cinematics.

The destination still owns the trigger, room notification, cutscene-control
flag, actor enablement, encounter-start flag, and progression.  Only the
original entrance ``PlayCutscene*`` instruction is replaced.  Combat phase
cinematics and post-defeat/endings live in other events and are outside this
policy.

For the four cutscenes which also warp, ``IssueShortWarpRequest`` combines a
source-witnessed local-player operand with the exact source-witnessed same-map
Area operand.  The MSB type and compiler surface are proven; gameplay
equivalence remains runtime-unproven and is recorded on each policy.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass

from .boss_canary import event_blocks, parse_events


@dataclass(frozen=True)
class EntranceEdit:
    instruction: str
    replacement: str
    count: int = 1


@dataclass(frozen=True)
class EntrancePolicy:
    event_file: str
    event_id: int
    source_sha256: str
    edits: tuple[EntranceEdit, ...] = ()
    relocation_regions: tuple[int, ...] = ()
    relocation_evidence: str | None = None

    @property
    def has_cinematic(self) -> bool:
        return bool(self.edits)


_FRAME = "WaitFixedTimeFrames(1);"


def _play(cutscene: int, mode: str) -> str:
    return f"PlayCutsceneToPlayer({cutscene}, CutscenePlayMode.{mode}, 10000);"


def _play_and_warp(cutscene: int, mode: str, region: int, area: int) -> str:
    return (
        f"PlayCutsceneAndWarpPlayer({cutscene}, CutscenePlayMode.{mode}, "
        f"{region}, {area}, 0, 10000);"
    )


def _short_warp(region: int) -> str:
    # Every destination is the exact same-map MSB Area operand used by the
    # removed PlayCutsceneAndWarpPlayer instruction.  Entity 10000 is the
    # original local-player operand.
    return f"IssueShortWarpRequest(10000, TargetEntityType.Area, {region}, -1);"


# Complete AP boss-arena census.  Entries with no edits prove that their
# original activation event has no entrance cinematic and must stay unchanged.
ENTRANCE_POLICIES: dict[str, EntrancePolicy] = {
    "cleric-beast": EntrancePolicy(
        "m24_01_00_00.emevd.dcx.js", 12411702,
        "702380b92bd2632ce4ff9527009f8c7209fffff89297bc38d8fb8d108655eaff"),
    "blood-starved-beast": EntrancePolicy(
        "m23_00_00_00.emevd.dcx.js", 12301802,
        "c8e1b3b8b94fe800a158228a1b177c944c90883fc45826b5060488a064ca145d"),
    "darkbeast-paarl": EntrancePolicy(
        "m23_00_00_00.emevd.dcx.js", 12301702,
        "374db59c960671a66ac7afdd712cc0576d03a554ec7ca3d74f0902799bfd517d"),
    "vicar-amelia": EntrancePolicy(
        "m24_00_00_00.emevd.dcx.js", 12401802,
        "b869911c8ee05015b1b90d6fcac40ae0f492433ce83f0f2629e4973cdfbbcde0",
        (EntranceEdit(_play(24000060, "Skippable"), _FRAME),
         EntranceEdit(_play(24000060, "Unskippable"), _FRAME))),
    "amygdala": EntrancePolicy(
        "m33_00_00_00.emevd.dcx.js", 13301802,
        "dbf7c452ecf425a41d9c724ba0568db015224bb1a3b1516c9033779c59c1d3ae"),
    "ebrietas": EntrancePolicy(
        "m24_02_00_00.emevd.dcx.js", 12421802,
        "9bc79c8e55c2a2c9793a90070de1f76c35a46ebd98c2c79176b2fcc02ae8adc4"),
    "lady-maria": EntrancePolicy(
        "m35_00_00_00.emevd.dcx.js", 13501801,
        "0fb99b1b7c02f3fb5ff2d4990ad8a6a24982278077675d19ef675f4df767fc31",
        (EntranceEdit(
            _play_and_warp(35000010, "Skippable", 3502808, 35),
            _short_warp(3502808), 2),),
        (3502808,), "source-composed; runtime-unproven"),
    "laurence": EntrancePolicy(
        "m34_00_00_00.emevd.dcx.js", 13401851,
        "c9bb7c19e16ebdc391bc1552e9328dd41d25bdc968701b2e1182506f940f255d",
        (EntranceEdit(
            _play_and_warp(34000010, "Skippable", 3402856, 34),
            _short_warp(3402856)),
         EntranceEdit(
            _play_and_warp(34000010, "Unskippable", 3402856, 34),
            _short_warp(3402856)),
         # The original multiplayer-client branch does not relocate the client.
         EntranceEdit(_play(34000010, "Unskippable"), _FRAME)),
        (3402856,), "source-composed; runtime-unproven"),
    "ludwig": EntrancePolicy(
        "m34_00_00_00.emevd.dcx.js", 13401801,
        "512227ef549cf14ead83ae803efb7f73294b7f406abea9c940b8b49a6d5f26bd",
        (EntranceEdit(_play(34000020, "Skippable"), _FRAME),
         EntranceEdit(_play(34000020, "Unskippable"), _FRAME, 2))),
    "orphan-of-kos": EntrancePolicy(
        "m36_00_00_00.emevd.dcx.js", 13601801,
        "a1e52549f15c53a6e55e4aeafb2f21cf863e1a267d58b9121695241118f2de78",
        (EntranceEdit(_play(36000000, "Skippable"), _FRAME),
         EntranceEdit(_play(36000000, "Unskippable"), _FRAME))),
    "martyr-logarius": EntrancePolicy(
        "m25_00_00_00.emevd.dcx.js", 12501802,
        "91d992106cdd9de1298ea848def19f816af24302f50dbf56f67cf5f5932c2e71",
        (EntranceEdit(_play(25000020, "Skippable"), _FRAME),
         EntranceEdit(_play(25000020, "Unskippable"), _FRAME))),
    "father-gascoigne": EntrancePolicy(
        "m24_01_00_00.emevd.dcx.js", 12411802,
        "f803bd5dfa427d7e8e80ed46fe4f346973ad5c9ae090d481c005d4bff10eba78",
        (EntranceEdit(_play(24010010, "Skippable"), _FRAME),
         EntranceEdit(_play(24010010, "Unskippable"), _FRAME))),
    "mergos-wet-nurse": EntrancePolicy(
        "m26_00_00_00.emevd.dcx.js", 12601802,
        "52825c64ffb75fcaf36996c80617c618c58182e0f0b34b74f7f5dc33dcf64864",
        (EntranceEdit(_play(26000010, "Skippable"), _FRAME),
         EntranceEdit(_play(26000010, "Unskippable"), _FRAME))),
    "witch-of-hemwick": EntrancePolicy(
        "m22_00_00_00.emevd.dcx.js", 12201802,
        "02cd835b56665e1eb6f2ceb9252ef6d3c92fdf468180918348d8bbf54e13c3b3"),
    "living-failures": EntrancePolicy(
        "m35_00_00_00.emevd.dcx.js", 13501851,
        "016b1ad769f7d2418e1e21b389723b3c0c2638f6a7586dbc5d22212532e6ad09"),
    "rom": EntrancePolicy(
        "m32_00_00_00.emevd.dcx.js", 13201802,
        "9ac690a52a2c21af5b5469de792caab012a501463ae8728261636b49e34fc444"),
    "celestial-emissary": EntrancePolicy(
        "m24_02_00_00.emevd.dcx.js", 12421702,
        "e5832b29e358dfe905ab5d47a0c23a84283f9b645dddecaf9a0e7e7ff56ed726"),
    "micolash": EntrancePolicy(
        "m26_00_00_00.emevd.dcx.js", 12601852,
        "1f584b3150d603147023e28cf6ad672b63c8ed4397b7d976e9e2017bfa397aef",
        (EntranceEdit(_play(26000060, "Skippable"), _FRAME),
         EntranceEdit(_play(26000060, "Unskippable"), _FRAME))),
    "the-one-reborn": EntrancePolicy(
        "m28_00_00_00.emevd.dcx.js", 12801802,
        "a91ed2bd9c33333b7d6549bca707ae31bd5516b473576363405c712d8ac16b13",
        (EntranceEdit(_play(28000000, "Skippable"), _FRAME),
         EntranceEdit(_play(28000000, "Unskippable"), _FRAME))),
    "shadows-of-yharnam": EntrancePolicy(
        "m27_00_00_00.emevd.dcx.js", 12701802,
        "44f2363adb49d6ce98ba68186988c55b9d086770fb4c8e99759f1f48dbfcc28b"),
    "gehrman": EntrancePolicy(
        "m21_00_00_00.emevd.dcx.js", 12101802,
        "9cb093d3e0aee513b4e2500b0b0a9a1e658c039b52e497eafa596a8752ccd26f",
        (EntranceEdit(
            _play_and_warp(21000040, "Skippable", 2102808, 21),
            _short_warp(2102808)),),
        (2102808,), "source-composed; runtime-unproven"),
    "moon-presence": EntrancePolicy(
        "m21_00_00_00.emevd.dcx.js", 12101852,
        "0bde50f079f63078dd127d785f34e8ebdd8fce5cdaf44f5f5581fb69c01df3fb",
        (EntranceEdit(
            _play_and_warp(21000050, "Skippable", 2102809, 21),
            _short_warp(2102809)),
         EntranceEdit(
            _play_and_warp(21000050, "Unskippable", 2102809, 21),
            _short_warp(2102809))),
        (2102809,), "source-composed; runtime-unproven",
    ),
}


def _replace_event(source: str, event_id: int, replacement: str) -> str:
    matches = [event for event in parse_events(source) if event.event_id == event_id]
    if len(matches) != 1:
        raise ValueError(f"entrance policy expected one event {event_id}")
    event = matches[0]
    newline = "\r\n" if "\r\n" in source else "\n"
    lines = source.splitlines()
    lines[event.first_line - 1:event.last_line] = replacement.splitlines()
    return newline.join(lines) + (newline if source.endswith(("\n", "\r")) else "")


def skip_replacement_entrance(arena_key: str, original: str, patched: str) -> str:
    """Skip one destination entrance cinematic while preserving its lifecycle."""
    if arena_key not in ENTRANCE_POLICIES:
        raise ValueError(f"no entrance policy for arena {arena_key}")
    policy = ENTRANCE_POLICIES[arena_key]
    original_blocks = event_blocks(original)
    source_body = original_blocks.get(policy.event_id)
    if (source_body is None
            or hashlib.sha256(source_body.encode("utf-8")).hexdigest()
            != policy.source_sha256):
        raise ValueError(
            f"unsupported original {arena_key} entrance event {policy.event_id}"
        )

    source_calls = tuple(
        line.strip() for line in source_body.splitlines() if "PlayCutscene" in line
    )
    expected_calls = tuple(
        edit.instruction for edit in policy.edits for _ in range(edit.count)
    )
    if sorted(source_calls) != sorted(expected_calls):
        raise ValueError(f"{arena_key} entrance cinematic witness drift")

    if not policy.edits:
        patched_body = event_blocks(patched).get(policy.event_id)
        if patched_body is None or "PlayCutscene" in patched_body:
            raise ValueError(f"{arena_key} adapter introduced an entrance cinematic")
        return patched

    patched_blocks = event_blocks(patched)
    body = patched_blocks.get(policy.event_id)
    if body is None:
        raise ValueError(f"patched source lacks entrance event {policy.event_id}")
    present = [body.count(edit.instruction) for edit in policy.edits]
    expected = [edit.count for edit in policy.edits]
    if present == [0] * len(policy.edits):
        if "PlayCutscene" in body:
            raise ValueError(f"{arena_key} adapter changed the entrance cinematic")
        relocations = Counter(
            edit.replacement
            for edit in policy.edits
            for _ in range(edit.count)
            if edit.replacement.startswith("IssueShortWarpRequest")
        )
        for instruction, count in relocations.items():
            if body.count(instruction) < count:
                raise ValueError(f"{arena_key} adapter removed required player relocation")
        return patched
    if present != expected:
        raise ValueError(f"{arena_key} adapter partially changed the entrance cinematic")

    adapted = body
    for edit in policy.edits:
        adapted = adapted.replace(edit.instruction, edit.replacement)
    if "PlayCutscene" in adapted:
        raise ValueError(f"{arena_key} entrance retains a cutscene instruction")
    result = _replace_event(patched, policy.event_id, adapted)
    result_blocks = event_blocks(result)
    for event_id, block in patched_blocks.items():
        if event_id != policy.event_id and result_blocks.get(event_id) != block:
            raise ValueError(f"entrance policy changed unrelated event {event_id}")
    return result
