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

- world, native runtime, and shadPS4 builds;
- source game hashes;
- options and enemizer seed;
- the suppression plan hash and exact suppression-binder bytes.

AP seed and slot remain in the activation ownership record and continue to
isolate client ledgers, but they are deliberately not cache terms: two players
whose inputs produce identical overlay bytes share one verified build. Changing
the binder always changes the key, even when the plan and installed game do not.

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

## Player mods: `CUSA03173-mods-user`

shadPS4 resolves loose files `mods > patch > base`, and that documented search
path names exactly one mods location per game. The launcher owns it, so a file
dropped into `CUSA03173-mods` by hand or by a third-party tool is carried aside
into `.CUSA03173-mods.bb-ap-previous-<txid>` on the next activation -- which is
the transaction working correctly, and looked like data loss (#134).

The supported place for player content is the sibling directory
`CUSA03173-mods-user`. The launcher **only ever reads it**: it is never renamed,
written, staged, quarantined, or removed by activation, recovery, `Launch
Vanilla`, or `Restore Previous`. On each activation the launcher hashes its
contents, decides a merge, copies the accepted files into the staged overlay
alongside the generated ones, and records them in the same ownership manifest
(`user_merge`). So the launcher still owns `CUSA03173-mods` exclusively and the
activation transaction is unchanged; the merge is one more thing the stage is
built from. Put your mods there once and they survive every activation.

```text
<games>/
├── CUSA03173/               # base, read-only
├── CUSA03173-patch/         # 01.09 update, read-only
├── CUSA03173-mods/          # launcher-owned overlay, rebuilt each activation
└── CUSA03173-mods-user/     # yours: dvdroot_ps4/chr/..., dvdroot_ps4/parts/...
```

Lay the directory out exactly as the mod ships it relative to `dvdroot_ps4`.
**The union of your mods sits directly under `CUSA03173-mods-user`, with no
per-mod wrapper folder.** Mods usually download as one folder per mod, each
containing its own `dvdroot_ps4` tree; dropping those folders in as-is is the
natural first attempt and it does not work:

```text
CUSA03173-mods-user/
├── Boczkek's FPS boost Lite/     # WRONG: overlay path becomes
│   └── dvdroot_ps4/...           # CUSA03173-mods/Boczkek's FPS boost Lite/dvdroot_ps4/...
└── Half Cloth Physics/           # -- a path shadPS4 never resolves
    └── dvdroot_ps4/...

CUSA03173-mods-user/
└── dvdroot_ps4/                  # RIGHT: every mod's contents merged here
    ├── chr/...
    └── parts/...
```

Move the contents of each wrapper up one level so paths start with
`dvdroot_ps4/` (#173).

The conflict rule is explicit and fails loudly rather than merging or dropping:

- **Archipelago-owned paths always win.** The suppression binder
  (`dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx`) and any MSB the
  enemizer emits under `dvdroot_ps4/map/MapStudio/` are seed correctness, not
  preference: a user `gameparam` would silently break suppression, so a user
  file at one of those paths is **excluded** (reason `ap-owned`), the
  Archipelago file is used, and the exclusion is recorded in the manifest and
  reported by the Doctor. Comparison is case-insensitive.
- **Paths that do not start with `dvdroot_ps4/` can never load.** shadPS4
  resolves nothing outside that tree, so such a file is **excluded** (reason
  `dead-path`) rather than merged into an overlay path nothing reads. The
  Doctor and the launch progress log both report it, grouped by the top-level
  wrapper folder, with the one move that fixes every file under it (#173).
  Comparison is case-insensitive.
- Names the launcher reserves inside the overlay (`.bb-ap-*`, the ownership
  manifest) are excluded with reason `reserved`.
- Symbolic links, absolute paths, and anything escaping the directory fail
  closed; nothing is merged.
- Changing the contents of `CUSA03173-mods-user` changes the overlay even when
  the seed build is identical, so the next activation runs a full transaction
  instead of short-circuiting.

`python -m bb_launcher doctor` reports a `user mods` line: how many files will
merge, and every exclusion with its reason -- including dead paths, which are
named by wrapper folder because one move fixes all of them. Files that only collide when enemy
randomization is on (your own MapStudio maps) are surfaced as a warning.

Which mods are safe to merge at all is a separate question -- see the folder
check in `docs/PLAYTESTING.md`.

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

A process plan is generated, not hand-written. `python -m bb_launcher plan`
pins each selected executable by SHA-256, derives the slot and runtime build
from the seed file (`--ap-request`: the `AP_<seed>.zip`, or an extracted
`.bbseed.json`), and writes a
`bb-launcher-process-plan-v1` document whose client arguments carry the
`{runtime_config}` / `{ledger}` placeholders the launcher substitutes at
launch — so the plan is portable across machines and sessions:

```powershell
python -m bb_launcher plan `
  --output plan.json `
  --shad C:\path\to\shadPS4.exe `
  --client C:\path\to\bb-ap-client.exe `
  --ap-request seed.bbseed.json
```

The client entry carries `--assume-correct-save`, the explicitly unsafe MVP
mode, because real save identity is still #56 — generating the plan does not
change that boundary. An existing plan is never overwritten without
`--force`.

## Desktop Randomize & Launch

Open the player-facing surface from a checkout with:

```powershell
python -m bb_launcher ui
```

The launcher remembers setup under
`%LOCALAPPDATA%\BloodborneArchipelago\launcher-settings.json`. Fields the
launcher can derive are filled automatically on empty: the seed cache
defaults to a `seeds` directory under the launcher state root, the
suppression binder/manifest pair is offered when
`work\vanilla-suppression-build` exists beside the package or checkout, and
choosing a `shadPS4.exe` derives the game root from its `games` sibling when
that discovery is unambiguous. The normal **Setup** tab asks for only:

- the seed file: either the `AP_<seed>.zip` Archipelago generation emits for
  the whole multiworld, or the `.bbseed.json` request inside it (generation
  emits one per slot whether or not the enemizer option is on; older seeds'
  `.bbenemizer.json` still works). Given a zip, the launcher selects the
  Bloodborne member whose `player_name` matches the entered AP player name --
  a lone Bloodborne slot needs no name and can supply one, several slots
  require it, and a zip with none is refused by name -- and extracts that
  member once under `<state root>/seed-requests`, keyed by content so
  re-selecting the same zip reuses it;
- the validated shadPS4 game root and `shadPS4.exe`;
- the Archipelago server; the seed supplies the player name when it identifies
  one Bloodborne slot and hides the unnecessary selector, while a
  multi-Bloodborne archive presents a read-only list of the Bloodborne slots
  it actually contains. The setup shows the resolved player, seed, and
  required runtime before launch.

MapStudio and the guarded enemy options live under **Enemy randomization**;
the uncommon seed and tier controls stay collapsed until **Advanced enemy
options** is selected.
Suppression, cache, state, log, and explicit process-plan overrides live under
**Troubleshooting**; packaged players do not need to touch them. Setup is saved
automatically whenever an action starts.
Changing the seed, player, game, shadPS4 path, or server refreshes the
readiness view. Launch stays unavailable and names the missing setup pieces
until the seed, game, shadPS4, and any required player choice are present.

A **Session status** panel below the setup shows, read-only and on demand: the
active overlay's seed/slot, cache key, suppression hash, and enemizer state;
the session's client config and ledger paths with delivery progress (cursor,
acknowledged count, watermark mode); and, for a host-authored CE-bridge
fallback plan only, that bridge's reported harness/protocol/status. Missing pieces are normal states ("no state yet"), and
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
6. starts the configured shadPS4 and native AP client as direct children of
   the launcher. A generated plan has exactly these two entries: item delivery
   is the client's native path (bb-archipelago#153), so the launcher no longer
   pins or starts a Cheat Engine bridge.

Planner/writer output streams into the on-screen log. A failed enemizer build
is retained under the cache root and its path is printed for diagnostics. A
successful temporary build is removed after its files enter the verified
cache. Turning **Randomize Enemies** off skips the inventory, map, SoulsFormats,
planner, and writer stages and builds a suppression-only overlay.

### Allowing a suppression mismatch (operators only)

Two of the launch-time refusals compare hashes that drift constantly during
rapid playtest iteration and never drift during play: the suppression binder's
`plan_sha256` against the seed's `suppression_plan_sha256`, and the binder's
`source_gameparam_sha256` against the gameparam actually installed. A host
running a session across a regenerated seed, a binder built on another machine,
or an install one re-copy behind knows exactly what is skewed, and today pays a
full refusal for it. **Allow suppression binder mismatch** in the launcher (and
`--allow-suppression-mismatch` on `python -m bb_launcher doctor`) turns those
two comparisons — and only those two — into loud warnings instead of refusals.
Each bypassed check prints its own line naming what was expected, what was
found, and the knob that let it through; Doctor reports it as `WARN` naming the
knob rather than passing quietly; and the activated overlay's ownership
manifest gains a `suppression_validation` section recording the bypass, so a
bug report filed against that session is attributable. The knob is
per-invocation by construction — the checkbox is deliberately never saved with
the rest of the setup, and Doctor never reads it from the settings file — so it
cannot be switched on once and forgotten. It does not soften a binder that
disagrees with its own manifest, or one that is byte-identical to vanilla:
those mean the binder itself is wrong, not merely stale.

**Players should not use this.** A binder built from a different seed plan
suppresses the wrong vanilla item grants, and a binder built from a different
gameparam can restore rows your installation never had — the resulting run
looks fine and quietly diverges from the seed. If you are playing rather than
testing, rebuild the binder for your seed and your installation instead.

The packaged path calls `BBEnemizerPlanner.exe`, `MSBBMiner.exe`, and
`BBEnemizerWriter.exe` directly. It needs no Python, .NET SDK, SoulsFormats
checkout, repository checkout, or pre-extracted enemy inventory. The checkout
path retains the original Python/`dotnet` fallback for development.

Secondary actions live under **Troubleshooting**, each running the same guarded
core operations as the CLI:

- **Launch Vanilla** resolves the plan first (a plan still carrying client
  placeholders refuses before anything moves), then deactivates only the
  verified launcher-owned overlay and launches. Cached seeds stay available.
- **Restore Previous** reactivates the previous cached seed through a full
  transactional activation and reports the restored cache key.
- **Rebuild Seed** (with a confirmation) evicts exactly this seed's
  hash-addressed cache directory and runs the full build/activate/launch
  again; without it, a matching cache is reused.
- **Open Logs & Diagnostics** opens the launcher state root (client configs,
  per-session ledgers, bridge directory).

Every launch, Doctor run, rebuild, and vanilla launch writes a fresh
hash-pinned process plan automatically. It reads the slot and runtime build
from the selected seed, pins the chosen `shadPS4.exe` and packaged
`tools/bb-ap-client.exe`, and uses the **Archipelago server** field (default
`localhost:38281`). From a checkout, where no client is bundled, the CLI
`plan` command remains the explicit developer path.

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

The manifest records the client explicitly: a `client` object naming
`tools/bb-ap-client.exe` and its SHA-256 (`null` under `-SkipClient`), so a
player or a support script can verify the exact client the package shipped
without scanning the per-file list.

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
  "enemizer_seed": "52100005:1",
  "suppression_plan_sha256": "<sha256>"
}
```

The `enemizer_seed` is `f"{seed_name}:{player}"` — the multiworld seed name
joined to the player *number* (`1` for a solo seed), not the slot name.
Regenerating a multiworld can renumber the players, which changes each
slot's enemizer seed even when the multiworld seed name is unchanged.

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

- `{game_path}` — the game directory shadPS4 is told to boot: the `CUSA03173`
  folder inside the validated game root. This is the only argument a generated
  shadPS4 entry carries. Passing the game by **path** rather than by the bare
  `CUSA03173` game ID is what makes the launcher's game-folder field
  authoritative (bb-archipelago#177): shadPS4 resolves a bare ID only against
  its own `install_dirs` config, which is empty on any emulator copy that has
  never been opened and configured, and it then exits with `Game ID or file
  path not found: CUSA03173`. shadPS4 0.18's positional argument is documented
  as "Game path or ID" and its resolver consults `install_dirs` only when the
  argument is not an existing path (`src/main.cpp`), so a real directory needs
  no in-emulator setup at all. Overlay resolution is unaffected: shadPS4
  derives the `CUSA03173-patch`/`-UPDATE` and `CUSA03173-mods` overlays from
  the booted game folder itself (`Emulator::Run` sets `game_folder` to the
  eboot's parent; `MntPoints::Mount` probes the `-mods`/`-UPDATE`/`-patch`
  siblings of that folder), never from its library config — so suppression and
  the launcher-owned mods overlay still apply. Unlike the client placeholders,
  `{game_path}` resolves on a `--vanilla` launch too;
- `{runtime_config}` — the runtime config the launcher just wrote;
- `{ledger}` — the session's durable receive ledger (never reused across
  seed/slot pairs, never wiped by a rebuild of the same pair);
- `{bridge_root}` — the launcher-managed CE bridge directory. Generated plans
  never use it; it stays substitutable for one release so a host-authored
  fallback plan (`--delivery=ce-bridge`) still resolves.

Any other `{...}` token, or any client placeholder in a `run --vanilla` plan,
is refused before launch.

A plan generated before bb-archipelago#177 passes the literal `CUSA03173`
instead. Because `write_process_plan` never overwrites an existing plan without
`force`, those files stay on disk, so every launch path refuses them up front
(before the overlay is touched or a build is spent) and the Doctor reports them
as a distinct `launch plan game argument` FAIL with the regenerate remedy. The
launcher does not rewrite the plan itself: a player may have hand-validated its
arguments. Regenerating is one click.

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
      "arguments": ["{game_path}"]
    },
    {
      "name": "AP client",
      "executable": "C:\\path\\to\\bb-ap-client.exe",
      "sha256": "<packaged bb-ap-client executable sha256>",
      "arguments": [
        "localhost:38281",
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
