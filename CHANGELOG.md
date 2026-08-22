# Changelog

Player-visible changes to Bloodborne Archipelago are recorded here. The project
uses semantic versioning for the apworld contract; unreleased changes accumulate
under `Unreleased` and move into a dated version section when released.

## Unreleased

### Added

- A DeathLink send-signal session kit now narrows the hunt from the committed
  corpus before any live gameplay minutes are spent: tests pin that no event
  flag fires on every player death (all three `CharacterDead(10000)` sites are
  quest-specific), seven player death-state SpEffect rows and the validated HP
  path are the live leads, and a death-vs-lamp-warp capture harness intersects
  trials, subtracts the no-death control so "changed" is not mistaken for
  "death", and classifies survivors as reload-persistent counters or transient
  edges. A write-breakpoint skeleton attributes the writer. No candidate is
  claimed as the signal until the live session validates it.
- Location names are now a declared contract ahead of the first numbered
  release that freezes them: `worlds/bloodborne/location_names.tsv` names all
  83 MVP-candidate fixed treasures, `docs/LOCATION-NAMING.md` defines the
  format and rename rules, and tests enforce completeness, uniqueness, and
  agreement with already-published names. Generated seeds still use the
  existing names; replacing the `(Lot NNN)` placeholders awaits the rename
  decision tracked in #75.
- A UI-independent Bloodborne AP launcher core now discovers and validates
  CUSA03173 `01.09`, caches seed overlays by every build/source/options input,
  activates only owned param/map replacements transactionally, recovers an
  interrupted swap, restores the previous seed, bypasses owned overlays for a
  vanilla launch, and preflights coordinated shadPS4/client/CE startup. Fake
  game-tree tests prove conflict refusal and zero base/update mutation. The
  desktop UI, bundled native tools, and real-game overlay canaries remain open.
- The desktop launcher now exposes a real **Randomize Enemies** toggle, enemy
  seed, tier-mixing, and locomotion controls. **Randomize & Launch** invokes the
  deterministic planner and guarded MSBB writer, verifies the suppression
  witness and generated maps, composes the seed cache, activates it through the
  transactional core, and starts the pinned launch components. Tool output and
  actionable failures are streamed into the UI; failed build diagnostics are
  preserved. Bundling the native tools remains a packaging follow-up.
- The generated world is now the bounded Central Yharnam vertical slice: 51
  physical pickups, Cleric Beast, and Father Gascoigne. Two later-cycle
  replacement lots are collapsed onto their physical chests, both boss flags
  are carried in slot data, and Gascoigne is the client-reported goal.
- Vanilla-award suppression now covers all 51 pickups across goods, weapons,
  attire, and blood gems. The 54-row plan includes the Hunter Set continuation
  rows, has zero refusals, and builds/reopens successfully through the guarded
  native writer. Installation and in-game canary validation remain pending.
- The live event-flag manager read path is validated on CUSA03173 `01.09`. A
  save-restored pickup replay and a one-shot write breakpoint proved divisor-1000
  grouping with MSB-first bit packing; a manager-relative resolver rediscovers the
  randomized eboot base, gates on the setter signature, fails closed on a
  mismatch, and returns live flag state without Cheat Engine. The apworld's own
  client still reports checks manually. The separate r5 native client now has
  save-identity, gameplay-state and debounce gates, and deliberately leaves
  live check sends disarmed until its backend can supply the first two.
- One runtime build string, `bb-0.1.0-r5`, now spans the apworld, the client, the
  Cheat Engine table and the grant helper. The client prints it on connect and
  refuses a harness reporting a different or missing version; the wire contract is
  `BBGRANT1` and the table identifies itself as `bb-native-grant-v5`.
- A repeatable event-flag playtest kit records hashed session manifests, captures
  four-stage snapshots, intersects candidates across trials, and logs the
  instruction that writes a surviving candidate.
- Nine catalog-backed fixed treasure checks expand the pool to 29 locations.
  Cainhurst Summons, Tonsil Stone, and Orphanage Key now each gate at least one
  multiworld check, and suppression planning covers every added vanilla award.
- Manual `/check` commands now keep a timestamped local journal and suggest close
  location names after a typo.
- The vanilla-award suppression tool can replace nine planned key-item awards
  while preserving their acquisition flags. Its output still requires repacking
  and in-game validation before it is part of the playable install.
- Saw Spear is the first equipment item admitted to the randomized pool. Slot
  data carries its separately validated raw and normalized descriptors, category,
  +0 reinforcement level, right-hand receive policy and evidence class. Torch
  remains explicitly excluded after its inferred descriptor produced no visible
  inventory item.

### Fixed

- The CE harness is portable across Windows accounts, respects the process
  manually attached in Cheat Engine, rejects stale logged eboot bases, falls
  back to live signature discovery, and reports setup/bootstrap outcomes
  visibly. It no longer treats emulator-specific Intel SFX patch bytes as an
  item-grant prerequisite. Bootstrap also waits for the inventory list to
  hydrate before declaring a Vial absent; this fixes a live second-machine race
  where a valid stack appeared at logical slot 78 after the first scan ended at
  slot 76.
- Absent Blood Vial delivery now fails closed. A second-machine shadPS4 0.18
  test showed native insertion could create an invalid `0xF00003E8`
  `?ItemInfo?` record instead of a Vial. Existing-stack Vial delivery remains
  supported while the absent-stack regression is tracked separately. The
  bootstrap lookup now correctly distinguishes native raw descriptors
  (`0xB...`) from canonical inventory runtime IDs (`0x400...`); live canaries
  proved a 12-to-13 Vial increment and a zero-Vial no-item-created refusal.

- Items the player does not already hold are granted correctly under shadPS4
  v0.18. Category-4 goods use the 24-byte descriptor in the consumable
  function's retiring stack frame; category-0 equipment uses a persistent
  24-byte descriptor. A native Saw Spear grant was verified in inventory while
  the game remained responsive. Absent-stack, existing-stack, equipment, and
  restart-replay recovery paths are validated live.
- Runtime location bindings now distinguish MSB treasures from EMEVD item-lot
  awards and carry source-specific provenance.

## 0.1.0 - 2026-08-18

Initial vertical-slice development release.

### Added

- An Archipelago world with stable network IDs, ten shufflable key items, twenty
  locations, boss-event progression, and deterministic generation.
- A Bloodborne client that connects to Archipelago, reports checks manually, and
  queues received items through the validated Cheat Engine grant bridge.
- A conservative deterministic enemizer planner, guarded MSB writer, packaging
  workflow, and a 25-seed offline release gate.
- Static acquisition-flag mappings for six fixed locations and read-only shadPS4
  hook-site inspection.

### Known limitations

- Location checks are not detected automatically; the live event-flag manager
  accessor has not been validated.
- The enemizer writer and vanilla-award suppression output have not been
  playtested in game.
- The grant bridge still needs live validation of its failed-verify and restart
  recovery paths.
