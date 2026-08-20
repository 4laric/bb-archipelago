# Contributor handoff

Status: 2026-08-20. This is the shortest path from a clean clone to the current
Central Yharnam vertical slice. Historical research remains in the other docs;
this file is the operational source of truth.

## Repositories

- `bb-archipelago`, branch `codex/central-yharnam-vertical-slice`: APWorld,
  stable IDs, location/item bindings, suppression tooling, CE tables, and
  research evidence.
- `from-software-archipelago-clients`, branch
  `codex/bloodborne-slice-runtime`: standalone Rust AP client, direct event-flag
  reader, durable receive ledger, and CE file bridge.

Do not commit game dumps, shadPS4 binaries, saves, launcher backups, CE process
dumps, or generated `work/` contents. The repositories intentionally contain
only code, reviewed derived facts, and reproducible fixtures.

## Proven live on CUSA03173 01.09 / shadPS4 0.18.0

- The Intel SFX patch prevents the known damage crash in the opening clinic.
- The 54-edit suppression binder loads. A suppressed pickup gives one Blood
  Vial, still sets its acquisition flag, survives reload, and does not respawn.
- The standalone Rust reader resolves the randomized eboot base and reads the
  live event-flag manager without Cheat Engine.
- `--assume-correct-save` automatically reported the already-collected Iosefka
  courtyard lot and two newly collected lots. No manual `/check` was used.
- AP returned three Vials. The r5 CE bridge granted them in AP index order and
  the ledger durably acknowledged indices 0 through 2. The first grant changed
  Vials 1 -> 2; the last observed grant changed 5 -> 6.
- Earlier focused canaries validated existing-stack goods, absent-stack Pebble,
  persistent Augur of Ebrietas, and category-0 Saw Spear insertion.

## Build and generate

World repository:

```powershell
python -m unittest discover -s tests -v
.\build.ps1 -Apworld
```

Install `build/bloodborne.apworld` into an Archipelago 0.6.7 checkout, copy
`examples/central-yharnam-variety.yaml` into its player directory, then run:

```powershell
python Generate.py --player_files_path Players --outputpath out --spoiler 3 --seed 52100005
python MultiServer.py out\<generated-seed>.zip --host localhost --port 38282
```

The varied pool has 53 items: Saw Spear and Augur once each, eleven Vials, and
ten each of Quicksilver Bullets x3, Pebbles x3, Molotov Cocktails x2, and Blood
Stone Shards x2. The checked-in test pins this composition.

Client repository:

```powershell
cargo test -p bb-archipelago
cargo clippy -p bb-archipelago --all-targets -- -D warnings
cargo build --release -p bb-archipelago
```

Copy `crates/bb-archipelago/runtime-config.example.json` outside the repo and
set `bridge_root`, `shad_log`, `suppression_manifest`, and
`installed_gameparam` for the local installation. Start the client elevated if
shadPS4 is elevated:

```powershell
bb-ap-client.exe localhost:38282 VarietyTester runtime-config.json live-ledger.json --assume-correct-save
```

The companion `crates/bb-archipelago/tools/start-bloodborne-ap.ps1` can launch
BBLauncher and wait for the game. The client itself retries the early shad/game
initialization window, so detecting the process before the flag manager exists
is not fatal.

## Runtime prerequisites

1. Install the seed-matching suppression binder as documented in
   `VANILLA-SUPPRESSION.md`; the client independently hashes the installed
   binder before arming.
2. Enable the Intel SFX patch in BBLauncher.
3. Run Cheat Engine 7.7 elevated, attach to `shadPS4.exe`, and load
   `tables/Bloodborne-native-item-grant-auto-v2.CT`.
4. Fire one bullet after each game launch to capture the inventory pointer.
   Leave CE and the r5 table running afterward.
5. Load the character intended for this AP seed and slot before passing
   `--assume-correct-save`. Do not switch characters while connected.

## Safety boundary

`--assume-correct-save` is an explicit MVP compromise. It creates a synthetic
ledger identity after the operator attests that the right character is loaded.
Three consecutive healthy event-flag-manager probes arm gameplay. A failed
probe immediately disarms and clears location debounce streaks.

This does not make the wrong save harmless. A check sent from another character
cannot be undone server-side, and an item delivered there still advances the
AP receive ledger. Normal live mode therefore remains fail closed until a real
loaded-save identity accessor is implemented.

## Known limitations

- Cheat Engine remains required for writes; checks themselves are direct.
- Every suppressed physical pickup gives one placeholder Vial in addition to
  its randomized AP reward. This is deliberate for the current writer but is a
  balance distortion.
- Automatic Molotov and Blood Stone Shard grants are formula-backed and covered
  by the common category-4 contract, but the varied seed has not yet exercised
  them live.
- Augur and Saw Spear have live focused canaries, but not yet through the new
  varied seed's complete automatic path.
- Cleric Beast, Gascoigne, `CLIENT_GOAL`, restart/reconnect replay prevention,
  and the full start-to-Gascoigne run remain to be playtested together.
- Auto-upgrade, auto-equip, Chalices, and enemizer integration are outside this
  slice.

## Best next session

Use a fresh character with the varied seed. Confirm one reward of each goods
shape, Augur, and Saw Spear; defeat both bosses; verify the server receives
Gascoigne goal status; then restart shad, CE, and the client and confirm no
acknowledged item or location is replayed. Record exact inventory before/after
counts and retain any terminal `native-grant-state.txt` failure before retrying.
