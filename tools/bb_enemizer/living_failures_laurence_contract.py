"""Living Failures combat overlay for Laurence's single-body destination arena.

This module retains Laurence's terminal, fog, entry cutscene and rewards.  It
transplants the documented six-actor Living Failures formation, its generator
wave graph, camera and music controllers.  The five source MapSFX records are
an explicit future native requirement: their MSBB records are witnessed, but
the current writer has no SFX transplantation path or approved FFX resource
closure.  Static source and compiler evidence does not establish runtime fit.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_canary import event_blocks
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
DONOR_SOURCE = "event/m35_00_00_00.emevd.dcx.js"
ARENA_SOURCE = "event/m34_00_00_00.emevd.dcx.js"

PROXY, BODY_ONE, BODY_TWO, BODY_THREE, BODY_FOUR, SUPPORT = (
    3500850,
    3500851,
    3500852,
    3500853,
    3500854,
    3500860,
)
LAURENCE = 3400850
COMPLETION = 13401850

BODY_ONE_ARCHETYPE = Archetype("c4030", 403000, 403000, 0)
PROXY_ARCHETYPE = Archetype("c4030", 403050, 1, 0)
BODY_TWO_ARCHETYPE = Archetype("c4030", 403010, 403010, 0)
BODY_THREE_ARCHETYPE = Archetype("c4030", 403020, 403020, 0)
BODY_FOUR_ARCHETYPE = Archetype("c4030", 403030, 403030, 0)
SUPPORT_ARCHETYPE = Archetype("c4031", 403100, 403100, 0)
LAURENCE_ARCHETYPE = Archetype("c4500", 450000, 450000, 0)

EVENT_MIN, EVENT_MAX = 12992000, 12992099
ACTOR_IDS = (980008, 980009, 980010, 980011, 980012)
GENERATOR_ENTITY_IDS = (980013, 980014, 980015, 980016)
GENERATOR_EVENT_IDS = (980023, 980024, 980025, 980026)
SFX_ENTITY_IDS = (980027, 980028, 980029, 980030, 980031)
SFX_EVENT_IDS = (980032, 980033, 980034, 980035, 980036)

DONOR_HASHES = {
    # The installed CUSA03173 01.09 decompilation differs only by an
    # unrelated Event(0) normalization. Both original bodies are pinned.
    0: (
        "f7acdb00c7384ac586de81b0c37e7e58d08c11876c76a04a9648844f4689d0a9",
        "78d94eb81ed0b21b0f7a14aaaefc5f5ec487d28e3029e8912e6551dd71d2cf50",
    ),
    13504852: "2c85d01e33eeec23bed4c9bc483963fd7f955443a7ee440356c909b3d5d7791e",
    13504853: "5385ba65580ca716f6a460aa1388f94828fe21e37337c6a8ba343636bd23bd64",
    13504854: "89743ba1d4c316b756d5c0d1f9b2b88fac0cb1adea48fc9e478ff17dd7631cfc",
    13504865: "c3ab637d4af4fc24cbeedde16f099ad50f1e8c2425d4ffbc15eb9900b9faa2ce",
    13504880: "eae0b65165cb984da0c3fcbb6c9b5c41d2d6b8212b5bb08e22930a29bccf9665",
    13504881: "1f43eccdd0539ab63a6f8eed248465fbbcbfa60bff1754dd608290784d1b1aec",
    13504885: "291d0ef2d64fecc6a8cd53062b44a306a597904397d6ce38417a64487db79d83",
    13504890: "b0004862a666a1854c3aba4a8c91d9156436438230c641f135aba30c26415388",
    13504895: "f3c5fdbaf791591392fdcdf79c3c99bf9571a962016c75d6ae3040fc6dfd733a",
    13505655: "7c6514d959890ac80969f9f1a3f1398ee102e2409ddb050fb2b9cdfdae537637",
    13505656: "d39373dc11ff84ded0a4de3e246325e7f46ddf197ee71b69f1c8ea7bd3eb83b7",
    13505661: "3dca956d1a60d3e53c851b84144710923dd5d0c98c9dc87f54c7dd276b066e4a",
    13505662: "e8b466710c0de022e6f0f561a0a0689afc03f88eb16d59144a18a37bb1f7cefd",
    13505680: "3bd8f41292a02f99878b780f87b10c32d6925b7027ebd7d9a01ba41eb22015c9",
}

ARENA_HASHES = {
    0: "3772e9c2957d38bcdbc984631dab0033deaef57c1d092a8c77005cdd4d7c1d55",
    13401800: "15c6ba33b2df44b9fdc67ea470d1f32281bac11a588ba6c876de7ac85df5d8dd",
    13401850: "dc390d680718c54d8a214a4d1ed0def18b7c110df7dd19a6862b436a2dcd6b44",
    13401851: "c9bb7c19e16ebdc391bc1552e9328dd41d25bdc968701b2e1182506f940f255d",
    13404852: "a55956b498c3908a0febf99daf2013e6d59eea5885a5ac837a3735f09d356470",
    13404853: "6d373eb2995d299bd4008cbc5c7fa72a0d77823ed62129af6916a4ad0235ce7a",
    13404854: "67283d0f1600a008235ffc109219ab98ee5028814738d45724c397bf4519430f",
    13404855: "e11b2c88da282d31e4a68f6c53606aa3b8b07b85025074c800db31937e0ea780",
    13404861: "7888497bc33ab25bdc668813a50cbc6a3ad44c2d6321b05fecdf4c500a297f7e",
    13404870: "237a55077776ca3b72ea95aee40b8da9655bf8f93d15315400b3d1f1eb8471be",
    13404875: "e5fb7120dd1c7759f763c39f7c04a1b01ba966dcb2ce48f9bc4f5e1331a57822",
}

PART_PINS = {
    PROXY: "ea596036d27313cb14f09921e698351fb97de32ce37fcab291d10f5dfcc2abbf",
    BODY_ONE: "ce7dd47b6bef551d18e340282ae6409f1920020d1ac36e85dc634f477caf51b6",
    BODY_TWO: "77607d287e7e2e2e2f282f22c8b78aa634a6ba6577a1c830b27420f86e095eea",
    BODY_THREE: "706a81c500efc571356102e5adc0a8ba3e081e64e063fc7d5d5c68bbb056f366",
    BODY_FOUR: "63e33c77647f60713d39de7f80b1f4dabca1b9856446843a9e9c9a69643663d4",
    SUPPORT: "5df657d5b8ea855cfd14b59cbd8a54c46ea41ebe0b8a5df7da67b6b0c3e360e8",
}
LAURENCE_PIN = "cdf84241072ed9304f89d145ca746572548edf26bcd5c80e571d3237e0e7a12c"
COLLISION_PIN = "d41ff91fe3070e8e5a6a662a71626db19f67130ba67faab0f24bac3817433d35"

GENERATOR_PINS = (
    (
        3503814,
        131,
        "851b36d8c9199d5f99939379b8bc52fd87f2427658d5ebe1ab5ac21e8a9c9d75",
        "患者Bジェネレーター1",
        "Event_ボス1_患者B_ジェネレートポイント2",
        "c4030_0000",
    ),
    (
        3503815,
        38,
        "5de3a2e98ef163a9e11c3ffd6331bd86f46ce3d0a9b043d11db42634f4cae464",
        "患者Bジェネレーター2",
        "Event_ボス1_患者B_ジェネレートポイント3",
        "c4030_0001",
    ),
    (
        3503816,
        39,
        "1ede849ae8e17f96c5a4ad69472b7daeed5837f4cdc5a57f9517efdddf118963",
        "患者Bジェネレーター3",
        "Event_ボス1_患者B_ジェネレートポイント4",
        "c4030_0002",
    ),
    (
        3503817,
        52,
        "76efcf2a792ef179084ace5f79eb347f44a002740275f78f0a4c0e1366be4c75",
        "患者Bジェネレーター4",
        "Event_ボス1_患者B_ジェネレートポイント1",
        "c4030_0003",
    ),
)
SFX_PINS = (
    (
        "SFX_患者B宇宙作成Lv1",
        144,
        3503850,
        640320,
        "783f24c3e8366115a2805e72032b17169a01a070cc83dd77259406a4e732465f",
    ),
    (
        "SFX_患者B宇宙作成Lv2",
        145,
        3503851,
        640321,
        "0e0d205fb5a9dc92747ebcd1913c4dca66cfc446e13fd4dd9bd88967b84e1d8f",
    ),
    (
        "SFX_患者B宇宙作成Lv3",
        146,
        3503852,
        640322,
        "7d919e7edae105559171d65a86bf36714f498ad85a9b64eb4dfd763943364873",
    ),
    (
        "SFX_患者B宇宙作成Lv4",
        147,
        3503853,
        640323,
        "2b1540b3ea0dc6ef71a656d1770311e9ccf61a405128fc425dbfa3441ceb35e4",
    ),
    (
        "SFX_患者B宇宙作成Lv5",
        148,
        3503854,
        640324,
        "d6188d222cb79cf8bd73e89b9d856d876b2451df9ce76a059d1df05241608377",
    ),
)

REGION_PINS = {
    "Event_ボス1_患者B_ジェネレートポイント1": "1ce593f12a4fdbc8028d75d22d58a08571d486e747119fa03d9a96eb6a8be646",
    "Event_ボス1_患者B_ジェネレートポイント2": "8075a9a7984f0c7517a7bc2bb1acfe5250e3a7692765ac234af28b5646a1ccc5",
    "Event_ボス1_患者B_ジェネレートポイント3": "8b219db78cffe2ae896e10611c7f6c181d271a63be9ebca5c23cad7a4be48f73",
    "Event_ボス1_患者B_ジェネレートポイント4": "702f28e7f6dceef857bbdbf5698f2f1a10202a28da42b7d82f0708d7febfddeb",
    "SFX_患者B宇宙作成": "ab9664b9a84f18429a12cf3b5e9864dfbbb429bab3b31899ca7d6dd6e8f291b4",
}


@dataclass(frozen=True)
class LivingFailuresLaurenceIds:
    player_effect: int = 12992000
    wave_selection: int = 12992001
    wave_commands: int = 12992002
    wave_animation: int = 12992003
    death_cleanup: int = 12992004
    generator_schedule: int = 12992005
    combat_tracker: int = 12992006
    combat_counter: int = 12992007
    generator_controller: int = 12992008
    support_controller: int = 12992009
    wave_reset: int = 12992010
    lifecycle_cleanup: int = 12992011
    phase_music_flag: int = 12992020
    generator_enable_flag: int = 12992021
    generator_phase_flag: int = 12992022
    wave_flags_start: int = 12992023
    wave_flags_end: int = 12992028
    scheduler_active_flag: int = 12992029
    combat_count_value: int = 12992030
    support_count_value: int = 12992033
    proxy_entity: int = 980008
    body_two_entity: int = 980009
    body_three_entity: int = 980010
    body_four_entity: int = 980011
    support_entity: int = 980012
    evidence: str = (
        "Living Failures/Laurence allocation v1; full original EMEVD operand and MSBB entity scan"
    )

    def event_values(self) -> tuple[int, ...]:
        return (
            self.player_effect,
            self.wave_selection,
            self.wave_commands,
            self.wave_animation,
            self.death_cleanup,
            self.generator_schedule,
            self.combat_tracker,
            self.combat_counter,
            self.generator_controller,
            self.support_controller,
            self.wave_reset,
            self.lifecycle_cleanup,
        )

    def added_entities(self) -> tuple[int, ...]:
        return (
            self.proxy_entity,
            self.body_two_entity,
            self.body_three_entity,
            self.body_four_entity,
            self.support_entity,
            *GENERATOR_ENTITY_IDS,
            *GENERATOR_EVENT_IDS,
            *SFX_ENTITY_IDS,
            *SFX_EVENT_IDS,
        )


DEFAULT_IDS = LivingFailuresLaurenceIds()


def _verify(
    blocks: Mapping[int, str],
    pins: Mapping[int, str | tuple[str, ...]],
    role: str,
) -> None:
    for event, digest in pins.items():
        allowed = (digest,) if isinstance(digest, str) else digest
        actual = hashlib.sha256(blocks.get(event, "").encode()).hexdigest()
        if actual not in allowed:
            raise ValueError(f"unsupported original {role} event {event}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Living Failures/Laurence expected one {label}")
    return text.replace(old, new, 1)


def _end_event(block: str) -> str:
    header = block.splitlines()[0]
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            (
                item.strip()
                if item.strip().startswith("unused_")
                else "unused_" + item.strip()
            )
            for item in match[1].split(",")
            if item.strip()
        )
        + ")",
        header,
    )
    return header + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


@cache
def _original_literals() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            int(value)
            for value in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
        )
    rows = read_prefix(BUNDLE, "mined/")
    for name in ("mined/msb_enemies.tsv", "mined/msb_regions.tsv"):
        for row in rows.get(name, b"").decode("utf-8-sig").splitlines()[1:]:
            for value in row.split("\t"):
                if value.lstrip("-").isdigit():
                    values.add(int(value))
    return values


def _validate_ids(ids: LivingFailuresLaurenceIds, destination: str = "") -> None:
    project_values = (
        *ids.event_values(),
        ids.phase_music_flag,
        ids.generator_enable_flag,
        ids.generator_phase_flag,
        *range(ids.wave_flags_start, ids.wave_flags_end + 1),
        ids.scheduler_active_flag,
        *range(ids.combat_count_value, ids.combat_count_value + 3),
        *range(ids.support_count_value, ids.support_count_value + 3),
    )
    all_values = (*project_values, *ids.added_entities())
    local = set(
        int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)
    )
    if (
        len(set(all_values)) != len(all_values)
        or any(value < EVENT_MIN or value > EVENT_MAX for value in project_values)
        or any(value <= 0 for value in ids.added_entities())
        or set(all_values).intersection(local | _original_literals())
        or not ids.evidence.strip()
    ):
        raise ValueError(
            "Living Failures/Laurence allocation collides with original operands or MSBB entities"
        )


def _mapping(ids: LivingFailuresLaurenceIds) -> dict[int, int]:
    return {
        PROXY: ids.proxy_entity,
        BODY_ONE: LAURENCE,
        BODY_TWO: ids.body_two_entity,
        BODY_THREE: ids.body_three_entity,
        BODY_FOUR: ids.body_four_entity,
        SUPPORT: ids.support_entity,
        13501850: COMPLETION,
        13504852: 13404852,
        13504853: 13404853,
        13504854: 13404854,
        13504858: 13404858,
        13504859: 13404859,
        13504860: 13404860,
        13504865: ids.player_effect,
        13504866: ids.generator_enable_flag,
        13504868: ids.generator_phase_flag,
        13504869: ids.scheduler_active_flag,
        13504870: ids.phase_music_flag,
        13504873: ids.wave_flags_start,
        13504874: ids.wave_flags_start + 1,
        13504875: ids.wave_flags_start + 2,
        13504876: ids.wave_flags_start + 3,
        13504877: ids.wave_flags_start + 4,
        13504878: ids.wave_flags_end,
        13504880: ids.wave_selection,
        13504881: ids.wave_commands,
        13504885: ids.wave_animation,
        13504890: ids.wave_reset,
        13504895: ids.death_cleanup,
        13505655: ids.generator_schedule,
        13505656: ids.combat_tracker,
        13505661: ids.combat_counter,
        13505662: ids.generator_controller,
        13505668: ids.generator_phase_flag,
        13505669: ids.scheduler_active_flag,
        13505680: ids.support_controller,
        13505690: ids.combat_count_value,
        13505694: ids.support_count_value,
        3500011: 3400030,
        3502812: 3402852,
        3503812: 3403852,
        3503813: 3403853,
        3503814: GENERATOR_ENTITY_IDS[0],
        3503815: GENERATOR_ENTITY_IDS[1],
        3503816: GENERATOR_ENTITY_IDS[2],
        3503817: GENERATOR_ENTITY_IDS[3],
        3503850: SFX_ENTITY_IDS[0],
        3503851: SFX_ENTITY_IDS[1],
        3503852: SFX_ENTITY_IDS[2],
        3503853: SFX_ENTITY_IDS[3],
        3503854: SFX_ENTITY_IDS[4],
    }


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(values.get(int(match[0]), int(match[0]))),
        text,
    )


def _calls(event_zero: str, event: int, expected: int) -> list[str]:
    calls = [
        line
        for line in event_zero.splitlines()
        if re.match(r"\s*\$InitializeEvent\([^,]+,\s*" + str(event) + r"(?:,|\))", line)
    ]
    if len(calls) != expected:
        raise ValueError(
            f"Living Failures Event(0) lacks {expected} initializer witnesses for {event}"
        )
    return calls


def _constructor(
    arena_zero: str, donor_zero: str, ids: LivingFailuresLaurenceIds
) -> str:
    mapping = _mapping(ids)
    groups = (
        (13504865, 1),
        (13504880, 1),
        (13504881, 1),
        (13504885, 2),
        (13504890, 4),
        (13504895, 4),
        (13505655, 1),
        (13505656, 4),
        (13505661, 1),
        (13505662, 1),
        (13505680, 1),
    )
    initializers = [
        _remap(line, mapping)
        for event, count in groups
        for line in _calls(donor_zero, event, count)
    ]
    initializers.append(f"    $InitializeEvent(0, {ids.lifecycle_cleanup});")
    anchor = "    $InitializeEvent(0, 13404875);"
    return _replace_once(
        arena_zero,
        anchor,
        anchor + "\n" + "\n".join(initializers),
        "Laurence constructor insertion anchor",
    )


def _music(source: str, ids: LivingFailuresLaurenceIds) -> str:
    result = _remap(source, _mapping(ids))
    result = _replace_once(
        result,
        f"    SetMapSoundState({GENERATOR_ENTITY_IDS[0]}, Disabled);\n",
        "",
        "Living Failures third music slot",
    )
    return _replace_once(
        result,
        "    EndIf(EventFlag(13501800));\n",
        "",
        "Living Failures source Maria completion gate",
    )


def _camera(source: str, ids: LivingFailuresLaurenceIds) -> str:
    result = _remap(source, _mapping(ids))
    for old, new in (
        ("SetLockcamSlotNumber(35, 0, 1);", "SetLockcamSlotNumber(34, 0, 1);"),
        ("SetLockcamSlotNumber(35, 0, 0);", "SetLockcamSlotNumber(34, 0, 0);"),
    ):
        result = _replace_once(result, old, new, "Living Failures camera map binding")
    if "SetLockcamSlotNumber(35," in result:
        raise ValueError("Living Failures/Laurence retains donor camera binding")
    return result


def _terminal_safe_controllers(
    generator_controller: str,
    support_controller: str,
    *,
    completion: int,
    enable_flag: int,
    phase_flag: int,
) -> tuple[str, str]:
    """Keep copied LF loops from crossing a destination completion boundary."""
    guard = f"    EndIf(EventFlag({completion}));\n"
    phase_wait = f"    WaitFor(EventFlag({phase_flag}));"
    if generator_controller.count(phase_wait) != 1:
        raise ValueError("Living Failures generator-controller phase witness drift")
    generator_controller = generator_controller.replace(
        phase_wait,
        f"    WaitFor(EventFlag({phase_flag}) || EventFlag({completion}));\n" + guard,
        1,
    )
    enabled = re.findall(
        r"(?m)^\s*DeactivateGenerator\([^)]*, Enabled\);$", generator_controller
    )
    if len(enabled) != 4:
        raise ValueError("Living Failures generator-controller enable witness drift")
    generator_controller = re.sub(
        r"(?m)^(\s*DeactivateGenerator\([^)]*, Enabled\);)$",
        guard + r"\1",
        generator_controller,
    )
    if generator_controller.count("    WaitFixedTimeSeconds(3);") != 1:
        raise ValueError("Living Failures generator-controller delay witness drift")
    generator_controller = generator_controller.replace(
        "    WaitFixedTimeSeconds(3);",
        "    WaitFixedTimeSeconds(3);\n" + guard,
        1,
    )

    support_wait = f"    WaitFor(CharacterType(10000, TargetType.Alive) && EventFlag({enable_flag}));"
    if support_controller.count(support_wait) != 1:
        raise ValueError("Living Failures support-controller entry witness drift")
    support_controller = support_controller.replace(
        support_wait,
        f"    WaitFor(\n        CharacterType(10000, TargetType.Alive)\n"
        f"            && (EventFlag({enable_flag}) || EventFlag({completion})));\n"
        + guard,
        1,
    )
    ai_boundaries = re.findall(
        r"(?m)^\s*RequestCharacterAI(?:Command|Replan)\([^;]+;$", support_controller
    )
    if len(ai_boundaries) != 7:
        raise ValueError("Living Failures support-controller AI witness drift")
    support_controller = re.sub(
        r"(?m)^(\s*)(RequestCharacterAI(?:Command|Replan)\([^;]+;)$",
        lambda match: (
            f"{match.group(1)}EndIf(EventFlag({completion}));\n"
            f"{match.group(1)}{match.group(2)}"
        ),
        support_controller,
    )
    return generator_controller, support_controller


def _lifecycle_cleanup(
    event_id: int, completion: int, ids, generators: tuple[int, ...]
) -> str:
    """Completion-side ownership cleanup for every added actor and generator."""
    flags = "".join(
        f"    SetEventFlag({flag}, OFF);\n"
        for flag in (
            ids.generator_enable_flag,
            ids.generator_phase_flag,
            ids.scheduler_active_flag,
            ids.phase_music_flag,
        )
    )
    waves = (
        f"    BatchSetEventFlags({ids.wave_flags_start}, {ids.wave_flags_end}, OFF);\n"
    )
    counts = (
        f"    ClearEventValue({ids.combat_count_value}, 3);\n"
        f"    ClearEventValue({ids.support_count_value}, 3);\n"
    )
    generators = "".join(
        f"    DeactivateGenerator({entity}, Disabled);\n" for entity in generators
    )
    actors = "".join(
        f"    SetCharacterAIState({entity}, Disabled);\n"
        f"    ChangeCharacterEnableState({entity}, Disabled);\n"
        f"    ForceCharacterDeath({entity}, false);\n"
        for entity in (
            ids.proxy_entity,
            ids.body_two_entity,
            ids.body_three_entity,
            ids.body_four_entity,
            ids.support_entity,
        )
    )
    return f"""$Event({event_id}, Default, function() {{
    WaitFor(EventFlag({completion}));
{flags}{waves}{counts}{generators}{actors}}});"""


def patch_living_failures_at_laurence(
    destination: str,
    donor_source: str,
    ids: LivingFailuresLaurenceIds = DEFAULT_IDS,
) -> str:
    """Transplant the full mapped EMEVD graph while retaining Laurence completion."""
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, ARENA_HASHES, "Laurence arena")
    _verify(donor, DONOR_HASHES, "Living Failures donor")
    _validate_ids(ids, destination)
    mapping = _mapping(ids)
    entry = _replace_once(
        arena[13401851],
        "ForceAnimationPlayback(3400850, 3029, false, false, false);",
        "ForceAnimationPlayback(3400850, 9060, false, false, false);",
        "Living Failures source wake animation",
    )
    activation = _replace_once(
        arena[13404861],
        "    ForceAnimationPlayback(3400850, 7002, true, false, false);\n",
        "    ForceAnimationPlayback(3400850, 9000, true, false, false);\n",
        "Living Failures source pre-entry animation",
    )
    donor_events = {
        ids.player_effect: 13504865,
        ids.wave_selection: 13504880,
        ids.wave_commands: 13504881,
        ids.wave_animation: 13504885,
        ids.death_cleanup: 13504895,
        ids.generator_schedule: 13505655,
        ids.combat_tracker: 13505656,
        ids.combat_counter: 13505661,
        ids.generator_controller: 13505662,
        ids.support_controller: 13505680,
        ids.wave_reset: 13504890,
    }
    translated = {
        target: _remap(donor[source], mapping)
        for target, source in donor_events.items()
    }
    (
        translated[ids.generator_controller],
        translated[ids.support_controller],
    ) = _terminal_safe_controllers(
        translated[ids.generator_controller],
        translated[ids.support_controller],
        completion=COMPLETION,
        enable_flag=ids.generator_enable_flag,
        phase_flag=ids.generator_phase_flag,
    )
    lifecycle_cleanup = _lifecycle_cleanup(
        ids.lifecycle_cleanup, COMPLETION, ids, GENERATOR_ENTITY_IDS
    )
    edits = {
        0: _constructor(arena[0], donor[0], ids),
        13401851: entry,
        13404861: activation,
        13404852: _remap(donor[13504852], mapping),
        13404853: _music(donor[13504853], ids),
        13404854: _camera(donor[13504854], ids),
        13404870: _end_event(arena[13404870]),
        13404875: _end_event(arena[13404875]),
        **translated,
        ids.lifecycle_cleanup: lifecycle_cleanup,
    }
    result = _replace_events(
        destination, {event: body for event, body in edits.items() if event in arena}
    )
    result = (
        result.rstrip()
        + "\n\n"
        + "\n\n".join(edits[event] for event in ids.event_values())
        + "\n"
    )
    output = event_blocks(result)
    expected = set(arena).union(ids.event_values())
    if set(output) != expected:
        raise ValueError("Living Failures/Laurence changed event identities")
    for event, original in arena.items():
        if event not in edits and output[event] != original:
            raise ValueError(
                f"Living Failures/Laurence changed unrelated arena event {event}"
            )
    for event in (13401800, COMPLETION, 13404855):
        if output[event] != arena[event]:
            raise ValueError(
                "Living Failures/Laurence changed destination terminal/progression"
            )
    copied = "\n".join(
        output[event] for event in (13404852, 13404853, 13404854, *ids.event_values())
    )
    if re.search(r"(?<!\d)(?:135|350)\d+(?!\d)", copied):
        raise ValueError(
            "Living Failures/Laurence copied combat retains donor-map literals"
        )
    return result


def _require(
    slots: Sequence[Slot], entity: int, archetype: Archetype, map_name: str
) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.entity_id == entity
        and slot.archetype == archetype
        and slot.map_name == map_name
    ]
    if len(found) != 1 or found[0].dummy:
        raise ValueError(
            f"Living Failures/Laurence requires one pinned source actor {entity} in {map_name}"
        )
    return found[0]


def _actor_addition(source: Slot, target: Slot, entity: int, part: str) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_anchor_part": "c4030_0000",
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_part_kind": "enemy",
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": PART_PINS[source.entity_id],
            "anchor_sha256": PART_PINS[BODY_ONE],
        },
        "source_initialization": {
            "talk_id": 0,
            "unk_t18": -1,
            "init_anim_id": -1,
            "damage_anim_id": -1,
        },
        "destination_map": target.map_name,
        "destination_anchor_part": target.part_name,
        "destination_part": part,
        "destination_entity_id": entity,
        "allocation_evidence": DEFAULT_IDS.evidence,
    }


def _regions(target: Slot) -> list[dict]:
    names = {
        "Event_ボス1_患者B_ジェネレートポイント1": "ap_lf_spawn_1",
        "Event_ボス1_患者B_ジェネレートポイント2": "ap_lf_spawn_2",
        "Event_ボス1_患者B_ジェネレートポイント3": "ap_lf_spawn_3",
        "Event_ボス1_患者B_ジェネレートポイント4": "ap_lf_spawn_4",
        "SFX_患者B宇宙作成": "ap_lf_universe_sfx",
    }
    return [
        {
            "source_map": "m35_00_00_00",
            "source_region": source,
            "source_entity_id": -1,
            "source_provenance": {
                "format": "bb-boss-region-pin-v1",
                "region_sha256": REGION_PINS[source],
            },
            "source_anchor_part": "c4030_0000",
            "source_anchor_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": PART_PINS[BODY_ONE],
            },
            "destination_map": target.map_name,
            "destination_region": destination,
            "destination_entity_id": -1,
            "destination_anchor_part": target.part_name,
            "destination_anchor_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": LAURENCE_PIN,
            },
        }
        for source, destination in names.items()
    ]


def _generators(target: Slot) -> list[dict]:
    destination_parts = (
        target.part_name,
        "ap_lf_body_two",
        "ap_lf_body_three",
        "ap_lf_body_four",
    )
    destination_regions = (
        "ap_lf_spawn_2",
        "ap_lf_spawn_3",
        "ap_lf_spawn_4",
        "ap_lf_spawn_1",
    )
    return [
        {
            "source_map": "m35_00_00_00",
            "source_event": source_name,
            "source_event_id": source_event_id,
            "source_entity_id": source_entity,
            "source_fingerprint": fingerprint,
            "destination_map": target.map_name,
            "destination_event": f"ap_lf_generator_{index + 1}",
            "destination_event_id": GENERATOR_EVENT_IDS[index],
            "destination_entity_id": GENERATOR_ENTITY_IDS[index],
            "destination_part_name": "h000027",
            "destination_region_name": None,
            "spawn_part_map": {source_part: destination_parts[index]},
            "spawn_point_map": {source_region: destination_regions[index]},
        }
        for index, (
            source_entity,
            source_event_id,
            fingerprint,
            source_name,
            source_region,
            source_part,
        ) in enumerate(GENERATOR_PINS)
    ]


def _sfx(target: Slot) -> list[dict]:
    """Declare the exact source-pinned MapSFX additions and their map bindings."""
    return [
        {
            "source_map": "m35_00_00_00",
            "source_event": source_name,
            "source_event_id": source_event_id,
            "source_entity_id": source_entity_id,
            "source_provenance": {
                "format": "bb-boss-sfx-pin-v1",
                "event_sha256": event_sha256,
            },
            "source_anchor_part": "c4030_0000",
            "source_anchor_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": PART_PINS[BODY_ONE],
            },
            "destination_map": target.map_name,
            "destination_event": f"ap_lf_universe_sfx_{index + 1}",
            "destination_event_id": SFX_EVENT_IDS[index],
            "destination_entity_id": SFX_ENTITY_IDS[index],
            "destination_part_name": "h000027",
            "destination_region_name": "ap_lf_universe_sfx",
            "destination_anchor_part": target.part_name,
            "destination_anchor_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": LAURENCE_PIN,
            },
            "effect_id": effect_id,
            "start_disabled": False,
        }
        for index, (
            source_name,
            source_event_id,
            source_entity_id,
            effect_id,
            event_sha256,
        ) in enumerate(SFX_PINS)
    ]


def native_plan_living_failures_at_laurence(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: LivingFailuresLaurenceIds = DEFAULT_IDS,
) -> dict:
    """Return the six-actor, generator, region, and visual requirement plan."""
    arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
    donor = read_blob(BUNDLE, DONOR_SOURCE).decode("utf-8-sig")
    _verify(event_blocks(arena), ARENA_HASHES, "Laurence arena")
    _verify(event_blocks(donor), DONOR_HASHES, "Living Failures donor")
    _validate_ids(ids, arena)
    primary = _require(slots, BODY_ONE, BODY_ONE_ARCHETYPE, "m35_00_00_00")
    target = _require(slots, LAURENCE, LAURENCE_ARCHETYPE, "m34_00_00_00")
    helpers = (
        (
            _require(slots, PROXY, PROXY_ARCHETYPE, "m35_00_00_00"),
            ids.proxy_entity,
            "ap_lf_proxy",
        ),
        (
            _require(slots, BODY_TWO, BODY_TWO_ARCHETYPE, "m35_00_00_00"),
            ids.body_two_entity,
            "ap_lf_body_two",
        ),
        (
            _require(slots, BODY_THREE, BODY_THREE_ARCHETYPE, "m35_00_00_00"),
            ids.body_three_entity,
            "ap_lf_body_three",
        ),
        (
            _require(slots, BODY_FOUR, BODY_FOUR_ARCHETYPE, "m35_00_00_00"),
            ids.body_four_entity,
            "ap_lf_body_four",
        ),
        (
            _require(slots, SUPPORT, SUPPORT_ARCHETYPE, "m35_00_00_00"),
            ids.support_entity,
            "ap_lf_support",
        ),
    )
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        primary.archetype,
        warnings=[
            "Living Failures-at-Laurence has unobserved arena fit and pending MapSFX writer support"
        ],
        destinations={
            target.key: {
                "map_name": target.map_name,
                "entity_id": target.entity_id,
                "x": target.x,
                "y": target.y,
                "z": target.z,
            }
        },
    )
    changes, skips = plan_scaling(
        [swap], [target], dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError(
            "Living Failures/Laurence primary swap has an ambiguous normalization plan"
        )
    additions = [
        _actor_addition(source, target, entity, part)
        for source, entity, part in helpers
    ]
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "boss_actor_additions": additions,
        "boss_region_additions": _regions(target),
        "boss_generator_additions": _generators(target),
        "boss_sfx_additions": _sfx(target),
        "boss_ffx_merges": [
            {
                "source_file": "frpg_sfxbnd_m35.ffxbnd.dcx",
                "source_sha256": "fd656c4a23d3a45202e7d0a5aec1b4f3bea95f71d96af3d1b4b181bcf24b931e",
                "destination_file": "frpg_sfxbnd_m34.ffxbnd.dcx",
                "destination_sha256": "c02322d8ad0e50b18e5f678f3bbfe735971e24aa4c5484f3849ace93f1dfd3b3",
                "required_effect_ids": [640320, 640321, 640322, 640323, 640324],
                "policy": "preserve_destination_union_source_v1",
            }
        ],
        "primary_init_source_bindings": [
            {
                "source_map": primary.map_name,
                "source_part": primary.part_name,
                "source_entity_id": primary.entity_id,
                "source_archetype": asdict(primary.archetype),
                "source_talk_id": primary.talk_id,
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": PART_PINS[BODY_ONE],
                },
                "source_initialization": {
                    "talk_id": 0,
                    "unk_t18": -1,
                    "init_anim_id": -1,
                    "damage_anim_id": -1,
                },
                "destination_map": target.map_name,
                "destination_part": target.part_name,
                "destination_entity_id": target.entity_id,
                "destination_original_talk_id": target.talk_id,
                "required_native_fields": [
                    "talk_id",
                    "unk_t18",
                    "init_anim_id",
                    "damage_anim_id",
                    "provenance",
                ],
            }
        ],
        "boss_actor_scaling_requirements": [
            {
                "destination_map": target.map_name,
                "destination_part": addition["destination_part"],
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": addition["source_archetype"]["npc_param_id"],
                "strategy": "allocate_distinct_verified_helper_clone",
            }
            for addition in additions
        ],
        "boss_contract": {
            "format": "bb-living-failures-laurence-contract-v1",
            "arena": "laurence",
            "donor": "living-failures",
            "status": "planned",
            "writer_status": "not_integrated_pending_builder_ffx_receipt",
            "runtime_status": "unobserved arena fit and in-game asset loading",
            "logical_encounter_count": 1,
            "physical_actor_count": 6,
            "attachment_event_ids": asdict(ids),
            "preserved_destination_events": [13401800, COMPLETION, 13404855],
            "terminal_policy": "retain byte-identical Laurence CharacterDead(3400850) terminal; donor death cleanup kills primary only after aggregate proxy reaches zero",
            "source_hash_pins": dict(DONOR_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "sfx_policy": "five source MapSFX records and their shared cloned region are required",
            "ffx_merge_policy": "preserve_destination_union_source_v1; source FXR dependencies are unparseable, so the full source binder union is required",
            "ffx_missing_entry_count": 360,
            "ffx_missing_entry_bytes": 8534064,
        },
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
