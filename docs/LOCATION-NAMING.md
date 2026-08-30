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
| `location_flag` | The canonical acquisition flag from `research/catalog/fixed_location_catalog.tsv`, or — for scripted checks outside the catalog — the boss-defeat / script-award event flag committed in `runtime_bindings.py`. This is the key: an existing game identifier, never an invented one. |
| `region` | Exactly one entry of `REGIONS` in `worlds/bloodborne/data.py`. |
| `name` | The player-facing English name. Unique across the table, ASCII, never a research placeholder. |
| `basis` | What the name rests on (vocabulary below). |

The table covers all 651 rows of the fixed-treasure catalog plus the twenty
scripted checks whose flags are committed (fourteen boss defeats, five EMEVD
script awards, one interaction). `data.py` draws those names from the table through
`worlds/bloodborne/location_names.py`; boss-defeat checks keep the
established bare boss name (`Cleric Beast`) rather than the
`Region - Core` shape. The boss-defeat flags were mapped from the committed
EMEVD decompiles: each map's boss event waits `CharacterDead` on the boss
entity and calls `HandleBossDefeat` on it, the event ID is the flag, and the
map's string table names the boss (internal dev names — Cleric Beast is
教区長, Lady Maria is 女性ハンター). The interaction check keys on event
12401803 (学長の記憶ポリ劇): the Grand Cathedral altar prompt that plays the
skull memory after Amelia, a one-shot flag under the same
event-ID-is-the-flag convention. Rows past the
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

## Landmark hints (#222)

Two playtesters in one day could not *locate* their checks: one hunted
`Central Yharnam - Blood Stone Shard x2` with a video guide open and still
needed operator support, and could not tell which of the eight
`Central Yharnam - Blood Stone Shard #N` rows the tracker had just lit; the
other asked, in as many words, for names that say *where* the item is.

So the optional place hint above stops being decoration and becomes the point:

    Central Yharnam - Blood Stone Shard x2 (sewer channel beam)

Two rules make this cheap and safe to land.

- **The item half is load-bearing and does not move.** AP hints, spoiler logs
  and `!hint` replies all carry the name; the vanilla contents are the handle
  players recognise.
- **The `#N` ordinal is stable.** A hint often makes a name unique on its
  own, and the ordinal could then be dropped. It is kept anyway: renumbering
  would churn every tracker pack, every spoiler a player has open, and every
  bit of muscle memory, and would buy nothing mechanical. The pass *appends*.
  `tests/test_location_names.py::test_ordinals_survive_hinting` holds the
  line: a hinted ordinal row must still read `... #N (hint)`.

`tools/build_location_hints.py` is the mechanical half. It never invents a
hint, never overwrites a hint a row already carries, and re-running it is a
no-op.

### Hint sources, in trust order

1. **The developers' own `lot_name` area tag** (`research/joined/lot_items.tsv`,
   joined on the acquisition flag, never on the lot name). Each map's tags are
   translated through the committed table below.
2. **MSB signals** from the inputs bundle's `mined/msb_treasures.tsv`:
   `in_chest` becomes `chest`; `start_disabled`, the model id and the
   coordinates are evidence for a hand-written hint rather than a generator.
   Coordinates also police the result -- two placements within 5 units of each
   other in the same map may not publish contradictory hints
   (`test_neighbouring_placements_do_not_contradict`). Five, not twenty:
   these maps stack vertically and the developers' halves interleave at their
   boundary, so a wider radius flags honest neighbours as contradictions.
3. **Hand-written**, in `docs/location_hint_overrides.tsv`, for the famous
   spots only where 1 and 2 fail. Every one carries its evidence in the `note`
   column and lands in the row's `basis`, exactly like the #75 rename rows.

**Coverage is deliberately partial.** 183 of 679 rows carry a hint; 496 do
not, and a name with no landmark yet is honest rather than unfinished. The
pass prioritised the collision groups (98 of the 407 `#N` rows now carry a
hint) and the rows the playtesters actually hunted. Both numbers are witnessed
in the test module and move only in the commit that earns them.

### Per-map tag vocabulary

Each table is the calibration, not just the translation: `confidence` says
whether the English is anchored to a lot whose real location this project has
already established, or is only a literal reading of the Japanese. These
tables and `docs/location_hint_vocabulary.tsv` are checked against each other
in both directions by
`test_documented_vocabulary_matches_the_committed_table`, and every emitted
hint is checked back against the table by
`test_every_emitted_hint_is_vocabulary_or_carries_provenance`.

A map absent from this section has no usable tag vocabulary and takes no
tag hints. `m28_00_00_00` keeps only its one object tag: its `初回` and
`人さらい` tags mark *visit phases* of the same geometry, not places -- lots
3.2 units apart carry different ones -- so they are not landmarks and are not
translated.

#### m24_01_00_00 -- Central Yharnam

| tag | hint | confidence | calibration |
| --- | --- | --- | --- |
| `前半` | `bridge side` | calibrated | 2410520 Torch is tagged 前半 and is the street corpse on the way to the Great Bridge |
| `後半` | `sewer side` | calibrated | 2410100 Saw Spear is tagged 後半 and is the sewer-channel corpse |
| `裏` | `clinic backstreets` | calibrated | 2410140 is tagged 裏 and is already named under Iosefka's Clinic |

#### m24_00_00_00 -- Cathedral Ward

| tag | hint | confidence | calibration |
| --- | --- | --- | --- |
| `聖C前` | `Grand Cathedral approach` | calibrated | 2400480 Radiant Sword Hunter Badge is tagged 聖C前 and is the chest by the Grand Cathedral |

#### m28_00_00_00 -- Yahar'gul

| tag | hint | confidence | calibration |
| --- | --- | --- | --- |
| `ミイラ` | `mummified corpse` | literal | ミイラ is 'mummy'; the tag names the corpse, not an area |

#### m32_00_00_00 -- Lecture Building

| tag | hint | confidence | calibration |
| --- | --- | --- | --- |
| `教室` | `classroom` | calibrated | 3200600 Augur of Ebrietas is tagged 教室 and is the 1F classroom |

#### m35_00_00_00 -- Research Hall

| tag | hint | confidence | calibration |
| --- | --- | --- | --- |
| `ひまわり畑` | `sunflower patient room` | calibrated | 3500830 Blacksky Eye is tagged ひまわり畑 and already publishes (sunflower patient room) |
| `地下牢` | `underground cell` | calibrated | 3500630 is tagged 地下牢03 and already publishes (underground cell) under the #82 ruling |
| `聖堂` | `chapel` | literal | 聖堂 is 'chapel' |
| `時計塔` | `tower` | literal | 時計塔 is 'clock tower', the Research Hall's main stack; a floor token in the tag refines it |

#### m36_00_00_00 -- Underground Corpse Pile (Fishing Hamlet)

| tag | hint | confidence | calibration |
| --- | --- | --- | --- |
| `賽の河原` | `shoreline` | literal | 賽の河原 is the mythic riverbed; the tag covers the arrival beach |
| `村2_下層` | `lower hamlet` | literal | 村2 下層 is 'village 2, lower level' |
| `村1` | `upper hamlet` | literal | 村1 is 'village 1', the first hamlet street |
| `山道` | `mountain path` | literal | 山道 is 'mountain path' |
| `灯台` | `lighthouse` | literal | 灯台 is 'lighthouse' |
| `養殖槽上層` | `fish tank upper` | literal | 養殖槽 is the fish-farming tank; 上層 is the upper level |
| `養殖槽中層` | `fish tank middle` | literal | 養殖槽 middle level |
| `養殖槽下層` | `fish tank lower` | calibrated | 3600600 Blood Rock is tagged 養殖槽下層 and is the deepest hamlet pickup |
| `暗渠中層` | `culvert middle` | literal | 暗渠 is 'culvert'; 中層 is the middle level |
| `暗渠下層` | `culvert lower` | literal | 暗渠 lower level |

`tower` takes a floor from the tag when the tag names one, so
`宝死体【時計塔11】_2F右通路手前` publishes `(tower 2F)` and a tag with no
floor token publishes the coarser `(tower)`. A coarse hint and its refinement
are the same claim at two resolutions, and the neighbour check treats them as
such.

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
  their table names, and this table feeds `tools/build_fixed_location_slice.py`.
  Quantities follow the owner ruling: `x1` is dropped, `xN` for N > 1 stays.
- #222 is decided and landed: the landmark-hint convention above, its
  committed per-map vocabulary, and the 182 hinted rows. The remaining 496
  bare rows are open work, not a defect; a new hint needs a vocabulary row or
  an override row with evidence, never a guess. `52410295` is exempt from the
  pass: it is the NG+ replacement corpse retired by #221, so no first
  playthrough can reach it and a landmark for it would be noise. `EXEMPT` in
  `tools/build_location_hints.py` carries the same note.
- #82 is decided and landed: the boss-defeat flags are mapped (#86), the
  `53500630` divergence is resolved by owner ruling — the check is Research
  Hall's cell block (event tag 地下牢03, same 地下牢NN family as the Fist of
  Gratia row), renamed "Research Hall - Blood Stone Chunk (underground cell)"
  and moved to the Research Hall region; the Inner Chamber Key treasure
  (50002360) keeps the Underground Corpse Pile contributing a check — and the
  skull interaction keys on its evidenced one-shot flag 12401803. No inline
  names remain in `data.py`.
