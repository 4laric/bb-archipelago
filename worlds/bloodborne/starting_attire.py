"""Reviewed, seed-stable starting-attire choices.

This module deliberately stops before runtime activation.  It gives generation
and the native writer one validated vocabulary, but no option consumes it yet.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from importlib.resources import files

SLOTS = ("head", "body", "arms", "legs")


@dataclass(frozen=True)
class AttirePiece:
    set_key: str
    protector_id: int
    slot: str
    name: str
    grant_descriptor: str

    @property
    def item_key(self) -> str:
        """Permanent design key shared by the AP pool and runtime catalog."""
        return f"attire_{self.set_key}_{self.slot}"


def _load_catalog() -> tuple[AttirePiece, ...]:
    resource = files(__package__).joinpath("starting_attire_catalog.tsv")
    with resource.open("r", encoding="utf-8", newline="") as stream:
        rows = tuple(AttirePiece(
            row["set_key"], int(row["protector_id"]), row["slot"], row["name"],
            row["grant_descriptor"],
        ) for row in csv.DictReader(stream, delimiter="\t"))
    validate_attire_catalog(rows)
    return rows


def validate_attire_catalog(rows: tuple[AttirePiece, ...]) -> None:
    if not rows:
        raise ValueError("starting-attire catalog is empty")
    ids: set[int] = set()
    by_set: dict[str, list[AttirePiece]] = {}
    for piece in rows:
        if piece.slot not in SLOTS:
            raise ValueError(f"{piece.set_key}: unknown attire slot {piece.slot}")
        if piece.protector_id <= 0 or piece.protector_id in ids:
            raise ValueError(f"{piece.set_key}: invalid/duplicate protector id {piece.protector_id}")
        ids.add(piece.protector_id)
        if piece.grant_descriptor != f"1:{piece.protector_id}:1":
            raise ValueError(f"{piece.set_key}: grant descriptor does not name its armor row")
        by_set.setdefault(piece.set_key, []).append(piece)
    for set_key, pieces in by_set.items():
        if tuple(piece.slot for piece in pieces) != SLOTS:
            raise ValueError(f"{set_key}: attire set is not ordered head/body/arms/legs")


STARTING_ATTIRE_CATALOG = _load_catalog()


def build_starting_attire_choice(seed: str) -> dict[str, object]:
    """Select one coherent set without touching AP options or runtime state."""
    sets: dict[str, list[AttirePiece]] = {}
    for piece in STARTING_ATTIRE_CATALOG:
        sets.setdefault(piece.set_key, []).append(piece)
    keys = sorted(sets)
    digest = hashlib.sha256(f"bloodborne-starting-attire:{seed}".encode()).digest()
    key = keys[int.from_bytes(digest[:8], "big") % len(keys)]
    return {
        "set_key": key,
        "pieces": {piece.slot: piece.protector_id for piece in sets[key]},
        "grant_descriptors": [piece.grant_descriptor for piece in sets[key]],
    }
