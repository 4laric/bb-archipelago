# Contributor handoff

Status: 2026-08-21. This is the shortest path from a clean clone to the current
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

- The Intel SFX patch prevented the known opening-clinic damage crash on the
  original test machine. It is an emulator/hardware workaround, not an item
  grant prerequisite, and the CE table must not enforce its patch bytes.
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
- A second-machine test exposed a narrower unsafe case: inserting a Blood Vial
  when no Vial stack exists returned a native slot but created an invalid
  `0xF00003E8` / `?ItemInfo?` record instead of the expected category-4
  `0xB00003E8` record. Discard or restore any save containing that record. The
  current table fails closed for absent Vials; existing Vial stacks remain the
  validated path.
- A fresh second-machine save exposed an inventory-hydration race: the consume
  hook captured the inventory while `last=76`, bootstrap finalized absent, and
  the canonical Vial appeared moments later at secondary slot 14 / logical
  slot 78. A bounded 10-second debounce now waits for that stack. The same
  machine then completed the existing-stack bootstrap successfully. A first
  shop-purchased Vial updated the HUD without creating the canonical goods
  record; an enemy/world Vial did create it.

## Build and generate

World repository — one command builds everything a player machine needs
(AP client via cargo, vanilla suppression binder, `bloodborne.apworld`, and
the launcher package):

```powershell
.\build.ps1 -Package -SoulsFormatsNextRoot C:\path\to\SoulsFormatsNEXT `
  -ClientRepo C:\path\to\from-software-archipelago-clients
```

`-ClientPath C:\path\to\bb-ap-client.exe` skips the cargo build. An existing
`work\vanilla-suppression-build` is kept (remove it to rebuild the binder);
`SOULSFORMATS_NEXT` works instead of the switch. Outputs land in `build\`:
`bloodborne.apworld` and `BloodborneAPLauncher-win-x64.zip`. For development
iteration, the individual stages remain available:

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

With **Full Item Pool** on (the default), the pool places each of the twelve
validated non-filler items once — Saw Spear, Augur of Ebrietas, and the ten
progression keys (Hunter Chief Emblem, Cainhurst Summons, Tonsil Stone, Upper
Cathedral Key, Orphanage Key, Eye of a Blood-drunk Hunter, Eye Pendant,
Astral Clocktower Key, Celestial Dial, Laurence's Skull) — then cycles filler
over the remaining 41 of the 53 locations. The playable area is unchanged;
the progression keys are forward unlocks whose vanilla homes are outside the
slice. With the option off, the pool is the original slice composition: Saw
Spear and Augur once each, eleven Vials, and ten each of Quicksilver
Bullets x3, Pebbles x3, Molotov Cocktails x2, and Blood Stone Shards x2. The
checked-in tests pin both compositions.

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
2. If this machine reproduces the opening-clinic damage crash, enable the
   appropriate shadPS4 workaround independently of the item-grant table.
3. Run Cheat Engine 7.7 elevated, attach to the shadPS4 process that is actually
   running Bloodborne, and load
   `tables/Bloodborne-native-item-grant-auto-v2.CT`.
4. The table visibly reports setup success and waits briefly for inventory
   hydration. If no bootstrap result appears, fire one bullet to capture the
   inventory pointer. Leave CE and the r5 table running afterward.
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
- Automatic Blood Vial delivery is supported only when a valid Vial stack
  already exists. Absent-stack Vial insertion is blocked pending #70.
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

Use a fresh character with the varied seed and ensure it already has a valid
Blood Vial stack. Confirm each currently safe goods shape, Augur, and Saw Spear;
defeat both bosses; verify the server receives
Gascoigne goal status; then restart shad, CE, and the client and confirm no
acknowledged item or location is replayed. Record exact inventory before/after
counts and retain any terminal `native-grant-state.txt` failure before retrying.

## Cross-machine CE onboarding notes

- Use stable shadPS4 0.18 for the current table. The Qt launcher catalog may lag
  the downloadable stable SDL build; the latter can be launched with
  `shadPS4.exe CUSA03173` or an explicit `eboot.bin` path.
- Loading the table twice in the same CE/game session reports `already_ready`;
  restart CE before replacing or reloading a table that already installed hooks.
- More than one shadPS4 process can make name-based attachment select the wrong
  process. The table now respects CE's manual process attachment, validates a
  logged eboot base, and falls back to a live signature scan.
- Table diagnostics and log paths are portable. Setup success, failure, and
  bootstrap outcome are shown explicitly rather than relying on an invisible
  side effect.
- The grant table does not inspect or enforce unrelated emulator patch bytes.
  Its inventory bootstrap waits for the canonical goods list to hydrate before
  declaring a Vial absent.
