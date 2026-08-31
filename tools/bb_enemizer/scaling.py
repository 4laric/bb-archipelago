"""Offline, fail-closed enemy transplant scaling plan.

The module only describes cloned rows. Applying those rows remains guarded by
the writer and is opt-in until the in-game construction canary is validated.
"""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from pathlib import Path

from tools.bb_inputs import read_blob

from .model import Slot, Swap


NPC_CLONE_START = 6_000_000
NPC_CLONE_END = 6_099_999
SPEFFECT_START = 60_000
SPEFFECT_END = 60_168
MIN_MULTIPLIER = 0.25
MAX_MULTIPLIER = 4.0

# Map-level destination oracle. Evidence is the designers' 74xx NG+ area
# names, joined to the maps whose development names represent those areas.
# m24_00 spans several Cathedral phases; level 4 is the conservative ordinary
# enemy baseline. Bosses and script-protected slots never reach this planner.
MAP_LEVELS = {
    "m21_00_00_00": 13,
    "m22_00_00_00": 5,
    "m23_00_00_00": 2,
    "m24_00_00_00": 4,
    "m24_01_00_00": 1,
    "m25_00_00_00": 9,
    "m26_00_00_00": 12,
    "m27_00_00_00": 6,
    "m28_00_00_00": 10,
    "m32_00_00_00": 8,
    "m33_00_00_00": 12,
    "m34_00_00_00": 11,
    "m35_00_00_00": 12,
    "m36_00_00_00": 13,
}


@dataclass(frozen=True)
class LadderRung:
    level: int
    source_id: int
    source_name: str
    max_hp_rate: float
    attack_rate: float
    defense_rate: float

    @property
    def strength(self) -> tuple[float, float, float]:
        return (1 / self.max_hp_rate, 1 / self.attack_rate, 1 / self.defense_rate)


@dataclass(frozen=True)
class ScalingChange:
    logical_key: str
    source_npc_param_id: int
    cloned_npc_param_id: int
    sp_effect_slot: str
    minted_sp_effect_id: int
    have_soul_rate: float
    source_level: int
    destination_level: int
    hp_multiplier: float
    attack_multiplier: float
    defense_multiplier: float

    def json(self) -> dict:
        return asdict(self)


def _csv_blob(bundle: Path, name: str) -> list[dict[str, str]]:
    text = read_blob(bundle, f"params/{name}.csv").decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def load_params(bundle: Path) -> tuple[dict[int, dict[str, str]], dict[int, dict[str, str]]]:
    npcs = {int(row["ID"]): row for row in _csv_blob(bundle, "NpcParam")}
    effects = {int(row["ID"]): row for row in _csv_blob(bundle, "SpEffectParam")}
    return npcs, effects


def derive_ladder(effects: dict[int, dict[str, str]]) -> dict[int, LadderRung]:
    result = {}
    for level in range(1, 14):
        row_id = 7400 + level
        row = effects[row_id]
        name = row["Name"]
        if f"レベル{level}" not in name:
            raise ValueError(f"SpEffect {row_id} is not the expected level {level} rung: {name}")
        result[level] = LadderRung(
            level, row_id, name, float(row["maxHpRate"]),
            float(row["physicsAttackPowerRate"]),
            float(row["physicsDiffenceRate"]),
        )
    if not all(rung.max_hp_rate > 1 for rung in result.values()):
        raise ValueError("native ladder contains a non-boosting HP rung")
    return result


def npc_native_level(row: dict[str, str]) -> int | None:
    effect = int(row["GameClearSpEffectID"])
    if 7401 <= effect <= 7413:
        return effect - 7400
    if 7490 <= effect <= 7497:
        return {7490: 11, 7491: 11, 7492: 12, 7493: 12,
                7494: 12, 7495: 13, 7496: 13, 7497: 12}[effect]
    return None


def free_effect_slot(row: dict[str, str]) -> str | None:
    for index in range(8):
        name = f"spEffectID{index}"
        if int(row[name]) < 0:
            return name
    return None


def _clamp(value: float) -> float:
    return round(max(MIN_MULTIPLIER, min(MAX_MULTIPLIER, value)), 6)


def plan_scaling(
    swaps: list[Swap], slots: list[Slot], npcs: dict[int, dict[str, str]],
    effects: dict[int, dict[str, str]],
) -> tuple[list[ScalingChange], list[dict]]:
    ladder = derive_ladder(effects)
    existing_npcs = set(npcs)
    existing_effects = set(effects)
    if existing_npcs & set(range(NPC_CLONE_START, NPC_CLONE_END + 1)):
        raise ValueError("claimed NpcParam clone range collides with bundled rows")
    if existing_effects & set(range(SPEFFECT_START, SPEFFECT_END + 1)):
        raise ValueError("claimed SpEffect range collides with bundled rows")

    by_key = {slot.key: slot for slot in slots}
    changes = []
    skipped = []
    for swap in sorted(swaps, key=lambda item: item.logical_key):
        destination = by_key[swap.destination_keys[0]]
        destination_level = MAP_LEVELS.get(destination.logical_key.split(":", 1)[0])
        target_row = npcs.get(swap.target.npc_param_id)
        source_level = npc_native_level(target_row) if target_row else None
        if source_level is None or destination_level is None:
            skipped.append({"logical_key": swap.logical_key, "reason": "unknown source or destination tier"})
            continue
        slot_name = free_effect_slot(target_row)
        if slot_name is None:
            skipped.append({"logical_key": swap.logical_key, "reason": "no free spEffectID slot",
                            "npc_param_id": swap.target.npc_param_id})
            continue
        source = ladder[source_level].strength
        dest = ladder[destination_level].strength
        index = len(changes)
        clone_id = NPC_CLONE_START + index
        effect_id = SPEFFECT_START + (source_level - 1) * 13 + destination_level - 1
        if clone_id > NPC_CLONE_END:
            raise ValueError("NpcParam clone range exhausted")
        changes.append(ScalingChange(
            swap.logical_key, swap.target.npc_param_id, clone_id, slot_name,
            effect_id, 1.0, source_level, destination_level,
            _clamp(dest[0] / source[0]), _clamp(dest[1] / source[1]),
            _clamp(dest[2] / source[2]),
        ))
    return changes, skipped
