# Standalone item and enemy randomizer

This is a separate local randomizer path. It does not install Archipelago, run
`Generate.py` or `MultiServer`, connect to an Archipelago room, or use the AP
client. The existing launcher’s **Create & host** feature remains a localhost
Archipelago session and does not satisfy this contract.

The first implemented component is the dependency-free item planner:

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
BBEnemizerWriter.exe --standalone-items `
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

The ordinary enemy planner already accepts a local `--seed`, and the boss
encounter builder consumes local original-game inputs. They can be composed
with this item plan without an AP request. Launcher and BBLauncher integration
still need a standalone build identity and receipt: existing `SeedIdentity`,
`.bb-ap-owner.json`, `Archipelago-*` exports, runtime config, client ledger, and
process plans are AP session contracts and must not be relabeled.

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
