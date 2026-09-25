# Standalone item and enemy randomizer

This is a separate local randomizer path. It does not install Archipelago, run
`Generate.py` or `MultiServer`, connect to an Archipelago room, or use the AP
client. The existing launcher’s **Create & host** feature remains a localhost
Archipelago session and does not satisfy this contract.

The implemented path includes a local item planner, native item/enemy builder,
and exporter for the existing BBLauncher.

## Windows package

`packaging/build_standalone.ps1` produces `BloodborneStandaloneRandomizer`
with `BloodborneRandomizer.exe` and self-contained native writers. Players need
no installed Python, .NET, or Archipelago runtime. The package contains the
pinned research metadata used by the planners; it reads the player's original
game archives to generate a new seed locally.

```powershell
.\BloodborneRandomizer.exe build `
  --game-root "D:\Games\CUSA03173\dvdroot_ps4" `
  --seed "my-seed" --output "D:\Randomizer\my-seed" `
  --randomize-enemies --normalize-enemy-scaling

.\BloodborneRandomizer.exe export `
  --overlay "D:\Randomizer\my-seed" `
  --zip-root "D:\Randomizer\exports" `
  --receipt-root "D:\Randomizer\receipts"
```

The overlay must be a new directory outside the game installation. Export and
receipt directories must already exist. Extract the exported mod folder into
the existing BBLauncher's `Mods` directory and activate it there with the game
stopped. `build --help`, `export --help`, and `verify --help` describe the options.

To build the Windows distribution from source, use Python 3.12 with
`packaging/requirements-build.txt`, the .NET SDK, and the pinned SoulsFormatsNEXT
checkout:

```powershell
.\packaging\build_standalone.ps1 `
  -SoulsFormatsNextRoot "D:\Source\SoulsFormatsNEXT" `
  -PythonExecutable "D:\Python312\python.exe"
```

[Clean Windows distribution evidence](standalone-windows-package-checkpoint.json)
records the package at commit `938e129`, all 39 focused tests, and a complete
frozen build/export/verify run with PATH limited to Windows system directories.
All 37 decompressed game payloads match the source build exactly.

## Planner development interface

To generate an item plan directly from source:

```powershell
python -m tools.bb_standalone `
  --seed my-seed `
  --source-hashes source-hashes.json `
  --output standalone-item-plan.json
```

`source-hashes.json` must pin both original archives under the exact keys
`dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx` and
`dvdroot_ps4/paramdef/paramdef.paramdefbnd.dcx`. The planner reads no game file
and writes no game, mod, or save file. It emits `bb-standalone-item-plan-v1`
for the guarded native writer.

The writer receives the tracked catalog as a separate, hash-bound input:

```powershell
BBSuppressionWriter.exe --standalone-items `
  standalone-item-plan.json `
  tools/bb_standalone/award_targets.json `
  gameparam.parambnd.dcx `
  paramdef.paramdefbnd.dcx `
  randomized-gameparam.parambnd.dcx `
  --apply
```

The plan records the SHA-256 of the exact catalog file bytes. The catalog maps
each `item_key` to one exact native category, ID, and quantity, and maps each
location to its complete delivery, alternative, and retirement target set.
Rows without a `when` object are active in the base profile; conditional rows
name the option that activates them. The writer derives the active location set
from those conditions and rejects arbitrary subsets, changed rewards, changed
targets, unsupported active rows, or source archive drift. Version 1 fixes the
consumable quantity bonus at zero, so reward quantity has no range policy.

The default catalog covers every seeded location that has a native award path.
It distinguishes mutually exclusive award branches from continuation rewards:
alternative branches receive the same randomized reward, while continuation
rows are retired so one pickup cannot grant several copies. Every target pins
the original ItemLot row, slot, category, item ID, quantity, and acquisition
flag. An unknown active route stops generation with its location key and source
kind. The opt-in Yurie one-time-enemy check is currently such a gap because the
original encounter has no ItemLot award.

The standalone pool contains native inventory awards only. The AP-created
Hemwick gate is disabled. The Forbidden Woods password stays the original
Amelia altar memory event and is represented as fixed logical progression, not
as a category-255 inventory grant. Moon Presence remains a completion-only
milestone because its original terminal event awards no ItemLot. No network
placeholder, sustain award, AP trap, recipient, slot, server, or ledger appears
in the plan.

Placement is deterministic. Progression items are placed only at currently
reachable locations, then the remainder is shuffled over the unfilled target
set. A separate sphere replay collects the completed plan and refuses it unless
every placement and the selected ending are reachable. This is a local
single-player fill policy; it does not reproduce Archipelago’s multiworld fill.

The ordinary enemy planner and guarded writers are composed by the standalone
builder below. It emits its own seed identity and receipts. Existing AP
`SeedIdentity`, `.bb-ap-owner.json`, runtime configuration, client ledger, and
process plans are not used by the standalone build or export.

The intended shipped package is a separate Bloodborne Randomizer artifact with
the local planner and guarded writers. It may reuse the launcher's verified
overlay transaction, restore path, source hashing, enemy toolchain, and
BBLauncher data-mod export. It must omit the apworld, `bb-ap-client.exe`,
Archipelago generator/server discovery, server/password fields, and AP runtime
configuration. Static ItemLot awards make the game itself persist acquisitions;
the randomizer does not write saves.

Static analysis and round-trip tests establish plan and file integrity. They do
not establish gameplay behavior. Runtime acceptance remains separate.


## Native static reward writer

Build the native writer with the pinned SoulsFormatsNEXT dependency, then run:

```powershell
dotnet BBSuppressionWriter.dll --standalone-items `
  standalone-item-plan.json tools/bb_standalone/award_targets.json `
  original-gameparam.parambnd.dcx original-paramdef.paramdefbnd.dcx `
  output-gameparam.parambnd.dcx --apply
```

The writer verifies both original input hashes, the exact catalog file hash,
active location set, item-to-reward mapping, and every source award slot before
staging. It preserves native acquisition flags and all unplanned parameter cells,
binder entries and metadata. Category-8 rewards require original native recipe
witnesses. It refuses existing outputs and emits a receipt after round-trip
verification. This mode does not apply AP placeholders or alter Hunter's Tool
stat requirements.

[Original-input native evidence](standalone-native-items-checkpoint.json) covers
503 default locations / 552 physical award targets and 654 DLC locations / 712
targets. Both plans pass the independent progression replay and native writer.
The generator also passes all 128 combinations of supported boolean options
(excluding the explicitly unsupported opt-in Yurie check). A `python -S`
subprocess verifies generation without installed Archipelago dependencies.


## Combined item and enemy build

`tools/build_standalone_randomizer.py` generates one standalone overlay. Supply
original `--gameparam` and `--paramdef` files, `--item-writer`, `--seed`, a new
`--output` directory, and `--apply`. Native DLLs also require `--dotnet`.
Add `--randomize-enemies --maps <complete-original-MapStudio> --enemy-scripts
<original-script-directory> --enemy-writer <writer>`; `--normalize-enemy-scaling`
adds destination-based scaling. The default enemy inventory is materialized
from the bundled original-data database; no AP request or installed AP world is
required. `--include-dlc` includes DLC item locations.

The item writer runs first. Enemy scaling consumes that item-modified archive,
so the final parameter file contains both changes. Source hashes, exact native
receipts and output inventories are verified before publication. The build emits
`standalone-build-identity.json` and `standalone-build-receipt.json`; it does not
activate the overlay.

A [real combined build](standalone-composed-native-checkpoint.json) passes with
503 item locations, 308 logical enemy replacements across 545 physical parts in
22 maps, 14 AI bundles with zero unresolved goals, and 226 scaled NPCs. All 45
receipt files were independently hash-checked. This is build validation, not live
acceptance.


## Install through the existing BBLauncher

The exporter uses BBLauncher's existing data-mod layout, with native game paths
under a single named package. It requires no launcher fork or Archipelago
companion. Generate a ZIP with existing output directories:

```powershell
python tools/export_standalone_mod.py export `
  --overlay <standalone-build> --zip-root <zip-directory> `
  --receipt-root <receipt-directory>
```

Or use `--mods-root <BBLauncher/Mods>` in place of `--zip-root` to create an
inactive package directly in its mod library. It refuses active mod directories,
existing packages, altered build files, and paths outside the receipt. Verification
metadata stays outside the package; only native game data is installed.

Extract a ZIP's single package folder into BBLauncher's `Mods` directory, then
activate that package using BBLauncher's Mod Manager with the game stopped.
Starting Bloodborne through BBLauncher requires no AP client or server.

`python tools/export_standalone_mod.py verify --package <folder-or-zip>
--receipt <export-receipt.json> --overlay <standalone-build>` verifies the export
against the original build. The [native export checkpoint](standalone-bblauncher-export-checkpoint.json)
contains 37 game payload files from the combined item/enemy test seed. Export
verification passed; in-game standalone acceptance remains untested.

## Original-input test gate

Set `BB_STANDALONE_WRITER_INPUTS` to a JSON manifest containing `writer`,
`gameparam`, and `paramdef` paths, then run
`python tools/run_tests.py --expect-file tests/expected_counts.tsv
--require test_standalone_item_writer=5`. This requires all five native
round-trip and refusal tests to execute. Hosted CI lacks those original inputs
and permits their exact skips; it still collects the tests.

## Shared pool curation

Standalone builds invoke the same `tools.bb_enemizer.cli` planner and bundle the
same `enemy_tags.json`, `slot_policy.json`, and `archetype_facts.json` as the AP
path. Changes to these shared rules are included when the standalone package is
rebuilt. Existing ZIPs and already-generated seeds do not update themselves.

The standalone entry point currently uses the default enemy pool. It does not
expose the AP launcher's experimental release tranches or boss-shuffle encounter
builder; changes to those opt-in pools do not automatically enable them here.
The local item planner is separate from AP item generation, so AP-only item-pool
changes need an explicit standalone integration.
