"""Source-backed ItemLot targets for the standalone item writer.

This module does not infer an award route from an event flag. Direct locations
must name an ItemLot in ``runtime_bindings``; indirect routes are a small,
reviewable table whose lots are witnessed by the original EMEVD and existing
suppression declarations. Locations with no native award are classified
explicitly rather than becoming silent vanilla fallbacks.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .schema import AwardTarget, Reward, SourceReward

ROOT = Path(__file__).resolve().parents[2]
LOT_ITEMS = ROOT / "research" / "joined" / "lot_items.tsv"
CATALOG_PATH = Path(__file__).with_name("award_targets.json")
CATALOG_FORMAT = "bb-standalone-award-target-catalog-v1"


@dataclass(frozen=True)
class CatalogEntry:
    location_key: str
    status: str
    targets: tuple[AwardTarget, ...] = ()
    reason: str = ""
    evidence: str = ""
    when: tuple[tuple[str, bool], ...] = ()

    def as_dict(self) -> dict:
        value = {
            "location_key": self.location_key,
            "status": self.status,
            "targets": [target.as_dict() for target in self.targets],
        }
        if self.reason:
            value["reason"] = self.reason
        if self.evidence:
            value["evidence"] = self.evidence
        if self.when:
            value["when"] = dict(self.when)
        return value


# Original event award routes. The first lot is the delivery row; ``alt`` lots
# are mutually exclusive branches and must carry the same reward; ``retire``
# lots would otherwise add a second reward for the same logical location.
_INDIRECT: dict[str, tuple[tuple[int, str], ...]] = {
    "boss_cleric_beast": ((50_000_010, "delivery"),),
    "boss_father_gascoigne": ((31_000, "delivery"),),
    "boss_blood_starved_beast": ((80_000_000, "delivery"),),
    "boss_darkbeast_paarl": ((50_800_000, "delivery"), (50_800_005, "alternative")),
    "boss_vicar_amelia": ((50_000_001, "delivery"),),
    "boss_witch_of_hemwick": ((21_002_950, "delivery"),),
    "boss_martyr_logarius": ((2_502_000, "delivery"),),
    "boss_celestial_emissary": ((25_700_000, "delivery"), (25_700_005, "alternative")),
    "boss_ebrietas": ((80_000_300, "delivery"),),
    "boss_shadows_of_yharnam": ((2_700_990, "delivery"), (2_700_995, "alternative")),
    "boss_rom": ((51_001_900, "delivery"), (3_200_800, "retire")),
    "boss_amygdala": ((80_000_200, "delivery"),),
    "boss_the_one_reborn": ((50_700_000, "delivery"),),
    "boss_micolash": ((21_000, "delivery"),),
    "boss_mergos_wet_nurse": ((55_100_000, "delivery"),),
    "boss_gehrman": ((15_000, "delivery"), (15_005, "alternative")),
    "boss_ludwig": ((3_401_800, "delivery"), (3_401_802, "alternative")),
    "boss_living_failures": ((3_501_850, "delivery"),),
    "boss_lady_maria": ((3_501_800, "delivery"),),
    "boss_orphan_of_kos": ((3_601_800, "delivery"),),
    "boss_laurence": ((3_401_850, "delivery"), (3_401_852, "alternative")),
    "enemy_cathedral_ward_avatar": (
        (75_002_400, "delivery"),
        (75_002_405, "alternative"),
    ),
    "award_crow_hunter_badge": (
        (35_012, "delivery"),
        (35_020, "alternative"),
        (35_030, "alternative"),
    ),
    "award_powder_keg_hunter_badge": ((33_000, "delivery"), (33_010, "alternative")),
    "award_wheel_hunter_badge": ((34_010, "delivery"), (34_031, "alternative")),
    "award_cainhurst_badge": ((17_001, "delivery"),),
}

_INDIRECT_EVIDENCE = {
    "boss_martyr_logarius": "m25 event 12501803 awards lot 2502000 after defeat",
    "boss_ebrietas": "m24_02 event 12421800 awards lot 80000300",
    "boss_amygdala": "m33 event 13301800 awards lot 80000200",
    "boss_living_failures": "m35 event 13501850 awards lot 3501850",
    "boss_lady_maria": "m35 event 13501803 awards lot 3501800 after defeat",
}

_FIXED = {
    "interaction_laurences_skull": (
        "fixed_progression",
        "the original Amelia memory interaction grants the password capability; it is not an inventory award",
    ),
    "boss_moon_presence": (
        "completion_only",
        "original event 12101850 completes the ending and awards no ItemLot",
    ),
}


def _lot_rows() -> dict[int, list[dict[str, str]]]:
    with LOT_ITEMS.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    by_lot: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        by_lot.setdefault(int(row["item_lot_id"]), []).append(row)
    return by_lot


def _source(row: dict[str, str]) -> SourceReward:
    flag = row["generic_acquisition_flag"]
    return SourceReward(
        int(row["item_category"]),
        int(row["item_id"]),
        int(row["quantity"]),
        -1 if flag == "" else int(flag),
    )


def _target(
    rows_by_lot: dict[int, list[dict[str, str]]], lot: int, role: str
) -> AwardTarget:
    rows = rows_by_lot.get(lot, ())
    if len(rows) != 1:
        raise ValueError(
            f"ItemLot {lot} requires exactly one source item row, found {len(rows)}"
        )
    row = rows[0]
    return AwardTarget(lot, int(row["slot"]), role, _source(row))


def derive_catalog(locations: Iterable) -> tuple[CatalogEntry, ...]:
    from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS

    rows_by_lot = _lot_rows()
    entries: list[CatalogEntry] = []
    occupied: dict[tuple[int, int], str] = {}
    for location in locations:
        key = location.key
        if key in _FIXED:
            status, reason = _FIXED[key]
            entries.append(CatalogEntry(key, status, reason=reason))
            continue
        binding = LOCATION_BINDINGS[key]
        targets: list[AwardTarget] = []
        if binding.item_lot_id is not None:
            targets.append(_target(rows_by_lot, binding.item_lot_id, "delivery"))
            expected_flag = binding.item_lot_flag or binding.event_flag
            related_lots = sorted(
                lot
                for lot, rows in rows_by_lot.items()
                if lot != binding.item_lot_id
                and rows
                and all(
                    row["all_acquisition_flags"] == str(expected_flag) for row in rows
                )
            )
            # These rows are one consecutive award or a reviewed collapsed
            # shared-flag pickup. They are retired so one check yields one item.
            for lot in related_lots:
                for row in rows_by_lot[lot]:
                    targets.append(
                        AwardTarget(lot, int(row["slot"]), "retire", _source(row))
                    )
        elif key in _INDIRECT:
            targets.extend(
                _target(rows_by_lot, lot, role) for lot, role in _INDIRECT[key]
            )
        else:
            entries.append(
                CatalogEntry(
                    key,
                    "unsupported",
                    reason=f"{binding.source_kind} has no source-witnessed native ItemLot route",
                    evidence=binding.evidence,
                )
            )
            continue
        if sum(target.role == "delivery" for target in targets) != 1:
            raise ValueError(f"{key}: catalog requires exactly one delivery target")
        for target in targets:
            identity = (target.item_lot_id, target.slot)
            previous = occupied.setdefault(identity, key)
            if previous != key:
                raise ValueError(
                    f"award target {identity} is shared by {previous} and {key}"
                )
        evidence = _INDIRECT_EVIDENCE.get(key, binding.evidence)
        entries.append(
            CatalogEntry(key, "placeable", tuple(targets), evidence=evidence)
        )
    return tuple(entries)


def _entry_from_dict(value: dict) -> CatalogEntry:
    targets = tuple(
        AwardTarget(
            int(row["item_lot_id"]),
            int(row["slot"]),
            str(row["role"]),
            SourceReward(**{key: int(raw) for key, raw in row["source"].items()}),
        )
        for row in value.get("targets", [])
    )
    return CatalogEntry(
        str(value["location_key"]),
        str(value["status"]),
        targets,
        str(value.get("reason", "")),
        str(value.get("evidence", "")),
        tuple(
            sorted((str(key), bool(raw)) for key, raw in value.get("when", {}).items())
        ),
    )


def load_catalog_document() -> dict:
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict) or raw.get("format") != CATALOG_FORMAT:
        raise ValueError("standalone award target catalog has an unsupported format")
    if not isinstance(raw.get("entries"), list) or not isinstance(
        raw.get("items"), list
    ):
        raise ValueError("standalone award target catalog is incomplete")
    return raw


def build_catalog(locations: Iterable) -> tuple[CatalogEntry, ...]:
    document = load_catalog_document()
    by_key = {
        _entry_from_dict(row).location_key: _entry_from_dict(row)
        for row in document["entries"]
    }
    keys = [location.key for location in locations]
    missing = sorted(set(keys) - set(by_key))
    if missing:
        raise ValueError(
            f"standalone catalog is missing locations: {', '.join(missing)}"
        )
    return tuple(by_key[key] for key in keys)


def catalog_sha256() -> str:
    return hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()
