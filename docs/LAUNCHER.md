# Bloodborne AP launcher core

Status: the repository carries both the UI-independent cache/activation core
and a desktop **Randomize & Launch** surface. The Windows package bundles the
deterministic planner, compressed-map miner, and guarded native writers before
it activates the verified overlay. At launch the launcher also writes the
native client's runtime configuration and names its per-session ledger, so no
tester-authored JSON remains in the flow. A prebuilt client can be added at
package time; live overlay canaries remain a follow-up slice.

## Safety model

The launcher recognizes one game target: `CUSA03173` AppVer `01.09`. It reads
that identity from the base and update `sce_sys/param.sfo` files. A valid game
root contains exactly one of `CUSA03173-patch` or `CUSA03173-UPDATE` next to the
base directory.

Every randomized build lives in an external hash-addressed cache. Its key
commits to:

- AP seed and slot;
- world, native runtime, and shadPS4 builds;
- source game hashes;
- options and enemizer seed;
- the suppression plan hash.

The build contains only the suppressed binder and optional enemizer maps:

```text
<cache>/<identity-sha256>/
├── seed-manifest.json
└── dvdroot_ps4/
    ├── param/gameparam/gameparam.parambnd.dcx
    └── map/MapStudio/*.msb.dcx
```

Every file is copied, hashed, recorded, and reopened before the cache directory
becomes visible. Reusing a cache repeats the full file-set, size, hash, identity,
and suppression-witness verification.

Activation stages a verified sibling of `CUSA03173-mods`, writes an ownership
manifest, and verifies it before any rename. A durable transaction records each
rename. On the next run, an interrupted transaction either finishes from the
verified stage or restores the verified previous overlay. shadPS4 must be
stopped for activation, recovery, restore, or vanilla bypass.

A pre-existing mods directory without the exact ownership manifest is a hard
conflict. An owned directory with an added file is also a conflict. Neither is
renamed, merged, deleted, or overwritten. The code never opens the base or
update trees for writing.

`Launch Vanilla` renames only a verified launcher-owned overlay out of shad's
`mods > patch > base` search path. Cached builds remain available. `Restore
Previous` resolves the predecessor by cache identity and performs another full
transactional activation.

## Command line contract

The checked-in CLI is the integration surface for the future desktop UI and is
also useful for fake-tree diagnostics:

```powershell
python -m bb_launcher --help
python -m bb_launcher discover `
  --game-root C:\path\to\shad-games `
  --shad-root C:\path\to\shad
python -m bb_launcher status --game-root C:\path\to\shad-games
```

## Desktop Randomize & Launch

Open the player-facing surface from a checkout with:

```powershell
python -m bb_launcher ui
```

The setup panel remembers paths under
`%LOCALAPPDATA%\BloodborneArchipelago\launcher-settings.json`. Select:

- the seed's `.bbenemizer.json` request;
- the validated shadPS4 game root;
- the generated suppression binder and its `build-manifest.json`;
- the player's source `MapStudio` (automatically discovered in the Windows package);
- for checkout-only development, an `msb_enemies.tsv` extraction and pinned
  SoulsFormatsNEXT checkout;
- the hash-pinned process plan and external seed-cache directory;
- optionally, the launcher state root and shadPS4 log path (the portable
  `%LOCALAPPDATA%`/`%APPDATA%` defaults fit a standard install).

A **Session status** panel below the setup shows, read-only and on demand: the
active overlay's seed/slot, cache key, suppression hash, and enemizer state;
the session's client config and ledger paths with delivery progress (cursor,
acknowledged count, watermark mode); and the CE bridge's reported
harness/protocol/status. Missing pieces are normal states ("no state yet"), and
conflicts or unreadable files appear as notes rather than errors. After every
launch the panel refreshes and the log names the written config and ledger
paths.

**Randomize Enemies** is enabled by default. Its enemy seed comes from the AP
request but can be overridden explicitly. **Allow tier mixing** and **Preserve
locomotion class** map directly to the planner's guarded policy switches.

When the player chooses **Randomize & Launch**, the workflow:

1. validates CUSA03173 `01.09`, the AP request's world/runtime builds,
   suppression source/plan/output hashes, shad build, and every process
   executable hash;
2. hashes the source gameparam and every source map into the cache identity;
3. runs `tools.bb_enemizer.cli` with the selected enemy seed and policy;
4. refuses zero safe swaps, then runs `BBEnemizerWriter` with `--apply` into an
   isolated temporary output;
5. requires compressed `*.msb.dcx` output, composes or reuses the verified seed
   cache, and activates it transactionally;
6. starts the configured shadPS4, CE bridge, and native AP client as direct
   children of the launcher.

Planner/writer output streams into the on-screen log. A failed enemizer build
is retained under the cache root and its path is printed for diagnostics. A
successful temporary build is removed after its files enter the verified
cache. Turning **Randomize Enemies** off skips the inventory, map, SoulsFormats,
planner, and writer stages and builds a suppression-only overlay.

The packaged path calls `BBEnemizerPlanner.exe`, `MSBBMiner.exe`, and
`BBEnemizerWriter.exe` directly. It needs no Python, .NET SDK, SoulsFormats
checkout, repository checkout, or pre-extracted enemy inventory. The checkout
path retains the original Python/`dotnet` fallback for development.

## Windows package

Build a Windows x64 folder and zip from PowerShell after installing
`packaging/requirements-build.txt`:

```powershell
./packaging/build_launcher.ps1 `
  -SoulsFormatsNextRoot C:\path\to\SoulsFormatsNEXT `
  -ClientPath C:\path\to\bb-ap-client.exe
```

The package uses a PyInstaller one-folder launcher and one-file planner, plus
self-contained single-file .NET publishes for the native tools. It includes the
CE table and documentation, writes a SHA-256 `package-manifest.json`, and emits
`build/BloodborneAPLauncher-win-x64.zip`. It never includes game or emulator
files. `-SkipClient` exists for CI artifacts and is deliberately explicit.

A seed identity file has this shape:

```json
{
  "seed": "52100005",
  "slot": "VarietyTester",
  "world_build": "bb-world-r1",
  "runtime_build": "bb-0.1.0-r5",
  "shad_build": "0.18.0",
  "source_hashes": {
    "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx": "<sha256>"
  },
  "options": {
    "enemy_randomizer": true
  },
  "enemizer_seed": "52100005:VarietyTester",
  "suppression_plan_sha256": "<sha256>"
}
```

Compose and activate derived outputs without placing either output back into
the game tree by hand:

```powershell
python -m bb_launcher build `
  --cache-root $env:LOCALAPPDATA\BloodborneArchipelago\seeds `
  --game-root C:\path\to\shad-games `
  --identity .\seed-identity.json `
  --suppression-binder .\generated\gameparam.parambnd.dcx `
  --map-studio .\generated\MapStudio

python -m bb_launcher activate `
  --game-root C:\path\to\shad-games `
  --build $env:LOCALAPPDATA\BloodborneArchipelago\seeds\<identity-sha256>
```

The `run` command activates a cached build, or selects vanilla, then starts all
configured components directly from the same launcher process. Direct children
inherit the same Windows privilege token. Before starting anything, `run`
writes the native client's runtime configuration into the launcher state root
(see "Client runtime state" below) and substitutes its paths into the process
plan. The plan deliberately carries exact arguments instead of guessing a
shadPS4 or third-party launcher command line, and it stays portable across
machines by naming placeholders instead of per-machine paths:

- `{runtime_config}` — the runtime config the launcher just wrote;
- `{ledger}` — the session's durable receive ledger (never reused across
  seed/slot pairs, never wiped by a rebuild of the same pair);
- `{bridge_root}` — the launcher-managed CE bridge directory.

Any other `{...}` token, or any placeholder at all in a `run --vanilla` plan,
is refused before launch.

```json
{
  "format": "bb-launcher-process-plan-v1",
  "shad_build": "0.18.0",
  "runtime_build": "bb-0.1.0-r5",
  "processes": [
    {
      "name": "shadPS4",
      "executable": "C:\\path\\to\\shadPS4.exe",
      "sha256": "<validated shadPS4 executable sha256>",
      "arguments": ["<locally validated Bloodborne launch arguments>"]
    },
    {
      "name": "CE bridge",
      "executable": "C:\\path\\to\\Cheat Engine.exe",
      "sha256": "<validated Cheat Engine executable sha256>",
      "arguments": ["C:\\path\\to\\Bloodborne-native-item-grant-auto-v2.CT"]
    },
    {
      "name": "AP client",
      "executable": "C:\\path\\to\\bb-ap-client.exe",
      "sha256": "<packaged bb-ap-client executable sha256>",
      "arguments": [
        "localhost:38282",
        "VarietyTester",
        "{runtime_config}",
        "{ledger}",
        "--assume-correct-save"
      ]
    }
  ]
}
```

```powershell
python -m bb_launcher run `
  --game-root C:\path\to\shad-games `
  --build $env:LOCALAPPDATA\BloodborneArchipelago\seeds\<identity-sha256> `
  --process-plan .\process-plan.json `
  --suppression-manifest .\generated\build-manifest.json

python -m bb_launcher run `
  --game-root C:\path\to\shad-games `
  --vanilla `
  --process-plan .\process-plan.json
```

## Client runtime state

The launcher owns one state root (`%LOCALAPPDATA%\BloodborneArchipelago` by
default; `--state-root` or the optional `state_root`/`shad_log` settings keys
override it) with this layout:

```text
<state>/
├── bridge/                                  CE bridge working directory
└── sessions/<seed\x1fslot sha256>/
    ├── runtime-config.json                  written at every randomized launch
    └── ledger.json                          the client's durable receive ledger
```

The runtime config is emitted as BOM-free UTF-8 (the native client rejects a
BOM at line 1 column 1) and points `installed_gameparam` at the *active
overlay's* binder, which is re-verified against the activation ownership
manifest before the path is written. Locations, items, and the seed-owned
suppression requirement stay empty in this file: the client replaces them from
slot_data when it connects, and local configuration cannot weaken the seed's
terms. The ledger file itself is never pre-created; the client treats a
missing ledger as an empty one.

Session state is keyed by AP seed and slot only, so rebuilding or re-caching
the same seed and slot reuses the same ledger, while a different seed or slot
can never touch it.

## Proven offline and remaining live gates

`tests/test_launcher_core.py` uses temporary legal fake game trees. It proves
backend precedence, strict serial/version validation, deterministic cache
identity, cache reuse, path allowlisting, ownership refusal, interruption
recovery, previous-seed restore, vanilla fallback, process preflight, and zero
base/update mutation. `tests/test_launcher_client_config.py` proves the
launch-time half: the written config points at the verified active overlay
binder, sessions isolate ledgers by seed and slot, plan placeholders
substitute or fail closed, and the one-click workflow hands the substituted
paths to the launched client.

Those tests do not prove shadPS4 consumed an overlay. The issue's live canaries
still need the real game: suppression alone, suppression plus seed-12345 maps,
and overlay removal back to vanilla. The status panel reads overlay, ledger,
and bridge state from disk; live AP connection state is still only visible in
the client's own output. A release package
must still be given the prebuilt native client; CI uses the explicitly labeled
tools-only mode.
