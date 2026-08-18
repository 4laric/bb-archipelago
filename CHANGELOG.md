# Changelog

Player-visible changes to Bloodborne Archipelago are recorded here. The project
uses semantic versioning for the apworld contract; unreleased changes accumulate
under `Unreleased` and move into a dated version section when released.

## Unreleased

### Added

- Manual `/check` commands now keep a timestamped local journal and suggest close
  location names after a typo.
- The vanilla-award suppression tool can replace nine planned key-item awards
  while preserving their acquisition flags. Its output still requires repacking
  and in-game validation before it is part of the playable install.

### Fixed

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
