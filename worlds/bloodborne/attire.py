"""Complete reviewed player-obtainable attire grant catalog."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from importlib.resources import files

from .starting_attire import STARTING_ATTIRE_CATALOG

SLOTS = ("head", "body", "arms", "legs")


@dataclass(frozen=True)
class AttirePiece:
    set_key: str
    protector_id: int
    slot: str
    name: str
    grant_descriptor: str
    dlc: bool

    @property
    def item_key(self) -> str:
        return f"attire_{self.set_key}_{self.slot}"


def validate_attire_catalog(rows: tuple[AttirePiece, ...]) -> None:
    if not rows:
        raise ValueError("attire catalog is empty")
    ids: set[int] = set()
    keys: set[str] = set()
    for piece in rows:
        if piece.slot not in SLOTS:
            raise ValueError(f"{piece.set_key}: unknown attire slot {piece.slot}")
        if piece.protector_id <= 0 or piece.protector_id in ids:
            raise ValueError(f"{piece.item_key}: invalid/duplicate protector id {piece.protector_id}")
        if piece.item_key in keys:
            raise ValueError(f"duplicate attire item key {piece.item_key}")
        if piece.grant_descriptor != f"1:{piece.protector_id}:1":
            raise ValueError(f"{piece.item_key}: descriptor does not name its protector row")
        ids.add(piece.protector_id)
        keys.add(piece.item_key)


def _load_catalog() -> tuple[AttirePiece, ...]:
    base = tuple(AttirePiece(
        row.set_key, row.protector_id, row.slot, row.name,
        row.grant_descriptor, row.set_key in {"old_hunter", "maria_hunter", "constable", "yamamura"},
    ) for row in STARTING_ATTIRE_CATALOG)
    resource = files(__package__).joinpath("attire_additions.tsv")
    with resource.open("r", encoding="utf-8", newline="") as stream:
        additions = tuple(AttirePiece(
            row["set_key"], int(row["protector_id"]), row["slot"], row["name"],
            row["grant_descriptor"], row["dlc"] == "1",
        ) for row in csv.DictReader(stream, delimiter="\t"))
    rows = base + additions
    validate_attire_catalog(rows)
    return rows


ATTIRE_CATALOG = _load_catalog()

# Catalog rows with no EquipParamProtector row in CUSA03173 01.09 (checked
# against the owner's dump, patch and base layers, 2026-09-03). Delivering one
# would create an invisible inventory record. They keep their catalog row and
# network id so every other attire id stays stable, but they never enter a
# pool and the client refuses them by protector id.
PHANTOM_PROTECTOR_IDS = frozenset({
    292_000,  # "Surgical Long Gloves (White)": the White Church set uses the black gloves, 112000.
})
PHANTOM_ATTIRE_ITEM_KEYS = frozenset(
    piece.item_key for piece in ATTIRE_CATALOG if piece.protector_id in PHANTOM_PROTECTOR_IDS
)
