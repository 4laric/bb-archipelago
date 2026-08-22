# Location naming contract

Player-facing location names are part of the Archipelago datapackage. Clients,
trackers, hint UIs, and player muscle memory all key on them, and the ID
stability bought in #16 does not cover them: a rename is wire-compatible but
player-visible, and after the first numbered release it is effectively frozen.
This contract defines the names before that freeze, while changing them is
still cheap (#75).

## The table

`worlds/bloodborne/location_names.tsv` is hand-authored design data, one row
per named location:

| column | rule |
| --- | --- |
| `location_flag` | The canonical acquisition flag from `research/catalog/fixed_location_catalog.tsv`. This is the key: an existing game identifier, never an invented one. |
| `region` | Exactly one entry of `REGIONS` in `worlds/bloodborne/data.py`. |
| `name` | The player-facing English name. Unique across the table, ASCII, never a research placeholder. |
| `basis` | What the name rests on (vocabulary below). |

The table covers all 651 rows of the fixed-treasure catalog. Boss,
interaction, and EMEVD script-award checks are named where they are defined
in `data.py`; folding them into the table is follow-up scope. Rows past the
83 `mvp_candidate` treasures rest on the committed map, event-tag, coordinate,
and item-category data; 60 of them name items whose English text is not in
the committed data (category-8 blood gems, plus two nameless goods), and those
rows say so in `basis` rather than inventing gem names.

## Name format

`Region - Core`, optionally `Region - Core (place hint)`.

- **Region first**, because that is how a player scans a tracker or hint list.
- **Core** is the vanilla contents (`Saw Spear`, `Hunter Set`). In a randomized
  seed the contents are not what is actually there; they are the stable,
  recognizable handle for the spot, and they match every name the slice
  already publishes. Quantities follow the #75 ruling: a bare `x1` is dropped,
  while `xN` for N > 1 stays (`Pebble x8`) — it is part of what tells two
  same-item spots apart.
- **Place hint** is optional and always parenthesized: a short landmark
  (`(rooftop)`, `(Headmaster's Room chest)`) that separates the spot from
  same-region lookalikes.
- **Ordinals.** Rows the catalog cannot distinguish take a bare `#N` suffix in
  flag order (`Nightmare of Mensis - Iron Door Key #2`). An ordinal is an
  admission that no defensible place name exists yet, not a permanent name;
  replacing one with an evidenced hint is always welcome.
- Never `(Lot NNNN)`, never `unknown`, never a raw Japanese event tag. Those
  are research identifiers; the datapackage is not.

## Basis vocabulary

Names are project choices, not game facts, so they need recorded provenance
rather than runtime evidence. The `basis` column says which:

- `published` — already shipped in `fixed_locations.tsv` or `data.py` under a
  clean name. The table must agree with these byte-for-byte;
  `tests/test_location_names.py` enforces it.
- `proposed rename` — the slice publishes this flag under a `(Lot NNN)`
  placeholder name and the table name is its proposed replacement. Such rows
  are listed in `PENDING_PLACEHOLDER_RENAMES` in the test module, the complete
  inventory of renames awaiting an owner decision. (The set is currently
  empty: the #75 rename landed all 45.)
- `event tag ...` — the hint translates this flag's committed Japanese event
  tag. Reviewer-confirmable in game.
- `map mNN...` — the name follows from the map and item identity alone; no
  finer place claim is made.
- `unestablished` — the spot is not pinned down; see the ordinal rule.

## Changing a name

- Before the first numbered release: rename freely in review, with a
  CHANGELOG line when the renamed location is one the slice publishes.
- After: a published rename needs owner sign-off and a CHANGELOG entry in the
  same commit. Keys (`location_flag` here, network IDs in `ids.tsv`) never
  change.
- New catalog rows fail CI until they are named. That failure
  is the ratchet working, not a bug.

## Follow-ups

- #75 is decided and landed: the 45 shipped `(Lot NNN)` placeholders publish
  their table names, and this table feeds `tools/build_central_yharnam_slice.py`.
  Quantities follow the owner ruling: `x1` is dropped, `xN` for N > 1 stays.
- #82 tracks unifying the inline names in `data.py` (boss, interaction, and
  EMEVD-award checks) so the table becomes the single source, and extending
  generation wiring past the Central Yharnam slice.
